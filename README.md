# Ask Rammy — Evaluation Harness

Automated benchmarking for **Ask Rammy**, West Chester University's HR chatbot: a retrieval-augmented generation (RAG) assistant that answers employee HR questions from WCU and PASSHE policy pages and documents.

I built this as **Testing & Data Lead** on a 6-person CSC402 Software Engineering capstone team (Fall 2026).

> **Attribution:** the original Ask Rammy chatbot was built by a previous capstone team: [GarrettCrowner/CSC402-Project](https://github.com/GarrettCrowner/CSC402-Project). **This repo contains only the testing and benchmarking code.** None of the chatbot's source is included here.

---

## The project

The team is upgrading Ask Rammy with WCU HR as the client. Today the chatbot runs a single-model pipeline: retrieve the top 5 matching chunks from Qdrant, then generate an answer with GPT-4.1-mini. The planned replacement is a **dual-model** design: an *orchestrator* that routes and prepares each request, and a *generator* that writes the answer.

Three setups are being compared:

1. **Baseline** — the current GPT-4.1-mini pipeline
2. **Local / Local** — local orchestrator + local generator
3. **Local / Proprietary** — local orchestrator + GPT-4.1-mini generator

The best-performing setup is intended to go to production, with handoff documentation for HR and IT.

**My role:** I own the evaluation that decides which setup ships. I built the HR-validated benchmark, deployed the isolated staging environment the team tests against, and wrote this harness so every setup is measured the same way.

---

## System under test

```
benchmark .xlsx ──► this harness ──HTTP──► Node.js gateway (:3000) ──► Flask chatbot
                                                                  ├─► Qdrant (top-5 retrieval)
                                                                  └─► OpenAI GPT-4.1-mini
```

Staging (described in the original project notes, not checked into this repo) was an isolated, HR-only Docker Compose stack: Node.js, Flask, Qdrant, and MinIO, loaded with 613 vectors from 44 HR web sources. All harness runs target staging, never production.

The chat API used by the scripts is a single-model OpenAI setup. A per-request model switch for the dual-model comparison is called out in `test_benchmark.py` as future work.

---

## What's in this repo

| File | Purpose |
|---|---|
| `test_benchmark.py` | Reads Q&A rows from the benchmark workbook, `POST`s each question to `/api/chat` with an empty history, and writes `benchmark_results.csv` (latency, HTTP status, whether a guided/clarifying flow started, a word-overlap accuracy score). Default API: `http://localhost:3000`. |
| `guided_flow_walkthrough.py` | Replays guided-flow questions as multi-turn conversations. At each `[OPTIONS: A \| B]` prompt it picks the first option so runs are reproducible. Stops after 6 turns and writes transcripts. |
| `xlsx_reader.py` | Excel reader using only the standard library (`zipfile` + XML), including the shared-strings table. |
| `inspect_benchmark.py` | Prints the first rows of the spreadsheet so you can check column mappings. |
| `requirements.txt` | `requests>=2.32.3` |

The default spreadsheet path in `test_benchmark.py` is one directory *above* this repo: `../HR_QA_Benchmark_Template_version2.xlsx`. Columns expected (0-indexed): Category, Question, Approved Answer, Source Document, Priority. A real test case is a row with both a question and an approved answer. The title, instructions, header, and section-divider rows are skipped.

The benchmark spreadsheet and run outputs belong to WCU HR and are **not included**.

---

## Baseline results (GPT-4.1-mini, staging)

Recorded in this repo's existing write-up:

| Metric | Result |
|---|---|
| Benchmark cases run | 171 |
| API success rate | 100% (no timeouts or errors) |
| Avg response latency | ~1.5 s |
| Direct answers / guided flows | 151 / 20 |
| Guided flows resolved within 6 turns | 20 / 20 |

The benchmark includes HR-approved answers across topic categories, plus adversarial cases: out-of-scope questions, redirect-to-HR questions, and messages containing personal data (PII).

### Findings from those runs

- **Word-overlap scoring understates accuracy.** Overlap with the approved answer cannot credit a correct paraphrase or a correct refusal. Manual spot-checks across four question types (direct FAQ, guided flow, out-of-scope, PII) behaved correctly but scored as low as 11–19% overlap.
- **Guided-flow state can leak between conversations** if the chatbot keeps progress in one global object. `guided_flow_walkthrough.py` runs conversations one at a time to work around this.
- **Four benchmark rows** held placeholder text instead of approved answers and were sent back to HR.

---

## Running it

Requires Python 3.9+ and a running staging instance of the chatbot (gateway on `localhost:3000`).

```bash
pip install -r requirements.txt

python3 inspect_benchmark.py path/to/benchmark.xlsx
python3 test_benchmark.py --benchmark path/to/benchmark.xlsx --limit 10
python3 test_benchmark.py --benchmark path/to/benchmark.xlsx          # -> benchmark_results.csv
python3 guided_flow_walkthrough.py                                    # reads benchmark_results.csv
```

`test_benchmark.py` also accepts `--output` for a custom results path. A `/api/health` check runs before the suite.

---

## Roadmap

The next step described in this project is to score seven HR-approved metrics across the three model setups:

- **Answer accuracy** — pass/fail
- **Answer quality** — 0–5, LLM judge against a written rubric (replacing word overlap)
- **Source accuracy** — right source, or a correct redirect to HR
- **Privacy compliance** — pass/fail on PII cases
- **Latency**
- **Cost per query** — from token usage (token counts are not in the `/api/chat` response today; the script notes they are logged server-side / via `/api/analytics`)
- **Retrieval hit rate** — whether the right source is in Qdrant's top 5, kept separate from source accuracy

Borderline scores are intended to go to a manual-review list rather than being decided automatically.

---

## Tech

Python · requests · Docker Compose · Qdrant · MinIO · OpenAI API · RAG
