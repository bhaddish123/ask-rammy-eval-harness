# Ask Rammy: Evaluation Harness

Automated benchmarking for **Ask Rammy**, West Chester University's HR chatbot. It is a retrieval-augmented generation (RAG) assistant that answers employee HR questions from WCU and PASSHE policy pages and documents.

I built this as **Testing & Data Lead** on a 6-person CSC402 Software Engineering capstone team (Fall 2026). Our team is modernizing Ask Rammy from a single-model setup (GPT-4.1-mini) to a dual-model orchestrator/generator architecture. This harness measures the current baseline so the new setups can be compared against it.

> **Attribution:** the Ask Rammy chatbot was built by a previous capstone team: [GarrettCrowner/CSC402-Project](https://github.com/GarrettCrowner/CSC402-Project). **This repo contains only my testing and benchmarking code.** None of the chatbot's code is included here.

## What the system under test looks like

```
benchmark .xlsx ──► test harness ──HTTP──► Node.js gateway ──► Flask chatbot service
                                                                 ├─► Qdrant (top-5 semantic retrieval)
                                                                 └─► OpenAI GPT-4.1-mini
```

I deployed an isolated, HR-only staging copy of the chatbot with Docker Compose (four services: Node.js, Flask, Qdrant, MinIO). Its knowledge base holds 613 vectors from 44 HR web sources. All testing runs against staging, never production.

## What's in this repo

| File | Purpose |
|---|---|
| `test_benchmark.py` | Sends every benchmark question to the live `/api/chat` endpoint. It records latency, HTTP status, whether the bot started a guided (clarifying-question) flow, and a baseline accuracy score. |
| `guided_flow_walkthrough.py` | Runs each guided-flow question as a full multi-turn conversation. At each `[OPTIONS: A \| B]` prompt it picks the first option, so runs are reproducible. It stops at 6 turns and saves full transcripts for review. |
| `xlsx_reader.py` | A small Excel reader using only the Python standard library (`zipfile` + XML). It looks up Excel's shared-strings table so cells come back as readable text. |
| `inspect_benchmark.py` | Prints the first rows of the benchmark spreadsheet, to check column mappings. |

## Baseline results (GPT-4.1-mini, staging)

| Metric | Result |
|---|---|
| Benchmark cases run | 171 |
| API success rate | 100% (no timeouts or errors) |
| Avg response latency | ~1.5 s |
| Direct answers / guided flows | 151 / 20 |
| Guided flows resolved within 6 turns | 20 / 20 |

The benchmark has HR-approved answers across topic categories, plus adversarial cases: out-of-scope questions, redirect-to-HR questions, and messages containing personal data (PII).

## Findings

- **Word-overlap scoring understates accuracy.** The first scoring method compared word overlap with HR's approved answer. It can't give credit for a correct paraphrase or a correct refusal. Manual spot-checks across four question types (direct FAQ, guided flow, out-of-scope, PII) all behaved correctly, yet scored as low as 11–19% overlap.
- **Guided-flow state leaks between conversations.** The chatbot keeps conversation progress in one global object instead of one per session. An unfinished eligibility flow can carry into the next user's question. `guided_flow_walkthrough.py` runs conversations one at a time to work around this.
- **Gaps in the benchmark.** Four benchmark rows held placeholder text instead of approved answers. They were sent back to HR to be filled in.

## Running it

Requires Python 3.9+ and a running staging instance of the chatbot (gateway on `localhost:3000`).

```bash
pip install -r requirements.txt

python3 inspect_benchmark.py path/to/benchmark.xlsx                       # check column layout
python3 test_benchmark.py --benchmark path/to/benchmark.xlsx --limit 10   # quick run
python3 test_benchmark.py --benchmark path/to/benchmark.xlsx              # full run -> benchmark_results.csv
python3 guided_flow_walkthrough.py                                        # reads benchmark_results.csv
```

The benchmark spreadsheet and run outputs belong to WCU HR and are **not included**. The scripts expect these columns: Category, Question, Approved Answer, Source Document, Priority.

## Roadmap

Next, I'm extending the harness to score seven HR-approved metrics across three setups: the GPT-4.1-mini baseline, local orchestrator + local generator, and local orchestrator + GPT-4.1-mini generator.

- **Answer accuracy:** pass/fail.
- **Answer quality:** 0–5, scored by an LLM judge against a written rubric instead of word overlap.
- **Source accuracy:** whether the answer cites the right source, or correctly redirects to HR.
- **Privacy compliance:** pass/fail on PII test cases.
- **Latency.**
- **Cost per query:** from token usage.
- **Retrieval hit rate:** whether the right source document is in Qdrant's top 5 results. This is kept separate from source accuracy so a failure can be traced to search or to generation.

Borderline scores will go to a manual-review list rather than being decided automatically.

## Tech

Python · requests · Docker Compose · Qdrant · MinIO · OpenAI API · RAG
