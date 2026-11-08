"""Notebook interaction layer; API credentials stay in Python memory."""
from pathlib import Path
import asyncio

import anywidget
import traitlets

from flow_api import RealtimeSession, api_root, validate_settings

DESCRIPTION_INSTRUCTION = "持续观看视频画面, 并描述画面内容"
DETECTION_INSTRUCTION = "持续观看视频画面, 当视频中的咖啡制作完成并完成拉花的时候, 向我汇报, 输出: 咖啡制作完成"
DEFAULT_SETTINGS = {
    "model": "VLX-Flow-1.5-10B", "duration_seconds": 60,
    "interval_seconds": 1000, "batch_size": 2, "window_size": 8,
    "temperature": 0.2, "max_tokens": 32,
}


class InteractivePlayground(anywidget.AnyWidget):
    _esm = Path(__file__).with_name("flow_player.js")
    _css = Path(__file__).with_name("flow_player.css")
    video_bytes = traitlets.Bytes().tag(sync=True)
    snapshot = traitlets.Dict().tag(sync=True)

    def __init__(self, *, endpoint, api_key, video_path, video_url, use_proxy=True,
                 settings=None, description=DESCRIPTION_INSTRUCTION, detection=DETECTION_INSTRUCTION):
        self.endpoint = api_root(endpoint)
        self.api_key = api_key
        self.video_url = video_url
        self.use_proxy = use_proxy
        self.settings = validate_settings({**DEFAULT_SETTINGS, **(settings or {})})
        self.instructions = {"describe": description, "detect": detection}
        self.mode = "describe"
        self.sessions = {}
        self.error = ""
        self.playback_id = 0
        self._played = False
        self._cleanup_task = None
        super().__init__(video_bytes=Path(video_path).read_bytes())
        self.on_msg(self._on_action)
        self._publish()

    @property
    def running(self):
        return (any(s.running for s in self.sessions.values())
                or self._cleanup_task is not None and not self._cleanup_task.done())

    @property
    def cleanup_blocked(self):
        return any(s.cleanup_blocked for s in self.sessions.values())

    def _safe(self, text):
        text = str(text)
        for secret in (self.api_key, self.video_url):
            if secret:
                text = text.replace(secret, "[已隐藏]")
        return text[:700]

    def _publish(self):
        lanes = {name: session.snapshot for name, session in self.sessions.items()}
        any_ready = any(s.state.ready for s in self.sessions.values())
        if any_ready and not self._played:
            self.playback_id += 1
            self._played = True
        if self.cleanup_blocked:
            status = "等待关闭确认"
        elif self.running:
            status = "停止中" if any(s.stop_event and s.stop_event.is_set() for s in self.sessions.values()) else "运行中" if any_ready else "正在连接"
        else:
            status = "已结束" if lanes else "准备就绪"
        self.snapshot = {
            "mode": self.mode, "settings": dict(self.settings),
            "instructions": dict(self.instructions), "lanes": lanes,
            "running": bool(self.running), "cleanup_blocked": self.cleanup_blocked,
            "status": status, "playback_id": self.playback_id,
            "error": self._safe(self.error),
        }

    def _session_changed(self, session):
        # A failed lane stops its peer: a half-started parallel run must not keep billing.
        if session.failure or session.state.fatal_error or session.cleanup_blocked:
            for other in self.sessions.values():
                if other is not session and other.running and not other.stop_event.is_set():
                    other.stop()
        self._publish()

    def start(self, *, mode=None, instructions=None, settings=None):
        if self.running or self.cleanup_blocked:
            return
        try:
            mode = mode or self.mode
            if mode not in ("describe", "detect", "parallel"):
                raise ValueError("请选择持续描述、主动检测或双路并行。")
            if settings is not None and not isinstance(settings, dict):
                raise ValueError("调用参数必须为对象。")
            if instructions is not None and not isinstance(instructions, dict):
                raise ValueError("指令必须为对象。")
            updated = validate_settings({**self.settings, **(settings or {})})
            prompts = {**self.instructions, **(instructions or {})}
            names = ("describe", "detect") if mode == "parallel" else (mode,)
            for name in names:
                prompt = prompts.get(name)
                if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 16384:
                    raise ValueError("请为每路填写 1–16384 字符的指令。")
            sessions = {
                name: RealtimeSession(endpoint=self.endpoint, api_key=self.api_key,
                                      video_url=self.video_url, use_proxy=self.use_proxy,
                                      instruction=prompts[name], **updated)
                for name in names
            }
        except (TypeError, ValueError) as exc:
            self.error = str(exc)
            self._publish()
            return
        self.mode, self.instructions, self.settings = mode, prompts, updated
        self.sessions = sessions
        self.error = ""
        self._played = False
        for session in sessions.values():
            session.on_change = self._session_changed
            session.start()
        self._publish()

    def stop(self):
        for session in self.sessions.values():
            session.stop()
        self._publish()

    async def shutdown(self):
        self.stop()
        results = await asyncio.gather(*(s.shutdown() for s in self.sessions.values()), return_exceptions=True)
        errors = [str(r) for r in results if isinstance(r, BaseException)]
        self.error = "；".join(errors)
        self._publish()
        if errors:
            raise RuntimeError(self._safe(self.error))

    async def _cleanup(self):
        try:
            await self.shutdown()
        except Exception as exc:
            self.error = str(exc)

    def _cleanup_finished(self, task):
        if not task.cancelled() and task.exception():
            self.error = str(task.exception())
        self._publish()

    def _on_action(self, _, content, buffers):
        action = content.get("action")
        if action == "start":
            self.start(mode=content.get("mode"), instructions=content.get("instructions"), settings=content.get("settings"))
        elif action == "stop":
            self.stop()
        elif action == "cleanup" and not self.running:
            self._cleanup_task = asyncio.create_task(self._cleanup())
            self._cleanup_task.add_done_callback(self._cleanup_finished)
            self._publish()
        elif action == "ask":
            try:
                session = self.sessions.get(content.get("target"))
                if session is None:
                    raise ValueError("请先启动对应的会话。")
                session.ask(content.get("prompt"))
                self.error = ""
            except ValueError as exc:
                self.error = str(exc)
            self._publish()

    def diagnostic_events(self):
        return {name: s.diagnostic_events() for name, s in self.sessions.items()}
