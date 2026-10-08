---
name: review-workflow-builder
description: 评价域工作流生产 skill。按步骤理解一个工作流需求、分步拆解、直至在平台上跑通：业务澄清→依赖分析→流程拆解→节点映射→prompt起草→方法论审查→平台落地跑通。状态由生产台账管理，推进权在门禁脚本，节点必须出自两层节点库。
---

# review-workflow-builder

## 总规则

- 每个生产任务：`python scripts/ledger.py init <任务名>` 建 `../runs/<任务名>/`。**runs 与 skill 平级存放（生产产物不属于 skill 本体）；任务状态的权威数据源是 ledger.json，一切状态读写经 ledger.py，进度视图只读。**
- 推进权在脚本：当前步骤产物落文件 → 跑门禁脚本 → 通过后 `ledger.py pass <任务名> <步骤>`。门禁不过就停在原地修，**不许跳步，不许口头声称完成**。
- 下一步只允许读上一步的产物文件。

## S1 业务澄清 → `01-工作流画像.md`
读 `references/intake-questions.md`，只问业务四问（红线：零技术提问）。产物五段：业务问题/成功标准/产出对象与形态/量级与频率/人审底线。
门禁：`python scripts/check_profile.py <任务名>`

## S2 依赖分析 → `02-依赖清单.md`
**skill 自己干，不问用户**：从画像推断输入数据与外部能力，逐项查 `references/domain-nodes/`，标注 已有可用/演示需mock/缺失需人补。清单交用户**确认与纠正**，产物须含用户确认记录。
门禁：`python scripts/check_dependencies.py <任务名>`

## S3 流程拆解与设计审查 → `03-流程拆解.md`【本 skill 的核心步骤】
严格按 `references/decomposition-guide.md` 五步走：
1. **目标倒推**：从产出字段倒推信息件清单——不在倒推链上的步骤删
2. **最便宜手段**：每个信息件按 传统→接口→LLM→人工 顺位选型，LLM 步骤必须写"为什么非LLM不可"
3. **漏斗排序**：便宜且过滤性强的放上游，贵的晚做少做；产出开销预估表（含日执行次数漏斗估算）
4. **分支/并行/汇聚**：可被剪枝的串行放下游，必须都执行的才并行
5. **三态出口**：判定节点 是/否/拿不准，拿不准走人审
产物三件套：信息件倒推表、步骤表（输入/输出/判断类型/非LLM不可理由/失败去向）、开销预估表。
门禁：`python scripts/check_decomposition.py <任务名>`

## S4 节点映射 → `04-节点方案.md`
S3 每步映射到具体节点：平台通用节点查 `references/platform-nodes/`（11类），业务能力查 `references/domain-nodes/`。**每个节点必须在库内有出处**，分支句柄与汇聚连线写全。拆法参照 `references/examples/`。
门禁：`python scripts/validate_solution.py <任务名>`

## S5 prompt 起草 → `05-prompts/*.md`
只为 LLM 节点写。按 `references/prompt-examples/00-四类节点模板.md` 选类，生产级范本 A3/A4/A7。每个 prompt 必备：单一任务声明、输入变量、严格 JSON schema、few-shot（含易混淆例）。
门禁：schema 完整性自检后 `ledger.py pass`（备注各 prompt 的输出 schema）。

## S6 方法论审查 → `06-审查报告.md`
按 `references/methodology.md` 五条逐项过审（通过/不通过/不适用 + 证据）。生成与审查分离：审查时只出报告不改方案；不通过项改完复审，清零才放行。
门禁：报告落文件且五条清零后 `ledger.py pass`。

## S7 平台落地与跑通验证 → `07-dsl.json` + `08-跑通报告.md`
1. 按 `references/tools/platform-api.md` 的定义规范把节点方案编译为 `07-dsl.json`
2. `python scripts/platform_deploy.py <任务名>`（导入+发布，平台校验错误即停）
3. 写 `08-测试输入.json`（含正常用例与失败注入用例），`python scripts/platform_run.py <任务名>`（试运行+回读断言+节点级报错定位）
4. `python scripts/render_canvas.py <任务名>` 生成 `09-画布.html`——自包含静态画布快照，浏览器直接打开可看节点图，不依赖平台运行
**跑通才算完事**：跑通报告全部用例通过，`ledger.py pass <任务名> S7`。

## 问题回流与迭代（仅 DONE 后）
线上/验收发现 bad case 时不新开任务，在原任务内回流：
1. 归因落文件 `../runs/<任务名>/bad-case/<caseid>-归因.md`，七段：case描述/复现输入/实际输出/期望输出/五层归因（主因：输入/数据/工具/流程/模型）/第一次偏离步骤/证据链。五层与步骤的参考映射：输入→S1、数据→S2、流程→S3、工具→S4/S7、模型→S5
2. 门禁：`python scripts/check_attribution.py <任务名> <归因文件名>`
3. `python scripts/ledger.py reopen <任务名> <步骤> <归因文件名>`：仅 DONE 可重开，目标步骤须与归因定位一致；该步起旧产物自动归档 `_history/<时间戳>/`，下游步骤级联置为待开始——**不许带着 passed 状态的下游账目改上游**
4. 从重开步骤按原门禁重走到 S7，跑通才算迭代完成
