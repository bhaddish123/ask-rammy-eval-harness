# Ask Rammy Evaluation Harness

## Overview

Ask Rammy is West Chester University's HR chatbot. It answers employee questions using retrieval-augmented generation (RAG) over WCU and PASSHE policy pages. I built this evaluation harness as **Testing & Data Lead** on a six-person CSC 402 Software Engineering capstone team (Fall 2026).

Our team is evaluating whether local open-source LLMs can replace the current GPT-4.1-mini setup. This repository contains only the testing and benchmarking code, not the chatbot itself. The original chatbot was built by a previous capstone team: [GarrettCrowner/CSC402-Project](https://github.com/GarrettCrowner/CSC402-Project).

## What it measures

The harness sends each benchmark question through the live chatbot route (Node front end → Python/Flask API → Qdrant retrieval → the model under test, including local models served with Ollama in Docker) and logs:

- the model's answer
- retrieved sources
- estimated correctness (see Limitations)
- retrieval hit rate
- source accuracy
- token counts
- response time

The 178-question benchmark includes HR-approved Q&A plus out-of-scope, redirect-to-HR, and privacy/PII cases. Results are also added to the team's shared evaluation workbook so models can be compared side by side.

## Results

Accuracy figures below are **estimated**. Model answers were AI-graded against HR's approved answers; this is not official HR sign-off.

| Model | Estimated accuracy | Notes |
|---|---|---|
| GPT-4.1-mini (baseline) | 65.2% | Current GPT setup used as the comparison point |
| Gemma 2 9B (local, Ollama in Docker) | 62.9% | This evaluation; median response time ~80 s on a laptop CPU |
| Qwen 2.5 3B (local) | 58.4% | Earlier team evaluation |
| Llama 3.2 3B (local) | 49.4% | Original local model, earlier evaluation |

Gemma 2 9B is close to the GPT-4.1-mini baseline and ahead of Qwen 2.5 3B. Speed, not estimated accuracy, is the main barrier to using the local 9B model in production.

During the Gemma 2 9B run, repeated model crashes were diagnosed as out-of-memory failures and fixed by tuning Docker resources. That same issue likely caused the 48 errors in a teammate's earlier Gemma 2B run.

## How it works

A Python test harness (written with AI assistance) reads questions from the team's Excel benchmark, posts each one to the real chatbot API, and records the answer, retrieved sources, token counts, and timings. Using the live route — not a stripped-down model call — keeps results reproducible and comparable across models. The benchmark workbook and run outputs belong to WCU HR and are not included in this repository.

## Features

- Loads a benchmark workbook with `xlsx_reader.py` (standard library only). A test case is a row with both a question and an approved answer. The header row (`Question` / `Approved Answer`) is skipped.
- `test_benchmark.py` checks `GET /api/health`, then `POST`s each question to `/api/chat` with an empty history.
- Writes `benchmark_results.csv` and prints a summary: case count, success and failure counts, guided-flow count, direct-answer count, average latency, and average word-overlap on direct answers.
- Treats a reply containing `[OPTIONS:` as a guided flow. Word overlap is computed only for successful direct answers.
- `guided_flow_walkthrough.py` replays those guided-flow rows one conversation at a time and writes `guided_flow_transcripts.csv` (transcript, final reply, turn count, whether it hit the turn cap).
- `inspect_benchmark.py` prints the worksheet row count and the first 15 rows so the column layout can be checked.

The benchmark workbook and run outputs are not in this repository. `.gitignore` excludes `*.xlsx`, `*.csv`, and `*.pdf`. No case counts or saved scores are checked in.

## Tech Stack

- Python 3 (scripts use `#!/usr/bin/env python3`)
- `requests>=2.32.3` (only third-party package; see `requirements.txt`)
- Standard library: `argparse`, `csv`, `pathlib`, `time`, `zipfile`, `xml.etree`, `re`

Both runners call `http://localhost:3000`. That base URL is a constant in the source, not an environment variable. Endpoints used: `GET /api/health`, `POST /api/chat`.

## Project Structure

```txt
.
├── test_benchmark.py            # run workbook questions against /api/chat; write benchmark_results.csv
├── guided_flow_walkthrough.py   # replay guided-flow rows as multi-turn chats; write guided_flow_transcripts.csv
├── xlsx_reader.py               # read sheet1 from an .xlsx file, including the shared-strings table
├── inspect_benchmark.py         # print the row count and the first 15 rows
├── local_model_eval/            # local-model run (Gemma 2 9B via Ollama); see below
│   ├── extract_questions.py     #   pull benchmark questions from the workbook, failed-before rows first
│   ├── run_eval.py              #   run inside the chatbot's Python container; swaps the OpenAI client for Ollama
│   ├── read_sheet.py            #   dump the workbook to JSON to compare with earlier runs
│   ├── review_batch.py          #   show answer vs. approved answer vs. retrieved chunks for grading
│   ├── save_scores.py           #   save grades to scores.json
│   └── build_workbook.py        #   write results as new columns in a copy of the team workbook (needs openpyxl)
├── requirements.txt             # requests>=2.32.3
├── .gitignore                   # ignores .env, *.xlsx, *.csv, *.pdf, virtualenvs
└── README.md
```

## Run

A chatbot gateway must already be accepting connections at `http://localhost:3000`. No environment variables are read. Install the dependency, then run from this directory:

```bash
pip install -r requirements.txt

python3 inspect_benchmark.py path/to/benchmark.xlsx
python3 test_benchmark.py --benchmark path/to/benchmark.xlsx --limit 10
python3 test_benchmark.py --benchmark path/to/benchmark.xlsx
python3 guided_flow_walkthrough.py
```

`test_benchmark.py` arguments:

- `--benchmark` — path to the workbook. Default: `../HR_QA_Benchmark_Template_version2.xlsx` (one directory above this repo). The run exits if the file is missing.
- `--output` — results CSV. Default: `benchmark_results.csv` in this directory.
- `--limit` — optional. After parsing, keep only the first N test cases.

`inspect_benchmark.py` takes an optional workbook path as its first argument. With no argument it uses the same default path as `test_benchmark.py`. If the file is missing it prints `File not found` and stops.

`guided_flow_walkthrough.py` takes no arguments. It reads `benchmark_results.csv` in this directory and writes `guided_flow_transcripts.csv` beside it. The results file has to exist already; rows are selected where `guided_flow` is `True`.

Workbook columns, 0-indexed, as read by `test_benchmark.py`: Category, Question, Approved Answer, Source Document, Priority. The runner keeps category, question, approved answer, and priority. The source-document cell is not written to the CSV. `xlsx_reader.py` reads `xl/worksheets/sheet1.xml` only.

Request details in `test_benchmark.py`:

- Health check: `GET /api/health`, 5 second timeout. If the connection fails, the script tells you to run `docker ps` and exits. A non-200 response is printed, and the run still continues.
- Chat: `POST /api/chat` with JSON `{"message": "<question>", "history": []}`, 30 second timeout.
- 0.5 seconds between questions.
- `status` is `success` on HTTP 200, `timeout` after 30 seconds, otherwise `error`.
- `guided_flow` is true when the reply contains `[OPTIONS:`.
- Failed requests, empty replies, and guided-flow rows score 0. For a successful direct answer, `word_overlap_score` is the number of distinct lowercase whitespace-separated words shared with the reply, divided by the number of distinct words in the approved answer, capped at 1.0, then rounded to two decimal places.

`benchmark_results.csv` columns: `row`, `category`, `priority`, `question`, `expected_answer`, `actual_reply`, `latency_ms`, `status`, `guided_flow`, `word_overlap_score`, `error`. `row` is the 1-based worksheet row number. `latency_ms` is client-side elapsed time.

`guided_flow_walkthrough.py` sends the same chat payload, appending `user` and `assistant` turns to `history`. When a reply matches `[OPTIONS: A | B | ...]`, it sends the first option as the next message. It stops at 6 bot turns (`MAX_TURNS`). It waits 0.3 seconds after each conversation.

`guided_flow_transcripts.csv` columns: `row`, `category`, `question`, `expected_answer`, `final_reply`, `unresolved`, `num_turns`, `transcript`. `unresolved` is true when the turn cap is hit before a reply with no options. `num_turns` counts bot replies. `transcript` joins turns with ` || `.

### Local model run (`local_model_eval/`)

`run_eval.py` imports the chatbot's own Flask app inside its `rammy-python` container and replaces only the model client with an Ollama server, so the PII check, guided flow, Qdrant retrieval and prompts stay the same as production. It resets conversation state before every question, appends one JSON line per question to `results.jsonl`, and can resume an interrupted run (`--retry-errors` re-runs only failed rows).

```bash
python3 local_model_eval/extract_questions.py path/to/workbook.xlsx local_model_eval/questions.json
docker cp local_model_eval/. rammy-python:/app/gemma9b_eval
docker exec rammy-python python /app/gemma9b_eval/run_eval.py --model gemma2:9b --limit 3
```

Setup used for the Gemma 2 9B run: Ollama 0.34.3 in Docker on the chatbot's network (CPU only, Apple M2, 16 GB RAM), `gemma2:9b` (Q4_0), 8192-token context, seed 42.

## Limitations

- **Estimated scoring.** Correctness was AI-graded against HR-approved answers, not reviewed or signed off by HR. Treat the percentages as estimates.
- **Latency.** Gemma 2 9B's median response time was about 80 seconds on a laptop CPU, which is too slow for production as tested.
- **This repo does not include the chatbot, the policy documents, or the benchmark spreadsheet.**
