"""
Run the Ask Rammy benchmark against a local Ollama model, through the chatbot's
real /chat route (PII check, guided flow, retrieval, prompts, post-processing).

Only the model client is swapped (OpenAI -> Ollama). Nothing in chatbot_api.py
is edited. Run INSIDE the rammy-python container:

    docker cp gemma9b_eval/. rammy-python:/app/gemma9b_eval
    docker exec rammy-python python /app/gemma9b_eval/run_eval.py --limit 3

Results are appended one row per line to results.jsonl, so an interrupted run can
resume (rows already in the file are skipped).
"""
import argparse
import datetime
import json
import os
import sys
import time
import types

sys.path.insert(0, "/app")

import chatbot_api as c  # noqa: E402
from openai import OpenAI  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

p = argparse.ArgumentParser()
p.add_argument("--model", default="gemma2-9b-rammy")
p.add_argument("--base-url", default="http://rammy-ollama:11434/v1")
p.add_argument("--questions", default=os.path.join(HERE, "questions.json"))
p.add_argument("--out", default=os.path.join(HERE, "results.jsonl"))
p.add_argument("--limit", type=int, default=0, help="only run the first N rows")
p.add_argument("--rows", default="", help="comma-separated Excel row numbers to run")
p.add_argument("--timeout", type=float, default=600.0, help="seconds per model call")
p.add_argument("--seed", type=int, default=42)
p.add_argument("--retry-errors", action="store_true",
               help="re-run rows whose last recorded result was an error (the newest line per row wins)")
args = p.parse_args()

# ---- wire the chatbot to Ollama ---------------------------------------------
real = OpenAI(base_url=args.base_url, api_key="ollama", timeout=args.timeout, max_retries=0)
calls = []  # per-row log of model calls


def create(**kw):
    kw.setdefault("seed", args.seed)
    t0 = time.perf_counter()
    entry = {"max_tokens": kw.get("max_tokens"), "temperature": kw.get("temperature")}
    calls.append(entry)
    try:
        r = real.chat.completions.create(**kw)
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {e}"
        entry["secs"] = round(time.perf_counter() - t0, 3)
        raise
    u = getattr(r, "usage", None)
    entry["prompt_tokens"] = getattr(u, "prompt_tokens", None)
    entry["completion_tokens"] = getattr(u, "completion_tokens", None)
    entry["secs"] = round(time.perf_counter() - t0, 3)
    return r


c._client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
c.MODEL = args.model
c._startup_done = True          # skip the OpenAI-key startup hook
c._init_qdrant()                # real Qdrant + MiniLM, same as the live service
c.log_interaction = lambda *a, **k: None   # do not pollute analytics.jsonl

contexts = []
retrieval_secs = []
_orig_build_context = c.build_context


def _recording_build_context(question, chunks=None):
    _t = time.perf_counter()
    ctx = _orig_build_context(question, chunks)
    retrieval_secs.append(time.perf_counter() - _t)
    contexts.append({"query": question, "context": ctx})
    return ctx


c.build_context = _recording_build_context

# ---- run ----------------------------------------------------------------------
questions = json.load(open(args.questions))
if args.rows:
    want = {int(x) for x in args.rows.split(",")}
    questions = [q for q in questions if q["row"] in want]
if args.limit:
    questions = questions[: args.limit]

done = set()
if os.path.exists(args.out):
    last = {}
    for line in open(args.out):
        try:
            r = json.loads(line)
            last[r["row"]] = r
        except Exception:
            pass
    done = {k for k, r in last.items() if not (args.retry_errors and r.get("error"))}

client = c.app.test_client()
todo = [q for q in questions if q["row"] not in done]
print(f"{len(todo)} rows to run ({len(done)} already done), model={args.model}", flush=True)

for i, q in enumerate(todo, 1):
    # Fresh chat for every row: reset global history and guided-flow state.
    c.reset_flow()
    c.GLOBAL_HISTORY.clear()
    calls.clear()
    contexts.clear()
    retrieval_secs.clear()
    start = datetime.datetime.now(datetime.timezone.utc)
    t0 = time.perf_counter()
    status, reply, err = None, None, None
    try:
        resp = client.post("/chat", json={"message": q["question"]})
        status = resp.status_code
        body = resp.get_json(silent=True) or {}
        reply = body.get("reply")
        err = body.get("error")
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    elapsed = time.perf_counter() - t0
    model_errs = [x["error"] for x in calls if "error" in x]
    rec = {
        "row": q["row"],
        "category": q["category"],
        "question": q["question"],
        "reply": reply,
        "http_status": status,
        "error": err or (model_errs[0] if model_errs else None),
        "elapsed_s": round(elapsed, 3),
        "retrieval_s": round(sum(retrieval_secs), 3),
        "elapsed_excl_retrieval_s": round(elapsed - sum(retrieval_secs), 3),
        "model_calls": len(calls),
        "prompt_tokens": sum(x.get("prompt_tokens") or 0 for x in calls) if calls else 0,
        "completion_tokens": sum(x.get("completion_tokens") or 0 for x in calls) if calls else 0,
        "calls": list(calls),
        "contexts": list(contexts),
        "start_utc": start.isoformat(),
        "model": args.model,
    }
    with open(args.out, "a") as f:
        f.write(json.dumps(rec) + "\n")
    kind = "built-in" if not calls else ("ERROR" if rec["error"] else "model")
    print(f"[{i}/{len(todo)}] row {q['row']:>3} {kind:8} {elapsed:6.1f}s "
          f"tok {rec['prompt_tokens']}/{rec['completion_tokens']}  {q['question'][:60]!r}", flush=True)

print("done", flush=True)
