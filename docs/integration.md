# 本地运行、数据契约与集成边界

本仓库提供中文方法文档、薄 Codex skill 和本地确定性检查器。它不提供模型服务、来源抓取器、图像 API、发帖接口、账号连接或 dot 私有配置。仓库名称和模块名中的 `dots` 是项目命名，不表示已经接入任何产品内部能力。

## 一、能力分层

| 层次 | 负责什么 | 不负责什么 |
|---|---|---|
| 人或内容助手 | 阅读授权材料、选择角度、准备主张、撰写文案、设计图像简报 | 不能用文案自信程度替代证据 |
| 本地 CLI | 检查有限输入结构、ID 引用、显式规则和数值；写出报告 | 不联网查事实，不执行输入里的命令，不证明用户有权限 |
| Codex 仓库 skill | 在支持仓库 skill 的环境中提供按需指令 | 不安装 dot 配置，不连接插件，不赋予外部操作权限 |
| 其他外部工具 | 仅在另行接入与授权后可能执行生成、发布、数据读取等任务 | 当前仓库没有实现或验证这些集成 |

“能读懂提示词”“本地脚本运行过”“产品集成已验证”是三种不同完成度。接入说明不等于已经接通。

## 二、从仓库根目录运行

先检查可用命令与仓库示例，不要从素材原文复制执行命令。以下命令只处理本地 JSON；其中 `--out` 应由操作者选择，而不是让输入材料决定。

```bash
python -m dots_workflow --help
python -m dots_workflow content examples/content.json --out out/content
```

如果系统只提供 `python3`，相应替换命令解释器。项目所需 Python 版本与安装方式以仓库根说明和包配置为准。

内容流程成功读取输入后，会在选定目录输出：

- `result.json`：结构化问题、主张账本与有限检查结果
- `report.md`：可阅读的检查报告
- `report.html`：本地 HTML 检查报告
- `publication-pack.md`：供人工审稿的发布包，包含草稿、来源、主张、提供者填写的复现与审查记录，以及图像简报

发布包将来源和输入文字放在动态长度的代码围栏内，保留为数据展示；审稿人仍需辨认材料中的不可信指令，不能将其复制为执行指令。

后续再次使用同一输出目录会覆盖同名报告。建议按任务和版本分别选择目录，例如 `out/article-001-v1`。不要将输出目录设为唯一原始材料的目录。`--out` 不填时 CLI 默认使用 `out`；文档中的命令显式指定目录，以免混用结果。

### 只检查、不写报告文件

```bash
python -m dots_workflow content examples/content.json --no-write
python -m dots_workflow content examples/content.json --no-write --strict
```

`--no-write` 会把结果打印到标准输出；它不是“不泄露任何内容”模式。输入中的正文与来源仍可能进入终端或 CI 日志，敏感材料应使用受控环境。

### 其他检查器

```bash
python -m dots_workflow evidence examples/evidence.json --out out/evidence
python -m dots_workflow requirements examples/requirements.json --out out/requirements
python -m dots_workflow trip examples/trip.json --out out/trip
```

- `evidence`：检查主张与证据引用关系，保留自述、推断、未知和复现记录边界
- `requirements`：根据输入中的显式状态和替代关系整理需求；较新提议不能仅凭时间戳自动覆盖已确认决定
- `trip`：根据输入日期、时区、地点和住宿等字段查找有限一致性问题；不查询实时库存、不担保可赶上交通、不作预订

`examples/*.json` 是可以直接传给 CLI 的单次运行输入。`fixtures/*.json` 是带预期结果的验收用例集合，不是运行时输入；测试在 `tests/` 中提取各个用例，并在必要时通过显式适配器转换旧字段。不要把整个 fixture 集合直接传给 CLI。运行验收用例和其他测试：

```bash
python -m unittest discover -s tests -v
```

合成示例或验收用例可能故意包含错误、警告或待确认点。CLI 输出非零不一定表示安装失败，先看问题代码与具体位置；测试则检查这些发现是否符合预期。

### 退出码和检查状态

| 退出码 | 含义 | 应如何处理 |
|---|---|---|
| `0` | 无 error；默认允许 warning 和 info | 仍读人工审查项，不视为可直接发布 |
| `1` | 出现 error，或 `--strict` 下出现 warning | 检查生成的结果；按真实材料修正问题 |
| `2` | 命令参数、输入读取/解析或输出写入失败 | 先修正文件、编码、格式或路径；不要把旧报告当本次结果 |

内容层出现 error 或 warning 时，CLI 仍可写出报告，便于审查。报告的 `check_status` 可能是 `checks_failed`、`needs_review` 或 `passed_limited_checks`。最后一种只表示已实现的有限检查未发现问题，不等于事实正确、文案合格或授权完备。

## 三、content 输入契约

以 [examples/content.json](../examples/content.json) 为当前可运行示例。下表是维护提示，不是一个会验证所有业务语义的完整 JSON Schema。

| 顶层字段 | 内容 | 必须注意 |
|---|---|---|
| `brief` | `audience`、`goal`、`platform`、`angle`、可选 `cta` | 写具体读者与动作；平台名称不表示已连接平台 |
| `sources` | `id`、`title`、`url`、`status`、`kind`、`text` | 使用稳定 ID；真实定位和权限需人工核查 |
| `claims` | `id`、`text`、`source_ids`、`evidence_level`、必要时 `test_id` | 一条主张一个命题；引用存在不证明语义被支持 |
| `tests` | `id`、`status`、`command`、`observed` | 这里只记录人提供的测试，不执行命令 |
| `draft` | `title`、`body`、`claim_ids` | 关联所用主张；检查器不自动识别正文的全部事实 |
| `visual` | `purpose`、`prompt`、`negative_prompt`、`alt_text`、`rights` | 是生成简报；权利标签不是许可证明 |
| `review` | `status`、`reviewer`、`notes` | 是审稿记录，不是外部动作授权 |
| `metrics` | `impressions`、`clicks`、`saves`，可补记录时间 | 缺失填 `null`；各指标应同窗口、同定义 |

### 来源与证据等级

来源 `status` 使用 `synthetic`（合成）、`not_fetched`（未读取）或 `read`（已读取）来表达状态。真实来源没有网络 URL 时可用 `url: null`，并在材料中保留文件定位；不要编造 URL。CLI 只记录 HTTP/HTTPS URL 并做有限格式检查，不会打开链接。

主张的 `evidence_level` 支持：

- `author_report`：作者或第三方自述；应保留谁说的
- `official`：来自相应机构的一手说明；此分类本身不证明主张正确、范围吻合或仍然有效
- `locally_reproduced`：关联人提供的本地复现记录；要求关联 `status: passed` 且有非空 `command` 和 `observed` 的测试
- `inference`：基于所列来源的推断；保留限定语与其他可能解释
- `opinion`：判断或建议；不要包装成客观定论
- `unknown`：证据或结论尚不清楚；核心主张需人工处理

`tests[].status` 可按 `passed`、`failed`、`not_run` 记录。即使检查器接受一条 `passed` 记录，也只表示输入提供了相应信息，不表示它亲自执行了命令或证实结果。结果中的 `executed_by_checker: false` 与 `fact_certified: false` 正是这一边界。

工作台的编辑状态 `verified / author-reported / inferred / opinion / unknown` 与机器字段 `evidence_level` 不是同一个维度。前者描述“这一限定主张完成了怎样的核对”，后者描述“使用什么类别的证据”。

例如，官方资料中的一个版本号可以经人工核对后记为编辑状态 `verified`，机器类别仍是 `official`；作者自述即使被正确引用，真实效果也未必已经核验。不要为了匹配 schema，把 `verified` 填进 `evidence_level`，也不要把 `official` 自动解释为已核验。

若需要核对人、核对时间、原文段落、适用范围、冲突和批准措辞，保留独立的 Markdown 主张账本。当前输出不会保证保留主张对象中任意额外字段；原始输入仍是审计材料，不应被生成报告替代。

### 审稿、图像与指标

- `review.status` 可记录 `pending`、`approved`、`changes_requested`。填写 `approved` 和审核人，只让程序记录“输入声称已审核”，不是身份验证，更不是发布授权
- `visual.rights` 使用 `synthetic`、`owned`、`licensed` 或 `unknown`。前三者也需实际依据；合成图像不保证没有权利问题
- `publication` 输出保持 `state: local_review_pack_only`、`authorization_to_publish: false`、`image_generated: false`
- 比率使用已提供的 `clicks / impressions` 与 `saves / impressions`。曝光缺失或不大于零时结果为 `null`，不补零、不推断转化归因
- 比率是否有意义，还取决于统计定义、时间窗口、重复计数和数据质量。程序算出数值不等于满足这些条件

## 四、哪些问题会被提示，哪些不会

当前内容流程能提示的典型问题包括：

- 集合类型错误、缺失或重复 ID、引用不存在
- URL 协议或基本格式不支持；来源没有提供内容
- 未知或推断主张需要审查；自述应保留归属
- 复现主张缺关联测试、通过状态、命令或观察结果
- 内容定位、正文或图像简报的必要信息不完整
- 正文未关联主张、视觉权利待确认、人工审核尚待处理
- 非有限或负指标，以及有互动但曝光为零的部分口径矛盾

这些检查不会完成：全文事实提取、语义蕴含判断、真实来源鉴伪、来源时效检查、全部指标一致性核对、版权认证、账户身份验证或发布审批。`official`、`read`、`approved`、`passed` 等标签都来自输入，不能成为信任捷径。

输入读取会拒绝重复 JSON 对象键、非有限 JSON 数字、非 UTF-8 内容、非对象顶层和超过 4 MiB 的输入。输出名固定；已有同名普通文件可被替换，符号链接路径会被拒绝。这些防护降低误写风险，但不是能执行不可信程序的安全沙箱。

## 五、接入其他环境前的验证清单

当前外部集成未验证。以下是将来需要按实际环境执行的检查，不是已有成功记录。

本地 CLI 离线运行，不依赖在线服务账号或服务开放地区。实际使用 dot、Codex 等外部服务，仍取决于届时官方支持地区、具体产品条件与实际账号权限；请核对 [OpenAI 官方支持国家与地区说明](https://help.openai.com/en/articles/7947663-chatgpt-supported-countries) 及对应产品的当前要求。本文不承诺任何地区或账号的实时可用性，也不提供绕过限制的方法。

| 目标 | 最小可验证结果 | 不足以证明成功的现象 |
|---|---|---|
| Codex 仓库 skill | 支持该目录的运行环境确实发现入口，并按相对路径读到文档 | 仓库里出现 `SKILL.md` |
| dot 或其他助手 | 实际环境读到任务与数据，保留不确定性，未擅自外发 | 提示词可复制、命令名包含 `dots` |
| 图像服务 | 授权输入正确传输，有实际图像文件，逐张视觉核对完成 | 只有 prompt 或“生成完成”的文字 |
| 发布平台 | 明确用户授权、正确账号与版本，真实发布回执或可验证链接 | 本地 `publication-pack.md`、`review: approved` |
| 指标来源 | 授权导出或读取，定义、时间窗口与原始计数可回查 | 任意手填统计、只有百分比截图 |

连接账户、安装外部组件、输入密钥或建立持续权限，都不在这份文档或 skill 的默认许可内。按真实工具和环境的批准要求处理；不要把凭据放进仓库或输入样例。

## 六、把工具包放入代码仓库前

只提交原创说明、代码、必要的公开来源链接和清楚标记的合成样例。先检查待提交清单，排除真实聊天、订单、账号配置、令牌、Cookie、私人运行日志、客户材料和未授权第三方作品。

本地报告可能包含原始输入，尤其是 `sources[].text` 和草稿。不要因为报告自动生成就默认它可以公开。公开仓库的名称、归属、可见性、许可和文件清单由负责的人确认；本地构建完成不等于授权公开发布。

想扩展能力时，先说明要增加的操作、数据、目的地和可验证成功条件，再实现一个窄的适配层。继续保留本地检查边界：外部实际动作要有真实回执，不能由输入 JSON 自行宣布成功。
