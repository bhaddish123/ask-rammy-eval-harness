"""Merge judgments (JSON object on stdin, keyed by row) into scores.json."""
import json, os, sys
f = "scores.json"
cur = json.load(open(f)) if os.path.exists(f) else {}
cur.update(json.load(sys.stdin))
json.dump(cur, open(f, "w"), indent=1)
print(len(cur), "rows scored")
