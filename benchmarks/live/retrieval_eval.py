#!/usr/bin/env python3
"""RETRIEVAL-ONLY diagnostic on official datasets (NOT the official LLM-judged score).
Usage: retrieval_eval.py BUNDLE DATASET_CSV NAME N SEED OUT.json [--extract]
Metric: normalized gold-answer containment in (a) top-5 snippets+titles, (b) + extracted text of top-3 pages.
Env failures (PROVIDER_BLOCKED/transport) are reported separately, never scored as 0."""
import csv, json, random, re, sys, time, unicodedata, datetime, os
sys.path.insert(0, os.path.dirname(__file__))
from common import load_tools, call
csv.field_size_limit(10**9)
bundle, path, name, n, seed, out = sys.argv[1:7]; extract = "--extract" in sys.argv
norm = lambda s: re.sub(r"[^a-z0-9 ]+", " ", unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().lower()).split()
def contains(hay, gold):
    h, g = " ".join(norm(hay)), " ".join(norm(gold)); return bool(g) and f" {g} " in f" {h} "
rows = list(csv.DictReader(open(path))); rnd = random.Random(int(seed)); sample = rnd.sample(rows, int(n))
tools = load_tools(bundle); res = []
for i, r in enumerate(sample):
    q, gold = r["problem"], r["answer"]
    o, ms = call(tools, "goat_search", {"query": q, "max_results": 5})
    code = (o.get("error") or {}).get("code"); hits = o.get("results", []) if o.get("ok") else []
    snip = " ".join(h["title"]+" "+h["snippet"] for h in hits)
    rec = {"i": i, "query": q, "gold": gold, "search_ms": round(ms,1), "ok": o.get("ok"), "error_code": code,
           "n_results": len(hits), "urls": [h["url"] for h in hits], "gold_in_snippets": contains(snip, gold) if o.get("ok") else None}
    if extract and o.get("ok"):
        txt = snip; t0 = time.perf_counter(); ex = []
        for h in hits[:3]:
            e, ems = call(tools, "goat_extract", {"url": h["url"]}); ex.append({"url": h["url"], "ok": e.get("ok"), "code": (e.get("error") or {}).get("code"), "ms": round(ems,1)})
            if e.get("ok"): txt += " " + e.get("text","")
        rec["extract"] = ex; rec["gold_in_snippets_or_pages"] = contains(txt, gold)
    res.append(rec); print(i, code or "ok", rec["gold_in_snippets"], rec.get("gold_in_snippets_or_pages"), f"{ms:.0f}ms", q[:60], "|", gold[:30], flush=True)
    time.sleep(1.5)
valid = [x for x in res if x["ok"]]
sm = {"dataset": name, "n_requested": int(n), "seed": int(seed), "n_valid": len(valid), "n_provider_blocked": sum(x["error_code"]=="PROVIDER_BLOCKED" for x in res),
      "n_other_error": sum((not x["ok"]) and x["error_code"]!="PROVIDER_BLOCKED" for x in res),
      "snippet_recall": sum(x["gold_in_snippets"] for x in valid)/max(1,len(valid)),
      "empty_result_rate": sum(x["n_results"]==0 for x in valid)/max(1,len(valid))}
if extract: sm["page_recall"] = sum(x.get("gold_in_snippets_or_pages",False) for x in valid)/max(1,len(valid))
lat = sorted(x["search_ms"] for x in valid)
if lat: sm["search_p50_ms"] = lat[len(lat)//2]; sm["search_p95_ms"] = lat[min(len(lat)-1,int(len(lat)*.95))]
print(json.dumps(sm, indent=1))
json.dump({"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "summary": sm, "cases": res}, open(out,"w"), indent=1, ensure_ascii=False)
