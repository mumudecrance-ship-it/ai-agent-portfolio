# 05 prompts · 评价质量自动审核（六个 LLM 节点）

> 每节点按判定类模板（范本 A3）：单一任务声明 + 输入变量 + 严格 JSON schema + few-shot（含易混淆例）。此处为规格与 schema，few-shot 全文在节点配置内。

## judge_hi 大于60字低质量判定
- 单一任务：只判 高质量候选(0)/疑似低质量(1)，不做类型细分、不做深度校验
- 输入变量：review_text、商品标题/卖点（detail）
- schema：`{"verdict": 0|1, "reason": str, "confidence": 0~1}`
- few-shot 要点：阴阳怪气反例（夸赞句式表达差评）、软广反例、正常长评正例；低置信输出如实标注（触发转审）

## judge_lo 小于60字低质量判定
- 单一任务：只判 普通(0)/疑似低质量(1)；短文本不进高质量
- 输入/schema 同上
- few-shot 要点：站外引流、纯情绪短评、正常短评

## tpl_chk 套模板校验
- 单一任务：只判是否套模板；参照 rag_tpl 检索的本商品历史高质量评价
- 输入变量：review_text、检索结果 top20
- schema：`{"is_template": 0|1, "template_text": str|null}`
- few-shot 要点：同义改写模板（易混淆）、真实个性化长评

## precision 商品价值描述精准度
- 单一任务：只判评价是否准确描述了该商品特点
- 输入变量：review_text、商品标题/卖点/参数
- schema：`{"accurate": 0|1, "matched_points": [str]}`

## after_use 是否使用后评价
- 单一任务：只判是否为使用后的评价（有使用痕迹）
- 输入变量：review_text、商品信息
- schema：`{"after_use": 0|1, "evidence": str|null}`

## low_type 低质量类型细分
- 单一任务：初筛判 1 的子集分类：广告引流/极端情绪/跑题/水字数/拼写混乱/客观差评
- 输入变量：review_text（广告引流/极端情绪生产态挂案例库参照）
- schema：`{"type": "<六类枚举>", "confidence": 0~1}`
- 特殊口径：客观差评且无过分词汇→下游综合判断放行正常展示
