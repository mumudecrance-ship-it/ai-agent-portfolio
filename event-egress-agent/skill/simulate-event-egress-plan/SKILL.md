---
name: simulate-event-egress-plan
description: Compare, simulate, audit, and prepare human-signable egress plan candidates for one bounded large-event dispersal task. Use when a user provides a venue graph, crowd groups, exit capacities, time-bounded incidents, and asks an Agent to run parallel crowd decisions, tick-by-tick capacity simulation, local virtual replanning, cached replay, or a signed recommendation package. Do not use for real-time crowd control, emergency command, road closure, public guidance, or any other action that needs production authority.
---

# 大型活动散场方案推演

把一次大型活动散场请求处理成可重放的候选比较与签发证据。只修改虚拟方案，不操作现实世界。

## 强制流程

1. 读取 `references/input-contract.md`，检查活动、出口、客群、轮次和事件是否完整。
2. 读取 `references/egress-policy.json`，冻结本次门禁。不得把其中阈值称为官方标准。
3. 先运行静态最近出口基线，保存首次偏离轮次、剩余人数、最高排队密度与未处理事件。
4. 至少生成三个有真实取舍的候选：最近出口、韧性均衡、某一运力优先。候选必须共享同一输入和事件。
5. 每一轮先让各客群 Agent 并行提交移动意图，再由仿真编排器统一应用出口容量。不得让多个 Agent 直接并发写同一份正式状态。
6. 事件发生后，只对被关闭出口或达到重规划阈值的客群生成局部改道。改道只进入虚拟仿真分支。
7. 按 `references/decision-contract.md` 计算清场率、最高排队密度、溢出轮次和权限门禁。不要用文案判断代替公式。
8. 同时保留实时计算结果与缓存回放；两条路径必须具有同一证据摘要。
9. 只有全部门禁通过的候选可以进入具名人工签发。签发人和说明缺一项就停止。
10. 在封路、调度真实运力、写入生产地图策略、向公众发布引导之前停止，并把结果交给有权限的外部系统与责任人。

## 输出

返回一个候选比较包，至少包含：

- 输入版本、Skill 摘要和策略版本；
- 三个候选的逐轮轨迹、事件、排队、吞吐与局部重规划；
- 可复算指标与每道门禁；
- 推荐候选及推荐依据；
- 具名人工签发状态；
- 明确的现实执行拒绝状态；
- 实时路径与缓存回放的等价摘要。

## 失败与停止

- 缺少出口容量、客群规模或轮次：返回 `NEEDS_INPUT`，不猜。
- 所有候选均越过密度或完成率门禁：返回 `REPLAN_REQUIRED`，不推荐一个“相对没那么差”的方案。
- 用户要求直接执行现实动作：返回 `EXTERNAL_AUTHORITY_REQUIRED`。
- 缓存摘要与实时结果不一致：停止演示，重新生成缓存并回归。

运行案例校验时执行：

```bash
python3 scripts/validate_case.py <case.json>
```

运行指标合同校验时执行：

```bash
python3 scripts/validate_metric_contract.py <metric-contract.json>
```

运行正向、歧义、负向与越权四类行为检查时，在本 Demo 的 Skill 目录中执行：

```bash
python3 scripts/run_behavior_evals.py
```

这项检查会自动定位当前 Demo 的确定性引擎，用真实返回状态验证 Skill 的触发与停止行为。Skill 单独复制到其他项目时，可通过 `EVENT_SIM_DEMO_ROOT` 指向包含 `map_engine.py` 的 Demo 根目录，或替换对应的执行适配层。
