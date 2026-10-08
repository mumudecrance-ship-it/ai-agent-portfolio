# HTTP 请求节点（http_request）

## 能力
- `config`: method / url / body（可含槽位）/ timeout；输出 `status_code`、`body`
- 对接一切公司业务能力：图像文本基础能力、商品信息中心、评价查询服务、词云服务

## 真实 DSL 片段
```json
{"id": "same_img", "type": "http_request", "title": "同图识别",
 "config": {"method": "POST", "url": "http://127.0.0.1:8787/mock/svc/same-image",
   "body": {"image_urls": "{{#inputs.image_urls#}}"}}}
```

## 评价域使用要点
- 业务节点的 url/入参/返回口径查 `domain-nodes/`，**不得凭空写接口**——不在库内的能力标记为缺口
- 接口失败即节点失败并停流程，节点级报错可在运行回读里定位；重试/降级策略在方案里显式写
- 三态返回（0/1/2）的语义必须按 domain-nodes 的口径下传给分支节点
