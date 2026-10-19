---
name: ga4-analytics
description: Pull GA4/GSC data via service account (JWT hand-signed with openssl, no google-auth) — three access gates, probe script, failure-signature table (403 not-enabled / wrong GCP project / sibling-API confusion), plus the universal GA+GSC combined report pipeline (fetch + page-path join + four-quadrant diagnosis). Use for any site's GA4/GSC data wiring, reports, conversion verification, or listing properties visible to the SA.
---

# GA4 Analytics Data Access

Class：用服务号程序化拉 GA4 数据（日报/周报/转化验证），Google 侧流量层。与 cloudflare-analytics（CF GraphQL）互补：CF 看 CDN/爬虫侧，本 skill 看用户行为侧。

## 触发场景
- 给站点接 GA4 数据管道（仿 fb-gsc-daily.py 的日报形态）
- 报表/转化验证前先确认 API 可达
- 盘点服务号名下有哪些 property

## 三道门模型（按序验证）

0. **GSC 侧先探库存（零成本）**：拉新站 GSC 数据前先 `GET https://www.googleapis.com/webmasters/v3/sites`（webmasters scope）——一次列出 SA 名下全部站点+权限级别（siteOwner/siteFullUser/…）。1018 实锤：example-vowsite.com 早已是 siteFullUser，免去一轮用户授权往返。**先跑 sites 列表再决定要不要请用户去 Search Console 加人**。
1. **Token（SA + JWT）**：服务账号凭据路径不硬编码——优先级 `GA_CREDS/GSC_CREDS env > config.json creds.*`（模板见 config.example.json）。scope=`https://www.googleapis.com/auth/analytics.readonly`，RS256 用 `openssl dgst -sha256 -sign` 手签。零 google-auth 依赖。凭据 JSON（SA key 文件）永不入 skill 目录。
2. **API 启用（用户侧控制台）**：项目里须同时启用 `analyticsadmin.googleapis.com` **和** `analyticsdata.googleapis.com`。SA 自助启用走不通（serviceusage enable → 403 Permission denied，无 service.management 权限）。深链**必须带 `?project=<项目ID>`（ID 形如 my-project-123，在 GCP 项目选择器每项下方灰色小字），带纯数字项目编号 console 可能不识别而静默落到用户默认项目**。
3. **属性授权（用户侧 GA4 后台）**：管理 → 属性访问管理 → 加 SA 邮箱为**查看者**。未授权时 accountSummaries 200 但空。账号级「账号访问权限管理」加人也等效且更省事（覆盖账号下全部属性）。

## 失败签名速查

| 症状 | 真因 | 动作 |
|---|---|---|
| 403 "has not been used in project … before or is disabled" | API 未启用，或启到了别的项目 | 用户侧重开锁定深链，**先核对右上角项目名** |
| API 端点返回 404 HTML | POST 打了 GET-only 端点（accountSummaries 只收 GET）——**不是**「已启用」的证据 | 换正规 GET 复测再下结论 |
| serviceusage enable 403 | SA 无自助启用权限，此路不通 | 转用户侧，别反复试 |
| 用户称「已启用」但复测仍 403 SERVICE_DISABLED | **项目身份错位**：项目显示名 ≠ 项目 ID；用户点在了显示名项目或默认项目上 | 让用户查项目选择器里灰色小字 ID，找 ID=<老项目ID> 的；深链用 `?project=<项目ID>`（ID 而非编号） |
| cloudresourcemanager projects 列表 403 | SA 无浏览权限（正常，非故障） | 不影响已启用 API 的调用，勿当授权失败处理 |
| accountSummaries 200 但空 | 门 2 过了、门 3 未授权 | 用户侧属性 Viewer 授权 |
| 刚启用仍 403 | 传播延迟（分钟级） | sleep 60 复测一次 |
| Data API 报 400 invalid property | 门 2 已通（占位 property id 试拉时的正常回包） | 换真 property id 取数 |

## Pitfalls
- **控制台三胞胎 API**：Google Analytics API（旧 UA）/ Google Analytics Admin API / Google Analytics Data API——要的是后两个。用户点错或启用到别的项目是最常见失败模式，复测仍 403 时优先怀疑这两点，不要归咎传播延迟。
- **显示名 vs 项目 ID 错位（1018 最大卡点）**：用户项目选择器里看到的是显示名（本案例：以站名命名的多个项目），而 SA 归属项目 ID=<老项目ID>（编号 <GCP项目编号>）——显示名列表里找不到 SA 归属项目 ≠ 没有该项目。正解：让用户看项目选择器每项下方的灰色小字（真 ID），或直接给 `?project=<项目ID>` 的 enable 深链。用户说「没有这个项目」时先教 ID 辨认法再下结论。
- **重复验收循环要设止损**：用户两次称「已完成」复测均 403 时，停止盲跑验证——转为教用户自查「已启用的 API」列表（须出现 Google Analytics Admin API + Google Analytics Data API 两行），并备好 Plan B（在新项目建独立 SA，脚本走 GA4_CREDS 双凭据 env 分离）。lh-ga-gsc-report.py 已支持 GA4_CREDS 环境变量。
- **http.client 批量探测**：复用 HTTPSConnection 必须 `r.read()` 读完整个 body；只读前 N 字节后续请求全挂 `Request-sent`。稳妥做法=每 URL 新建连接。URL 健康批量检查（200/308 判别）同样适用。
- readonly scope 足够取数；不要为取数申请更高权限。
- 「请求编入索引」是 GSC 体系的事，GA4 无对应操作，别混。
- **keyEvents 恒 0 先查计量层再谈转化（1019 两站同病）**：GA4 默认不标任何关键事件——两站首拉均有会话有事件流但 keyEvents=0，这不是「转化为零」而是没在后台把生成完成 / 表单提交类事件标为 key event。分析报告遇 keyEvents=0 的正确输出=提示用户去 GA4 后台标关键事件，勿下转化流失结论。
- **多站连跑防 OUT_DIR 互覆**：raw JSON 落点默认按 LH_SITE 自动派生子目录（1019 修复）；显式传 OUT_DIR 且两站共用同一路径时会互相覆盖（wv 曾覆盖 lh），连跑多站时 OUT_DIR 也要逐站换。
- **skill 公开化（推 GitHub）三步法（1019 实录）**：①配置解耦——站点表+凭据路径抽到 config.json（.gitignore 排除）+ config.example.json 模板占位，脚本改三层读取（CLI/env > config），凭据 JSON 本体永不进 skill 目录；②泄露审计——分层判定：硬凭据（私钥/AIza/密码/token 值）=0 容忍；标识符类（SA 邮箱/项目编号/本机路径/property ID/G- measurement ID）须脱敏或挪 config，其中功能性标识（排障指引依赖的 SA 邮箱）留 config 不删；③desensitize.py 正则批替后必须 grep 终验。**重构脚本后先跑真调用回归（T1 默认站/T2 --site 切站/T3 env 覆盖）再谈完成**——1019 重构把模块级 SITE 改成 main() 局部变量时漏改 fetch_gsc 的引用，首跑 `name 'SITE' is not defined`，靠三条路径回归抓回。grep 扫残留别漏 references/ 的案例叙述与文件名本身（文件名带站名也是暴露面，通用化或接受由用户拍板）。
- **泄露分层的第一敏感项是经营数据而非标识符（1019 B-refined 裁定）**：G-ID/property ID 本就嵌在网站 HTML 半公开，清了只是干净；真正不能出库的是**绑域名的经营数字**（曝光/点击/CTR/会话数/逐页弱点清单）——那是把流量规模、SEO 短板、转化漏斗完整画给竞品。处置：带日期事故实录与基线数字全挪 `references/private/`（.gitignore 排除 + README 索引收容基线），公开面=纯方法论+通用工具，一个真实数字不出。
- **脱敏器自身不得携带真值**：desensitize.py 模式表里写真实 SA 邮箱/项目编号/域名 = 把要脱敏的字符串原样运进公开库（1019 终验实锤）。正解架构：真值模式表放 config.json 的 `desensitize_patterns` 键（gitignored），脚本只内置通用形状规则（G-[A-Z0-9]{10}、9-10 位数字 property id 形态），运行时合并两层、长串优先替换，并跳过 private/、config、自身。
- **终验要扫 __pycache__**：改完脚本后旧 .pyc 字节码仍保着清理前的真实串（grep 报 Binary file matches）；虽被 gitignore 排除，清掉再验才干净。

## Scripts
- `scripts/ga4-probe.py` —— 一键探测三道门：铸 token → GET accountSummaries 列属性 → Data API runReport 试拉。接线前先跑它，输出各门状态与结论。
- `scripts/ga-gsc-report.py` —— **通用取数管道（1016 建 / 1019 通用化+配置解耦）**：GSC（pages/queries/pairs/trend）+ GA4（每页 sessions/engagedSessions/eventCount/keyEvents）一次拉全，JSON 落本地。接口三层优先级 `CLI --site > env（LH_SITE/GA4_PROPERTY_ID/OUT_DIR/GSC_CREDS/GA4_CREDS）> config.json`；`--site <名>` 取 config sites.<名> 的 gsc_site/ga4_property_id/out_dir。config.json 被 .gitignore 排除（模板=config.example.json，凭据 JSON 永不入 skill 目录）。多属性且未指定时会列出候选。
- `scripts/ga-gsc-join.py` —— join 分析：`python3 ga-gsc-join.py <raw.json> <host>`，按页面路径拼 GSC 曝光/点击/位次 × GA4 会话/互动/事件/关键事件，输出漏斗表+四象限诊断（搜索可见无会话/有点击无转化/有会话无曝光/CTR 病灶）。**坑：GA4 行 dimensionValues/metricValues 无 name 字段，按请求顺序取值**。

- `scripts/gsc-cluster.py` —— GSC 词簇聚合：`python3 gsc-cluster.py <raw.json> --host <域名>`，簇级 imp/ck/CTR（簇规则 cluster() 按站改）+ 机会词表（pos≤15 & imp≥5 & CTR<2%）+ 位次好零点击 P0 直给（pos≤10 & imp≥8）。实测可复现报告的簇结构与机会词表（实录见 references/private/）。

### 站点配置（不入库）
各站的 GSC 资源 / GA4 property ID / 输出目录 / 凭据路径全部在 `config.json`（gitignored；模板=`config.example.json`）。跑 `scripts/ga4-probe.py` 可自动列出当前 SA 可见的全部属性及其 ID，照抄进 config 即可。同名站多 property 时注意：空的老属性返回 0 行，极易误判「没数据/没权限」——候选属性各拉一次对比行数。

## References
- `references/publish-checklist.md` —— **skill 公开化（推 GitHub/团队库）清单与脱敏配方**：配置解耦三层法、泄露分层判定表、desensitize.py 用法、回归三测、残留 grep 终验。
- `references/ga-gsc-reporting.md` —— **方法论主文件（1019 随脚本迁入）**：管道事实/换站三 env/四属性速查/API 启用卡点（显示名≠项目ID）/Join 四象限逻辑/报告固定结构/基线数据管理（基线与实录不入公开库）。
- `references/private/` —— **本机私有实录目录（.gitignore 排除，不随库分发）**：各站带日期的事故实录（接线排障时间线 / GSC 全量分析含 P0-P2 清单 / join 脚本踩坑修复）与两站基线数字。公开版只留通用方法论；引用具体数字回此目录或 Obsidian 报告查。
