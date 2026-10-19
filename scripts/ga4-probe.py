#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GA4 三道门一键探测：token → API 启用 → 属性可见性 → 试拉。

用法:
    python3 scripts/ga4-probe.py                     # 列出 SA 可见的全部 property
    python3 scripts/ga4-probe.py properties/123456   # 额外对该 property 试拉近7天 activeUsers

环境变量:
    GA_CREDS  凭据 JSON 路径（或 config.json creds.ga4_creds_path）

依赖: 仅 openssl + python3 标准库。
"""
import json, sys, time, base64, subprocess, tempfile, os
import urllib.request, urllib.parse
from datetime import date, timedelta

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cfg = {}
_p = os.path.join(SKILL_DIR, "config.json")
if os.path.exists(_p):
    try:
        _cfg = json.load(open(_p))
    except Exception:
        pass
CREDS_PATH = (os.environ.get("GA_CREDS")
              or os.environ.get("GA4_CREDS")
              or _cfg.get("creds", {}).get("ga4_creds_path", ""))

def get_token():
    creds = json.load(open(CREDS_PATH))
    b64u = lambda b: base64.urlsafe_b64encode(b).rstrip(b'=')
    now = int(time.time())
    header = b64u(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = b64u(json.dumps({
        "iss": creds["client_email"],
        "scope": "https://www.googleapis.com/auth/analytics.readonly",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now, "exp": now + 3600,
    }).encode())
    signing = header + b'.' + claims
    with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as f:
        f.write(creds["private_key"]); kp = f.name
    try:
        sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", kp],
                             input=signing, capture_output=True, check=True).stdout
    finally:
        os.unlink(kp)
    jwt = (signing + b'.' + b64u(sig)).decode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token",
        data=urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt}).encode())
    with urllib.request.urlopen(req) as r:
        return creds["client_email"], json.load(r)["access_token"]

def call(url, body=None, token=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw

def main():
    prop = sys.argv[1] if len(sys.argv) > 1 else None
    email, token = get_token()
    print(f"[门1 token] ✅ {email}")

    st, res = call("https://analyticsadmin.googleapis.com/v1beta/accountSummaries", token=token)
    if st == 403 and "is disabled" in json.dumps(res):
        print("[门2 API启用] ❌ 403 not-enabled —— 用户侧开深链(锁项目)后重跑本脚本")
        print("  admin:  https://console.developers.google.com/apis/api/analyticsadmin.googleapis.com/overview?project=<PROJECT_ID>")
        print("  data:   https://console.developers.google.com/apis/api/analyticsdata.googleapis.com/overview?project=<PROJECT_ID>")
        return
    if st != 200:
        print(f"[门2 API启用] ❌ HTTP{st}: {json.dumps(res)[:200]}")
        return
    print("[门2 API启用] ✅")

    props = [(p["property"], p.get("displayName", ""))
             for acc in res.get("accountSummaries", []) for p in acc.get("propertySummaries", [])]
    if not props:
        print("[门3 属性授权] ❌ 200 但空 —— GA4 后台把 SA 邮箱加为属性查看者")
        return
    print(f"[门3 属性授权] ✅ 可见 {len(props)} 个属性:")
    for pid, name in props:
        print(f"  {pid}  {name}")

    if prop:
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=6)
        st, res = call(
            f"https://analyticsdata.googleapis.com/v1beta/{prop}:runReport", body={
                "dateRanges": [{"start": start.isoformat(), "end": end.isoformat()}],
                "metrics": [{"name": "activeUsers"}, {"name": "sessions"}],
                "dimensions": [{"name": "date"}],
            }, token=token)
        if st == 200:
            rows = res.get("rows", [])
            print(f"[取数] ✅ 近7天 {len(rows)} 个数据日")
            for row in rows:
                print(f"  {row['dimensionValues'][0]['value']}  activeUsers={row['metricValues'][0]['value']}  sessions={row['metricValues'][1]['value']}")
        else:
            print(f"[取数] ❌ HTTP{st}: {json.dumps(res)[:200]}")

if __name__ == "__main__":
    main()
