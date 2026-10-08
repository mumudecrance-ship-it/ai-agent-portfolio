# 平台调度接口（tools）

> 平台团队提供的三类接口：工作流导入、发布、试运行/结果回读。S7 脚本按此调用；接口描述与工作流定义规范同源（见platform `platform/平台定义文档.md`）。演示环境 base `http://127.0.0.1:8787`，生产环境仅 base URL 与鉴权头不同。

## 1. 导入

`POST {base}/apps/imports`，body `{"definition": <工作流JSON定义>}`
- 201：`{"imported": true, "app_id": "..."}`
- 422：`{"imported": false, "errors": [平台校验错误清单]}`——节点类型非法/边悬空/start缺失等，逐条修

## 2. 发布

`POST {base}/apps/{app_id}/publish` → `{"published": true, "version": n}`
未发布的应用调运行接口返回 409。

## 3. 试运行

`POST {base}/workflows/run`，body `{"app_id": "...", "inputs": {...}}`
→ `{"run_id", "status": "succeeded|failed", "outputs", "error", "elapsed_ms"}`

## 4. 结果回读

`GET {base}/workflows/run/{run_id}` → 完整运行记录：
- `node_runs`: 逐节点 `{node_id, title, type, status, output, error, elapsed_ms}`——失败时恰有一个 failed 节点，实现节点级报错定位
- `skipped_nodes`: 被分支剪枝未执行的节点

## 工作流定义规范要点（编译 07-dsl.json 时对照）

- 顶层：`app.name` / `variables[{name,type,required,example}]` / `graph.nodes` / `graph.edges`
- 变量引用：`{{#节点id.字段#}}`，start 输入用 `{{#inputs.变量#}}`
- 分支出边必须带 `source_handle`（if_else: true/false；分类器: class id）
- 节点 config 字段以 `platform-nodes/` 各节点文档为准，不得虚构字段
