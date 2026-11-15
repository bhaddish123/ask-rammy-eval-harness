"""Dump the evaluation workbook's main sheet to JSON keyed by Excel row (stdlib only)."""
import html, json, re, sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
ss = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
      for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S)]
out = {}
for m in re.finditer(r'<row r="(\d+)"[^>]*>(.*?)</row>', z.read("xl/worksheets/sheet1.xml").decode(), re.S):
    d = {}
    for c in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', m.group(2), re.S):
        col, attrs, b = c.groups()
        if not b:
            continue
        v = re.search(r"<v>(.*?)</v>", b, re.S)
        d[col] = ss[int(v.group(1))] if 't="s"' in attrs and v else (
            html.unescape(v.group(1)) if v else html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", b, re.S))))
    out[int(m.group(1))] = d
json.dump(out, open(sys.argv[2], "w"), indent=1)
