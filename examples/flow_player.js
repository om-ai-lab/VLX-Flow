function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "相对时间未提供";
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${(seconds % 60).toFixed(3).padStart(6, "0")}`;
}
const names = {describe: "持续描述", detect: "主动检测"};
const statuses = {generating: "生成中…", sending: "等待接受", queued: "排队中", completed: "完成", failed: "失败", cancelled: "已取消", unknown: "结果未确认"};

export default {
  render({ model, el }) {
    el.classList.add("flow-demo");
    el.innerHTML = `
      <header class="flow-header">
        <div><span class="flow-eyebrow">VLX-FLOW · API PLAYGROUND</span><h3>视频分析交互体验</h3></div>
        <span class="flow-status" role="status"></span>
      </header>
      <label class="flow-mode-label"><strong>持续任务</strong>
        <select class="flow-mode"><option value="describe">持续描述 · 单会话</option><option value="detect">主动检测 · 单会话</option><option value="parallel">描述 + 检测 · 双会话并行</option></select>
      </label>
      <p class="flow-parallel-note flow-hint" hidden>双路共用下方采样与生成参数，使用各自的指令和会话，分别计量。两路处理进度可能不同；任一路运行失败时会停止另一路。</p>
      <fieldset class="flow-settings">
        <legend>⚙ 调用参数</legend>
        <div class="flow-session-settings">
          <label class="flow-model-setting">
            <strong>模型 <code>model</code></strong>
            <input data-setting="model" type="text" required spellcheck="false">
            <small>填写账号可调用的模型部署 ID。</small>
          </label>
          <label>
            <strong>自动停止（秒）</strong>
            <input data-setting="duration_seconds" type="number" min="5" max="600" step="1" required>
            <small>本地演示时限，5–600 秒。</small>
          </label>
        </div>
        <div class="flow-parameter-grid">
          <label>
            <strong>采样间隔（毫秒）</strong><code>interval_seconds</code>
            <input data-setting="interval_seconds" type="number" min="1000" max="2000" step="1" required>
            <small>1000–2000；1000 毫秒 = 1 秒。</small>
          </label>
          <label>
            <strong>触发分析的新帧数</strong><code>batch_size</code>
            <select data-setting="batch_size"><option value="1">1 帧</option><option value="2">2 帧</option></select>
            <small>每累计 1 或 2 张新帧分析一次。</small>
          </label>
          <label>
            <strong>窗口数</strong><code>window_size</code>
            <input data-setting="window_size" type="number" min="1" max="8" step="1" required>
            <small>窗口数，支持 1–8。</small>
          </label>
          <label>
            <strong>生成温度</strong><code>temperature</code>
            <input data-setting="temperature" type="number" min="0" max="2" step="any" required>
            <small>0 ≤ 值 &lt; 2。</small>
          </label>
          <label>
            <strong>单轮生成上限</strong><code>max_tokens</code>
            <input data-setting="max_tokens" type="number" min="1" max="32" step="1" required>
            <small>1–32 tokens。</small>
          </label>
        </div>
      </fieldset>

      <div class="flow-prompts">
        <label class="flow-instruction" data-prompt-label="describe"><strong>描述指令 · instruction</strong>
          <textarea data-instruction="describe" rows="2" maxlength="16384" required></textarea>
        </label>
        <label class="flow-instruction" data-prompt-label="detect"><strong>检测指令 · instruction</strong>
          <textarea data-instruction="detect" rows="2" maxlength="16384" required></textarea>
        </label>
      </div>
      <p class="flow-hint">指令原文直接发送；描述与检测是指令预设。修改运行参数需先停止，再重新开始。</p>
      <details class="flow-request"><summary>查看创建请求预览（视频 URL 已隐藏）</summary><pre></pre></details>
      <div class="flow-toolbar">
        <button class="flow-start">▶ 开始分析</button><button class="flow-stop" disabled>■ 全部停止</button>
        <button class="flow-cleanup" hidden>检查关闭</button><span class="flow-elapsed"></span>
      </div>
      <div class="flow-grid">
        <section class="flow-video-panel">
          <video controls playsinline preload="metadata"></video>
          <div class="flow-video-caption"><span>本地视频预览</span><span class="flow-playhead">00:00.000</span></div>
          <p class="flow-hint">预览与服务端独立运行。暂停、拖动视频不会改变模型处理进度，追问也不定位到播放器当前帧。</p>
          <p class="flow-media-note" role="status"></p>
        </section>
        <section class="flow-lanes"><p class="flow-empty">开始后在这里查看每路的流式结果。</p></section>
      </div>
      <section class="flow-inquiry-panel">
        <div class="flow-card-heading"><strong>💬 会话内追问</strong>
          <label>发送给 <select class="flow-target" aria-label="追问目标会话"></select></label>
        </div>
        <label class="flow-instruction"><span>问题 · prompt</span><textarea class="flow-question" rows="2" maxlength="2000" placeholder="例如：现在画面中的地形有什么特点？"></textarea></label>
        <div class="flow-toolbar"><button class="flow-ask" disabled>发送追问</button><span class="flow-ask-hint flow-hint"></span></div>
        <div class="flow-inquiries" aria-live="off"></div>
      </section>
      <p class="flow-error" role="alert"></p>
      <p class="flow-footnote">描述时间来自服务端相对时间，尚未确认与视频进度一致。空文本与纯省略号仅折叠计数，不能据此认定模型静默。输出保留原文。</p>
    `;
    const find = selector => el.querySelector(selector);
    const mode = find(".flow-mode"), video = find("video");
    const start = find(".flow-start"), stop = find(".flow-stop"), cleanup = find(".flow-cleanup");
    const target = find(".flow-target"), ask = find(".flow-ask"), question = find(".flow-question");
    const inputs = [...el.querySelectorAll("[data-setting]")];
    const prompts = [...el.querySelectorAll("[data-instruction]")];
    const previous = {}, laneElements = new Map();
    let objectURL, lastPlayback = 0, lastMode, disposed = false, inquiryKey = "", laneKey = "";

    function readSettings() {
      return Object.fromEntries(inputs.map(input => [input.dataset.setting,
        input.dataset.setting === "model" ? input.value : Number(input.value)]));
    }
    function selectedNames() { return mode.value === "parallel" ? ["describe", "detect"] : [mode.value]; }
    function preview() {
      const selected = selectedNames();
      for (const input of prompts) find(`[data-prompt-label="${input.dataset.instruction}"]`).hidden = !selected.includes(input.dataset.instruction);
      find(".flow-parallel-note").hidden = mode.value !== "parallel";
      const {model: modelID, duration_seconds, ...parameters} = readSettings();
      const requests = selected.map(name => ({type: "session.create", data: {
        model: modelID, source: {type: "2", path: "<已上传的视频 URL>"},
        instruction: find(`[data-instruction="${name}"]`).value, ...parameters,
      }}));
      find(".flow-request pre").textContent = JSON.stringify(requests.length === 1 ? requests[0] : requests, null, 2);
    }
    function timeLabel(row) { return Number.isFinite(row?.seconds) ? `服务端 ${formatTime(row.seconds)}` : "相对时间未提供"; }
    function addText(parent, tag, text, className = "") {
      const node = document.createElement(tag); node.textContent = text; node.className = className; parent.append(node); return node;
    }
    function laneElement(name) {
      if (laneElements.has(name)) return laneElements.get(name);
      const node = document.createElement("article"); node.className = "flow-lane";
      node.innerHTML = `<div class="flow-card"><div class="flow-card-heading"><strong></strong><span class="flow-lane-status"></span></div><span class="flow-current-time flow-time"></span><p class="flow-current"></p><small class="flow-current-state"></small></div><details class="flow-lane-history"><summary>最近完成的分析</summary><div class="flow-history"></div></details><p class="flow-metrics"></p><p class="flow-notice"></p><p class="flow-error"></p>`;
      node.querySelector("strong").textContent = names[name];
      find(".flow-lanes").append(node); laneElements.set(name, node); return node;
    }
    function updateInquiry(s) {
      const laneNames = Object.keys(s.lanes || {});
      const nextLaneKey = laneNames.join(",");
      if (nextLaneKey !== laneKey) {
        const oldTarget = target.value; target.replaceChildren();
        for (const name of laneNames) { const option = document.createElement("option"); option.value = name; option.textContent = names[name]; target.append(option); }
        if (laneNames.includes(oldTarget)) target.value = oldTarget;
        laneKey = nextLaneKey;
      }
      const lane = s.lanes?.[target.value];
      target.disabled = !laneNames.length;
      ask.disabled = !lane?.can_ask;
      find(".flow-ask-hint").textContent = !lane?.running ? "先开始分析，再发送问题。" : lane.can_ask ? "追问不停止持续分析。" : "等待首轮分析或上一条追问完成；停止过程中不能追问。";
      const key = JSON.stringify(laneNames.map(name => [name, s.lanes[name].questions, s.lanes[name].inquiries]));
      if (key === inquiryKey) return;
      inquiryKey = key;
      const area = find(".flow-inquiries"); area.replaceChildren();
      for (const name of laneNames) {
        const data = s.lanes[name];
        for (const q of data.questions || []) {
          const row = (data.inquiries || []).find(r => r.id === q.response_id);
          const article = document.createElement("article"); area.append(article);
          addText(article, "strong", `${names[name]} · ${q.question}`);
          addText(article, "small", statuses[row?.status || q.status] || q.status);
          addText(article, "p", row?.text || (q.status === "failed" ? "请求失败" : q.status === "unknown" ? "结果未确认，请勿自动重发。" : "等待流式回答……"));
          if (q.error || row?.error) addText(article, "p", q.error || row.error, "flow-error");
        }
        // Results can arrive before command.result: keep them visible without guessing the question.
        for (const row of data.inquiries || []) if (!(data.questions || []).some(q => q.response_id === row.id)) {
          const article = document.createElement("article"); area.append(article);
          addText(article, "strong", `${names[name]} · 回答 ${row.id}（等待问题关联）`);
          addText(article, "p", row.text);
        }
      }
    }
    function update() {
      const s = model.get("snapshot") || {}, running = Boolean(s.running);
      find(".flow-status").textContent = s.status || "准备就绪";
      find(".flow-status").classList.toggle("is-running", running);
      start.disabled = running || Boolean(s.cleanup_blocked); stop.disabled = !running;
      cleanup.hidden = !s.cleanup_blocked; cleanup.disabled = running;
      mode.disabled = running; find(".flow-settings").disabled = running;
      if (s.mode !== lastMode) { mode.value = s.mode || "describe"; lastMode = s.mode; }
      for (const input of inputs) {
        const key = input.dataset.setting, value = s.settings?.[key];
        if (value !== previous[key]) { input.value = value ?? ""; input.setCustomValidity(""); previous[key] = value; }
      }
      for (const input of prompts) {
        const key = input.dataset.instruction, value = s.instructions?.[key];
        if (value !== previous[key]) { input.value = value || ""; previous[key] = value; }
        input.disabled = running;
      }
      preview();
      const lanes = s.lanes || {};
      if (Object.keys(lanes).length) find(".flow-lanes > .flow-empty")?.remove();
      for (const [name, node] of laneElements) if (!lanes[name]) { node.remove(); laneElements.delete(name); }
      for (const [name, lane] of Object.entries(lanes)) {
        const node = laneElement(name), row = lane.current || {};
        node.querySelector(".flow-lane-status").textContent = lane.status;
        node.querySelector(".flow-current-time").textContent = timeLabel(row);
        node.querySelector(".flow-current").textContent = row.text || "等待有效分析文本……";
        node.querySelector(".flow-current-state").textContent = statuses[row.status] || row.status || "";
        node.querySelector(".flow-notice").textContent = lane.notice || "";
        node.querySelector(".flow-error").textContent = lane.error || "";
        const tokens = lane.tokens == null ? "待返回" : `${lane.tokens}（${lane.usage_final ? "服务端累计" : "已收到轮次"}，含追问）`;
        node.querySelector(".flow-metrics").textContent = `${Math.floor(lane.elapsed || 0)} / ${lane.limit} 秒 · 分析 ${lane.rounds || 0} 轮 · 折叠 ${lane.empty_rounds || 0} 轮 · Token ${tokens}`;
        const key = JSON.stringify(lane.history || []);
        if (node.historyKey !== key) {
          node.historyKey = key; const history = node.querySelector(".flow-history"); history.replaceChildren();
          for (const r of lane.history || []) { const article = document.createElement("article"); history.append(article); addText(article, "small", `${timeLabel(r)} · ${statuses[r.status] || r.status}`); addText(article, "p", r.text); }
        }
      }
      find(".flow-error[role=alert]").textContent = s.error || "";
      updateInquiry(s);
      if (s.playback_id && s.playback_id !== lastPlayback) {
        lastPlayback = s.playback_id; video.currentTime = 0;
        find(".flow-media-note").textContent = "";
        video.play().catch(() => { if (!disposed) find(".flow-media-note").textContent = "浏览器未允许自动播放，请点击视频播放键。"; });
      }
      if (!running) video.pause();
    }
    mode.onchange = preview;
    for (const input of [...inputs, ...prompts]) input.oninput = preview;
    target.onchange = () => updateInquiry(model.get("snapshot") || {});
    start.onclick = () => {
      for (const input of inputs) {
        const key = input.dataset.setting, value = key === "model" ? input.value : Number(input.value);
        input.setCustomValidity("");
        if (key === "model" && !value.trim()) input.setCustomValidity("请填写模型 ID。");
        if (key === "temperature" && !(value >= 0 && value < 2)) input.setCustomValidity("temperature 必须满足 0 ≤ 值 < 2。");
        if (!input.reportValidity()) return;
      }
      for (const name of selectedNames()) {
        const input = find(`[data-instruction="${name}"]`);
        if (!input.value.trim()) { input.focus(); find(".flow-error[role=alert]").textContent = "请填写每路指令。"; return; }
      }
      start.disabled = true;
      model.send({action: "start", mode: mode.value, settings: readSettings(), instructions: Object.fromEntries(prompts.map(input => [input.dataset.instruction, input.value]))});
    };
    ask.onclick = () => {
      if (!question.value.trim()) { question.focus(); return; }
      ask.disabled = true; model.send({action: "ask", target: target.value, prompt: question.value});
    };
    stop.onclick = () => { stop.disabled = true; model.send({action: "stop"}); };
    cleanup.onclick = () => model.send({action: "cleanup"});
    function setVideo() {
      video.pause(); if (objectURL) URL.revokeObjectURL(objectURL);
      objectURL = URL.createObjectURL(new Blob([model.get("video_bytes")], {type: "video/mp4"})); video.src = objectURL;
    }
    video.ontimeupdate = () => { find(".flow-playhead").textContent = formatTime(video.currentTime); };
    video.onerror = () => { find(".flow-media-note").textContent = "无法播放该文件，请确认使用 H.264 MP4。"; };
    setVideo(); update(); model.on("change:snapshot", update); model.on("change:video_bytes", setVideo);
    return () => { disposed = true; video.pause(); video.removeAttribute("src"); video.load(); URL.revokeObjectURL(objectURL); model.off("change:snapshot", update); model.off("change:video_bytes", setVideo); };
  },
};
