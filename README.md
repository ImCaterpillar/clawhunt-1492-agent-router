# Agent 协作路由 — 按角色与任务类型路由，失败回退 + 人工接管

对应 ClawHunt 任务 **#1492**（企业 Agent 系统 05/50｜Agent 协作路由）。

**验收标准**：至少演示**正常路由、无匹配和转人工**三类路径。

## 一条命令验证全部

```bash
python run_tests.py      # -> PASS 11 / FAIL 0
python demo.py           # -> 三类路径直观演示
```

## 验收三要素（与验收标准逐条对应）

**① 核心实现（路由层）路径**
`agent_router.py` —— `AgentRouter` 类，按 (role, task_type) 匹配路由表，
三条路径清晰划分：**正常路由**（命中规则→转发）、**无匹配**（→失败回退，
明确报错不静默丢弃）、**转人工**（命中转人工规则→生成人工接管单）。

**② 示例/演示文件路径**
- `examples/router_config.json` —— 路由表配置样例（含三类场景说明）
- `demo.py` —— 三类路径的直观演示（`python demo.py`）

**③ 路由验证：运行命令 + 正/反例预期输出**

```bash
python run_tests.py
# ✅ 1. route: hr onbording -> hr-bot
# ✅ 2. route: finance invoice -> finance-bot
# ✅ 4. no-match -> fallback-bot (default)
# ✅ 7. human takeover triggered (high-value payment)
# ...
# Result: PASS 11   FAIL 0
```

无人为途径绕过三类路径——每条路径都有独立断言（测试 1-11）。

## 快速开始

```bash
# 零第三方依赖（纯 Python 标准库）
python run_tests.py          # 全部验收验证
python demo.py               # 三类路径演示
```

## 目录

```
.
├── agent_router.py          # 协作路由层（核心）
├── run_tests.py             # 验收验证（11 项断言）
├── demo.py                  # 三类路径演示
├── examples/
│   └── router_config.json   # 路由表示例（含三类场景说明）
├── docs/
│   ├── 验收对照.md           # 验收标准逐条对照
│   ├── 实现说明.md           # 设计与实现
│   └── 验证记录.md           # 真实执行输出
├── SETUP.md
└── README.md
```

## 设计要点

1. **可配置路由表**：每条规则 = (role, task_type 匹配条件) → 目标 agent
   或 human=True。role/task_type 支持精确、列表、通配（`any`/`*`）。
2. **三类路径清晰**：
   - **正常路由**：精确命中规则 → 转发，带 rule_id 审计；
   - **无匹配**：未命中 → 失败回退（配了 default_target 则降级转发，
     否则明确返回 `no_match` + 原因，**不静默丢弃**）；
   - **转人工**：命中人工规则 → 生成 `HUMAN-XXX` 接管单进人工队列。
3. **转人工优先**：先查人工规则再查转发规则——高危操作（资金/权限）
   绝不被自动 agent 拦截。
4. **优先级**：priority 数字大者先匹配，兜底规则 priority 最低。
5. **人工接管入口**：`claim_human(ticket, handler)` 认领、`pending_human()`
   查待办——人可以在队列上接管任何转人工任务。
6. **审计**：每次路由写入 delivery_log，`stats()` 汇总三路径计数。
7. **与 #1490 隔离层协同**：路由决定"任务去哪"，不改变会话隔离边界——
   转交后各 bot 仍只读自己的命名空间。

## 环境

- Python 3.8+
- **零第三方依赖**（纯标准库）

## 边界说明

本单范围 = **按角色/任务类型路由 + 失败回退 + 人工接管入口**；
以下不在本单范围：
- 会话上下文与历史记录的隔离 —— 属拆分单 03（#1490）
- Bot 角色卡结构 —— 属拆分单 02（#1489）
- 知识库实际接入 —— 属「知识接线」类拆分单