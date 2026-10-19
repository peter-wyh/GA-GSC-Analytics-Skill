#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill 公开化脱敏：批替私有标识为通用表述（推 GitHub 前跑一次）。

真实模式表在本机 config.json 的 desensitize_patterns（gitignored）——真值不入公开库；
本脚本只内置通用形状规则。两层合并后按「长串优先」应用。
"""
import re, json, pathlib

BASE = pathlib.Path(__file__).parent.parent

# 通用形状规则（与站点无关，可安全入库）
SHAPE_RULES = [
    # GA4 measurement ID 任意形态
    (r"G-[A-Z0-9]{10}", "G-XXXXXXXXXX"),
    # 纯数字 property id（9-10 位，JSON/表格里裸出现时）
    (r"\b5\d{8}\b", "<property_id>"),
]

# 私有真值 → 通用表述：config.json desensitize_patterns（本机文件，不入库）
cfg_path = BASE / "config.json"
patterns = []
if cfg_path.exists():
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    for k, v in cfg.get("desensitize_patterns", {}).items():
        if k.startswith("_"):
            continue
        patterns.append((re.escape(k), v))
# 长串优先，防短串先替换破坏长串锚点
patterns.sort(key=lambda kv: -len(kv[0]))
patterns += SHAPE_RULES

# 处理面：全部 .md（含根）与 scripts/*.py，排除私有实录/config/自身
targets = [p for p in BASE.rglob("*.md")] + list((BASE / "scripts").glob("*.py"))
skip = lambda p: ("config.json" in p.name or ".git" in p.parts
                  or "private" in p.parts or p.name == "desensitize.py"
                  or "__pycache__" in p.parts)
changed = []
for p in targets:
    if skip(p):
        continue
    t = p.read_text(encoding="utf-8")
    orig = t
    for pat, rep in patterns:
        t = re.sub(pat, rep, t)
    if t != orig:
        p.write_text(t, encoding="utf-8")
        changed.append(str(p.relative_to(BASE)))

print("脱敏完成，改动文件：" if changed else "无匹配项，未改任何文件")
for c in changed:
    print(" -", c)
print("\n终验建议：grep -rn -iE '你的站名|SA 邮箱|本机路径' " + str(BASE))
