# simple-llm-bench

Benchmark piccoli, ripetibili e **privati** per valutare i modelli open-weight che installiamo in casa (o su GPU in cloud), divisi per tipo di compito.

Perché un altro benchmark? I benchmark pubblici (HumanEval, SWE-Bench, LiveCodeBench...) servono a confrontare i modelli fra loro, ma:

- sono **contaminati**: i problemi e le soluzioni finiscono nei dati di addestramento;
- i numeri li dichiarano spesso **gli autori stessi**, con harness e prompt scelti da loro;
- non misurano **il nostro hardware**: quanti token al secondo, quanta attesa, quanti utenti insieme.

Qui ogni modello passa esattamente gli stessi test, sulla nostra infrastruttura, con lo stesso harness. I problemi sono scritti da zero e i test restano nascosti al modello.

## Suite

| Suite | Stato | Cosa misura |
|---|---|---|
| `coding` | ✅ v1 (12 task) | Correttezza del codice generato, verificata con test unitari nascosti |
| `perf` | ✅ v1 | TTFT, token/s per stream e aggregati a concorrenza 1/4/8, velocità di prefill su prompt lungo |
| `text` | 🗓️ pianificata | Italiano: riassunto, estrazione strutturata (JSON), riscrittura di tono, Q&A su documenti |
| `tools` | 🗓️ pianificata | Function calling: scelta del tool, argomenti corretti, catene multi-step |
| `agentic-coding` | 🗓️ pianificata | Correggere un bug in un mini-repository multi-file usando tool (leggi/scrivi file, esegui test) |
| `long-context` | 🗓️ pianificata | "Ago nel pagliaio" e ragionamento su documenti da 32K-128K token |
| `vision` | 🗓️ pianificata | OCR di documenti, lettura di grafici e tabelle, descrizione di screenshot UI |

### `coding` v1

12 problemi Python originali, dal facile al difficile.

> **Task pubblici e privati.** Se i problemi fossero pubblicati, finirebbero presto nei dati di addestramento dei modelli e il benchmark perderebbe valore. Per questo il repository contiene solo **due task di esempio** (01 e 07, in `suites/coding/tasks/`) che mostrano il formato. Il set completo è in un repository privato e si carica con `--tasks-dir` o con la variabile `BENCH_TASKS_DIR`. Tutti i risultati pubblicati sono calcolati sul set completo.

| # | Task | Difficoltà | Categoria |
|---|---|---|---|
| 01 | Parsing di durate (`"1h30m"`) — *pubblico* | easy | parsing |
| 02 | Numeri romani rigorosi | easy | algoritmi |
| 03 | Inserimento e fusione di intervalli | easy | algoritmi |
| 04 | Cache LRU con TTL e orologio iniettabile | medium | strutture dati |
| 05 | Valutatore di espressioni (precedenze, unario, `^` destro) | medium | parsing |
| 06 | Cammino minimo con portali e caselle lente | medium | algoritmi |
| 07 | Debug di un rate limiter token-bucket (5 bug) — *pubblico* | medium | debugging |
| 08 | Parser JSON da zero (RFC 8259, surrogate pair) | medium | parsing |
| 09 | Scheduler asyncio di un DAG con concorrenza limitata | hard | concorrenza |
| 10 | Query SQL: miglior cliente per paese (window function) | medium | SQL |
| 11 | Diff di righe minimale (stile Myers) con vincoli di performance | hard | algoritmi |
| 12 | Motore di foglio di calcolo con cicli e propagazione degli errori | hard | design |

Ogni task ha:
- `prompt.md`: la specifica inviata al modello;
- `tests.py`: test nascosti (casi limite, test randomizzati con oracolo, vincoli di tempo);
- `reference.py`: soluzione di riferimento, usata **solo** per validare i test (`bench.py validate`).

Metriche:
- **pass@1**: probabilità che un singolo tentativo risolva il problema, cioè che passi *tutti* i suoi test (metrica introdotta con HumanEval, [Chen et al., 2021](https://arxiv.org/abs/2107.03374)). Con `--samples N` si stima, per ogni task, come c/N (c = tentativi corretti), poi si fa la media sui task. Con temperatura > 0 conviene N ≥ 3: con un solo campione il numero oscilla molto da un run all'altro;
- **test score**: frazione media di test superati (credito parziale);
- token generati (reasoning incluso), latenza, risposte troncate.

## Uso

Requisiti: Python 3.10+, nessuna dipendenza esterna. Funziona con qualsiasi endpoint OpenAI-compatibile (vLLM, SGLang, Ollama, llama.cpp server, LM Studio).

```bash
# 0. (opzionale) set completo di task da un repo privato
export BENCH_TASKS_DIR=/percorso/simple-llm-bench-tasks   # contiene coding/<task>

# 1. verifica che i test siano corretti
python bench.py validate

# 2. performance
python bench.py perf --base-url http://localhost:8000/v1 --model <nome> --label <etichetta>

# 3. coding (3 campioni per task, 4 richieste in parallelo)
python bench.py run --suite coding --base-url http://localhost:8000/v1 \
    --model <nome> --label <etichetta> --samples 3 --concurrency 4

# modalità senza thinking (se il chat template lo supporta)
python bench.py run ... --extra-body '{"chat_template_kwargs": {"enable_thinking": false}}'

# 4. confronto fra run
python bench.py report results/*.json --out results/REPORT.md
```

La chiave API si passa con `--api-key`, con la variabile `BENCH_API_KEY` o con un file `.apikey` (ignorato da git).

Ogni run salva:
- `results/<label>__coding__<timestamp>.json`: parametri, riepilogo e dettaglio di ogni tentativo;
- `results/<label>__coding__<timestamp>/`: reasoning e risposta completi di ogni tentativo, per l'analisi qualitativa.

> ⚠️ **Sicurezza**: il codice generato dal modello viene eseguito localmente (sottoprocesso con timeout, cartella temporanea). Non è una sandbox vera: usate una macchina o un container usa-e-getta.

## Risultati

| Modello | Hardware | pass@1 coding | tok/s (1 utente) | Diario |
|---|---|---|---|---|
| Nanbeige4.3-33B (BF16, thinking) | 1x A100 80GB, vLLM 0.32 | _in corso_ | 23,3 | [2026-10-28](docs/journal/2026-10-28-nanbeige4.3-33b.md) |

## Aggiungere un task

1. Create `NN_nome/` nella cartella dei task (gli esempi pubblici in `suites/coding/tasks/`, il set privato in `$BENCH_TASKS_DIR/coding/`) con `meta.json`, `prompt.md`, `tests.py`, `reference.py`.
2. I test sono funzioni `test_*` con `assert`; `pytest_shim` offre `raises`, `approx` e `source()` (il sorgente della soluzione, per vietare ad esempio `eval`).
3. `python bench.py validate --only NN_nome` deve dare OK.
4. Controprova: una soluzione sbagliata deve fallire.

## Licenza

MIT
