# AI Agent 项目作品集

两个围绕「用工程手段驯化 AI / LLM」的项目：一个把 AI 从「不可信黑盒」驯化成「可控生产工具」，一个把多 Agent 系统「做对」——协作、确定性、人审、安全边界。

| 项目 | 一句话 | 核心亮点 |
|---|---|---|
| [review-workflow-builder](./review-workflow-builder) | 把模糊业务诉求自动生产成可上线的 LLM 工作流 | 分层约束 + 脚本门禁 + 状态台账，生产耗时 26 倍压缩 |
| [event-egress-agent](./event-egress-agent) | 大型活动散场推演的多 Agent 系统 | 并行意图/单写者结算 + 确定性引擎 + 具名人工签发 |

---

## 项目一：评价域工作流生产 Skill

**问题**：评价域 AI 工作流的生产靠少数人手工完成（单条约 25.75 人日），能力门槛高、方法论内隐、迭代成本高。

**做法**：设计一个跑在通用 Agent 上的 Skill，把生产流程固化为 **S1–S7 七步**，用**门禁脚本 + 生产台账 + 两层节点库**约束 AI，把「告诉 AI 怎么做」升级为「确保 AI 做了」。

**结果**：单条生产耗时 **25.75 人日 → 2 人日（约 26 倍）**，盲测节点命中率 **94%**，想象节点 **0**，流程稳定执行率 **100%**。

详见 [review-workflow-builder/README.md](./review-workflow-builder/README.md)

## 项目二：大型活动散场推演 Agent

**问题**：普通路线推荐只回答「一个人怎么走」，散场推演要回答「12000 人同时走，方案成不成立」；旧静态方案无法响应突发事件。

**做法**：多 Agent 协作（**并行意图、统一写入**，避免超卖共享容量）+ 确定性仿真引擎（同一输入同一结果、可回放）+ 具名人工签发 + 权限边界（现实动作一律拒绝）。

**结果**：固定案例中 B 方案 16 分钟 0 溢出清场；**38/38 测试、8/8 硬门槛、独立审计 93 分**。

详见 [event-egress-agent/README.md](./event-egress-agent/README.md)

---

## 技术栈总览

- **Python 3**（两项目后端均为标准库 / 零或极少第三方依赖）
- **Agent / Skill**：通用 Agent Skill 格式，跨平台
- **LLM 工作流平台**（自建 FlowBench）+ 多 Agent 仿真系统
- 前端：原生 HTML / JS，响应式
- 方法论：工作流拆解五步、设计五原则、四层约束、盲测验收、硬门禁评测

## 目录结构

```
ai-agent-portfolio/
├── review-workflow-builder/   项目一：评价域工作流生产 Skill + FlowBench 平台
└── event-egress-agent/        项目二：大型活动散场推演 Agent
```

## 如何运行

- 项目一：`cd review-workflow-builder/platform && python platform.py` → http://127.0.0.1:8787
- 项目二：`cd event-egress-agent && python3 server.py --port 8927` → http://127.0.0.1:8927

> 本项目所有业务数据均为演示用 mock 数据，不涉及任何真实公司信息。
