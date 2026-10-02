# 验证记录 · 0.1.0

验证日期：2026-10-02（UTC）  
实际环境：Linux，Python 3.12.14  
测试材料：仓库合成 JSON；无真实订单、企业聊天、个人账号或凭据

## 实际通过

```text
python -m unittest discover -s tests -v
Ran 100 tests
OK

python -m compileall -q dots_workflow tests
退出码 0
```

100 个测试方法包含全部 27 个研究验收场景；证据 E01–E08 通过一个方法中的八个 subtest 逐条断言，需求 R01–R08 和行程 T01–T11 分别有命名测试。不是把“文件存在”或“JSON 能解析”当业务成功。

| 模块 | 关键业务断言 |
|---|---|
| 证据 8 场景 | 作者自述不升级、未知引用定位、重复来源不覆盖、未读取保持未知、缺复现记录、输入指令为数据、HTML 协议/转义、重复主张 |
| 需求 8 场景 | 新建议不覆盖旧决定、有效显式替代、互斥决定保留冲突、作用范围隔离、未知引用、循环、转述不授权、倒序结果不变 |
| 行程 11 场景 | 跨午夜、跨时区、本地钟面倒退、负时长、缺时区、不同车站、缺航站楼、明确缓冲、月份错位、旅行 ID 隔离、DST 显式不支持、备注只作资料 |
| 追加需求边界 | 撤回替代链不复活旧决定、重新明确决定、无时区关系、深层循环、重复来源、null 值、布尔/数字区别、输入不变性 |
| 追加行程边界 | 日期变更线、完整偏移 DST、全部重叠对、精确/小数门槛、缺转站时间、重复住宿、退房日不包含、输入不变性 |
| CLI / 内容 | 有效与严格退出码、空任务、坏 JSON、重复键、极大/非有限数字、文件上限、Unicode、HTML/Markdown 注入、输出路径/符号链接保护、不覆盖输入、重复运行字节一致 |

另做过离线随机畸形数据探测：证据/内容 2,000 个输入；需求 4,000 个输入及 2,000 个图关系对照。它们是额外有限探测，不能替代可重复运行的固定测试或证明没有其他缺陷。

仓库 skill 的 YAML/name/description 与正文结构通过当前 skill 校验器；相对文档链接检查通过。格式校验不证明真实产品会自动发现或正确执行该 skill。

## 四个真实 CLI 冒烟运行

```bash
python -m dots_workflow evidence examples/evidence.json --out out/evidence
python -m dots_workflow content examples/content.json --out out/content
python -m dots_workflow requirements examples/requirements.json --out out/requirements
python -m dots_workflow trip examples/trip.json --out out/trip
```

结果：四条命令均退出 0，并写出可解析 result.json、Markdown 和 HTML；content 额外有发布审阅包。evidence 为有限规则通过；content 因推断/待审稿而 needs_review；requirements 中示例显式替代生效且建议未覆盖；trip 保留异站、未知转移时间、门槛不足及住宿未覆盖等问题。`content --strict` 因待审项退出 1，符合预期。

发布审阅包含来源、测试记录、审稿记录、草稿、图像简报和指标；它没有实际生成图像或外发内容。HTML 注入与外部资源隔离有自动测试，未声称完成多浏览器视觉验收。

## 尚未验证

- GitHub 托管与对应 commit 的远端 CI：当前只创建了 CI 配置，远端结果以实际执行为准
- Python 3.10、3.11、3.13 与 Windows/macOS：CI 定义覆盖 3.10–3.13 的 Linux，当前本地只实跑 3.12.14
- pip / wheel 构建、包索引发布与全局安装：快速开始无需这些步骤
- Codex 自动发现 skill、真实模型按流程完成任务、dots 账号/插件或其他 agent 集成
- 实时来源抓取、事实真伪、原作者效果复现、任何商业收益
- 图像服务生成、社交平台发布、日历/邮箱/预订/支付及指标平台读取
- 真实交通可达性、签证或其他法律条件、酒店实际状态

## 下一次改动怎么验

先复跑全套测试与四个例子；规则变化时补相关正常、错误、未知及顺序不变性案例。记录实际 Python 版本、commit、输入和退出码。远端 CI 必须核对本次 commit，不能沿用其他版本的绿灯。任何真实材料须先获得授权，且不进入公开测试或日志。
