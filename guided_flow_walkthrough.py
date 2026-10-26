#!/usr/bin/env python3
"""
Drives each guided-flow benchmark question to full completion, one
conversation at a time, so FLOW_PROGRESS (a global, non-per-session dict in
chatbot_api.py) resets properly between test cases instead of leaking state
into the next question.

At each [OPTIONS: A | B | ...] prompt, the FIRST listed option is chosen
(deterministic, reproducible). Full transcripts + final answers are saved
for manual review against the benchmark's approved answer.
"""

import csv
import re
import time
from pathlib import Path

import requests

API_BASE_URL = "http://localhost:3000"
CHAT_ENDPOINT = f"{API_BASE_URL}/api/chat"

SCRIPT_DIR = Path(__file__).parent
RESULTS_FILE = SCRIPT_DIR / "benchmark_results.csv"
OUTPUT_FILE = SCRIPT_DIR / "guided_flow_transcripts.csv"

MAX_TURNS = 6  # safety cap per conversation

OPTIONS_RE = re.compile(r"\[OPTIONS:\s*(.+?)\]")


def extract_first_option(reply):
    match = OPTIONS_RE.search(reply)
    if not match:
        return None
    options = [o.strip() for o in match.group(1).split("|")]
    return options[0] if options else None


def run_conversation(question):
    history = []
    turns = [("user", question)]

    message = question
    for _ in range(MAX_TURNS):
        payload = {"message": message, "history": history}
        resp = requests.post(CHAT_ENDPOINT, json=payload, timeout=30)
        resp.raise_for_status()
        reply = resp.json().get("reply", "")
        turns.append(("bot", reply))

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})

        next_option = extract_first_option(reply)
        if next_option is None:
            return turns, reply, False  # done, final answer

        message = next_option
        turns.append(("user", message))

    return turns, reply, True  # hit MAX_TURNS without resolving


def main():
    with open(RESULTS_FILE) as f:
        guided_rows = [r for r in csv.DictReader(f) if r["guided_flow"] == "True"]

    print(f"Walking through {len(guided_rows)} guided-flow conversations, one at a time...\n")

    results = []
    for i, row in enumerate(guided_rows, 1):
        question = row["question"]
        print(f"[{i}/{len(guided_rows)}] Row {row['row']}: {question[:60]}...")

        turns, final_reply, unresolved = run_conversation(question)

        transcript = " || ".join(f"{who}: {text}" for who, text in turns)
        results.append({
            "row": row["row"],
            "category": row["category"],
            "question": question,
            "expected_answer": row["expected_answer"],
            "final_reply": final_reply,
            "unresolved": unresolved,
            "num_turns": len([t for t in turns if t[0] == "bot"]),
            "transcript": transcript,
        })

        status = "UNRESOLVED (hit turn cap)" if unresolved else "resolved"
        print(f"    -> {status} in {len([t for t in turns if t[0] == 'bot'])} bot turns")

        time.sleep(0.3)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["row", "category", "question", "expected_answer", "final_reply", "unresolved", "num_turns", "transcript"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    unresolved_count = sum(1 for r in results if r["unresolved"])
    print(f"\nDone. {len(results) - unresolved_count}/{len(results)} resolved to a final answer within {MAX_TURNS} turns.")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
