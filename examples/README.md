# VLX-Flow API Notebooks

两个入口按学习阶段组织，仅包含线上 API 客户端与展示代码，不包含模型训练或推理实现。

| Notebook | 用途 | 内容 |
| --- | --- | --- |
| [01 · API 基础](notebooks/01_api_quickstart.ipynb) | 学会独立接入 | 上传、指令与参数、WebSocket、流式接收、同会话追问、停止、可选双路并行 |
| [02 · 进阶交互](notebooks/02_interactive_playground.ipynb) | 体验与组合能力 | 视频预览、调参、描述／检测指令预设、追问、双路结果与统一停止 |

进阶版把基础版的调用组织成按钮和结果区域。想了解运行单元格后为何出现页面、按钮如何调用 API，以及两个 Python 文件的职责，先读[进阶版工作原理](docs/interactive_playground.md)。

## 安装与启动

需要 Python 3.10 或更高版本（当前使用 Python 3.13 验证），以及平台提供的 HTTPS API 根地址、访问令牌和模型权限。双路模式需要至少两个可用并发会话。视频会上传到平台，模型调用产生的用量以平台返回为准。

从仓库根目录运行（已有 `.venv` 时无需重新创建）：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r examples/requirements.txt
python -m ipykernel install --user --name vlx-flow-demos --display-name "Python (VLX-Flow Demos)"
python -m jupyterlab
```

在 JupyterLab 文件栏中打开 `examples/notebooks/` 下的文件，选择 **Python (VLX-Flow Demos)** 内核。从仓库根目录启动可同时查看示例说明、工作原理与辅助代码。

只学习基础版可以安装 `examples/requirements-basic.txt`，无需 anywidget。已有依赖可直接使用。`USE_PROXY=True` 表示使用环境代理；直连可改为 `False`。依赖已包含 SOCKS 支持。

## 示例视频与默认指令

两份 Notebook 使用不同的本地视频，视频地址在上传后保存在当前内核中。

| 视频 | 使用位置 | 时长 / 格式 | 检测示例 |
| --- | --- | --- | --- |
| [video01](assets/videos/vlxflow-video01_keyframe_1s.mp4) | 基础版及其可选并行章节 | 30 秒，H.264 MP4，640×480 | 夕阳出现时汇报 |
| [video04](assets/videos/vlxflow-video04_keyframe_1s.mp4) | 进阶版 | 30 秒，H.264 MP4，640×480 | 咖啡制作与拉花完成时汇报 |

描述指令统一为 `持续观看视频画面, 并描述画面内容`。基础版的检测指令是 `持续观看视频画面, 当画面中出现夕阳的时候向我汇报`；进阶版是 `持续观看视频画面, 当视频中的咖啡制作完成并完成拉花的时候, 向我汇报, 输出: 咖啡制作完成`。

替换视频时修改 Notebook 的 `VIDEO_PATH`，相应调整检测指令，再重新运行上传步骤。默认演示时限为 60 秒，给视频结束后的尾部回答和追问留出时间；视频源结束本身不会立即关闭会话。

## 基础版运行顺序

手动逐块运行，不要直接 Run All。

1. 第 1 步导入依赖，第 2 步输入鉴权、设置视频与指令。
2. 第 3 步上传视频，第 4 步查看创建请求预览（不调用模型）。
3. 第 5 步先运行两块函数定义，再运行启动块。此时创建线上会话并产生用量，文本逐段更新；默认 60 秒自动停止。
4. 首轮分析到达后，第 6 步填入 `QUESTION` 并运行。在上一问完成后可修改问题再次运行；停止后的会话需重新创建。
5. 第 7 步停止并确认关闭，可重复运行。
6. 可选的第 8 步将 `RUN_PARALLEL` 改为 `True`，启动描述与检测两个独立会话。试用后执行“停止两路”或第 7 步。

基础版直接展示上传、连接、创建 JSON、接收循环与发送追问的代码。`RealtimeSession` 管理后台任务和清理，`EventState` 管理去重、文本拼接、追问关联与用量；实际接收函数在 Notebook 单元格中定义和执行。普通 `text/plain` 输出按 `display_id` 更新，不依赖播放器或前端文件。

## 进阶版运行顺序

依次执行第 1–4 步，点击「开始分析」才会调用模型。可以选择：

- 持续描述：一个会话，使用描述指令。
- 主动检测：一个会话，使用条件检测指令。
- 描述＋检测：两个会话，各自指令、结果和用量，共用下方采样与生成参数。

首轮分析到达后可发送追问；双路时选择目标会话。每路同时只允许一条未完成追问，问题与回答单独显示。修改运行配置时先「全部停止」，确认关闭后再开始；无需重新上传视频。任一路运行失败会停止另一条活动会话，关闭未确认时阻止新建。

第 5 步为备用停止入口，第 6 步为可选诊断。关 Notebook 或重启内核前先正常停止。

## 参数与协议

默认模型 ID 为 `VLX-Flow-1.5-10B`，实际可用模型与 API 根地址以平台为准。

| 字段 | 示例初始值 | 范围与含义 |
| --- | --- | --- |
| `instruction` | 持续观看视频画面, 并描述画面内容 | 创建会话时的持续分析指令，最多 16384 字符 |
| `interval_seconds` | 1000 | 实际单位为毫秒，1000–2000 |
| `batch_size` | 2 | 每累计 1 或 2 张新帧触发分析 |
| `window_size` | 基础版 4；进阶版 8 | 窗口数，范围 1–8 |
| `temperature` | 0.2 | 0 ≤ 值 < 2 |
| `max_tokens` | 32 | 每轮 1–32 tokens |

自动停止时限为本地控制，支持 5–600 秒，不作为模型参数发送。描述与检测均通过 `instruction` 表达，没有额外的模式参数。

追问在原连接中发送 `response.create`，问题放在 `data.prompt`（最多 2000 字符），不会停止持续分析；`algorithm.analysis` 与 `algorithm.inquiry` 分开处理，通过 `response_id` 关联回答。`response.cancel` 只取消指定回答，`session.close` 才是结束会话。发送结果未知时不自动重发。

## 使用边界

- 双路复用同一视频 URL，但需要至少两路并发额度，分别产生用量，处理进度可能不同。
- 本地预览与服务端分析独立；暂停、拖动播放器不会控制分析进度，追问也不定位到本地当前帧。
- 已观察到 `frameTime` 返回日期时间；页面使用 `timestamp_ms / 1000` 标注服务端相对时间，尚未确认其基准为视频开头。
- 基础版顶部与页面每路底部的秒数是本地已运行时长；页面回答旁的时间属于当前展示的有效结果。检测没有新有效内容时会保留旧结果时间，不能仅凭两路标签差值判断处理进度差。
- 基础版显示最近一轮原文，包括省略号。进阶版折叠空文本／省略号并单独计数，保留用量，不能把折叠当作模型静默的证据。
- 指令遵循、语言和检测触发效果需要使用实际模型验证，客户端不自动翻译输出。
- 每轮用量包含分析与追问；关闭时的服务端累计值替换本地累计，不再次相加。

## 文件与验证

| 文件 | 职责 |
| --- | --- |
| [flow_api.py](flow_api.py) | `RealtimeSession` 管理单个 API 会话；`EventState` 处理流式文本、追问关联、去重与用量。基础版和进阶版共用。 |
| [flow_demo.py](flow_demo.py) | `InteractivePlayground` 将页面操作映射到一路或两路会话。进阶版使用。 |
| [flow_player.js](flow_player.js) / [flow_player.css](flow_player.css) | Notebook 内嵌组件的按钮、播放器、结果展示与样式。 |

视频只放在 `assets/videos/`，引用相对路径。文件之间的调用关系见[工作原理](docs/interactive_playground.md)。

令牌和视频 URL 仅保存在 Python 内存，不同步到浏览器控件。提交前停止会话，清除 Notebook 输出和保存的 Widget State，避免嵌入视频或运行数据。

离线验证（模拟连接与响应，不访问平台）：

```bash
python -m unittest discover -s examples/tests -v
```

协议：[Realtime API](https://s.apifox.cn/46c7cae8-f2d7-4780-a960-e531d6c5eaa8/9598749m0) · [上传接口](https://s.apifox.cn/46c7cae8-f2d7-4780-a960-e531d6c5eaa8/9598751m0)
