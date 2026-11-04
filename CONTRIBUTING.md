# Contributing to VLX-Flow

English | [中文](#中文说明)

This repository publishes the official VLX-Flow technical overview, capability demonstrations, and evaluation summaries. Model training and inference code will not be open-sourced. The repository currently provides no model weight downloads or local deployment packages.

## Contribution Scope

- Documentation corrections and clearer technical explanations
- Broken links or demonstration asset issues
- English and Chinese wording alignment
- Evaluation source, metric definition, and reporting corrections
- Usage feedback and application suggestions

Changes to model training, inference implementation, or checkpoint packaging are outside this repository's contribution scope.

## Issue Guidelines

Include the affected page or asset, the issue, and the expected behavior or wording. For evaluation questions, identify the benchmark, metric, model version, and supporting source.

Examples:

- "The Chinese README describes a capability differently from the English version."
- "The proactive response figure does not load on GitHub."
- "The latency description needs to distinguish first-token delay from complete-answer latency."

## Pull Request Guidelines

- Keep English and Chinese pages aligned for capability claims, metrics, and repository scope.
- Cite sources for numerical results and distinguish reported results from new measurements.
- Keep local asset links relative to the document and verify they resolve within this repository.
- Do not add model installation instructions, code-release promises, or unannounced weight availability.
- Keep changes focused and explain their purpose.

## 中文说明

本仓库提供 VLX-Flow 的官方技术介绍、能力展示素材和评测摘要。模型训练与推理代码不对外开源，当前仓库不提供模型权重下载或本地部署包。

欢迎贡献文档修正、技术表述改进、失效链接与素材问题修复、中英文内容对齐、评测来源与指标说明修正，以及使用反馈和应用建议。模型训练、推理实现与权重打包不属于本仓库的贡献范围。

提交 issue 时，请说明涉及的页面或素材、具体问题和预期表述。评测问题请注明基准、指标、模型版本及来源。

提交 PR 时，请同步维护中英文能力表述、评测数据和仓库范围；为数值结果提供来源，区分已报告结果与新增测试；使用文档相对路径引用本仓库素材并检查链接。请勿添加模型安装说明、代码开放承诺或尚未宣布的权重下载信息。每次修改应聚焦具体问题，并说明修改目的。
