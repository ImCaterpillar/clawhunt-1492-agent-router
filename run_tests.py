# -*- coding: utf-8 -*-
"""Agent 协作路由主流程验证 —— 对应验收标准
「至少演示正常路由、无匹配和转人工三类路径」

零第三方依赖。打印每条验收标准的实测结果。
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_router import AgentRouter, RouterError  # noqa

PASS, FAIL = [], []
OK = "\u2705"
NO = "\u274c"


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    mark = OK if cond else NO
    line = "  " + mark + " " + name
    if detail:
        line += " -- " + detail
    print(line)


print("=" * 78)
print("Agent Collaboration Router -- acceptance verification")
print("=" * 78)
print("Acceptance: demonstrate route / no-match / human takeover\n")

# 路由表：企业 Agent 系统系列的真实角色
RULES = [
    # 转人工优先：高危操作（资金、权限）
    {"role": "any", "task_type": "approve_high_value_payment",
     "human": True, "priority": 100,
     "note": "高额支付需人工审批"},
    {"role": "finance_bot", "task_type": "create_invoice",
     "target": "finance-bot", "priority": 80},
    {"role": "hr_bot", "task_type": "onboard_employee",
     "target": "hr-bot", "priority": 80},
    {"role": "hr_bot", "task_type": "query_leave_balance",
     "target": "hr-bot", "priority": 70},
    {"role": "support_bot", "task_type": ["ticket_triage", "faq_answer"],
     "target": "support-bot", "priority": 70},
    # 无匹配时回退
    {"role": "any", "task_type": "unknown_operation",
     "target": "fallback-bot", "priority": 1, "note": "兜底"},
]

router = AgentRouter(rules=RULES, default_target="fallback-bot")

print("-- 演示一：正常路由 --")
o1 = router.route({"bot": "hr-bot", "role": "hr_bot",
                   "task_type": "onboard_employee", "input": "新人入职"})
check("1. route: hr onbording -> hr-bot",
      o1["path"] == "route" and o1["target"] == "hr-bot",
      f"path={o1['path']} target={o1['target']}")
o2 = router.route({"role": "finance_bot", "task_type": "create_invoice"})
check("2. route: finance invoice -> finance-bot",
      o2["path"] == "route" and o2["target"] == "finance-bot",
      f"target={o2['target']}")
o3 = router.route({"role": "support_bot", "task_type": "faq_answer"})
check("3. route: support faq -> support-bot (list match)",
      o3["path"] == "route" and o3["target"] == "support-bot",
      f"target={o3['target']}")

print("-- 演示二：无匹配 + 失败回退 --")
o4 = router.route({"role": "data_bot", "task_type": "run_analytics"})
check("4. no-match -> fallback-bot (default)",
      o4["path"] == "no_match" and o4["target"] == "fallback-bot",
      f"path={o4['path']} target={o4['target']}")
o5 = router.route({"task_type": "undefined_thing"})
check("5. no-match with default fallback",
      o5["path"] == "no_match" and o5["target"] == "fallback-bot",
      f"reason={o5['reason'][:50]}")
# 无兜底 router 时 no_match 路径必须明确、不静默
router_nb = AgentRouter(rules=RULES, default_target=None)
o6 = router_nb.route({"role": "unknown", "task_type": "weird"})
check("6. no-match WITHOUT fallback stays explicit",
      o6["path"] == "no_match" and o6["target"] is None
      and "无匹配" in o6["reason"],
      f"path={o6['path']} reason={o6['reason'][:40]}")

print("-- 演示三：转人工接管 --")
o7 = router.route({"role": "finance_bot",
                   "task_type": "approve_high_value_payment"})
check("7. human takeover triggered (high-value payment)",
      o7["path"] == "human" and o7["human_ticket"],
      f"ticket={o7['human_ticket']}")
take = router.claim_human(o7["human_ticket"], handler="ops-manager")
check("8. human claims the ticket",
      take is not None and take["status"] == "claimed"
      and take["handler"] == "ops-manager",
      f"claimed={take['status'] if take else 'None'}")
pending = router.pending_human()
check("9. only awaiting tickets visible after claim",
      all(t["ticket"] != o7["human_ticket"] for t in pending),
      f"pending={len(pending)}")

print("-- 路径完整性 --")
st = router.stats()
check("10. all three paths exercised",
      st["route"] >= 3 and st["no_match"] >= 2 and st["human"] >= 1,
      f"stats={st}")
paths = {o["path"] for o in router.delivery_log()}
check("11. path enum is exactly route/no_match/human",
      paths == {"route", "no_match", "human"}, str(paths))

print("-- 转人工队列容量（overflow 标记）--")
r_ovf = AgentRouter(rules=[{"role": "any", "task_type": "t",
                            "human": True}], human_queue_capacity=1)
o_ovf1 = r_ovf.route({"role": "a", "task_type": "t"})
o_ovf2 = r_ovf.route({"role": "b", "task_type": "t"})
check("12. human queue overflow marked but ticket kept",
      o_ovf1["queue_overflow"] is False
      and o_ovf2["queue_overflow"] is True
      and bool(o_ovf1["human_ticket"]) and bool(o_ovf2["human_ticket"]),
      f"t1_overflow={o_ovf1['queue_overflow']} "
      f"t2_overflow={o_ovf2['queue_overflow']}")


print()
print("=" * 78)
print("Result: PASS " + str(len(PASS)) + "   FAIL " + str(len(FAIL)))
print("=" * 78)
if FAIL:
    print("Failed: " + ", ".join(FAIL))
sys.exit(1 if FAIL else 0)