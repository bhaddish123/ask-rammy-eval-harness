# Ask Rammy Evaluation Harness

This is an evaluation harness for Ask Rammy, West Chester University's RAG-based HR chatbot. It was built for the CSC402 capstone, where Bereket is Testing & Data Lead. It reads question-and-answer rows from an Excel workbook, sends each question to a running chatbot HTTP API, and records latency, request status, whether a guided flow started, and a word-overlap score against the approved answer.

It does not host or modify the chatbot. This repository has no chatbot source, retrieval index, model configuration, or Docker setup. The scripts only call an API that is already running. They do not select a model. The chat client stores the `reply` field and does not record token usage or call `/api/analytics`.

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
