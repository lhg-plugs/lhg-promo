<!-- About 简介（推送后填写到仓库 About 栏）：
小白也能做赚钱的促销：目标→档期→玩法→利润测算→执行→复盘一条龙 ｜ 一键安装：/plugin marketplace add lhg-plugs/lhg-promo
-->
<!-- topics（推送后打）：claude-code, claude-plugin, agent-skills, ecommerce, promotion, retail -->

# lhg-promo：促销策划专家

> **一句话介绍**：给 AI 助手装上"促销策划全流程"——定目标、排档期、设计玩法、算利润、列执行清单、做复盘，小白也能做出不亏本的促销方案。
>
> **一键安装**：在 Claude Code 里运行
> ```
> /plugin marketplace add lhg-plugs/lhg-promo
> /plugin install lhg-promo@lhg-plugs
> ```

## 它是什么

`lhg-promo` 是一个 Claude Code 插件（plugin 为主、skill 为辅）：

- **4 个命令**（小白入口）：`promo` 六步全流程一条龙，`promo-play` 玩法设计工作坊，`promo-calc` 利润测算（红线叫停），`promo-audit` 方案自查
- **4 个平台中立 skill**（方法论，可移植到豆包/Workbuddy 等 agent 平台）：目标与档期、玩法设计、利润测算、执行与复盘
- **2 个专家 agent**：促销策划专家、独立审查专家
- **2 个硬门 hooks**：commit 前促销方案审计拦截、写方案缺章节提醒（均可一键豁免）
- **42 条确定性审计规则**：纯 Python、零第三方依赖，查结构缺失、数字矛盾、玩法冲突、档期撞车、宣传合规

差异化：**先算账再开卖**（利润测算表+保本点+三档测算，红线直接叫停）、**玩法矛盾机器检查**（满减门槛 vs 客单价、叠加规则自相矛盾、活动价低于成本价，脚本直接报警）、**目标卡宪法**（主目标三选一锁定，后续加需求先对照目标卡）。

## 4 个命令用法

| 命令 | 作用 | 示例 |
|---|---|---|
| `/lhg-promo:promo` | 目标→档期→玩法→测算→执行→复盘，一条龙输出完整方案 | `/lhg-promo:promo "双11清仓尾货"` |
| `/lhg-promo:promo-play` | 玩法设计工作坊：选组合、写 6 要素规则、矛盾自查 | `/lhg-promo:promo-play "清仓" "80"` |
| `/lhg-promo:promo-calc` | 利润测算：三档测算+保本点，红线直接叫停 | `/lhg-promo:promo-calc 方案.md` |
| `/lhg-promo:promo-audit` | 42 条规则审计 + 人工评审清单 | `/lhg-promo:promo-audit 方案目录` |

## 自查说明

自查 = 确定性脚本（机器）+ 人工评审（人）：

1. 先跑 `scripts/audit/promo_audit.py`（42 条规则），零 LLM 成本；
2. 发现分三级：**blocker**（会亏本/违法/落不了地，commit 前 hook 会拦截）、**warning**（大概率是坑）、**nit**（洁癖项）；
3. 再按 `lhg-promo-exec` 第 5 步上线前检查清单过一遍脚本抓不到的（数字真实性、规则歧义、客服话术）。

blocker 清零才算做完；为清零改规则算作弊，不许。

## 目录结构

```
lhg-promo/
├── .claude-plugin/          # plugin.json（插件清单）+ marketplace.json（本仓即市场）
├── commands/                # 4 个命令：promo / promo-play / promo-calc / promo-audit
├── skills/                  # 4 个平台中立 skill（goal/play/profit/exec）
├── agents/                  # 2 个专家 agent（promo-planner / promo-auditor）
├── hooks/                   # 2 个硬门（commit 前审计拦截 / 缺章节提醒）+ 豁免说明
├── scripts/audit/           # 42 条确定性审计规则（零第三方依赖）
├── fixtures/                # 冒烟测试用例（坏/好对照）
├── smoke_test.py            # 一键冒烟测试
├── ATTRIBUTION.md           # 灵感来源与许可声明
└── LICENSE                  # MIT
```

## 什么时候用 / 什么时候不用（FAQ）

**什么时候用：**

- 你要做一次促销（清仓/拉新/冲 GMV），但不知道从哪下手时 → 用 `/lhg-promo:promo` 一条龙
- 你已经想好玩法，只想确认"会不会亏本"时 → 用 `/lhg-promo:promo-calc` 算一遍
- 方案写完了，怕有满减门槛高于客单价、叠加规则矛盾这类硬伤时 → 跑 `/lhg-promo:promo-audit`
- 你是电商/门店运营，想给团队立一套"促销上线前必须检查"的纪律时 → 它的 hooks 硬门开箱即用

**什么时候不用：**

- 你只是想发一张促销海报，不涉及定价和规则 → 本插件是"策划全家桶"，单张海报去找设计类插件
- 你的促销完全在线下、没有可数字化的方案文档 → 审计脚本扫的是方案文档，纯口头策划用不上脚本（但 skill 方法论照样可用）
- 你希望 AI 无条件按你的想法出方案、不接受"别做"的结论 → 它的红线叫停会让你烦（这是设计，不是 bug）

## lhg-plugs 插件矩阵

| 插件 | 一句话 | 安装 |
|---|---|---|
| [lhg-promo](https://github.com/lhg-plugs/lhg-promo) | 促销策划专家：目标→档期→玩法→利润测算→执行→复盘，小白也能做不亏本的促销 | `/plugin install lhg-promo@lhg-plugs` |
| *（后续插件在此追加，保持表格格式一致）* | | |

## 自检与反馈

本插件自带质检：每次使用后可跑 `python3 smoke_test.py` 一键验证（JSON 合法、skill/command/agent 完整性、42 条规则、fixtures 命中、hooks 行为）。

发现 bug 或有改进建议，以 `[QC] <一句话问题>` 为标题提交到 https://github.com/lhg-plugs/lhg-promo/issues，正文写清"复现步骤 → 实际表现 → 期望表现"。

## 出品：刘洪光

本插件由真人出镜 IP「刘洪光」（安徽合肥）出品，归属 [lhg-skills](https://github.com/lhg-skills)。

- GitHub 主页：https://github.com/lhg-skills —— 全部 skill 开源在此，欢迎 star
- 视频号：搜「刘洪光实名上网」
- 微信：lhgsmsw
