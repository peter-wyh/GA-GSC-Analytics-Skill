#!/usr/bin/env python3
"""GSC 词簇聚合分析：簇级曝光/点击/CTR/位次 + 机会词表
用法: python3 gsc-cluster.py <raw.json> [--host yoursite.com]
簇规则按站而异，cluster() 里改；默认示例五簇 + 通用兜底簇。
"""
import json, sys
from collections import defaultdict

raw_path = sys.argv[1]
host = "yoursite.com"
for i, a in enumerate(sys.argv):
    if a == "--host" and i + 1 < len(sys.argv):
        host = sys.argv[i + 1]

d = json.load(open(raw_path))
gsc = d.get("gsc", d)  # 兼容两种 raw 结构：{gsc:{...}} 或裸四维
pages, queries, pairs = gsc.get("pages", []), gsc.get("queries", []), gsc.get("pairs", [])
trend = gsc.get("trend", [])

tot_i = sum(r["impressions"] for r in pages)
tot_c = sum(r["clicks"] for r in pages)
ctr = tot_c / tot_i * 100 if tot_i else 0
print(f"窗口汇总: {tot_i}imp {tot_c}ck CTR={ctr:.2f}%  {len(pages)}页 {len(queries)}词")

if trend:
    trend = sorted(trend, key=lambda r: r["keys"][0])
    print("\n日趋势(尾10):")
    for r in trend[-10:]:
        print(f"  {r['keys'][0]} {r['impressions']:>4}imp {r['clicks']:>2}ck")

# ---- 簇规则：按站改这里 ----
def cluster(path_or_q):
    u = path_or_q.replace(f"https://{host}", "")
    if "generator" in u: return "generator工具页"
    if "speech" in u: return "speech生成器"
    if "vow" in u and "renewal" not in u: return "vow风格页"
    if "/blog/" in u: return "blog"
    if "list" in u or "vows/" in u: return "vow长尾库"
    return "其他"

agg = defaultdict(lambda: {"imp": 0, "ck": 0})
for r in pages:
    c = cluster(r["keys"][0])
    agg[c]["imp"] += r["impressions"]; agg[c]["ck"] += r["clicks"]
print("\n页面簇聚合:")
for c, v in sorted(agg.items(), key=lambda kv: -kv[1]["imp"]):
    print(f"  {c:<14} {v['imp']:>5}imp {v['ck']:>3}ck CTR={v['ck']/v['imp']*100 if v['imp'] else 0:.1f}%")

# ---- 机会词表：位次好(≤15) 曝光≥5 CTR 低(<2%) ----
print("\n机会词 (pos≤15 & imp≥5 & CTR<2%):")
opp = [r for r in queries if r["clicks"] / r["impressions"] < 0.02
       and r["impressions"] >= 5 and r["position"] <= 15]
for r in sorted(opp, key=lambda r: -r["impressions"])[:15]:
    print(f"  {r['keys'][0]:<44} {r['impressions']:>4}imp pos={r['position']:.1f} ck={r['clicks']}")

# ---- 位次好零点击（P0 直给） ----
print("\n位次好零点击 (pos≤10 & imp≥8 & ck=0):")
for r in sorted([r for r in queries if r["position"] <= 10 and r["impressions"] >= 8 and r["clicks"] == 0],
                key=lambda r: -r["impressions"])[:10]:
    print(f"  {r['keys'][0]:<44} {r['impressions']:>4}imp pos={r['position']:.1f}")
