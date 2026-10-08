<div align="center">

<img src="assets/banner.svg" alt="AI Agent 作品集 — 两个用工程手段驯化 AI 的项目" width="100%" />

# AI Agent 作品集

<img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"/>
<img src="https://img.shields.io/badge/Agent-Skill-8B5CF6?style=for-the-badge" alt="Agent Skill"/>
<img src="https://img.shields.io/badge/LLM-Workflow-06B6D4?style=for-the-badge" alt="LLM Workflow"/>
<img src="https://img.shields.io/badge/Multi--Agent-10B981?style=for-the-badge" alt="Multi-Agent"/>
<img src="https://img.shields.io/badge/Zero-Dependencies-F59E0B?style=for-the-badge" alt="Zero Dependencies"/>

**两个围绕「用工程手段驯化 AI / LLM」的项目：一个把 AI 从「不可信黑盒」驯化成「可控生产工具」，一个把多 Agent 系统「做对」——协作、确定性、人审、安全边界。**

</div>

━━━━━━━━━━━━━━━━━━━━ ✦ ━━━━━━━━━━━━━━━━━━━━

## 🔧 项目一 · 评价域工作流生产 Skill

> 把「模糊的业务诉求」自动生产成「可上线、可复现的 LLM 工作流」——一个跑在通用 Agent 上的 Skill，配套零依赖的本地工作流平台 FlowBench。

<div align="center">

| ⚡ 生产提速 | 🎯 盲测命中率 | 🧩 想象节点 | 🛡️ 稳定执行率 |
|:---:|:---:|:---:|:---:|
| 25.75 → 2 人日（**26 倍**） | **94%** | **0** | **100%** |

🔗 [查看项目 README](./review-workflow-builder/README.md)

</div>

**核心做法**：把生产流程固化为 **S1–S7 七步**，用**门禁脚本 + 生产台账 + 两层节点库**约束 AI——把「告诉 AI 怎么做」升级为「确保 AI 做了」，让想象节点归零、结构稳定、断点可续跑。

## 🎪 项目二 · 大型活动散场推演 Agent

> 一套本地可运行的「活动散场预演台」：多 Agent 协作 + 确定性仿真引擎 + 具名人工签发，回答普通路线推荐回答不了的问题——**「一群人同时离场时，方案到底成不成立？」**

<div align="center">

| ✅ 单元测试 | 🚧 硬门槛 | 📋 独立审计 | ⚡ 最优清场 |
|:---:|:---:|:---:|:---:|
| **38 / 38** | **8 / 8** | **93 分** | B 方案 16 分钟 0 溢出 |

🔗 [查看项目 README](./event-egress-agent/README.md)

<img src="event-egress-agent/qa/audit-after-desktop-1440.png" alt="散场推演 A/B/C 方案审计结果" width="90%" />

</div>

**核心做法**：多 Agent **并行意图、统一写入**（避免超卖共享容量）+ **确定性仿真引擎**（同一输入同一结果、可回放）+ **具名人工签发** + **权限边界**（现实动作一律拒绝）。

━━━━━━━━━━━━━━━━━━━━ ✦ ━━━━━━━━━━━━━━━━━━━━

## 🧩 技术栈

<div align="center">

<img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/标准库-零依赖-059669?style=flat-square" alt="标准库"/>
<img src="https://img.shields.io/badge/前端-原生_HTML%2FJS-E34F26?style=flat-square&logo=html5&logoColor=white" alt="HTML/JS"/>
<img src="https://img.shields.io/badge/LLM-DeepSeek_%2F_OpenAI-4F46E5?style=flat-square" alt="LLM API"/>
<img src="https://img.shields.io/badge/方法-四层约束%2B盲测验收-DB2777?style=flat-square" alt="方法论"/>

</div>

- **Python 3.8+**：两项目后端均为标准库 / 零或极少第三方依赖
- **Agent / Skill**：通用 Agent Skill 格式，跨平台
- **LLM 工作流平台**（自建 FlowBench）+ 多 Agent 确定性仿真系统
- **前端**：原生 HTML / JS，响应式
- **方法论**：工作流拆解五步、设计五原则、四层约束、盲测验收、硬门禁评测

## 📂 目录结构

```
ai-agent-portfolio/
├── review-workflow-builder/   项目一：评价域工作流生产 Skill + FlowBench 平台
└── event-egress-agent/        项目二：大型活动散场推演 Agent
```

## 🚀 快速开始

```bash
# 项目一：FlowBench 工作流平台
cd review-workflow-builder/platform && python platform.py
# → http://127.0.0.1:8787

# 项目二：散场推演台
cd event-egress-agent && python3 server.py --port 8927
# → http://127.0.0.1:8927
```

━━━━━━━━━━━━━━━━━━━━ ✦ ━━━━━━━━━━━━━━━━━━━━

<div align="center">

> 本项目所有业务数据均为演示用 mock 数据，不涉及任何真实公司信息。

🌈 用工程手段驯化 AI，把「黑盒」变成「可复现的生产线」。

</div>
