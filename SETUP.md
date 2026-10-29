# 设置与运行

零第三方依赖，无需安装任何包。

## 环境要求

- Python 3.8+（标准库：json / os / sys / time / uuid）

## 快速验证

```bash
# 在项目根目录
python run_tests.py        # 12 项验收断言，期望 PASS 12 / FAIL 0
python demo.py             # 三类路径演示，期望退出码 0
```

## 在自己的代码中使用

```python
from agent_router import AgentRouter

# 方式 A：从 JSON 配置加载
router = AgentRouter(config_path="examples/router_config.json")

# 方式 B：代码构建
router = AgentRouter(rules=[
    {"role": "hr_bot", "task_type": "onboard_employee",
     "target": "hr-bot"},
    {"role": "any", "task_type": "approve_high_value_payment",
     "human": True, "note": "高额支付需人工审批"},
], default_target="fallback-bot")

# 路由
outcome = router.route({"role": "hr_bot", "task_type": "onboard_employee"})
# -> {"path": "route", "target": "hr-bot", "rule_id": "RXXXXXX", ...}

outcome = router.route({"role": "data_bot", "task_type": "run_analytics"})
# -> {"path": "no_match", "target": "fallback-bot", "reason": "无匹配: ...", ...}

outcome = router.route({"role": "finance_bot",
                        "task_type": "approve_high_value_payment"})
# -> {"path": "human", "human_ticket": "HUMAN-XXXX", ...}

# 人工接管
ticket = outcome["human_ticket"]
claimed = router.claim_human(ticket, handler="ops-manager")
pending = router.pending_human()
```

## 常见问题

- **为什么无匹配不直接抛错？**
  业务上"无匹配"也是合法输入（新任务类型上线初期），必须显式可观测——
  要么降级到默认 agent，要么返回明确的 `no_match` + 原因，绝不静默丢弃。
- **转人工的规则会不会被自动 agent 抢走？**
  不会。`route()` 先查人工规则再查转发规则，命中人工的绝不转发。