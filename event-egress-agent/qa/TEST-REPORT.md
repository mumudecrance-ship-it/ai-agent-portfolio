# 测试报告

日期：2026-08-24  
服务端口：`127.0.0.1:8927`

## 自动检查

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`：38 / 38 通过。
- `python3 skill/simulate-event-egress-plan/scripts/run_behavior_evals.py`：4 / 4 通过。
- `python3 -m py_compile server.py live_agent.py map_engine.py project_rules.py tests/*.py`：通过。
- `app.js` 与 `project.js` JavaScript 语法检查：通过。
- `project.json` 与实时输出 Schema JSON 检查：通过。
- 交付目录 API Key 特征扫描：未发现真实 Key。
- 8925 / 8926 端口残留扫描：未发现；当前项目统一使用 8927。

## 后端行为

- 2 个出口可运行，8 个出口可运行；少于 2 或多于 8 会拒绝。
- 重复出口 ID、无效容量、客群人数与总人数不等会拒绝。
- 无突发事件也可以运行 A/B/C，不强行制造事件。
- 动态事件只能引用当前场馆实际存在的出口 ID。
- 同一输入的证据摘要一致，三个候选都返回 12 轮轨迹。
- AI 返回 `NEEDS_CLARIFICATION`、不存在的出口/客群、无效轮次或容量乘数时，确定性仿真不会继续。
- DeepSeek 根端点会归一化到 Chat Completions，并使用 JSON Object + Schema 指令。
- API Key 状态只返回末 4 位掩码，页面配置标记为 `PROCESS_MEMORY_ONLY`。
- 尝试现实封路或调度会返回 `EXTERNAL_AUTHORITY_REQUIRED`。

## 浏览器验收

- 桌面端 1440 × 1000：页面横向溢出 0 px。
- 移动端 390 × 844：页面横向溢出 0 px；候选比较表在自身容器内横向滚动。
- 固定目标方案运行后：5 个数据流节点依次到达，前 4 个为“已交出”，人工节点为“等待确认”。
- 固定目标方案运行后：A/B/C 候选 3 行，仿真轮次 12 个，队列账本、客群意图和场馆出口均可见。
- 移动端出口编辑：4 个出口可添加到 5 个，删除后回到 4 个，场馆草图标记同步更新。
- 模式切换与 Agent 展开状态会同步 `aria-pressed` / `aria-expanded`；390px 下无页面级横向溢出。
- 首屏主状态显示“可以开始固定回放”等中文说明；结果证据仍保留少量机器状态码，作为后续可读性优化项。
- 未配置 API Key 运行实时模式：显示 `API_KEY_REQUIRED`，Agent 流程节点转为失败，固定结果仍为空，页面明确说明没有切回 Mock。
- 浏览器控制台 warning / error：0。

## 视觉证据

- `qa/audit-after-desktop-1440.png`：桌面端 A/B/C 比较、第 5 轮事件、队列传播和客群流向。
- `qa/audit-after-mobile-390.png`：移动端轮次、场馆与客群流向。

## 已知局限

- 未使用真实付费 Key 做网络调用；已通过可控的 DeepSeek 响应适配测试验证请求体、JSON 解析和后续规则交接。
- 场馆草图是按用户配置方位生成的仿真图，不是现实 GIS 底图。
- 未单独配置客群时，代码会均分生成最多 4 个客群；分区说明只用作 AI 理解上下文。
- 所有队列阈值与容量都是固定案例的仿真参数，不构成现实安全评估或任何官方标准。
- 390px 下品牌入口约 34px、确认输入约 38px，尚未达到 44px 触控建议值。
