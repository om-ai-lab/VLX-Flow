# Contributing to VLX-Flow

English | [中文](#中文说明)

This repository publishes the official VLX-Flow technical overview, capability demonstrations, evaluation summaries, and public API client notebooks. Model training and inference code will not be open-sourced. The repository currently provides no model weight downloads or local deployment packages.

## Contribution Scope

- Documentation corrections and clearer technical explanations
- Broken links or demonstration asset issues
- English and Chinese wording alignment
- Evaluation source, metric definition, and reporting corrections
- Usage feedback and application suggestions
- Fixes and improvements to the public API notebooks, client helpers, and interaction UI in `examples/`

Changes to model training, inference implementation, or checkpoint packaging are outside this repository's contribution scope.

## Issue Guidelines

Include the affected page or asset, the issue, and the expected behavior or wording. For evaluation questions, identify the benchmark, metric, model version, and supporting source.

For API demo issues, include the notebook and step, Python/dependency versions, the selected model, and a short event or error excerpt. Remove access tokens, private video URLs, and personal paths before sharing. Report whether the issue occurs in the basic notebook, the playground, or both.

Examples:

- "The Chinese README describes a capability differently from the English version."
- "The proactive response figure does not load on GitHub."
- "The latency description needs to distinguish first-token delay from complete-answer latency."

## Pull Request Guidelines

- Keep English and Chinese pages aligned for capability claims, metrics, and repository scope.
- Cite sources for numerical results and distinguish reported results from new measurements.
- Keep local asset links relative to the document and verify they resolve within this repository.
- Do not add model installation instructions, model-code release promises, or unannounced weight availability.
- Keep changes focused and explain their purpose.
- For API client changes, run `python -m unittest discover -s examples/tests -v` using the dependencies in `examples/requirements.txt`. These tests use simulated connections; live API validation is separate and should be identified as such.
- Clear notebook outputs, execution counts, and saved Widget State before submitting. Keep parallel sessions opt-in and preserve the explicit start/stop workflow.
- Update [example instructions](examples/README.md) when changing parameters, sample paths, or the run order.

## 中文说明

本仓库提供 VLX-Flow 的官方技术介绍、能力展示素材、评测摘要和公开 API 客户端 Notebook。模型训练与推理代码不对外开源，当前仓库不提供模型权重下载或本地部署包。

欢迎贡献文档修正、技术表述改进、失效链接与素材问题修复、中英文内容对齐、评测来源与指标说明修正，以及使用反馈和应用建议。`examples/` 下的 API Notebook、客户端辅助代码和交互界面也接受修复与改进。模型训练、推理实现与权重打包不属于本仓库的贡献范围。

提交 issue 时，请说明涉及的页面或素材、具体问题和预期表述。评测问题请注明基准、指标、模型版本及来源。

API 示例问题请注明 Notebook、操作步骤、Python 与依赖版本、模型 ID，以及简短的事件或错误摘要；分享前移除令牌、私有视频 URL 和个人路径，并说明问题出现在基础版、进阶版还是两者都有。

提交 PR 时，请同步维护中英文能力表述、评测数据和仓库范围；为数值结果提供来源，区分已报告结果与新增测试；使用文档相对路径引用本仓库素材并检查链接。请勿添加模型安装说明、模型代码开放承诺或尚未宣布的权重下载信息。每次修改应聚焦具体问题，并说明修改目的。

修改 API 客户端后，使用 `examples/requirements.txt` 中的依赖运行 `python -m unittest discover -s examples/tests -v`。该测试使用模拟连接，线上验证需单独说明。提交前清除 Notebook 输出、执行计数与 Widget State；保持并行调用默认关闭，并保留显式启动和停止流程。参数、示例路径或运行顺序变化时，同步更新[示例说明](examples/README.md)。
