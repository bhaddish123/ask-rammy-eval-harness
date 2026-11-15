"""
Build a copy of the evaluation workbook with Gemma 9B columns (AM-AW) added after Granite.

Inputs (this folder): results_raw.jsonl, results_final.json, scores.json, sheet.json
Usage: python build_workbook.py <original.xlsx> <output.xlsx>
Requires openpyxl. The original workbook is not modified.
"""
import collections
import copy
import datetime as dt
import json
import re
import statistics as st
import sys

import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string

SRC, OUT = sys.argv[1], sys.argv[2]
sheet = json.load(open("sheet.json"))
final = {r["row"]: r for r in json.load(open("results_final.json"))}
scores = json.load(open("scores.json"))
attempts = collections.Counter()
earlier_errors = collections.defaultdict(list)
for line in open("results_raw.jsonl"):
    r = json.loads(line)
    attempts[r["row"]] += 1
    if r.get("error"):
        earlier_errors[r["row"]].append(r["error"])

MODEL_VERSION = "gemma2:9b (9.2B, Q4_0)"
DIGEST = "ff02c3702f322b9e075e9568332d96c0a7028002f1a5a056e0a6784320a4db0b"
SETTINGS = ("CPU (Docker, Ollama 0.34.3, 12.65 GiB VM); live top-5 HR retrieval through the chatbot /chat route "
            "(613-point index, original question); fresh chat; 6 threads; context 8192; seed 42; "
            "temperature 0.3/max 300; fallback 0.8/max 100. Timing includes any model load; excludes retrieval.")

HEADERS = ["Gemma 9B Result", "Gemma 9B Correct? (Estimated)", "Gemma 9B Retrieval Hit Rate (Estimated)",
           "Gemma 9B Source Accuracy (Estimated)", "Gemma 9B Metric Evidence / Scoring Note",
           "Gemma 9B Input Tokens", "Gemma 9B Output Tokens",
           "Gemma 9B Response Time (s; excludes retrieval)", "Gemma 9B Model Version",
           "Gemma 9B Test Start (UTC)", "Gemma 9B Run Settings / Errors"]
SRC_COL = column_index_from_string("AB")   # Granite block start, used as the style template
DST_COL = column_index_from_string("AM")


def excel_serial(iso):
    t = dt.datetime.fromisoformat(iso).astimezone(dt.timezone.utc).replace(tzinfo=None)
    return (t - dt.datetime(1899, 12, 30)).total_seconds() / 86400


def sources(r):
    ctx = r["contexts"][0]["context"] if r["contexts"] else ""
    part = ctx.split("Available source URLs:\n")
    return [u[2:].strip() for u in part[1].splitlines() if u.startswith("- ")] if len(part) > 1 else []


def retrieval(row, sc):
    """(hit rate, positions text, note) - reuse the 2B judgment when retrieval matched it."""
    if sc and "ret" in sc:
        return sc["ret"][0], sc["ret"][1], sc["retnote"]
    s2 = sheet[str(row)].get("S")
    pos = re.search(r"Relevant positions in retrieved top-5 order: ([^.]*)\.", sheet[str(row)].get("U", ""))
    rate = float(s2) if s2 not in (None, "N/A") else "N/A"
    return rate, (pos.group(1) if pos else "none"), "Same ordered sources as the 2B run; relevance judgment carried over."


wb = openpyxl.load_workbook(SRC)
ws = wb["HR Q&A Template"]

# Copy column widths and every cell style from the Granite block so fills/borders match.
for i in range(11):
    s_letter, d_letter = get_column_letter(SRC_COL + i), get_column_letter(DST_COL + i)
    if s_letter in ws.column_dimensions:
        ws.column_dimensions[d_letter].width = ws.column_dimensions[s_letter].width
    for row in range(1, ws.max_row + 1):
        src = ws.cell(row=row, column=SRC_COL + i)
        dst = ws.cell(row=row, column=DST_COL + i)
        if src.has_style:
            dst._style = copy.copy(src._style)

for i, h in enumerate(HEADERS):
    ws.cell(row=4, column=DST_COL + i, value=h)

summary = collections.Counter()
times, hit_rates, src_yes, src_graded = [], [], 0, 0
for row, r in sorted(final.items()):
    sc = scores.get(str(row))
    builtin = r["model_calls"] == 0
    tries = attempts[row]
    retry_note = ""
    if tries > 1:
        retry_note = (f" Succeeded on attempt {tries} after {tries - 1} request error(s) "
                      f"(Ollama model runner stopped/killed under memory pressure; see run.log).")
    srcs = ", ".join(sources(r))
    if builtin:
        d2 = sheet[str(row)]
        correct, source_acc, rate = d2.get("R") or "N/A", "N/A", "N/A"
        note = (f"Fresh Gemma 9B run {r['start_utc'][:10]} (UTC). HTTP {r['http_status']}. Built-in response; "
                f"model not called. Reply identical to the 2B run, so its correctness grade ({correct}) carries over. "
                f"Generation calls: 0. Generation tokens: 0 input, 0 output.")
        version, settings = "Not called — built-in rule", "Built-in rule only; model was not called; fresh guided state."
    else:
        rate, pos, retnote = retrieval(row, sc)
        correct, source_acc = sc["c"], sc["s"]
        k = round(rate * 5) if isinstance(rate, float) else "N/A"
        pct = f"{round(rate * 100)}%" if isinstance(rate, float) else "N/A"
        note = (f"Fresh Gemma 9B run {r['start_utc'][:10]} (UTC). HTTP {r['http_status']}. "
                f"Response time {r['elapsed_excl_retrieval_s']:.2f}s (retrieval excluded). "
                f"Relevant chunks: {k}/5 ({pct}). Relevant positions in retrieved top-5 order: {pos}. {retnote} "
                f"Source accuracy {source_acc}: {sc['ns']} Sources: {srcs}. "
                f"Answer correctness {correct}: {sc['nc']} "
                f"Generation calls: {r['model_calls']}. Generation tokens: {r['prompt_tokens']} input, "
                f"{r['completion_tokens']} output.{retry_note}")
        version, settings = MODEL_VERSION, SETTINGS + (f" Attempts: {tries}." if tries > 1 else "")
        times.append(r["elapsed_excl_retrieval_s"])
        if isinstance(rate, float):
            hit_rates.append(rate)
        if source_acc in ("Yes", "No"):
            src_graded += 1
            src_yes += source_acc == "Yes"
    summary[correct] += 1
    values = [r["reply"], correct, rate, source_acc, note, r["prompt_tokens"], r["completion_tokens"],
              r["elapsed_excl_retrieval_s"], version, excel_serial(r["start_utc"]), settings]
    for i, v in enumerate(values):
        ws.cell(row=row, column=DST_COL + i, value=v)

# Run details sheet: append Gemma 9B lines.
rd = wb["Run details"]
graded = summary["Yes"] + summary["No"]
lines = [
    ("Gemma 9B status", f"178 recorded; {178 - sum(1 for r in final.values() if r['model_calls'] == 0)} model-generated; "
                        f"{sum(1 for r in final.values() if r['model_calls'] == 0)} built-in; 0 unresolved request errors "
                        f"({sum(attempts.values()) - 178} failed attempts retried; {sum(1 for v in attempts.values() if v > 1)} rows needed retries)."),
    ("Gemma 9B model", f"{MODEL_VERSION}; Ollama tag gemma2:9b; manifest digest {DIGEST}. Same Ollama runtime version (0.34.3, Docker, CPU) as the 2B run."),
    ("Gemma 9B results", f"Correct {summary['Yes']}/{graded} graded ({summary['Yes'] / graded:.1%}); correct delivery {summary['Yes']}/178 "
                         f"({summary['Yes'] / 178:.1%}). Mean retrieval hit rate {st.mean(hit_rates):.1%} over {len(hit_rates)} rows. "
                         f"Source accuracy Yes {src_yes}/{src_graded}. Model-row response time mean {st.mean(times):.1f}s, "
                         f"median {st.median(times):.1f}s, max {max(times):.1f}s (retrieval excluded)."),
    ("Gemma 9B differences from 2B run", "Retrieval ran live through the chatbot /chat route against a 613-point rammy_hr index "
                                         "(2B run: 615-point frozen contexts). 160 of 168 model rows retrieved the same ordered sources "
                                         "and reuse the 2B relevance judgment; 8 rows (9, 21, 27, 35, 40, 176, 177, 183) differed and were judged fresh."),
    ("Gemma 9B request errors", "Ollama's model runner was repeatedly killed for lack of memory (OOMKilled) at 11.7 GiB; Docker memory was raised "
                                "to 12.65 GiB with 2 GB swap mid-run. Failed rows were retried until all 178 succeeded. The laptop also slept "
                                "for periods overnight; timings are wall-clock per request and exclude those gaps."),
    ("Gemma 9B scoring", "Correctness, retrieval relevance and source support were judged by an automated reviewer (Claude) against the saved "
                         "Approved Answer and the exact retrieved chunks, using the same rubric as above. Estimated judgments; not HR approval. "
                         "A human spot-check is recommended."),
]
start = rd.max_row + 1
for i, (k, v) in enumerate(lines):
    rd.cell(row=start + i, column=1, value=k)
    rd.cell(row=start + i, column=2, value=v)
    for col in (1, 2):
        tmpl = rd.cell(row=start - 1, column=col)
        if tmpl.has_style:
            rd.cell(row=start + i, column=col)._style = copy.copy(tmpl._style)

wb.save(OUT)
print("saved", OUT)
print("correct:", dict(summary), "| graded acc %.1f%% | delivery %.1f%%" % (100 * summary["Yes"] / graded, 100 * summary["Yes"] / 178))
print("hit rate mean %.3f (n=%d) | source yes %d/%d | time mean %.1f median %.1f max %.1f"
      % (st.mean(hit_rates), len(hit_rates), src_yes, src_graded, st.mean(times), st.median(times), max(times)))
