# LLM 节点（llm）

## 能力
- `config.prompt` 内含变量槽位 `{{#节点id.字段#}}`；输出 `text`（原文），若可解析出 JSON 则同时给 `json`
- 一个 LLM 节点 = 一个单一判定/生成任务（方法论第②条），要求 prompt 里显式声明输出 JSON schema

## 真实 DSL 片段
```json
{"id": "judge_hi", "type": "llm", "title": "大于60字低质量判定",
 "config": {"prompt": "只做高质量与低质量判定，输出JSON{verdict,reason}。\n商品：{{#detail.body.product.title#}}\n评价：{{#inputs.review_text#}}"}}
```

## 评价域使用要点
- 判定商品相关性的 prompt 必须把商品信息作为变量传入（质量管控主 prompt 的教训口径）
- 下游要用 `{{#节点id.json.字段#}}` 取值，所以 prompt 必须锁死 JSON 输出格式并给 few-shot
- 判定类输出用 0/1 或枚举，不用自由文本；置信度字段便于设"拿不准转人审"阈值
