#!/usr/bin/env python3
"""
Benchmark Testing Script for Rammy HR Chatbot
Feeds Q&A test cases from HR_QA_Benchmark_Template_version2.xlsx through the
live /api/chat endpoint and collects metrics: latency, accuracy, status.

Usage:
    python3 test_benchmark.py [--benchmark path/to/benchmark.xlsx] [--output results.csv] [--limit 20]

Notes:
    - The chat API is currently a single-model OpenAI setup (dual-model
      Local/Local and Local/Proprietary comparison is future Weeks 5-6 work),
      so there is no per-request model switch yet.
    - Token usage isn't returned in the /api/chat response -- it's logged
      server-side and readable via GET /api/analytics if needed later.
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from xlsx_reader import read_xlsx_rows

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

API_BASE_URL = "http://localhost:3000"  # Node.js gateway
HEALTH_ENDPOINT = f"{API_BASE_URL}/api/health"
CHAT_ENDPOINT = f"{API_BASE_URL}/api/chat"

SCRIPT_DIR = Path(__file__).parent
BENCHMARK_FILE = SCRIPT_DIR.parent / "HR_QA_Benchmark_Template_version2.xlsx"
DEFAULT_OUTPUT_FILE = SCRIPT_DIR / "benchmark_results.csv"

# Spreadsheet columns (0-indexed): Category, Question, Approved Answer, Source Document, Priority
COL_CATEGORY, COL_QUESTION, COL_ANSWER, COL_SOURCE, COL_PRIORITY = range(5)

# ─────────────────────────────────────────────────────────────────────────────
# BENCHMARK PARSING
# ─────────────────────────────────────────────────────────────────────────────

def parse_benchmark_rows(rows):
    """
    Skip the title, instructions, header, and section-divider rows.
    A real test-case row has both a Question and an Approved Answer populated.
    """
    test_cases = []
    for i, row in enumerate(rows, start=1):
        question = row[COL_QUESTION].strip() if len(row) > COL_QUESTION and row[COL_QUESTION] else ""
        answer = row[COL_ANSWER].strip() if len(row) > COL_ANSWER and row[COL_ANSWER] else ""
        category = row[COL_CATEGORY].strip() if len(row) > COL_CATEGORY and row[COL_CATEGORY] else ""
        priority = row[COL_PRIORITY].strip() if len(row) > COL_PRIORITY and row[COL_PRIORITY] else ""

        if question == "Question" and answer == "Approved Answer":
            continue  # literal header row

        if question and answer:
            test_cases.append({
                "row": i,
                "category": category,
                "question": question,
                "expected_answer": answer,
                "priority": priority,
            })

    return test_cases

# ─────────────────────────────────────────────────────────────────────────────
# API CALLS
# ─────────────────────────────────────────────────────────────────────────────

def call_chat_api(question):
    """Call POST /api/chat and measure response time."""
    payload = {"message": question, "history": []}
    start_time = time.time()

    try:
        resp = requests.post(CHAT_ENDPOINT, json=payload, timeout=30)
        latency_ms = (time.time() - start_time) * 1000

        if resp.status_code == 200:
            data = resp.json()
            return {
                "status": "success",
                "reply": data.get("reply", ""),
                "latency_ms": round(latency_ms, 2),
                "error": None,
            }
        else:
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            return {
                "status": "error",
                "reply": None,
                "latency_ms": round(latency_ms, 2),
                "error": f"HTTP {resp.status_code}: {data.get('error', resp.text[:150])}",
            }
    except requests.exceptions.Timeout:
        return {
            "status": "timeout",
            "reply": None,
            "latency_ms": (time.time() - start_time) * 1000,
            "error": "Request timeout (>30s)",
        }
    except Exception as e:
        return {
            "status": "error",
            "reply": None,
            "latency_ms": (time.time() - start_time) * 1000,
            "error": str(e),
        }

def simple_accuracy_check(expected, actual):
    """Crude word-overlap heuristic. Use for a rough signal only -- read
    the actual_response column by hand for real accuracy judgments."""
    if not actual:
        return 0.0

    expected_words = set(expected.lower().split())
    actual_words = set(actual.lower().split())

    if not expected_words:
        return 0.0

    overlap = len(expected_words & actual_words)
    return min(1.0, overlap / len(expected_words))

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, default=BENCHMARK_FILE, help="Path to the benchmark .xlsx")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N test cases")
    args = parser.parse_args()

    print("=" * 80)
    print(f"Rammy Benchmark Testing | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output: {args.output}")
    print("=" * 80)

    if not args.benchmark.exists():
        print(f"Benchmark file not found: {args.benchmark}")
        sys.exit(1)

    print(f"\nReading {args.benchmark}...")
    rows = read_xlsx_rows(args.benchmark)
    test_cases = parse_benchmark_rows(rows)
    print(f"Loaded {len(test_cases)} test cases")

    if args.limit:
        test_cases = test_cases[: args.limit]
        print(f"Limiting to first {len(test_cases)} test cases")

    print(f"\nTesting API connectivity to {HEALTH_ENDPOINT}...")
    try:
        resp = requests.get(HEALTH_ENDPOINT, timeout=5)
        if resp.status_code == 200:
            print("API is reachable and healthy")
        else:
            print(f"API responded with {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        print(f"Cannot reach API: {e}")
        print("   Ensure Docker services are running: docker ps")
        sys.exit(1)

    print(f"\nRunning {len(test_cases)} test cases...\n")

    results = []
    for i, test in enumerate(test_cases, 1):
        print(f"[{i}/{len(test_cases)}] ({test['category']}) {test['question'][:55]}...", end=" ", flush=True)

        api_result = call_chat_api(test["question"])

        is_guided_flow = bool(api_result["reply"]) and "[OPTIONS:" in api_result["reply"]

        accuracy = 0.0
        if api_result["status"] == "success" and not is_guided_flow:
            accuracy = simple_accuracy_check(test["expected_answer"], api_result["reply"])

        results.append({
            "row": test["row"],
            "category": test["category"],
            "priority": test["priority"],
            "question": test["question"],
            "expected_answer": test["expected_answer"],
            "actual_reply": api_result["reply"] or "",
            "latency_ms": api_result["latency_ms"],
            "status": api_result["status"],
            "guided_flow": is_guided_flow,
            "word_overlap_score": round(accuracy, 2),
            "error": api_result["error"] or "",
        })

        status_icon = "OK" if api_result["status"] == "success" else "FAIL"
        print(f"[{status_icon}] {api_result['latency_ms']:.0f}ms | overlap: {accuracy:.0%}")

        if i < len(test_cases):
            time.sleep(0.5)

    print(f"\nSaving results to {args.output}...")
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "row", "category", "priority", "question", "expected_answer",
            "actual_reply", "latency_ms", "status", "guided_flow", "word_overlap_score", "error",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    successful = [r for r in results if r["status"] == "success"]
    guided = [r for r in successful if r["guided_flow"]]
    direct = [r for r in successful if not r["guided_flow"]]
    avg_latency = sum(r["latency_ms"] for r in successful) / len(successful) if successful else 0
    avg_overlap = sum(r["word_overlap_score"] for r in direct) / len(direct) if direct else 0

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total test cases: {len(results)}")
    print(f"Successful: {len(successful)} ({len(successful) / len(results) * 100:.0f}%)" if results else "Successful: 0")
    print(f"Failed: {len(results) - len(successful)}")
    print(f"Guided-flow (clarifying question, not final answer): {len(guided)}")
    print(f"Direct answers: {len(direct)}")
    print(f"Avg latency: {avg_latency:.0f}ms")
    print(f"Avg word-overlap score on direct answers (rough signal, not real accuracy): {avg_overlap:.0%}")
    print(f"\nResults saved to {args.output}")
    print("=" * 80)

if __name__ == "__main__":
    main()
