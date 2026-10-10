#!/usr/bin/env python3
"""lhg-promo 确定性促销方案审计：42 条规则，零第三方依赖。

扫描目标目录下的促销方案文档（*.md），检查：
  结构完整性（档期/测算/执行清单/复盘）、数字一致性（满减门槛 vs 客单价、
  活动价 vs 成本价）、玩法规则自相矛盾、档期冲突、执行清单缺项、
  宣传合规（绝对化用语/限时话术）。

用法：
    python3 promo_audit.py --target <目录> [--format json|text] [--fail-on blocker|warning|nit]

有 blocker 时以 exit code 2 退出（供 hooks 与 CI 使用）。
规则文案均为本项目原创。
"""

import argparse
import json
import os
import re
import sys

VERSION = "1.0.0"
TOOL = "lhg-promo/promo-audit"

SKIP_DIRS = {
    "node_modules", ".next", "dist", "build", ".git", "coverage",
    "__pycache__", "vendor", ".turbo", "out", "fixtures",
}
SCAN_EXTS = {".md", ".markdown", ".txt"}

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}月\d{1,2}日")


class Finding:
    __slots__ = ("rule_id", "severity", "category", "title", "file",
                 "line", "snippet", "detail")

    def __init__(self, rule_id, severity, category, title, file, line,
                 snippet, detail):
        self.rule_id = rule_id
        self.severity = severity
        self.category = category
        self.title = title
        self.file = file
        self.line = line
        self.snippet = snippet
        self.detail = detail

    def to_dict(self):
        return {
            "rule_id": self.rule_id, "severity": self.severity,
            "category": self.category, "title": self.title,
            "file": self.file, "line": self.line,
            "snippet": self.snippet, "detail": self.detail,
        }


RULES = []
_RULE_BY_ID = {}


def rule(rule_id, severity, category, title, detail):
    def deco(fn):
        r = {"id": rule_id, "severity": severity, "category": category,
             "title": title, "detail": detail}
        _RULE_BY_ID[rule_id] = r
        r["check"] = fn
        RULES.append(r)
        return fn
    return deco


def _mk(rule_id, path, line, snippet):
    r = _RULE_BY_ID[rule_id]
    return Finding(r["id"], r["severity"], r["category"], r["title"],
                   path, line, snippet[:160], r["detail"])


def collect_files(target):
    out = []
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            _, ext = os.path.splitext(f)
            if ext in SCAN_EXTS:
                out.append(os.path.join(root, f))
    return sorted(out)


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _nums(pattern, text):
    return [float(x) for x in re.findall(pattern, text)]


def _avg_order(text):
    m = re.search(r"客单价\D{0,8}(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def _has_calc(text):
    return bool(re.search(r"利润测算|测算表|成本测算", text))


def _task_lines(lines):
    """执行清单区的任务行：- 开头或数字编号的行。"""
    tasks = []
    in_exec = False
    for i, ln in enumerate(lines):
        if re.match(r"^#{1,4}\s*.*(执行清单|任务清单|分工安排)", ln):
            in_exec = True
            continue
        if in_exec and re.match(r"^#{1,4}\s+", ln):
            break
        if in_exec and re.match(r"\s*(?:[-*]|\d+[.、])\s*\S", ln):
            tasks.append((i + 1, ln.strip()))
    return tasks


# ================================================================ 结构规则

@rule("PMO-STRUCT-001", "blocker", "结构", "缺档期起止时间",
      "方案没有明确的活动起止日期。没有档期，后续排期、预热、复盘都无从谈起：写清起止日期。")
def _s001(lines, text, path, ctx):
    if not DATE_RE.search(text) and "档期" not in text:
        return [_mk("PMO-STRUCT-001", path, 1, lines[0] if lines else "")]
    return []


@rule("PMO-STRUCT-002", "blocker", "结构", "缺利润测算",
      "方案没有任何利润测算（成本/毛利/保本点）。不算账的促销等于盲打：补一张利润测算表。")
def _s002(lines, text, path, ctx):
    if not _has_calc(text):
        return [_mk("PMO-STRUCT-002", path, 1, lines[0] if lines else "")]
    return []


@rule("PMO-STRUCT-003", "blocker", "结构", "缺执行清单",
      "方案没有执行清单/任务分工。策划落不了地等于白写：列出任务、负责人、时间点。")
def _s003(lines, text, path, ctx):
    if not re.search(r"执行清单|任务清单|分工安排", text):
        return [_mk("PMO-STRUCT-003", path, 1, lines[0] if lines else "")]
    return []


@rule("PMO-STRUCT-004", "warning", "结构", "缺复盘安排",
      "方案没有复盘环节。不复盘的促销，坑下次还会再踩：加上复盘时间与复盘维度。")
def _s004(lines, text, path, ctx):
    if "复盘" not in text:
        return [_mk("PMO-STRUCT-004", path, 1, lines[0] if lines else "")]
    return []


@rule("PMO-STRUCT-005", "warning", "结构", "活动目标未量化",
      "目标只有定性描述（如\"提升销量\"），没有数字。目标不量化，复盘时无法判定成败：补上 GMV/订单量/转化率等数字目标。")
def _s005(lines, text, path, ctx):
    if "目标" in text and not re.search(r"(GMV|销售额|目标|订单量|转化率)[^\n]{0,20}\d", text):
        return [_mk("PMO-STRUCT-005", path, 1, "目标未量化")]
    return []


@rule("PMO-STRUCT-006", "warning", "结构", "缺目标人群",
      "方案没有说明目标人群。不知道卖给谁，玩法和话术都无从设计：补上目标人群画像。")
def _s006(lines, text, path, ctx):
    if not re.search(r"目标人群|人群画像|目标用户|客群", text):
        return [_mk("PMO-STRUCT-006", path, 1, lines[0] if lines else "")]
    return []


# ================================================================ 测算规则

@rule("PMO-CALC-001", "blocker", "测算", "满减门槛高于客单价",
      "满减门槛高于平均客单价，大部分用户够不着门槛，满减等于摆设：把门槛降到客单价的 0.6~0.9 倍，或换玩法。")
def _c001(lines, text, path, ctx):
    avg = _avg_order(text)
    if avg is None:
        return []
    out = []
    for i, ln in enumerate(lines):
        for m in re.finditer(r"满\s*(\d+(?:\.\d+)?)\s*减", ln):
            if float(m.group(1)) > avg:
                out.append(_mk("PMO-CALC-001", path, i + 1, ln.strip()))
                break
    return out


@rule("PMO-CALC-002", "blocker", "测算", "活动价低于成本价",
      "活动价/秒杀价低于成本价，每卖一单都在亏钱。除非是明确的亏本引流款（限量+预算），否则就是定价事故。")
def _c002(lines, text, path, ctx):
    m = re.search(r"成本价?\D{0,6}(\d+(?:\.\d+)?)", text)
    if not m:
        return []
    cost = float(m.group(1))
    out = []
    for i, ln in enumerate(lines):
        for mm in re.finditer(r"(?:秒杀价|活动价|促销价|到手价)\D{0,6}(\d+(?:\.\d+)?)", ln):
            if float(mm.group(1)) < cost:
                out.append(_mk("PMO-CALC-002", path, i + 1, ln.strip()))
                break
    return out


@rule("PMO-CALC-003", "blocker", "测算", "测算缺保本点",
      "有测算表但没算保本点。不知道卖多少单才不亏，目标就是拍脑袋：补上保本销量/保本销售额。")
def _c003(lines, text, path, ctx):
    if _has_calc(text) and "保本" not in text:
        return [_mk("PMO-CALC-003", path, 1, "测算表无保本点")]
    return []


@rule("PMO-CALC-004", "warning", "测算", "测算缺费用项",
      "测算表只算了商品成本，没算推广费/平台佣金/物流等费用。费用漏一项，利润虚增一分：补全费用项。")
def _c004(lines, text, path, ctx):
    if _has_calc(text) and not re.search(r"推广费|佣金|物流|快递费|人力成本|投流", text):
        return [_mk("PMO-CALC-004", path, 1, "测算表无费用项")]
    return []


@rule("PMO-CALC-005", "warning", "测算", "缺悲观情形测算",
      "测算只有乐观/中性情形，没有悲观情形。活动效果不及预期时毫无准备：加一档悲观测算（销量打 5~7 折）。")
def _c005(lines, text, path, ctx):
    if _has_calc(text) and not re.search(r"悲观|最坏|下限|保守估计", text):
        return [_mk("PMO-CALC-005", path, 1, "测算表无悲观情形")]
    return []


@rule("PMO-CALC-006", "warning", "测算", "折扣过深无说明",
      "折扣低于 5 折却没有任何说明。深折扣要么是清仓（需说明尾货逻辑），要么是价格体系要崩：写清深折扣的原因与范围。")
def _c006(lines, text, path, ctx):
    if re.search(r"清仓|尾货|亏本引流", text):
        return []
    out = []
    for i, ln in enumerate(lines):
        m = re.search(r"(\d+(?:\.\d+)?)\s*折", ln)
        if m and float(m.group(1)) < 5:
            out.append(_mk("PMO-CALC-006", path, i + 1, ln.strip()))
    return out


@rule("PMO-CALC-007", "warning", "测算", "赠品成本未计入测算",
      "方案有赠品玩法，但测算表里没计赠品成本。赠品是真金白银：把赠品成本计入测算。")
def _c007(lines, text, path, ctx):
    if "赠品" in text and _has_calc(text):
        calc_sec = "\n".join(
            ln for ln in lines if True)  # 全文级检查：测算区无赠品字样
        # 取测算标题之后的内容
        idx = None
        for i, ln in enumerate(lines):
            if re.search(r"利润测算|测算表", ln):
                idx = i
                break
        tail = "\n".join(lines[idx:]) if idx is not None else ""
        if "赠品" not in tail:
            return [_mk("PMO-CALC-007", path, 1, "测算表未计赠品成本")]
    return []


@rule("PMO-CALC-008", "warning", "测算", "测算无客单价假设",
      "测算表没有客单价假设。GMV=流量×转化率×客单价，缺一项公式就不闭环：补上客单价假设。")
def _c008(lines, text, path, ctx):
    if _has_calc(text) and _avg_order(text) is None:
        return [_mk("PMO-CALC-008", path, 1, "测算表无客单价")]
    return []


@rule("PMO-CALC-009", "warning", "测算", "测算无转化率假设",
      "测算表没有转化率假设。没有转化率，销量预测就是空想：补上转化率假设（参考历史活动数据）。")
def _c009(lines, text, path, ctx):
    if _has_calc(text) and "转化率" not in text:
        return [_mk("PMO-CALC-009", path, 1, "测算表无转化率")]
    return []


@rule("PMO-CALC-010", "warning", "测算", "测算无流量假设",
      "测算表没有流量/访客假设。不知道多少人进店，销量无从算起：补上流量假设（自然流+付费流分开）。")
def _c010(lines, text, path, ctx):
    if _has_calc(text) and not re.search(r"流量|访客|曝光|UV|人次", text):
        return [_mk("PMO-CALC-010", path, 1, "测算表无流量假设")]
    return []


# ================================================================ 玩法规则

@rule("PMO-PLAY-001", "blocker", "玩法", "优惠叠加规则自相矛盾",
      "方案里同时出现\"可叠加\"和\"不可叠加\"，客服和用户会打起来：统一叠加规则，全文只保留一种说法。")
def _p001(lines, text, path, ctx):
    if "可叠加" in text and "不可叠加" in text:
        ln_no = next((i + 1 for i, ln in enumerate(lines) if "不可叠加" in ln), 1)
        return [_mk("PMO-PLAY-001", path, ln_no, "可叠加/不可叠加并存")]
    return []


@rule("PMO-PLAY-002", "warning", "玩法", "满减档位过多",
      "满减档位超过 3 档。档位太多用户算不过来，转化率反而下降：精简到 1~3 档。")
def _p002(lines, text, path, ctx):
    thresholds = set(re.findall(r"满\s*(\d+(?:\.\d+)?)\s*减", text))
    if len(thresholds) > 3:
        return [_mk("PMO-PLAY-002", path, 1, "满减档位 %d 档" % len(thresholds))]
    return []


@rule("PMO-PLAY-003", "warning", "玩法", "秒杀无库存/名额上限",
      "有秒杀玩法但没写库存上限。秒杀不限量等于全场降价，还可能超卖：写清限量件数。")
def _p003(lines, text, path, ctx):
    if "秒杀" in text and not re.search(r"限量|库存|名额|件|有限", text):
        return [_mk("PMO-PLAY-003", path, 1, "秒杀不限量")]
    return []


@rule("PMO-PLAY-004", "warning", "玩法", "拼团无成团条件",
      "有拼团玩法但没写成团条件。用户不知道几人成团、多久成团，参与意愿大打折扣：写清几人成团与成团时限。")
def _p004(lines, text, path, ctx):
    if "拼团" in text and not re.search(r"成团|\d+\s*人团", text):
        return [_mk("PMO-PLAY-004", path, 1, "拼团无成团条件")]
    return []


@rule("PMO-PLAY-005", "warning", "玩法", "直播无排期",
      "有直播玩法但没写排期。直播没排期等于没计划：写清场次、时间、主播。")
def _p005(lines, text, path, ctx):
    if "直播" in text and not re.search(r"场次|主播|排期|时间表|每晚\d|点", text):
        return [_mk("PMO-PLAY-005", path, 1, "直播无排期")]
    return []


@rule("PMO-PLAY-006", "warning", "玩法", "满赠门槛高于客单价",
      "满赠门槛高于客单价，大部分用户拿不到赠品，满赠等于画饼：把门槛降到客单价附近。")
def _p006(lines, text, path, ctx):
    avg = _avg_order(text)
    if avg is None:
        return []
    out = []
    for i, ln in enumerate(lines):
        for m in re.finditer(r"满\s*(\d+(?:\.\d+)?)\s*[赠送]", ln):
            if float(m.group(1)) > avg:
                out.append(_mk("PMO-PLAY-006", path, i + 1, ln.strip()))
                break
    return out


@rule("PMO-PLAY-007", "warning", "玩法", "优惠券无门槛说明",
      "发了优惠券但没写使用门槛。用户领了不知道能不能用，核销率会很难看：写清满多少可用（或注明无门槛）。")
def _p007(lines, text, path, ctx):
    if "优惠券" in text and not re.search(r"优惠券.{0,12}门槛|满\s*\d+\s*可用|无门槛", text):
        return [_mk("PMO-PLAY-007", path, 1, "优惠券无门槛说明")]
    return []


@rule("PMO-PLAY-008", "warning", "玩法", "玩法与清仓目标错配",
      "目标是清仓/去库存，但玩法里没有折扣、秒杀、买赠这类去库存利器：清仓目标优先用直接降价类玩法。")
def _p008(lines, text, path, ctx):
    if re.search(r"清仓|去库存|尾货", text) and not re.search(r"折扣|秒杀|买赠|特价|直降", text):
        return [_mk("PMO-PLAY-008", path, 1, "清仓目标无去库存玩法")]
    return []


# ================================================================ 档期规则

@rule("PMO-DATE-001", "warning", "档期", "档期与大促撞车",
      "档期撞上 618/双11 等大促。流量会被大促吸走，除非你就是去蹭大促流量：要么错峰，要么写清蹭大促的打法。")
def _d001(lines, text, path, ctx):
    if re.search(r"双11|双十一|618|双12|双十二|年货节", text):
        return [_mk("PMO-DATE-001", path, 1, "档期含大促关键词")]
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", text):
        mm, dd = int(m.group(2)), int(m.group(3))
        if (mm == 11 and 1 <= dd <= 15) or (mm == 6 and 1 <= dd <= 20):
            return [_mk("PMO-DATE-001", path, 1, "档期落在 %02d-%02d 大促窗口" % (mm, dd))]
    return []


@rule("PMO-DATE-002", "warning", "档期", "无预热期或预热不足",
      "方案没有预热期，或预热不足 3 天。没有预热直接开卖，首日流量会很难看：至少留 3 天预热（蓄水+种草）。")
def _d002(lines, text, path, ctx):
    if "预热" not in text:
        return [_mk("PMO-DATE-002", path, 1, "无预热期")]
    m = re.search(r"预热\D{0,6}(\d+)\s*天", text)
    if m and int(m.group(1)) < 3:
        return [_mk("PMO-DATE-002", path, 1, "预热仅 %s 天" % m.group(1))]
    return []


@rule("PMO-DATE-003", "warning", "档期", "活动时长异常",
      "活动时长超过 14 天（用户疲劳、价格体系受损）或不足 2 天（来不及发酵）：常规促销建议 3~10 天。")
def _d003(lines, text, path, ctx):
    dates = re.findall(r"(\d{4})-(\d{2})-(\d{2})", text)
    if len(dates) >= 2:
        from datetime import date as _date
        try:
            d0 = _date(*map(int, dates[0]))
            d1 = _date(*map(int, dates[1]))
            days = abs((d1 - d0).days) + 1
            if days > 14 or days < 2:
                return [_mk("PMO-DATE-003", path, 1, "活动时长 %d 天" % days)]
        except ValueError:
            pass
    return []


@rule("PMO-DATE-004", "nit", "档期", "节假日档期未安排人力",
      "档期覆盖法定节假日，但方案没提人力/值班安排。节假日客服和发货不能断：补上值班表。")
def _d004(lines, text, path, ctx):
    if re.search(r"国庆|春节|中秋|五一|元旦", text) and not re.search(r"值班|人力安排|排班", text):
        return [_mk("PMO-DATE-004", path, 1, "节假日无人力安排")]
    return []


@rule("PMO-DATE-005", "warning", "档期", "大促档期无备货盘点",
      "档期撞大促却没提备货/盘点。大促爆单发不出货，差评会淹没店铺：加上备货量与盘点计划。")
def _d005(lines, text, path, ctx):
    hit_d001 = bool(re.search(r"双11|双十一|618|双12|双十二|年货节", text))
    if hit_d001 and not re.search(r"备货|盘点|库存准备", text):
        return [_mk("PMO-DATE-005", path, 1, "大促无备货盘点")]
    return []


# ================================================================ 执行规则

@rule("PMO-EXEC-001", "blocker", "执行", "执行任务无负责人",
      "执行清单里有任务没写负责人。没负责人的任务等于没人做：每条任务都要有明确负责人。")
def _e001(lines, text, path, ctx):
    out = []
    for ln_no, ln in _task_lines(lines):
        if not re.search(r"负责人|负责：|负责:|owner|@[\u4e00-\u9fa5A-Za-z]{2,}", ln):
            out.append(_mk("PMO-EXEC-001", path, ln_no, ln))
    return out


@rule("PMO-EXEC-002", "blocker", "执行", "执行任务无时间点",
      "执行清单里有任务没写时间点。没 DDL 的任务会无限拖延：每条任务都要有截止时间。")
def _e002(lines, text, path, ctx):
    out = []
    for ln_no, ln in _task_lines(lines):
        if not re.search(r"\d{1,2}月\d{1,2}日|\d{4}-\d{2}-\d{2}|截止|前完成|D-\d+|当天", ln):
            out.append(_mk("PMO-EXEC-002", path, ln_no, ln))
    return out


@rule("PMO-EXEC-003", "warning", "执行", "无风险预案",
      "方案没有风险预案。流量不及预期、系统崩了、竞品截胡，发生时再想就来不及了：至少准备 2 条预案。")
def _e003(lines, text, path, ctx):
    if not re.search(r"预案|风险应对|Plan B|备选方案|应急", text):
        return [_mk("PMO-EXEC-003", path, 1, lines[0] if lines else "")]
    return []


@rule("PMO-EXEC-004", "warning", "执行", "无物料清单",
      "方案没列物料清单（海报/详情页/短信/推送）。活动前一天才发现海报没做，是最常见的翻车：列出全部物料与交付时间。")
def _e004(lines, text, path, ctx):
    if not re.search(r"海报|详情页|短信|推送|私域|物料", text):
        return [_mk("PMO-EXEC-004", path, 1, lines[0] if lines else "")]
    return []


@rule("PMO-EXEC-005", "warning", "执行", "无预算总表",
      "方案没有预算总表。费用散落在各处，老板批钱时对不上账：汇总一张预算总表（推广/物料/人力/赠品）。")
def _e005(lines, text, path, ctx):
    if not re.search(r"总预算|预算合计|费用预算|预算表", text):
        return [_mk("PMO-EXEC-005", path, 1, lines[0] if lines else "")]
    return []


# ================================================================ 宣传合规

@rule("PMO-CLAIM-001", "blocker", "合规", "绝对化低价宣传",
      "出现\"全网最低价/历史最低\"等绝对化用语。无法举证就是虚假宣传，广告法罚起来很疼：删掉，或换成可举证的说法。")
def _cl001(lines, text, path, ctx):
    out = []
    for i, ln in enumerate(lines):
        if re.search(r"全网最低价|历史最低|绝无仅有|史无前例", ln):
            out.append(_mk("PMO-CLAIM-001", path, i + 1, ln.strip()))
    return out


@rule("PMO-CLAIM-002", "warning", "合规", "极限词风险",
      "出现\"第一/首家/独家\"等极限词。极限词需要充分举证，否则有合规风险：要么举证，要么删掉。")
def _cl002(lines, text, path, ctx):
    out = []
    for i, ln in enumerate(lines):
        if re.search(r"全网第一|行业第一|首家|独家|仅此一家", ln):
            out.append(_mk("PMO-CLAIM-002", path, i + 1, ln.strip()))
    return out


@rule("PMO-CLAIM-003", "warning", "合规", "限时话术无明确截止",
      "用了\"仅限今天/最后X天/错过再等一年\"这类限时话术，却没写明确截止日期。话术与事实不符就是虚假宣传：写清截止日期。")
def _cl003(lines, text, path, ctx):
    if re.search(r"仅限今天|最后\d+天|错过再等一年|限时抢购", text):
        if not re.search(r"截止|截至|止", text):
            return [_mk("PMO-CLAIM-003", path, 1, "限时话术无截止日期")]
    return []


@rule("PMO-CLAIM-004", "warning", "合规", "\"免费\"有隐藏门槛",
      "\"免费领/免费送\"后面跟着满减门槛。免费却要先消费，涉嫌误导：要么真免费，要么把门槛写在同一句话里。")
def _cl004(lines, text, path, ctx):
    if re.search(r"免费领|免费送|免费得", text) and re.search(r"满\s*\d+", text):
        return [_mk("PMO-CLAIM-004", path, 1, "免费宣传附带消费门槛")]
    return []


# ================================================================ 洁癖项

@rule("PMO-NIT-001", "nit", "洁癖", "价格单位混用",
      "同一方案里\"¥\"和\"元\"混用。统一用一种，看着才专业。")
def _n001(lines, text, path, ctx):
    if "¥" in text and "元" in text:
        return [_mk("PMO-NIT-001", path, 1, "¥ 与 元 混用")]
    return []


@rule("PMO-NIT-002", "nit", "洁癖", "同比环比缺口径",
      "出现同比/环比却没写对比基期。读者不知道跟谁比：补上基期（如\"较去年同期\"）。")
def _n002(lines, text, path, ctx):
    if re.search(r"同比|环比", text) and not re.search(r"去年同期|上月|基期", text):
        return [_mk("PMO-NIT-002", path, 1, "同比/环比无基期")]
    return []


@rule("PMO-NIT-003", "nit", "洁癖", "档期只有天数无具体日期",
      "只写了\"活动X天\"，没有具体起止日期。执行时容易扯皮：写清起止日期。")
def _n003(lines, text, path, ctx):
    if re.search(r"活动\s*\d+\s*天|为期\s*\d+\s*天", text) and not DATE_RE.search(text):
        return [_mk("PMO-NIT-003", path, 1, "无具体起止日期")]
    return []


@rule("PMO-NIT-004", "nit", "洁癖", "缺对接人联系方式",
      "方案没有对接人联系方式。执行中卡住了找不到人：加上对接人及联系方式。")
def _n004(lines, text, path, ctx):
    if not re.search(r"对接人|联系人|联系方式|微信|电话", text):
        return [_mk("PMO-NIT-004", path, 1, lines[0] if lines else "")]
    return []


# ================================================================ 主流程

SEVERITY_ORDER = {"blocker": 0, "warning": 1, "nit": 2}


def audit_file(path):
    text = read_text(path)
    lines = text.split("\n")
    ctx = {}
    findings = []
    for r in RULES:
        try:
            findings.extend(r["check"](lines, text, path, ctx) or [])
        except Exception:
            continue  # 单条规则出错不影响整体
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.file, f.line))
    return findings


def main():
    ap = argparse.ArgumentParser(description="lhg-promo 促销方案确定性审计")
    ap.add_argument("--target", required=True, help="待扫描目录")
    ap.add_argument("--format", default="text", choices=["json", "text"])
    ap.add_argument("--fail-on", default="blocker",
                    choices=["blocker", "warning", "nit"])
    args = ap.parse_args()

    files = collect_files(args.target)
    all_findings = []
    for p in files:
        all_findings.extend(audit_file(p))

    sev_count = {"blocker": 0, "warning": 0, "nit": 0}
    for f in all_findings:
        sev_count[f.severity] += 1

    summary = {
        "tool": TOOL,
        "version": VERSION,
        "target": args.target,
        "files_scanned": len(files),
        "rules_run": len(RULES),
        "blocker": sev_count["blocker"],
        "warning": sev_count["warning"],
        "nit": sev_count["nit"],
        "total": len(all_findings),
    }

    if args.format == "json":
        print(json.dumps({"summary": summary,
                          "findings": [f.to_dict() for f in all_findings]},
                         ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("lhg-promo 促销方案审计报告  v%s" % VERSION)
        print("=" * 60)
        print("扫描文件: %d  运行规则: %d" % (len(files), len(RULES)))
        print("blocker: %d  warning: %d  nit: %d" %
              (sev_count["blocker"], sev_count["warning"], sev_count["nit"]))
        print("-" * 60)
        cur = None
        for f in all_findings:
            if f.severity != cur:
                cur = f.severity
                print("\n[%s]" % cur.upper())
            print("  %s %s:%d" % (f.rule_id, os.path.basename(f.file), f.line))
            print("    %s" % f.title)
            if f.snippet:
                print("    > %s" % f.snippet)
        if not all_findings:
            print("\n未发现问题，方案结构完整。")

    threshold = SEVERITY_ORDER[args.fail_on]
    bad = any(SEVERITY_ORDER[f.severity] <= threshold for f in all_findings)
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
