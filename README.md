# dots-workflow-kit · 中文内容工作台

把来源变成可追溯的选题、主张账本、文案、配图说明和发布审阅包，再用真实指标复盘。

这是一套**原创方法文档 + 零第三方运行时依赖的 Python CLI + 薄 Codex skill**。它负责保留证据与检查明确规则；创作、语义核验、实际出图和发布由人及已授权工具完成。

## 先跑一次

需要 Python 3.10+。在解压后的仓库根目录运行，无需 pip 安装、API key 或登录：

```bash
python -m dots_workflow --help
python -m dots_workflow content examples/content.json --out out/content
python -m unittest discover -s tests -v
```

只有 `python3` 命令时把 `python` 替换为 `python3`。Windows 可使用已安装的 `py -3`。这些命令不下载依赖、不启动服务。

打开 `out/content/report.html` 查看本地报告；审阅 `out/content/publication-pack.md`。示例会显示待人工审查的推断和待审稿状态，这是预期结果。HTML 不加载外部资源，没有脚本。浏览器任选；若使用 Chrome，直接打开本地文件即可。

## 四个命令，三个确定性检查引擎

| 命令 | 用途 | 示例关键结果 |
|---|---|---|
| `content` | 串起定位、主张、文案、视觉说明、审查与指标 | 发布包保留来源、审查状态和未知数据，不外发 |
| `evidence` | 主张到来源的引用与证据类型检查 | 作者自述不会升级为独立实测 |
| `requirements` | 需求版本对账、显式替代及撤回 | `format-replacement`、`keyboard-navigation` 为有效决定；更新建议不覆盖它们 |
| `trip` | 跨时区时间、明确换乘门槛、住宿覆盖 | 同城不同站、未知转站时间、缓冲不足和住宿月份错位可见 |

```bash
python -m dots_workflow evidence examples/evidence.json --out out/evidence
python -m dots_workflow requirements examples/requirements.json --out out/requirements
python -m dots_workflow trip examples/trip.json --out out/trip
python -m dots_workflow content examples/content.json --no-write --strict
```

最后一个命令预期退出 1，因为合成内容仍需人工审查。默认：错误退出 1，只有警告仍退出 0；`--strict` 使警告也退出 1；读取/解析/写入失败退出 2。**退出 0 不代表事实正确、已获得发布授权或行程一定可行。**

## 从资料到成品

1. [中文工作台](docs/content-workbench.md)：七步流程、原创合成案例、每一步的交付物
2. [可复制提示词](docs/prompts.md)：素材整理、角度选择、事实核查、文案、图像说明、审稿、发布包和复盘
3. [输入与接入](docs/integration.md)：字段、退出码、能力边界和未来集成验证清单
4. [业务规则](docs/engine-rules.md)：证据、需求、行程的具体规则与未知项
5. [测试记录](docs/validation.md)：实际运行过什么，哪些从未验证
6. [来源与原创边界](docs/references.md)：方法背景和公开链接

`examples/` 是可直接运行的合成任务。`fixtures/` 是 27 个研究验收场景的集合，**不是 CLI 输入格式**；由 `tests/` 中显式适配器执行，测试具体结论而不是只检查 JSON 结构。

## 输出及保密

每次写出 `result.json`、`report.md` 和 `report.html`；`content` 额外写 `publication-pack.md`。同目录同名文件会被替换，建议每个任务/版本使用独立目录。源文件不修改，固定输出名不由 JSON 控制；符号链接输出路径会被拒绝。结果可能保留完整素材，勿把真实私密资料的报告提交到公共仓库。

本工具没有网络客户端、凭据读取、shell 执行、邮件或支付接口。输入里写“上传”“执行命令”“发布”不会触发外部动作。图像简报并不是已生成图片，`review.status=approved` 也不赋予发布授权。

## dots / Codex 使用范围

`.agents/skills/content-workbench/SKILL.md` 是仓库内薄指令入口，YAML `name` / `description` 加 Markdown 正文。它不是个人 dot 配置或可复制的内部系统提示词。可以让支持该格式的 Codex 环境读取；当前仅校验了文件格式、文档链接和本地 CLI，**未验证产品自动发现、真实模型行为、账号插件或个人 dot 的集成链**。

离线 CLI 不依赖任何在线地区服务可用性。中文材料不代表任一账号或地区可以使用 dots/Codex；访问外部服务前检查[官方支持地区](https://help.openai.com/en/articles/7947663-chatgpt-supported-countries)及账号实际权限。本项目不提供访问限制绕过方案。

## 开发与许可

```bash
python -m unittest discover -s tests -v
python -m compileall -q dots_workflow tests
```

首次本地测试使用 Linux / Python 3.12.14；提交 `e152d206dc8ca88e91a1151545a7dc1b1b4481a1` 的 Python 3.10–3.13 Linux CI 已全部通过，精确运行链接见[测试记录](docs/validation.md#github-发布与远端-ci-已验证)。后续提交仍需核对各自 CI，不能沿用此前的绿灯。

运行代码只用标准库。可选的 `pip install .` 打包安装会使用 setuptools 构建依赖，可能触发包索引访问；快速开始不需要这一步。

MIT 许可。代码、提示词与合成样例为本项目原创；公开参考链接不意味着复制了第三方教程、获得对方背书或复现其效果。
