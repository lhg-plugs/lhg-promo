#!/usr/bin/env python3
"""lhg-promo 插件冒烟测试：全部绿才算过。

检查项：
 1. 三个 JSON 合法（plugin.json / marketplace.json / hooks.json）
 2. 4 个 SKILL.md 都有 name/description frontmatter，且 150+ 行
 3. 4 个 commands 都有 description + argument-hint frontmatter
 4. 2 个 agents 都有 name/description/tools/model frontmatter
 5. skills 平台中立：不含 Claude Code 专有工具名
 6. fixtures：坏 fixture 的埋点规则必须全部命中且脚本 exit!=0；
    好 fixture 零 blocker 且 exit==0；规则总数 >=40
 7. hooks 脚本：commit 拦截 / 非 commit 放行 / 逃生开关 / 方案缺章节提醒

用法：python3 smoke_test.py [--repo <插件根目录>]
退出码：0=全绿，1=有失败。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, cond, detail=""):
    results.append((PASS if cond else FAIL, name, detail))
    return cond


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def frontmatter(path):
    """解析 markdown 顶部 --- YAML 块（只取一层 key: value）。"""
    text = read(path)
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm = {}
    for ln in text[3:end].split("\n"):
        m = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", ln)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                          **kw)


# 预期的埋点命中（坏 fixture 必须全部命中）
BAD_MUST = {
    "PMO-STRUCT-002", "PMO-STRUCT-004", "PMO-STRUCT-005", "PMO-STRUCT-006",
    "PMO-CALC-001", "PMO-CALC-002",
    "PMO-PLAY-001", "PMO-PLAY-003", "PMO-PLAY-004", "PMO-PLAY-005",
    "PMO-PLAY-007",
    "PMO-DATE-001", "PMO-DATE-002", "PMO-DATE-003", "PMO-DATE-005",
    "PMO-EXEC-001", "PMO-EXEC-002", "PMO-EXEC-003", "PMO-EXEC-005",
    "PMO-CLAIM-001", "PMO-CLAIM-003", "PMO-CLAIM-004",
    "PMO-NIT-001",
}
# 平台中立红线：skill 正文不许出现这些 Claude Code 专有表述
NEUTRAL_DENY = ["Task tool", "Bash tool", "Edit tool", "Write tool",
                "Read tool", "AskUserQuestion", "subagent_type",
                "PreToolUse", "PostToolUse",
                "${CLAUDE_", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)
    AUDIT = os.path.join(repo, "scripts", "audit", "promo_audit.py")

    # 1. JSON 合法
    for rel in [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
                "hooks/hooks.json"]:
        p = os.path.join(repo, rel)
        try:
            d = json.loads(read(p))
            check("JSON 合法: " + rel, True)
            if rel.endswith("plugin.json"):
                check("plugin.json name==lhg-promo",
                      d.get("name") == "lhg-promo", str(d.get("name")))
                check("plugin.json 有 version/description/author",
                      all(d.get(k) for k in ("version", "description",
                                             "author")))
            if rel.endswith("marketplace.json"):
                ps = d.get("plugins", [])
                check("marketplace.json source==./ 且 name 一致",
                      len(ps) == 1 and ps[0].get("source") == "./" and
                      ps[0].get("name") == "lhg-promo", str(ps))
            if rel.endswith("hooks.json"):
                evts = d.get("hooks", {})
                check("hooks.json 有 PreToolUse+PostToolUse",
                      "PreToolUse" in evts and "PostToolUse" in evts,
                      str(list(evts)))
        except Exception as e:
            check("JSON 合法: " + rel, False, str(e))

    # 2. SKILL.md frontmatter + 行数 + 平台中立 + 出品区
    for skill in ["lhg-promo-goal", "lhg-promo-play", "lhg-promo-profit",
                  "lhg-promo-exec"]:
        p = os.path.join(repo, "skills", skill, "SKILL.md")
        fm = frontmatter(p)
        check("skill frontmatter: " + skill,
              bool(fm.get("name")) and bool(fm.get("description")),
              "name=%s" % fm.get("name"))
        nlines = len(read(p).split("\n"))
        check("skill 行数>=150: %s (%d 行)" % (skill, nlines), nlines >= 150,
              str(nlines))
        body = read(p)
        bad_words = [w for w in NEUTRAL_DENY if w in body]
        check("skill 平台中立: " + skill, not bad_words,
              "命中: %s" % bad_words)
        check("skill 有出品区: " + skill,
              "出品：刘洪光" in body and "https://github.com/lhg-skills" in body)
        check("skill 有自检与反馈: " + skill, "自检与反馈" in body)

    # 3. commands
    for cmd in ["promo", "promo-play", "promo-calc", "promo-audit"]:
        p = os.path.join(repo, "commands", cmd + ".md")
        fm = frontmatter(p)
        check("command description+argument-hint: " + cmd,
              bool(fm.get("description")) and bool(fm.get("argument-hint")),
              str(fm.get("description"))[:50])

    # 4. agents
    for ag in ["promo-planner", "promo-auditor"]:
        p = os.path.join(repo, "agents", ag + ".md")
        fm = frontmatter(p)
        check("agent frontmatter: " + ag,
              all(fm.get(k) for k in ("name", "description", "tools",
                                      "model")),
              str({k: fm.get(k) for k in ("name", "model")}))

    # 5. 审计脚本冒烟
    def audit_hits(target):
        r = run([sys.executable, AUDIT, "--target", target,
                 "--format", "json"])
        try:
            d = json.loads(r.stdout)
        except Exception:
            return None, r.returncode, []
        return (d["summary"], r.returncode,
                [f["rule_id"] for f in d["findings"]])

    s, code, ids = audit_hits(os.path.join(repo, "fixtures"))
    check("坏 fixture exit!=0", code != 0, "exit=%d" % code)
    check("坏 fixture blocker>0", s and s["blocker"] > 0, str(s))
    missing = BAD_MUST - set(ids)
    check("坏 fixture 埋点全命中 (%d/%d)"
          % (len(BAD_MUST - missing), len(BAD_MUST)),
          not missing, "缺失: %s" % sorted(missing))

    with tempfile.TemporaryDirectory() as td:
        shutil.copy(os.path.join(repo, "fixtures", "plan-good.md"),
                    os.path.join(td, "plan-good.md"))
        s, code, ids = audit_hits(td)
        check("好 fixture 零 blocker", s and s["blocker"] == 0, str(s))
        check("好 fixture exit==0", code == 0, "exit=%d" % code)
        check("规则总数>=40 (%d)" % s["rules_run"], s["rules_run"] >= 40,
              str(s["rules_run"]))

    # 6. hooks 脚本
    def hook(script, payload, env=None, cwd=None):
        e = dict(os.environ)
        e.update(env or {})
        return run([sys.executable, os.path.join(repo, "hooks", script)],
                   input=payload, env=e, cwd=cwd or repo)

    r = hook("pre_commit_promo.py",
             '{"tool_input":{"command":"git status"}}')
    check("hook: 非 commit 放行", r.returncode == 0 and not r.stdout.strip())

    with tempfile.TemporaryDirectory() as td:
        run(["git", "init", "-q"], cwd=td)
        run(["git", "config", "user.email", "t@t.t"], cwd=td)
        run(["git", "config", "user.name", "t"], cwd=td)
        shutil.copy(os.path.join(repo, "fixtures", "plan-bad.md"),
                    os.path.join(td, "双11促销方案.md"))
        run(["git", "add", "-A"], cwd=td)
        payload = '{"tool_input":{"command":"git commit -m \\"x\\""}}'
        r = hook("pre_commit_promo.py", payload, cwd=td)
        try:
            d = json.loads(r.stdout)
            denied = (d["hookSpecificOutput"]["permissionDecision"]
                      == "deny")
        except Exception:
            denied = False
        check("hook: commit 暂存坏方案拦截", denied, r.stdout[:120])
        r = hook("pre_commit_promo.py", payload,
                 {"LHG_PROMO_HOOKS_OFF": "1"}, cwd=td)
        check("hook: 逃生开关生效",
              r.returncode == 0 and not r.stdout.strip())

    with tempfile.TemporaryDirectory() as td:
        bad_plan = os.path.join(td, "促销方案.md")
        with open(bad_plan, "w", encoding="utf-8") as f:
            f.write("# 促销方案\n\n## 玩法\n\n满100减10。\n")
        r = hook("post_plan_warn.py",
                 json.dumps({"tool_input": {"file_path": bad_plan}}))
        check("hook: 方案缺章节提醒", "additionalContext" in r.stdout,
              r.stdout[:80])
        good_plan = os.path.join(td, "促销方案2.md")
        with open(good_plan, "w", encoding="utf-8") as f:
            f.write("# 促销方案\n\n## 利润测算\n\n## 执行清单\n")
        r = hook("post_plan_warn.py",
                 json.dumps({"tool_input": {"file_path": good_plan}}))
        check("hook: 章节齐全不提醒", not r.stdout.strip())
        r = hook("post_plan_warn.py",
                 json.dumps({"tool_input": {"file_path": bad_plan}}),
                 {"LHG_PROMO_HOOKS_OFF": "1"})
        check("hook: 提醒逃生开关生效", not r.stdout.strip())
        other = os.path.join(td, "notes.md")
        with open(other, "w", encoding="utf-8") as f:
            f.write("hello")
        r = hook("post_plan_warn.py",
                 json.dumps({"tool_input": {"file_path": other}}))
        check("hook: 非方案文件放行", not r.stdout.strip())

    # 报告
    print("=" * 60)
    print("lhg-promo 冒烟测试报告")
    print("=" * 60)
    fails = 0
    for st, name, detail in results:
        mark = "✓" if st == PASS else "✗"
        print("%s %s %s" % (mark, st, name))
        if detail and st == FAIL:
            print("    → %s" % detail)
        if st == FAIL:
            fails += 1
    print("=" * 60)
    print("共 %d 项，通过 %d，失败 %d"
          % (len(results), len(results) - fails, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
