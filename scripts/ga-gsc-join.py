#!/usr/bin/env python3
"""GA+GSC 组合分析：join 页面路径，输出漏斗表 + 异常诊断"""
import json, sys
from collections import defaultdict
from urllib.parse import urlparse

raw_path = sys.argv[1]
site_host = sys.argv[2]
d = json.load(open(raw_path))

gsc_pages = d.get("gsc", {}).get("pages", [])
ga_rows = d.get("ga4_pages", [])

def gp(u):
    p = urlparse(u).path if u.startswith("http") else urlparse("https://x" + u if not u.startswith("/") else "https://x" + u).path
    return p.rstrip("/") or "/"

# GA4 按 pagePath 聚合（GA4 行格式：dimensionValues[i].value 按请求顺序 = pagePath）
MET_KEYS = ["sessions", "engagedSessions", "eventCount", "keyEvents"]
ga = {}
for r in ga_rows:
    p = gp(r.get("dimensionValues", [{}])[0].get("value", "/"))
    vals = [int(x.get("value", 0)) for x in r.get("metricValues", [])]
    mets = dict(zip(MET_KEYS, vals + [0] * (len(MET_KEYS) - len(vals))))
    cur = ga.setdefault(p, {"sessions": 0, "engaged": 0, "events": 0, "key": 0})
    cur["sessions"] += mets["sessions"]
    cur["engaged"] += mets["engagedSessions"]
    cur["events"] += mets["eventCount"]
    cur["key"] += mets["keyEvents"]

gsc = {}
for r in gsc_pages:
    p = gp(r["keys"][0])
    cur = gsc.setdefault(p, {"imp": 0, "ck": 0, "pos_sum": 0.0, "n": 0})
    cur["imp"] += r["impressions"]; cur["ck"] += r["clicks"]
    cur["pos_sum"] += r.get("position", 0); cur["n"] += 1

paths = sorted(set(gsc) | set(ga), key=lambda p: -(gsc.get(p, {}).get("imp", 0)))
print(f"{'路径':<44}{'imp':>5}{'ck':>3}{'pos':>6}{'sess':>6}{'enga':>6}{'evt':>6}{'key':>4}")
diag = {"搜索可见无会话": [], "有点击无转化": [], "有会话无曝光": [], "有keyE无点击": []}
for p in paths:
    g = gsc.get(p, {}); a = ga.get(p, {})
    imp, ck, pos = g.get("imp", 0), g.get("ck", 0), (g["pos_sum"]/g["n"] if g.get("n") else 0)
    s, en, ev, ke = a.get("sessions", 0), a.get("engaged", 0), a.get("events", 0), a.get("key", 0)
    print(f"{p[:42]:<44}{imp:>5}{ck:>3}{pos:>6.1f}{s:>6}{en:>6}{ev:>6}{ke:>4}")
    if imp >= 2 and s == 0: diag["搜索可见无会话"].append((p, imp, round(pos,1)))
    if ck >= 1 and ke == 0: diag["有点击无转化"].append((p, ck, ke))
    if s > 0 and imp == 0: diag["有会话无曝光"].append((p, s, ev))
    if ke > 0 and ck == 0: diag["有keyE无点击"].append((p, ke, ck))

print("\n诊断:")
for k, v in diag.items():
    if v:
        print(f"  {k}: {len(v)} 页")
        for item in v[:5]:
            print(f"    {item}")

# GA4 事件总览（eventCount 维度没拉，用页面级 events 汇总代替）
tot_s = sum(v["sessions"] for v in ga.values())
tot_ev = sum(v["events"] for v in ga.values())
tot_ke = sum(v["key"] for v in ga.values())
print(f"\nGA4 汇总: sessions={tot_s} events={tot_ev} keyEvents={tot_ke}")
print(f"GSC 汇总: imp={sum(g['imp'] for g in gsc.values())} ck={sum(g['ck'] for g in gsc.values())}")
