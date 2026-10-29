# -*- coding: utf-8 -*-
"""Agent 协作路由层 —— 按角色与任务类型路由，明确失败回退和人工接管入口。

对应 ClawHunt 任务 #1492（企业 Agent 系统 05/50｜Agent 协作路由），
验收标准：**至少演示正常路由、无匹配和转人工三类路径**。

设计：
  - **路由表**（可配置）：每条规则 = (角色 / 任务类型 匹配条件) → 目标。
  - 三类路径清晰划分：
      1. **正常路由**：任务精确命中路由规则 → 转发到目标 agent；
      2. **无匹配**：没有规则命中 → 进入**失败回退**（明确报"无匹配"，
         不静默丢弃，可选回退到默认 agent 或返回错误码）；
      3. **转人工**：命中「转人工」规则（危险操作/复杂任务/规则强制）
         → 产生人工接管单（人工接管入口），不交给任何 agent。
  - 零第三方依赖（纯 Python 标准库），可内存运行或持久化路由表为 JSON。
  - 与 #1490 会话隔离协同：路由只决定"任务去哪"，不改变隔离边界。

使用：
    from agent_router import AgentRouter
    r = AgentRouter(rules=[...])
    outcome = r.route(task)
    # outcome: {"path": "route"|"no_match"|"human", "target": ..., ...}
"""
import json
import os
import time
import uuid


class RouterError(Exception):
    """路由层异常（配置错误等）。"""


def _match(value, rule_val):
    """匹配一个字段值。rule_val 支持:
      - str "any" 或 "*": 通配（始终匹配）
      - str: 精确相等
      - list: value ∈ 列表
      - callable: 自定义判定（高级用法）
      - None: 该字段不参与匹配
    """
    if rule_val is None:
        return True
    if callable(rule_val):
        return bool(rule_val(value))
    if isinstance(rule_val, str) and rule_val in ("any", "*"):
        return True
    if isinstance(rule_val, (list, tuple, set)):
        return value in rule_val
    return value == rule_val


class AgentRouter:
    """按 (角色, 任务类型) 路由任务；失败回退 + 人工接管入口。"""

    def __init__(self, rules=None, default_target=None, config_path=None,
                 human_queue_capacity=100):
        # rules: [{role, task_type, target, priority, note}]
        self.rules = []
        self.default_target = default_target   # 无匹配时的兜底（可为 None=不兜底）
        self.human_queue = []                  # 人工接管队列
        self.human_queue_capacity = human_queue_capacity
        self._delivery_log = []                # 每次路由的审计
        if config_path and os.path.isfile(config_path):
            self.load_config(config_path)
        for r in (rules or []):
            self.add_rule(r)

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    def add_rule(self, rule):
        """添加一条路由规则。rule: {role?, task_type?, target?, human?,
        priority?, note?}。target 与 human 必须二选一。"""
        if not isinstance(rule, dict):
            raise RouterError("规则必须是 dict")
        target = rule.get("target")
        human = rule.get("human", False)
        if not target and not human:
            raise RouterError(f"规则必须有 target 或 human=True: {rule}")
        if target and human:
            raise RouterError(f"规则不能同时有 target 和 human: {rule}")
        entry = {
            "role": rule.get("role"),
            "task_type": rule.get("task_type"),
            "target": target,
            "human": bool(human),
            "priority": int(rule.get("priority", 0)),
            "note": rule.get("note", ""),
            "rule_id": "R" + uuid.uuid4().hex[:6].upper(),
        }
        self.rules.append(entry)
        # 高优先级在前（priority 数字大 = 先匹配）
        self.rules.sort(key=lambda r: -r["priority"])
        return entry["rule_id"]

    def save_config(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rules": self.rules, "default_target":
                       self.default_target}, f, ensure_ascii=False, indent=2)
        return path

    def load_config(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.rules = []
        self.default_target = data.get("default_target")
        for r in data.get("rules", []):
            self.add_rule(r)

    # ------------------------------------------------------------------
    # 核心路由
    # ------------------------------------------------------------------
    def route(self, task):
        """路由一个任务，返回决策结果。

        task: {bot?, role?, task_type?, input?, ...}（至少含 role / task_type
        之一用于匹配；两者皆无则视为"无法分类"→ 无匹配。）

        返回 dict:
          {"path": "route"|"no_match"|"human", "target": str|None,
           "rule_id": str|None, "human_ticket": str|None,
           "reason": str, "ts": float}
        """
        if not isinstance(task, dict):
            raise RouterError("task 必须是 dict")
        role = task.get("role")
        task_type = task.get("task_type")

        # 1. 转人工优先：命中"人工接管"规则的直接进人工队列
        for r in self.rules:
            if r["human"] and _match(role, r["role"]) \
                    and _match(task_type, r["task_type"]):
                return self._to_human(task, r)

        # 2. 正常路由：命中目标规则则转发
        for r in self.rules:
            if (not r["human"]) and _match(role, r["role"]) \
                    and _match(task_type, r["task_type"]):
                return self._route(task, r)

        # 3. 无匹配 → 失败回退
        return self._no_match(task)

    # ------------------------------------------------------------------
    # 三条路径
    # ------------------------------------------------------------------
    def _route(self, task, rule):
        outcome = {
            "path": "route",
            "target": rule["target"],
            "rule_id": rule["rule_id"],
            "human_ticket": None,
            "reason": f"正常路由: 命中规则 {rule['rule_id']}",
            "ts": time.time(),
            "task": task,
        }
        self._delivery_log.append(outcome)
        return outcome

    def _no_match(self, task):
        """无匹配路径：明确失败回退。

        - 若配置了 default_target → 回退到默认 agent（降级但不丢任务）；
        - 否则返回 path=no_match，reason 明确"无匹配"，不静默丢弃。
        """
        outcome = {
            "path": "no_match",
            "target": self.default_target,
            "rule_id": None,
            "human_ticket": None,
            "reason": ("无匹配: 未命中任何路由规则"
                       + (f"，回退到默认 Agent {self.default_target}"
                          if self.default_target else "，无兜底 Agent")),
            "ts": time.time(),
            "task": task,
        }
        self._delivery_log.append(outcome)
        return outcome

    def _to_human(self, task, rule):
        ticket = "HUMAN-" + uuid.uuid4().hex[:10].upper()
        if len(self.human_queue) >= self.human_queue_capacity:
            # 队列满：仍然产生接管单（拒绝转人工会丢真实任务）
            pass
        self.human_queue.append({
            "ticket": ticket,
            "task": task,
            "rule_id": rule["rule_id"],
            "reason": rule.get("note") or "转人工规则命中",
            "created_at": time.time(),
            "status": "awaiting_human",
        })
        outcome = {
            "path": "human",
            "target": None,
            "rule_id": rule["rule_id"],
            "human_ticket": ticket,
            "reason": f"转人工: 命中规则 {rule['rule_id']}"
                      f"（{rule.get('note') or '人工接管'}），已生成接管单",
            "ts": time.time(),
            "task": task,
        }
        self._delivery_log.append(outcome)
        return outcome

    # ------------------------------------------------------------------
    # 人工接管入口
    # ------------------------------------------------------------------
    def claim_human(self, ticket, handler=None):
        """人工从队列认领一个接管单。只允许认领**待办**单；
        已认领/已完成的单返回 None（防止双人同时处理同一单）。"""
        for item in self.human_queue:
            if item["ticket"] == ticket:
                if item["status"] != "awaiting_human":
                    return None          # 已被认领/完成，禁止双认领
                item["status"] = "claimed"
                item["claimed_at"] = time.time()
                item["handler"] = handler
                return item
        return None

    def pending_human(self):
        return [i for i in self.human_queue if i["status"] == "awaiting_human"]

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------
    def delivery_log(self):
        return list(self._delivery_log)

    def stats(self):
        from collections import Counter
        c = Counter(o["path"] for o in self._delivery_log)
        return {"total": len(self._delivery_log),
                "route": c.get("route", 0),
                "no_match": c.get("no_match", 0),
                "human": c.get("human", 0)}