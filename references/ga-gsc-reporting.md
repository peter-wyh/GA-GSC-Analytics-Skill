# GA4+GSC 组合报告 · 方法论与阈值（1016 首版 / 1019 双源全通版；本文件随脚本归位 ga4-analytics）

## 管道事实（1019 定型，多站通用）
- 取数脚本：`scripts/ga-gsc-report.py`（纯 stdlib，JWT 手工 RS256 签名免 google-auth；openssl 签名；GA4_CREDS env 支持双凭据分离）
- join+四象限诊断：`scripts/ga-gsc-join.py <raw.json>`（漏斗表 + 自动诊断 + keyEvents=0 计量警告），本文件「Join 与诊断」节即其逻辑说明
- 词簇聚合：`scripts/gsc-cluster.py <raw.json> --host <域名>`（簇级 imp/ck/CTR + 机会词表 + 位次好零点击 P0 直给；簇规则在脚本 cluster() 里按站改）
- 授权模型：**同一枚服务账号** SA_EMAIL（config.json 对应凭据的 client_email）（密钥 `config.json creds.*_creds_path 所指的 SA key 文件`）
  - GSC：Search Console 资源用户（webmasters scope）。**跨站先探测**：`GET webmasters/v3/sites` 一条命令列出 SA 可访问全部站点+权限级（1019 实测：一枚 SA 可同时是多站的 siteFullUser / siteOwner）——别假设要逐站授权，先查列表。
  - GA4：属性 Viewer + GCP 项目（ID=<老项目ID>，编号 <GCP项目编号>）须开 analyticsadmin + analyticsdata 两个 API。
- scope：GSC=webmasters，GA4=analytics.readonly；token 各签各的
- GA4 property 发现：analyticsadmin `accountSummaries`（一次拉全）→ properties/<id>；多 property 时须 env GA4_PROPERTY_ID 指定
- 数据落点：Obsidian `关键词需求分析/{site-tag}/ga-gsc-data/raw-YYYYMMDD.json`（pages/queries/pairs/trend + ga4_pages）
- join+四象限诊断：`scripts/ga-gsc-join.py <raw.json>`（漏斗表 + 自动诊断 + keyEvents=0 计量警告），本文件「Join 与诊断」节即其逻辑说明
- GSC 四维拉法：dimensions=["page"] / ["query"] / ["page,query"] / ["date"] 各一次，rowLimit 500-1000

## 属性盘点（真实清单不入公开库）
各站 property id 只记在 config.json（gitignored）；用 `scripts/ga4-probe.py` 自动列出 SA 可见的全部属性照抄。本机盘点与「真身 / 空老属性」标注见 references/private/。

坑：同名站有多个 property 时选错空属性 = GA4 返回 0 行，极易误判「没数据/没权限」——先跑两个候选属性各拉一次对比行数。

## GA4 API 启用卡点（1018 卡 4 轮的根因）
**项目显示名 ≠ 项目 ID**：用户项目选择器里显示的是几个以站名命名的项目（显示名），而 SA 所属项目 ID=<老项目ID>（独立老项目，不在显示名列表里）。用户按名字点「启用」永远点在错项目上，报错一直 403 SERVICE_DISABLED。
解法三件：
1. 深链强制定位：`https://console.developers.google.com/apis/api/analyticsadmin.googleapis.com/enable?project=<项目ID>`（用项目 ID 不用编号）；analyticsdata 同款
2. 辨认法：项目选择器里每个项目名下灰色小字 = 项目 ID，找 ID=<老项目ID> 的
3. 判别：API overview 页有蓝色「启用」按钮=没开（点它）；直接显示配额图表=已开
辅助探测：SA 自助 `serviceusage services/{svc}:enable` 返回 403（无 Owner 权限）= 只能人工；GET service state 也 403（连读权限都没有）= 状态查询不可行，直接跑 accountSummaries 探最省事。

## Join 与诊断（1019 四象限定型）
norm_path：URL 或 pagePath → path，rstrip('/')，空为 '/'。
**GA4 行格式坑：dimensionValues[i].value / metricValues[i].value 没有 name 字段，必须按请求时 dimensions/metrics 顺序按序取值**（pyright 不报、运行时 KeyError 'name'）。

join 诊断四象限（join key = 归一路径）：
1. **搜索可见无会话**（imp≥2 且 sessions=0）：收录+排名有，人没来 → title/位次深
2. **有点击无转化**（ck≥1 且 keyEvents=0）：先查 keyEvents 计量是否配置，再看承接
3. **有会话无曝光**（sessions>0 且 imp=0）：收录在 SERP 未给量（长尾资产待激活）或非搜索渠道（直达/社区）
4. **有 keyEvents 无点击**：转化来自非搜索，SEO 增量机会
标准分析动作（1016 版保留）：高曝光低 CTR（≥20imp 且 pos≤15 且 CTR<2%→title 重写）；新页收录监控（sitemap vs GSC）；词机会（实测词×词谱系→下批建页）。

**keyEvents=0 必查项（1019 两站同病）**：GA4 后台没把转化事件标「关键事件」时 keyEvents 恒 0——组合报告第一步先确认计量层（各站的转化事件，如生成完成 / 表单提交类），否则转化侧永远空白，报告须注明此为计量缺失非业务零。

## 报告固定结构（GA-GSC组合报告-MMDD.md）
一、总览（曝光/点击/CTR/会话/事件/关键事件+阶段定位语）→ 二、漏斗 join 表（imp/ck/pos/sess/enga/evt 一行打通）→ 三、诊断四象限 → 四、行动项表（类型+谁做）。量小阶段（新站扩容后）报告价值点=收录监控与词信号，须写明避免误读为流量报告。

## 基线数据管理
真实基线数字（流量 / CTR / 会话 / 逐页弱点清单）**不入公开库**——存 references/private/ 与 Obsidian 报告目录；公开版示例只用示意值。资产清单同理：property 表只在 config.json，方法论文档里用占位符。

## 坑
- GSC 数据 2-3 天延迟，当日新上线页不会出现
- 403 "API not been used in project" = GCP 项目级开关问题，不是权限问题（但 1018 教训：先确认点在了**哪个项目**——显示名≠ID）
- GA4 runReport 的 dateRanges 用 `28daysAgo`/`today` 相对窗口；GSC 用绝对日期，两端窗口口径对齐时注意 GSC 有 2-3 天尾巴缺失
- `git apply --check` 拆 patch 时见 SKILL.md 拆 commit 条目（只打 index，别打 worktree）
