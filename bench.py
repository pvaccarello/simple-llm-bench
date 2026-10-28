#!/usr/bin/env python3
"""llm-bench: benchmark ripetibili per i modelli che installiamo in locale.

Comandi:
  validate               verifica che le soluzioni di riferimento passino tutti i test
  run   --suite coding   esegue una suite contro un endpoint OpenAI-compatibile
  perf                   misura TTFT / velocità di decodifica a diverse concorrenze
  report results/*.json  confronta più run in una tabella markdown

Solo standard library: gira ovunque ci sia Python 3.10+.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from client import ChatClient

ROOT = Path(__file__).resolve().parent
SUITES = ROOT / "suites"
RESULTS = ROOT / "results"

CODING_INSTRUCTIONS = (
    "\n\nWrite the complete Python 3.12 module `solution.py` implementing the above. "
    "Use only the standard library. Do not include tests or code that runs at import time. "
    "Reply with the full module in a single ```python code block."
)


# ----------------------------------------------------------------------------- coding suite

def tasks_root(suite, tasks_dir=None):
    """Cartella dei task: --tasks-dir, poi BENCH_TASKS_DIR, poi gli esempi pubblici del repo.

    Il set completo dei task resta in un repository privato (per evitare che finisca nei dati di
    addestramento dei modelli futuri): BENCH_TASKS_DIR punta alla sua radice, che contiene una
    sottocartella per suite (es. <radice>/coding/01_parse_duration).
    """
    if tasks_dir:
        return Path(tasks_dir)
    if os.environ.get("BENCH_TASKS_DIR"):
        return Path(os.environ["BENCH_TASKS_DIR"]) / suite
    return SUITES / suite / "tasks"


def load_tasks(suite, only=None, tasks_dir=None):
    tasks = []
    for d in sorted(tasks_root(suite, tasks_dir).iterdir()):
        if not d.is_dir() or (only and not any(o in d.name for o in only)):
            continue
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        tasks.append({"id": d.name, "dir": d, **meta})
    return tasks


def extract_code(text):
    blocks = re.findall(r"```(?:python|py|python3)?[ \t]*\n(.*?)```", text, re.S)
    if not blocks:
        return None
    return max(blocks, key=len)  # il blocco più lungo è quasi sempre il modulo completo


def grade(task_dir, code, timeout=180):
    """Esegue i test nascosti in una cartella temporanea isolata."""
    harness_dir = SUITES / "coding"
    with tempfile.TemporaryDirectory(prefix="bench_") as tmp:
        for f in ("harness.py", "pytest_shim.py"):
            shutil.copy(harness_dir / f, tmp)
        shutil.copy(task_dir / "tests.py", tmp)
        Path(tmp, "solution.py").write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, "-I", "harness.py", tmp], cwd=tmp, capture_output=True,
                                  text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"passed": 0, "total": None, "error": "timeout globale"}
        lines = [l for l in proc.stdout.strip().splitlines() if l.startswith("{")]
        if not lines:
            return {"passed": 0, "total": None, "error": (proc.stderr or proc.stdout)[-800:]}
        return json.loads(lines[-1])


def cmd_validate(args):
    ok = True
    for task in load_tasks("coding", args.only, args.tasks_dir):
        res = grade(task["dir"], (task["dir"] / "reference.py").read_text(encoding="utf-8"))
        good = res.get("total") and res["passed"] == res["total"]
        ok &= bool(good)
        print(f"{'OK ' if good else 'KO '} {task['id']:<28} {res.get('passed')}/{res.get('total')} "
              f"{'' if good else json.dumps(res)[:600]}")
    sys.exit(0 if ok else 1)


def run_attempt(client, task, sample, params, out_dir):
    prompt = (task["dir"] / "prompt.md").read_text(encoding="utf-8") + CODING_INSTRUCTIONS
    resp = client.chat([{"role": "user", "content": prompt}], **params)
    rec = {"task": task["id"], "sample": sample, "difficulty": task["difficulty"], "category": task["category"]}
    if "error" in resp:
        rec.update(error=resp["error"], passed=0, total=None, score=0.0, full_pass=False)
        return rec
    code = extract_code(resp["content"])
    g = grade(task["dir"], code) if code else {"passed": 0, "total": None, "error": "nessun blocco di codice"}
    total = g.get("total") or 0
    rec.update({k: resp[k] for k in ("finish_reason", "prompt_tokens", "completion_tokens", "latency_s",
                                     "ttft_s", "time_to_answer_s", "decode_tok_s")})
    rec.update(passed=g.get("passed", 0), total=g.get("total"), failures=g.get("failures"),
               grade_error=g.get("error") or g.get("import_error"),
               score=round(g.get("passed", 0) / total, 4) if total else 0.0,
               full_pass=bool(total) and g.get("passed") == total,
               reasoning_chars=len(resp["reasoning"]))
    (out_dir / f"{task['id']}__{sample}.md").write_text(
        f"# {task['id']} (sample {sample})\n\n## Reasoning\n\n{resp['reasoning']}\n\n## Answer\n\n{resp['content']}\n",
        encoding="utf-8")
    return rec


def summarize(records):
    def agg(recs):
        if not recs:
            return {}
        toks = [r.get("completion_tokens") or 0 for r in recs]
        return {
            "attempts": len(recs),
            "pass_at_1": round(statistics.mean(r["full_pass"] for r in recs), 4),
            "avg_test_score": round(statistics.mean(r["score"] for r in recs), 4),
            "avg_completion_tokens": round(statistics.mean(toks)),
            "avg_latency_s": round(statistics.mean(r.get("latency_s") or 0 for r in recs), 1),
            "truncated": sum(1 for r in recs if r.get("finish_reason") == "length"),
            "errors": sum(1 for r in recs if r.get("error")),
        }
    out = {"overall": agg(records), "by_difficulty": {}, "by_task": {}}
    for key, field in (("by_difficulty", "difficulty"), ("by_task", "task")):
        for v in sorted({r[field] for r in records}):
            out[key][v] = agg([r for r in records if r[field] == v])
    return out


def cmd_run(args):
    if args.suite != "coding":
        sys.exit(f"suite '{args.suite}' non ancora implementata (vedi ROADMAP in README.md)")
    client = make_client(args)
    tasks = load_tasks("coding", args.only, args.tasks_dir)
    params ={"temperature": args.temperature, "top_p": args.top_p, "max_tokens": args.max_tokens,
              "extra_body": json.loads(args.extra_body) if args.extra_body else None}
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{args.label}__coding__{stamp}"
    out_dir = RESULTS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = [(t, s) for s in range(args.samples) for t in tasks]
    print(f"{len(jobs)} tentativi ({len(tasks)} task x {args.samples}), concorrenza {args.concurrency}")
    records, t0 = [], time.perf_counter()
    with cf.ThreadPoolExecutor(args.concurrency) as pool:
        futs = {pool.submit(run_attempt, client, t, s, params, out_dir): (t, s) for t, s in jobs}
        for fut in cf.as_completed(futs):
            r = fut.result()
            records.append(r)
            mark = "PASS" if r["full_pass"] else "fail"
            print(f"[{len(records):>3}/{len(jobs)}] {mark} {r['task']:<28} s{r['sample']} "
                  f"{r['passed']}/{r['total']}  {r.get('completion_tokens', 0):>6} tok  "
                  f"{r.get('latency_s', 0):>6}s  {r.get('finish_reason') or r.get('error', '')}", flush=True)
    wall = time.perf_counter() - t0

    result = {
        "run_id": run_id, "suite": "coding", "label": args.label, "model": args.model,
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "endpoint": args.base_url, "params": params, "samples": args.samples,
        "tasks": [t["id"] for t in tasks],
        "concurrency": args.concurrency, "notes": args.notes,
        "wall_time_s": round(wall, 1),
        "aggregate_tok_s": round(sum(r.get("completion_tokens") or 0 for r in records) / wall, 1),
        "summary": summarize(records),
        "records": sorted(records, key=lambda r: (r["task"], r["sample"])),
        "runner": {"python": platform.python_version(), "host": platform.node()},
    }
    path = RESULTS / f"{run_id}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    s = result["summary"]["overall"]
    print(f"\npass@1 {s['pass_at_1']:.1%}  test score medio {s['avg_test_score']:.1%}  "
          f"token medi {s['avg_completion_tokens']}  tempo {wall:.0f}s  -> {path}")


# ----------------------------------------------------------------------------- perf

PERF_PROMPT = ("Write a detailed, well-structured technical explanation of how a B-tree index works in a "
               "relational database, including insertion, deletion and page splits.")


def cmd_perf(args):
    client = make_client(args)
    extra = json.loads(args.extra_body) if args.extra_body else {}
    extra.setdefault("ignore_eos", True)  # lunghezza di output fissa (vLLM/SGLang)
    rows = []
    long_ctx = "Here is a log line: user=42 action=login status=ok latency=12ms\n" * args.long_prompt_lines
    scenarios = [("short", PERF_PROMPT, c) for c in args.concurrency_levels] + \
                [("long-prompt", long_ctx + "\nSummarize the log above in one sentence.", 1)]
    for name, prompt, conc in scenarios:
        t0 = time.perf_counter()
        with cf.ThreadPoolExecutor(conc) as pool:
            res = list(pool.map(lambda _: client.chat([{"role": "user", "content": prompt}], temperature=0.0,
                                                      max_tokens=args.output_tokens, extra_body=extra),
                                range(conc)))
        wall = time.perf_counter() - t0
        res = [r for r in res if "error" not in r]
        if not res:
            print(f"{name} c={conc}: tutti i request falliti")
            continue
        row = {
            "scenario": name, "concurrency": conc,
            "prompt_tokens": res[0]["prompt_tokens"],
            "ttft_s": round(statistics.median(r["ttft_s"] for r in res), 3),
            "per_stream_tok_s": round(statistics.median(r["decode_tok_s"] or 0 for r in res), 1),
            "aggregate_tok_s": round(sum(r["completion_tokens"] for r in res) / wall, 1),
            "prefill_tok_s": round(res[0]["prompt_tokens"] / max(res[0]["ttft_s"], 1e-6)),
        }
        rows.append(row)
        print(json.dumps(row))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RESULTS / f"{args.label}__perf__{stamp}.json"
    RESULTS.mkdir(exist_ok=True)
    path.write_text(json.dumps({"label": args.label, "model": args.model, "suite": "perf",
                                "date": dt.datetime.now().isoformat(timespec="seconds"),
                                "output_tokens": args.output_tokens, "notes": args.notes, "rows": rows},
                               indent=2), encoding="utf-8")
    print(f"-> {path}")


# ----------------------------------------------------------------------------- report

def cmd_report(args):
    runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.files]
    coding = [r for r in runs if r.get("suite") == "coding"]
    perf = [r for r in runs if r.get("suite") == "perf"]
    lines = []
    if coding:
        lines += ["## Coding", "",
                  "| Modello | pass@1 | test score | easy | medium | hard | token medi | troncati | tempo |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in coding:
            s, d = r["summary"]["overall"], r["summary"]["by_difficulty"]
            cell = lambda k: f"{d[k]['pass_at_1']:.0%}" if k in d else "-"
            lines.append(f"| {r['label']} | **{s['pass_at_1']:.1%}** | {s['avg_test_score']:.1%} | {cell('easy')} | "
                         f"{cell('medium')} | {cell('hard')} | {s['avg_completion_tokens']} | {s['truncated']} | "
                         f"{r['wall_time_s']:.0f}s |")
        tasks = sorted({t for r in coding for t in r["summary"]["by_task"]})
        lines += ["", "| Task | " + " | ".join(r["label"] for r in coding) + " |",
                  "|---|" + "---|" * len(coding)]
        for t in tasks:
            cells = []
            for r in coding:
                bt = r["summary"]["by_task"].get(t)
                cells.append(f"{bt['pass_at_1']:.0%} ({bt['avg_test_score']:.0%})" if bt else "-")
            lines.append(f"| {t} | " + " | ".join(cells) + " |")
    if perf:
        lines += ["", "## Performance", "",
                  "| Modello | scenario | concorrenza | TTFT | tok/s per stream | tok/s aggregati | prefill tok/s |",
                  "|---|---|---|---|---|---|---|"]
        for r in perf:
            for row in r["rows"]:
                lines.append(f"| {r['label']} | {row['scenario']} | {row['concurrency']} | {row['ttft_s']}s | "
                             f"{row['per_stream_tok_s']} | {row['aggregate_tok_s']} | {row['prefill_tok_s']} |")
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")


# ----------------------------------------------------------------------------- cli

def make_client(args):
    key = args.api_key or os.environ.get("BENCH_API_KEY")
    if not key and (ROOT / ".apikey").exists():
        key = (ROOT / ".apikey").read_text().strip()
    return ChatClient(args.base_url, args.model, key, timeout=args.timeout)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def endpoint(sp):
        sp.add_argument("--base-url", default="http://localhost:8000/v1")
        sp.add_argument("--model", required=True)
        sp.add_argument("--label", required=True, help="nome del run, es. nanbeige4.3-33b-bf16")
        sp.add_argument("--api-key")
        sp.add_argument("--extra-body", help='JSON aggiunto al body, es. \'{"chat_template_kwargs":{"enable_thinking":false}}\'')
        sp.add_argument("--timeout", type=int, default=3600)
        sp.add_argument("--notes", default="")

    tasks_help = "cartella dei task (default: $BENCH_TASKS_DIR/<suite> oppure gli esempi del repo)"

    v = sub.add_parser("validate")
    v.add_argument("--only", nargs="*")
    v.add_argument("--tasks-dir", help=tasks_help)
    v.set_defaults(fn=cmd_validate)

    r = sub.add_parser("run")
    endpoint(r)
    r.add_argument("--suite", default="coding")
    r.add_argument("--tasks-dir", help=tasks_help)
    r.add_argument("--only", nargs="*", help="sottostringhe degli id dei task")
    r.add_argument("--samples", type=int, default=1)
    r.add_argument("--concurrency", type=int, default=4)
    r.add_argument("--temperature", type=float, default=0.6)
    r.add_argument("--top-p", type=float, default=0.95)
    r.add_argument("--max-tokens", type=int, default=28000)
    r.set_defaults(fn=cmd_run)

    pf = sub.add_parser("perf")
    endpoint(pf)
    pf.add_argument("--concurrency-levels", type=int, nargs="*", default=[1, 4, 8])
    pf.add_argument("--output-tokens", type=int, default=512)
    pf.add_argument("--long-prompt-lines", type=int, default=600, help="~20 token per riga")
    pf.set_defaults(fn=cmd_perf)

    rp = sub.add_parser("report")
    rp.add_argument("files", nargs="+")
    rp.add_argument("--out")
    rp.set_defaults(fn=cmd_report)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
