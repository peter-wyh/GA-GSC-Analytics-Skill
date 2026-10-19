#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GA4+GSC 组合报告取数管道（多站通用）。

用法:
    python3 ga-gsc-report.py                     # config.default_site 站，近 28 天
    python3 ga-gsc-report.py --days 7
    python3 ga-gsc-report.py --site site-b

配置三层优先级: 命令行/env > config.json > 内置默认
    config.json  (gitignored)  站点→GSC资源/GA4属性/输出目录 + 凭据路径
    环境变量                    LH_SITE / GA4_PROPERTY_ID / OUT_DIR / GSC_CREDS / GA4_CREDS
    模板                        config.example.json（复制为 config.json 填真值）

依赖: 仅 openssl + python3 标准库（JWT 手工签名，免 google-auth）。
授权前提:
    GSC: SA 已加为对应 GSC 资源用户
    GA4: SA 已加为对应属性 Viewer，且 GCP 项目已启用 analyticsadmin + analyticsdata
"""
import json, sys, time, base64, subprocess, tempfile, os, argparse
import urllib.request, urllib.parse

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    """读 config.json（不存在则空配置，全部回落 env/内置默认）。"""
    p = os.path.join(SKILL_DIR, "config.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  config.json 解析失败（{e}），忽略之，回落环境变量")
    return {}


CFG = load_config()


def site_conf(site_name):
    """取站点配置 dict；env 覆盖 config。"""
    sc = (CFG.get("sites") or {}).get(site_name, {})
    cred_default = os.environ.get("GSC_CREDS") or os.environ.get("GA4_CREDS") \
        or CFG.get("creds", {}).get("gsc_creds_path") or CFG.get("creds", {}).get("ga4_creds_path") or ""
    return {
        "site": os.environ.get("LH_SITE") or sc.get("gsc_site", "sc-domain:example.com"),
        "property_id": os.environ.get("GA4_PROPERTY_ID") or sc.get("ga4_property_id", ""),
        "out_dir": os.environ.get("OUT_DIR") or sc.get("out_dir", "~/reports/ga-gsc-data"),
        "gsc_creds": os.environ.get("GSC_CREDS") or CFG.get("creds", {}).get("gsc_creds_path", "") or cred_default,
        "ga4_creds": os.environ.get("GA4_CREDS") or CFG.get("creds", {}).get("ga4_creds_path", "") or cred_default,
    }


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def get_token(scope: str, creds_path: str) -> str:
    if not creds_path:
        sys.exit("✋ 未提供凭据路径：请在 config.json creds.* 填路径，或设 GSC_CREDS/GA4_CREDS 环境变量")
    creds = json.load(open(os.path.expanduser(creds_path)))
    now = int(time.time())
    header = b64u(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = b64u(json.dumps({
        "iss": creds["client_email"], "scope": scope,
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now, "exp": now + 3600,
    }).encode())
    signing = (header + '.' + claims).encode()
    with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as f:
        f.write(creds["private_key"]); pk = f.name
    try:
        sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", pk],
                             input=signing, capture_output=True, check=True).stdout
    finally:
        os.unlink(pk)
    jwt = header + '.' + claims + '.' + b64u(sig)
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    return json.load(urllib.request.urlopen(req, timeout=30))["access_token"]


def api(url: str, token: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", "Bearer " + token)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        return json.load(urllib.request.urlopen(req, timeout=60)), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode('utf8','replace')[:200]}"


def norm_path(u: str) -> str:
    """URL/landingPagePath 归一为可 join 的路径。"""
    p = urllib.parse.urlparse(u if u.startswith('/') is False else 'https://x' + u).path
    return p.rstrip('/') or '/'


def fetch_gsc(token, days, site):
    end, start = time.strftime("%Y-%m-%d"), time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    url = ("https://searchconsole.googleapis.com/webmasters/v3/sites/%s/searchAnalytics/query"
           % urllib.parse.quote(site, safe=":"))
    rows = []
    for dim, name in [("page", "pages"), ("query", "queries"), ("page,query", "pairs")]:
        payload = {"startDate": start, "endDate": end, "dimensions": dim.split(","), "rowLimit": 500}
        data, err = api(url + "", token, payload)
        if err:
            return None, f"GSC {name} {err}"
        rows.append((name, data.get("rows", [])))
    return rows, None


def find_ga4_property(token):
    """Admin API v1beta 枚举账号→属性，按 measurementId 匹配（property.id 数字、measurementId 在属性列表接口不返回，走 accountSummaries 一次拉全）。"""
    data, err = api("https://analyticsadmin.googleapis.com/v1beta/accountSummaries?pageSize=200", token)
    if err or not isinstance(data, dict):
        return None, f"accountSummaries {err or 'empty response'}"
    matched = []
    for acc in data.get("accountSummaries", []):
        for p in acc.get("propertySummaries", []):
            # propertySummaries[].property = "properties/123", displayName 存在
            matched.append({"account": acc["displayName"], "property": p["property"],
                            "name": p.get("displayName", "")})
    if not matched:
        return None, "账号下无 GA4 property（SA 未加为 Viewer 时看不到）"
    return matched, None


def fetch_ga4(token, days, property_id):
    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
    payload = {
        "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "pagePath"}],
        "metrics": [{"name": "sessions"}, {"name": "engagedSessions"},
                    {"name": "eventCount"}, {"name": "keyEvents"}],
        "limit": 500,
    }
    data, err = api(url, token, payload)
    if err:
        return None, f"GA4 runReport {err}"
    return data.get("rows", []), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--site", default=CFG.get("default_site", ""),
                    help="config.json sites.<name> 里的站名，见 config.example.json")
    args = ap.parse_args()
    sc = site_conf(args.site)
    SITE, OUT_DIR = sc["site"], os.path.expanduser(sc["out_dir"])
    report = {"generated": time.strftime("%Y-%m-%d %H:%M"), "days": args.days, "site": SITE}

    # GSC
    try:
        tok_gsc = get_token("https://www.googleapis.com/auth/webmasters", sc["gsc_creds"])
        gsc, err = fetch_gsc(tok_gsc, args.days, SITE)
    except Exception as e:
        gsc, err = None, str(e)
    if err:
        print(f"⚠️  GSC 未就绪: {err}")
        report["gsc_error"] = err
    elif gsc:
        gsc_dict = {name: rows for name, rows in gsc}
        report["gsc"] = gsc_dict
        for name, rows in gsc:
            print(f"GSC {name}: {len(rows)} rows")
        tot = {k: sum(r.get(k, 0) for r in gsc_dict["pages"]) for k in ("clicks", "impressions")}
        print(f"GSC 汇总: clicks={tot['clicks']} impressions={tot['impressions']}")

    # GA4（凭据可独立：config creds.ga4_creds_path / GA4_CREDS env）
    try:
        tok_ga = get_token("https://www.googleapis.com/auth/analytics.readonly", sc["ga4_creds"])
        props, perr = find_ga4_property(tok_ga)
    except Exception as e:
        props, perr = None, str(e)
    pid = sc["property_id"]
    if not pid and props:
        cands = [p["property"].split("/")[1] for p in props]
        if len(cands) == 1:
            pid = cands[0]
        elif cands:
            print("⚠️  多个 GA4 property，请设置 GA4_PROPERTY_ID:", [(p["name"], p["property"]) for p in props])
    if pid:
        rows, err = fetch_ga4(tok_ga, args.days, pid)
        if err:
            print(f"⚠️  GA4 未就绪: {err}"); report["ga4_error"] = err
        else:
            report["ga4_property"] = pid
            report["ga4_pages"] = rows
            print(f"GA4 pages: {len(rows)} rows")
    else:
        msg = perr or "property 未发现（SA 是否已加为 Viewer？）"
        print(f"⚠️  GA4 未就绪: {msg}"); report["ga4_error"] = msg

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"raw-{time.strftime('%Y%m%d')}.json")
    with open(out, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"\n原始数据: {out}")
    ok = "gsc" in report and "ga4_pages" in report
    print("双源就绪，可出组合报告" if ok else "存在未授权数据源（见上），授权后重跑即出完整报告")


if __name__ == "__main__":
    main()
