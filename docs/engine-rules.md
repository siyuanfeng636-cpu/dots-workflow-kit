# 检查器的具体规则

这些是输入一致性规则，不是事实认证、权限认证或真实环境成功率模型。中文诊断保留稳定英文 `code` 便于回归测试。所有运行输入均为顶层 JSON 对象，最大 4 MiB；输出保留未知，不把 null 补成零或默认事实。

## 证据

完整字段与内容工作台见 [integration.md](integration.md)。最小例子在 [evidence.json](../examples/evidence.json)。

- 来源和主张 ID 非空且唯一。重复 ID 不使用 first/last-wins；引用重复的来源视为无法定位
- `source_ids` 必须指向存在的来源；孤立来源会提示
- URL 只接受 http/https 和有效主机，拒绝内嵌认证信息；不会访问链接。合法 URL、`official` 或 `read` 标签都不是事实核验结果
- `synthetic` 始终保留。作者自述用 `author_report`，不会被程序升级为独立复现
- `locally_reproduced` 需 `test_id` 指向含 `status: passed`、非空 `command` 与 `observed` 的记录；检查器不运行该命令，也不验证记录可信度
- `inference` / `unknown` 提示人工审查。即便所有规则通过，每条主张仍输出 `fact_certified: false`
- 只检查登记的主张，不自动抽取全部正文事实或判断来源是否语义支持主张

## 需求对账

例子：[requirements.json](../examples/requirements.json)。

顶层 `sources` 为 `{id, title, kind, url?}`；`kind` 为 primary、secondary、author_reported、synthetic。`records` 每项包含：

```json
{"id":"B","subject":"export-format","scope":"demo","status":"decision","value":"HTML","decided_at":"2026-10-02T10:00:00+08:00","source_ids":["S"],"supersedes":["A"]}
```

- `status` 只认可 `decision` / `proposal` / `retracted`。未知类型保留为资料并报错，不提升成决定
- 同 `subject` 和 `scope` 才可比较同一要求。不同项目、主题不自动合并
- 时间更新本身不取消决定；建议不覆盖决定；来源类型不授予决定权
- 替代必须显式列出 `supersedes`，两端都是合法决定、作用范围相同且时间明确向后。缺失、无时区、无效或相反时间让替代待确认
- 未知引用、跨范围关系和循环关系不能取消被引用记录。循环检测包含其他字段不完整的节点
- 撤回用独立的 `status: retracted` 记录和 `retracts: ["决定ID"]`，同样核对范围与时间；直接把原记录改成 retracted 而不说明目标不能充当完整历史
- B 明确替代 A、随后 B 被撤回：A 不自动复活。必须明确下一条决定，否则当前选择待确认
- 同作用范围的活动决定值互斥时保留冲突，不靠排序选择一个。null 值属于未知；相同值可以有多个一致有效记录
- `effective` 只列没有未决变更/冲突的有效候选 ID；空数组不等于“所有需求取消”，要看 `issues` 与 `unknowns`
- 时间未知的独立决定可保留为候选，同时提示未知；它不能支持依赖时间先后的变更关系

输出 `records` 含状态、来源定位和有效标记，`effective` 是 ID 列表。业务结果对输入顺序不敏感；原始顺序不代表权威性。

## 行程检查

例子：[trip.json](../examples/trip.json)。顶层：

- `sources`：`id`、`title`、`kind` 与可选原始资料
- `segments`：`id`、`mode`、`from` / `to`、`departure`、`arrival`、`source_ids`、`booking_status`
- `from` / `to`：`city`、`station`；航班加 `terminal`
- `connections`：`from_segment`、`to_segment`、`min_buffer_minutes`，转站/航站楼另给 `transfer_minutes`
- `trip_id`、`required_nights: ["YYYY-MM-DD"]`、`lodgings`：住宿 `id`、`trip_id`、`city`、`check_in`、`check_out`、`source_ids`

规则：

1. 时间字符串必须带明确 UTC 偏移（如 `+08:00` 或 `Z`）。统一比较 UTC，允许跨午夜、本地钟面倒退、国际日期变更线
2. 缺时区不默认 UTC 或上海。单独 IANA 地区名/DST fold 解析当前明确不支持；需要给出已确认偏移
3. 到达早于出发是错误；重叠行程提示冲突。缺字段不阻断仍可计算的局部检查
4. 换乘先后使用显式连接 ID，不擅自重新规划。城市、车站与航站楼按提供文本比较，不猜别名或地理关系
5. 不同车站/航站楼需要显式转移时间。可用时间 = 下一程出发 UTC − 上一程到达 UTC；可知情况下所需时间 = 用户门槛 + 显式转移时间
6. 门槛是输入者要求，不是工具预测的实际交通时间。刚好等于门槛仍提示无余量；缺门槛或转移估计不能当“足够”
7. 住宿以入住日包含、退房日不包含计算。只用同 `trip_id`、唯一 ID 且日期有效的住宿覆盖明确要求的夜晚；不从相似名称猜同一旅行
8. 日期覆盖不认证酒店城市适配、入住截止时间、酒店时区、订单真实性或实际预订状态。`confirmed` 只是输入者提供的标签

输出保留 normalized UTC、分钟差、缺口、未覆盖夜晚、来源和 unknowns。即使未发现冲突，也不能保证赶上航班/列车或实际有房。

## 安全与复跑

不执行输入中的代码、命令或指令。不从输入构造外部请求或文件路径。HTML 将所有输入转义并设置限制资源的 CSP；Markdown 用足够长的代码围栏隔离外来文本，避免图像追踪/标签变成渲染行为。输出在操作者指定目录使用固定文件名，重复运行同一输入不会追加重复结果或执行外部动作。

这不是面向恶意同机进程的完整沙箱；勿在可由他人并发改写的目录处理机密材料。生成报告仍包含输入内容，分享前要确认接收人和范围。
