#!/usr/bin/env python3
"""lhg-promo 硬门①：git commit 前检查暂存区里的促销方案，有 blocker 则拦截。

触发：PreToolUse / Bash。先判断本次 Bash 是否为 git commit，
不是则 0 开销直接放行；是则看暂存区有无促销方案文件
（文件名含 promo/促销/大促/清仓，或 plan*.md/方案*.md），
有则对这些文件所在目录跑插件自带的 promo 审计脚本，有 blocker 才拦截。

逃生方式（按推荐度排序）：
  1. 修掉 blocker 后重新 commit（推荐：补测算表/降门槛/统一叠加规则）。
  2. 紧急情况：LHG_PROMO_HOOKS_OFF=1 git commit -m "..."（单次豁免本次 hook）。
  3. /plugin disable lhg-promo（整个插件停用，hooks 不再触发）。

设计原则：脚本内部出错（无 git、审计脚本缺失、超时等）fail-open 直接放行；
真正的门禁在 /lhg-promo:promo-audit。零第三方依赖。
"""

import json
import os
import re
import subprocess
import sys

AUDIT_TIMEOUT = 60
COMMIT_RE = re.compile(r"(^|[;&|])\s*git\s+.*\bcommit\b")
PROMO_FILE_RE = re.compile(r"promo|促销|大促|清仓|plan.*\.md$|方案.*\.md$", re.I)


def _git(args, cwd):
    try:
        p = subprocess.run(["git"] + args, capture_output=True, text=True,
                           timeout=15, cwd=cwd)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


def main() -> int:
    # 逃生开关
    if os.environ.get("LHG_PROMO_HOOKS_OFF") == "1":
        return 0

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0  # 输入解析失败：fail-open

    tool_input = payload.get("tool_input", {}) or {}
    command = tool_input.get("command", "") or ""

    # 非 git commit：快速放行
    if not COMMIT_RE.search(command):
        return 0

    cwd = os.getcwd()
    staged = _git(["-c", "core.quotepath=false", "diff", "--cached",
                   "--name-only", "--diff-filter=ACM"], cwd).split()
    promo_files = [f for f in staged if PROMO_FILE_RE.search(
        os.path.basename(f))]
    if not promo_files:
        return 0  # 暂存区无促销方案：放行

    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(plugin_root, "scripts", "audit", "promo_audit.py")
    if not os.path.isfile(script):
        return 0  # 审计脚本缺失：fail-open

    # 对每个方案文件所在目录跑审计（去重）
    targets = sorted({os.path.dirname(os.path.join(cwd, f)) or cwd
                      for f in promo_files})
    blockers = []
    for target in targets:
        try:
            proc = subprocess.run(
                [sys.executable, script, "--target", target,
                 "--format", "json"],
                capture_output=True, text=True, timeout=AUDIT_TIMEOUT)
            data = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except Exception:
            continue  # 单个目录失败：fail-open
        for f in data.get("findings", []):
            if f.get("severity") == "blocker":
                blockers.append(f)

    if not blockers:
        return 0

    lines = [
        "提交被 lhg-promo 硬门拦截：促销方案审计发现 %d 个 blocker（会亏本/违法/落不了地的问题），"
        "修完再提交。" % len(blockers),
        "",
    ]
    for f in blockers[:10]:
        lines.append("- [%s] %s:%s %s"
                     % (f.get("rule_id"), f.get("file"), f.get("line"),
                        f.get("title")))
    if len(blockers) > 10:
        lines.append("…另有 %d 个，完整清单请跑 /lhg-promo:promo-audit"
                     % (len(blockers) - 10))
    lines += [
        "",
        "修复方式：运行 /lhg-promo:promo-audit 按报告逐条修复；",
        "紧急豁免（单次）：LHG_PROMO_HOOKS_OFF=1 git commit",
    ]
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "\n".join(lines),
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
