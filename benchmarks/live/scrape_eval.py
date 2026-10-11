#!/usr/bin/env python3
"""Firecrawl scrape-content-dataset-v1 (pinned HF sha aad2b00) evaluated on goat_extract.
Usage: scrape_eval.py BUNDLE CSV N SEED OUT.json
NOTE: Firecrawl's official grader repo was not reachable; this is a DOCUMENTED APPROXIMATION:
 truth_recall = share of truth_text tokens present in extracted text; truth_hit = recall>=0.8;
 lie_hit = normalized lie_text substring present (noise leaked); coverage = extract returned ok with text.
Env/transport failures are reported separately and excluded from quality."""
import csv, json, random, re, sys, time, datetime, os
sys.path.insert(0, os.path.dirname(__file__))
from common import load_tools, call
csv.field_size_limit(10**9)
bundle, path, n, seed, out = sys.argv[1:6]
tok = lambda s: re.findall(r"[a-z0-9]+", s.lower())
rows = [r for r in csv.DictReader(open(path)) if r["url"].startswith("https://") and not r.get("error")]
sample = random.Random(int(seed)).sample(rows, int(n)); tools = load_tools(bundle); res = []
for i, r in enumerate(sample):
    e, ms = call(tools, "goat_extract", {"url": r["url"]}); code = (e.get("error") or {}).get("code")
    rec = {"i": i, "url": r["url"], "ms": round(ms,1), "ok": e.get("ok"), "error_code": code}
    if e.get("ok"):
        text = e.get("text",""); T = set(tok(text)); tt = tok(r["truth_text"])
        rec.update(status=e.get("status"), text_len=len(text), truncated=e.get("truncated"),
                   truth_recall=sum(t in T for t in tt)/max(1,len(tt)), lie_hit=" ".join(tok(r["lie_text"])) in " ".join(tok(text)))
        rec["truth_hit"] = rec["truth_recall"] >= 0.8
    res.append(rec); print(i, code or "ok", rec.get("status"), rec.get("truth_recall"), rec.get("lie_hit"), f"{ms:.0f}ms", r["url"][:60], flush=True)
ok = [x for x in res if x["ok"]]
sm = {"n": len(res), "coverage_ok": len(ok)/len(res), "errors": {c: sum(x["error_code"]==c for x in res) for c in {x["error_code"] for x in res if not x["ok"]}},
      "truth_hit_rate_of_ok": sum(x["truth_hit"] for x in ok)/max(1,len(ok)), "mean_truth_recall_of_ok": sum(x["truth_recall"] for x in ok)/max(1,len(ok)),
      "lie_leak_rate_of_ok": sum(x["lie_hit"] for x in ok)/max(1,len(ok)), "truncated_rate": sum(bool(x["truncated"]) for x in ok)/max(1,len(ok))}
lat = sorted(x["ms"] for x in ok)
if lat: sm["p50_ms"] = lat[len(lat)//2]; sm["p95_ms"] = lat[min(len(lat)-1,int(len(lat)*.95))]
print(json.dumps(sm, indent=1))
json.dump({"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "dataset_sha": "aad2b002cd74147236ee6fb4fd7e2bcf28955c3c", "summary": sm, "cases": res}, open(out,"w"), indent=1)
