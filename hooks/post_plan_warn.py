#!/usr/bin/env python3
"""lhg-promo 硬门②（警告级，不拦截）：写促销方案缺关键章节时提醒。

触发：PostToolUse / Write|Edit。只检查文件名含 promo/促销/大促/清仓 的
markdown 文件；缺"利润测算"或"执行清单"章节时给出提醒，永远 exit 0。

逃生方式：LHG_PROMO_HOOKS_OFF=1（环境变量）可关闭本提醒；
或 /plugin disable lhg-promo 停用整个插件。
零第三方依赖。
"""

import json
import os
import re
import sys

PROMO_NAME_RE = re.compile(r"promo|促销|大促|清仓", re.I)
REQUIRED_SECTIONS = ("利润测算", "执行清单")


def main() -> int:
    if os.environ.get("LHG_PROMO_HOOKS_OFF") == "1":
        return 0

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0  # fail-open

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or ""
    if not file_path:
        return 0

    _, ext = os.path.splitext(file_path)
    if ext.lower() not in (".md", ".markdown", ".txt"):
        return 0
    if not PROMO_NAME_RE.search(os.path.basename(file_path)):
        return 0  # 非促销方案文件：快速放行

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return 0  # 读不到文件：fail-open

    missing = [s for s in REQUIRED_SECTIONS if s not in text]
    if not missing:
        return 0

    msg = (
        "促销方案提醒（lhg-promo）：%s 缺少关键章节【%s】。\n"
        "不算账的促销等于盲打：补上利润测算表（成本/保本点/费用项）；\n"
        "没执行清单的策划落不了地：列出任务、负责人、时间点。\n"
        "跑 /lhg-promo:promo-audit 可一键检查全部 42 条规则。\n"
        "关闭本提醒：export LHG_PROMO_HOOKS_OFF=1（当前会话有效）。"
    ) % (os.path.basename(file_path), "、".join(missing))
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
