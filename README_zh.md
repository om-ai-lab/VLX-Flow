<p align="center">
  <img src="assets/figures/readme/logo-small.png" alt="VLX-Flow logo" width="180">
</p>

<h1 align="center">VLX-Flow</h1>

<h3 align="center">让多模态模型持续看见视频世界</h3>

<p align="center">
  <a href="README.md">English</a> | 中文
</p>

<p align="center">
  <a href="https://x.com/OmAI_lab">
    <img alt="X" src="https://img.shields.io/badge/%F0%9F%93%A3%20X-%E5%85%B3%E6%B3%A8%20%40OmAI_lab-000000">
  </a>
  <a href="https://om-ai-lab.github.io/2026_06_25_vlx_flow_zh.html">
    <img alt="博客" src="https://img.shields.io/badge/%F0%9F%93%9D%20%E5%8D%9A%E5%AE%A2-%E9%98%85%E8%AF%BB%E6%96%87%E7%AB%A0-2563eb">
  </a>
  <a href="https://platform.om-agent.cn/subapp-index/#/front">
    <img alt="体验页面" src="https://img.shields.io/badge/%F0%9F%9A%80%20%E4%BD%93%E9%AA%8C%E9%A1%B5%E9%9D%A2-%E7%AB%8B%E5%8D%B3%E4%BD%93%E9%AA%8C-16a34a">
  </a>
  <a href="https://huggingface.co/omlab">
    <img alt="Hugging Face 待补充" src="https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-%E5%BE%85%E8%A1%A5%E5%85%85-f9d54a">
  </a>
</p>




介绍视频文件已放在 `assets/demo/`。在确认 GitHub 视频渲染正常之前，README 中的视频嵌入暂时保持关闭。

<p align="center">
  <video src="assets/demo/VLX-Flow.mp4" controls muted width="88%"></video>
</p>

## 项目概览

VLX-Flow 是一个面向实时视频理解的流式视觉语言模型设计。它关注的场景不是把预录视频作为一次性文件处理，而是来自摄像头、机器人、无人机、媒体流或边缘设备的连续输入流。

VLX-Flow 将输入视频拆成连续片段，编码每个新片段，并以增量方式更新模型内部的流式记忆。当用户提问时，模型可以直接从这份已维护的记忆中回答，而不需要从完整历史重新构建上下文。

<p align="center">
  <img src="assets/figures/readme/vlx-flow-overview.png" alt="VLX-Flow 总览图：流式片段、视觉缓存、语义记忆与低延迟交互" width="88%">
  <br>
  <sub>VLX-Flow 处理连续输入的视频片段，并维护视觉缓存与语义记忆以支持低延迟交互。</sub>
</p>

## 为什么需要 VLX-Flow

多数视频理解 VLM 依赖全帧输入或固定采样。这两类方法适合离线视频分析，但不太适合在线场景：在真实环境中，视频持续变化，用户问题也可能在任意时刻出现。

VLX-Flow 的目标是将视频理解从：

```text
离线视频请求 -> 全量重新处理 -> 回答
```

转变为：

```text
持续观察 -> 增量记忆更新 -> 即时交互
```

这个设计关注：

- **流式优先处理：** 在视频片段到达时增量处理，而不是反复重处理完整历史。
- **模型内部流式记忆：** 在模型内部维护视觉缓存和语义记忆。
- **低延迟交互：** 随视频流增长，仍然从已维护记忆中回答。

## 核心思路

### 流式输入

VLX-Flow 将视频划分为连续片段。每个片段包含少量帧，并按时间顺序处理。

对于每个新片段：

1. 视觉编码器将新帧转换为模型可读取的视觉特征。
2. 语言模型结合当前上下文消费这些特征。
3. 模型更新视觉缓存和语义记忆。
4. 历史信息以压缩状态保留，而不是反复追加为原始帧。

这避免了两个极端：完全丢弃旧信息，或者保留无限增长的完整历史上下文。

### 双层记忆

VLX-Flow 通过两层互补结构维护模型内部的流式记忆：

- **视觉缓存：** 保留近期帧级细节，用于即时交互和事件检测。
- **语义记忆：** 存储模型内部从视频流和交互中持续累积的高层上下文，包括流式描述、先前观察、用户问题、模型回答和对话上下文。

两层记忆协同工作：视觉缓存保护近期细节，语义记忆保持更长时间范围的叙事连贯性。

### 缓存感知推理

VLX-Flow 使用缓存感知执行，使新片段可以被增量处理。语言模型包含 Linear Attention 模块。相比标准自注意力随序列增长需要持续扩大的 KV cache，Linear Attention 可以通过递推状态保留历史并进行增量更新。

这带来两个实际收益：

- **延迟更稳定：** 系统不需要为每次新交互重新计算完整历史。
- **记忆增长更平滑：** 长视频流可以在更低内存压力下保持语义连续性。

<p align="center">
  <img src="assets/figures/readme/ttft-comparison.png" alt="Full Attention、SlideWindow 与 VLX-Flow 的 TTFT 对比" width="88%">
  <br>
  <sub>首 token 生成时延（TTFT）随输入图像数量变化的趋势对比。Full Attention（橙色）随着历史上下文变长持续上升；SlideWindow（绿色）通过窗口重置限制历史长度，因此呈现“上升-重置-再上升”的波动趋势；VLX-Flow（红色）通过双层记忆机制压缩历史状态，使 TTFT 在长序列下仍保持较低且稳定。</sub>
</p>

## 能力

VLX-Flow 旨在支持多种在线视频理解工作流：

- **流式视频描述：** 在视频持续进入时生成描述，并保持时间连续性。
- **实时视频问答：** 用户可以在视频播放或摄像头运行过程中提问，模型基于已维护上下文回答。
- **事件触发式交互：** 后续可扩展到当维护状态满足特定事件条件时生成提醒。

## 发布

模型即将发布

## 关注我们

你可以通过 [X](https://x.com/OmAI_lab) 关注 Om AI Lab，或扫描下方微信社群二维码关注 VLX 的更新与讨论。

<p align="left">
  <img src="assets/figures/qrcode.png" alt="微信社群二维码" width="200">
</p>
