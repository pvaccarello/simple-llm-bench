"""Esegue i test_* di tests.py contro solution.py (stessa cartella) e stampa un JSON sull'ultima riga.

Lanciato in un sottoprocesso con timeout dal runner: python -I harness.py <dir>
Ogni test è indipendente, così otteniamo anche un punteggio parziale.
"""
import json
import os
import sys
import threading
import traceback

PER_TEST_TIMEOUT = 20


def run_with_timeout(fn, timeout):
    result = {}

    def target():
        try:
            fn()
            result["ok"] = True
        except BaseException as e:  # noqa: BLE001 - vogliamo catturare tutto
            result["ok"] = False
            result["err"] = f"{type(e).__name__}: {e}"[:300]

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return False, "Timeout"
    return result["ok"], result.get("err")


def main():
    workdir = sys.argv[1]
    sys.path.insert(0, workdir)
    os.chdir(workdir)
    try:
        import tests  # importa a sua volta solution
    except BaseException:
        print(json.dumps({"passed": 0, "total": None, "import_error": traceback.format_exc()[-800:]}))
        return
    names = sorted(n for n in dir(tests) if n.startswith("test_") and callable(getattr(tests, n)))
    failures = {}
    for name in names:
        ok, err = run_with_timeout(getattr(tests, name), PER_TEST_TIMEOUT)
        if not ok:
            failures[name] = err
    print(json.dumps({"passed": len(names) - len(failures), "total": len(names), "failures": failures}))
    sys.stdout.flush()
    os._exit(0)  # evita di restare appesi su thread non terminati


if __name__ == "__main__":
    main()
