"""Print a compact review view of N rows (question, approved answer, 9B reply, retrieved chunks)."""
import json, re, sys, html as H
s = json.load(open("sheet.json")); R = json.load(open("results_final.json"))
rows = [r for r in R if r["model_calls"]]
if len(sys.argv) > 3:
    want = {int(x) for x in sys.argv[3].split(",")}
    rows = [r for r in rows if r["row"] in want]
start, n = int(sys.argv[1]), int(sys.argv[2])
def strip(t): return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()
def links(t): return re.findall(r'href="([^"]+)"', t or "")
for r in rows[start:start+n]:
    row = str(r["row"]); d = s[row]
    pos = re.search(r"Relevant positions in retrieved top-5 order: ([^.]*)\.", d.get("U", ""))
    print(f"##### ROW {row} [{r['category']}]  calls={r['model_calls']} tok={r['prompt_tokens']}/{r['completion_tokens']}")
    print("Q:", r["question"])
    print("APPROVED:", strip(d.get("C"))[:600])
    print("2B grade:", d.get("R"), "| 2B relevant pos:", pos.group(1) if pos else "?")
    print("9B REPLY:", strip(r["reply"])[:700], "| LINKS:", links(r["reply"]))
    ctx = r["contexts"][0]["context"] if r["contexts"] else ""
    DIFF = {9, 21, 27, 35, 40, 176, 999}
    relset = {int(x) for x in re.findall(r"\d", pos.group(1))} if pos else set()
    for i, (u, t) in enumerate(re.findall(r"Source \d+: (.*?)\nContent:\n(.*?)(?=\n\nSource \d+:|\n\nAvailable source URLs:)", ctx, re.S), 1):
        full = r["row"] in DIFF or i in relset
        print(f"  [{i}{'*' if i in relset else ''}] {u.split('//')[-1][:55]}: {strip(t)[:800 if full else 140]}")
    print()
