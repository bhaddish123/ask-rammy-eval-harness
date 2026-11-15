"""Extract benchmark questions from the evaluation workbook (stdlib only).
Rows with a Gemma 2B model-version entry (col Y) are the 178 attempted rows; rows without one
(pending HR answers) are excluded, matching the 2B run. Excel row numbers are kept.
"""
import html, json, re, sys, zipfile

src = sys.argv[1]
out = sys.argv[2]
z = zipfile.ZipFile(src)
ss = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
      for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S)]
rows = []
for m in re.finditer(r'<row r="(\d+)"[^>]*>(.*?)</row>', z.read("xl/worksheets/sheet1.xml").decode(), re.S):
    rnum, body = int(m.group(1)), m.group(2)
    d = {}
    for c in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', body, re.S):
        col, attrs, b = c.groups()
        if not b:
            continue
        v = re.search(r"<v>(.*?)</v>", b, re.S)
        d[col] = ss[int(v.group(1))] if 't="s"' in attrs and v else (
            html.unescape(v.group(1)) if v else html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", b, re.S))))
    if rnum > 5 and d.get("B"):
        rows.append({"row": rnum, "category": d.get("A", ""), "question": d["B"].strip(),
                     "attempted_2b": bool(d.get("Y")),
                     "builtin_2b": str(d.get("Y", "")).startswith("Not called"),
                     "error_2b": bool(d.get("Y")) and not d.get("Q") and not str(d.get("Y", "")).startswith("Not called")})
sel = [r for r in rows if r["attempted_2b"]]
# Run order: (0) rows the 2B run errored on, (1) out-of-scope / redirect / PII rows,
# (2) everything else; Excel row order within each group.
def prio(r):
    if r["error_2b"]:
        return 0
    if re.search(r"out.of.scope|redirect|privacy|pii", r["category"], re.I):
        return 1
    return 2
for r in sel:
    r["priority"] = prio(r)
sel.sort(key=lambda r: (r["priority"], r["row"]))
json.dump(sel, open(out, "w"), indent=1)
import collections
print("priority groups:", dict(collections.Counter(r["priority"] for r in sel)))
print(f"{len(rows)} question rows; {len(sel)} attempted by the 2B run; skipped rows:",
      [r["row"] for r in rows if not r["attempted_2b"]])
