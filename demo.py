# -*- coding: utf-8 -*-
"""演示：三类路径（正常路由/无匹配/转人工）

运行：python demo.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_router import AgentRouter  # noqa


def show(o):
    tag = {"route": "正常路由", "no_match": "无匹配", "human": "转人工"}
    extra = ""
    if o["path"] == "route":
        extra = f" -> 转发到 {o['target']}"
    elif o["path"] == "human":
        extra = f" -> 生成接管单 {o['human_ticket']}"
    else:
        extra = f" -> {o['target'] or '无兜底'}"
    print(f"  [{tag[o['path']]:<4}] {o.get('task', {}).get('task_type', '?'):<28}{extra}")


print("Agent 协作路由演示 — 三类路径\n")
router = AgentRouter(config_path=os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "examples", "router_config.json"))

print("--- ① 正常路由 ---")
show(router.route({"role": "hr_bot", "task_type": "onboard_employee"}))
show(router.route({"role": "finance_bot", "task_type": "create_invoice"}))
show(router.route({"role": "support_bot", "task_type": "faq_answer"}))

print("--- ② 无匹配 + 失败回退 ---")
show(router.route({"role": "data_bot", "task_type": "run_analytics"}))

print("--- ③ 转人工接管 ---")
o = router.route({"role": "finance_bot",
                  "task_type": "approve_high_value_payment"})
show(o)
claimed = router.claim_human(o["human_ticket"], handler="ops-manager")
print(f"  人工认领: {o['human_ticket']} -> "
      f"{'✅ 已认领 by ' + (claimed or {}).get('handler', '?') if claimed else '❌'}")

print("\n三条路径演示完成 ✅")
sys.exit(0)