"""Client-side helpers for the public VLX-Flow Realtime notebook.

Protocol state, upload and session lifecycle shared by the two notebooks.
Importing this module never connects to the API; it has no widget dependency.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlsplit, urlunsplit
import uuid

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


def api_root(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("请填写平台提供的 HTTPS API 根地址，不包含 /os 或 /kernel-rs。")
    return value


def timestamp_seconds(value):
    """Convert the documented millisecond field, without claiming it is video PTS."""
    if value is None or isinstance(value, bool):
        return None
    try:
        seconds = float(value) / 1000
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def useful_text(text: str) -> bool:
    # This is only a presentation filter, not a model-level silence judgment.
    return bool(text.strip()) and not re.fullmatch(r"[\s.…。·]+", text)


def token_count(usage):
    if not isinstance(usage, dict):
        return None
    value = usage.get("total_tokens")
    if type(value) is int and value >= 0:
        return value
    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if all(type(n) is int and n >= 0 for n in (prompt, completion)):
        return prompt + completion
    return None


def validate_settings(settings):
    """Validate UI settings before opening a paid API session."""
    integer_limits = {
        "interval_seconds": (1000, 2000), "batch_size": (1, 2),
        "window_size": (1, 8), "max_tokens": (1, 32),
        "duration_seconds": (5, 600),
    }
    if set(settings) != set(integer_limits) | {"model", "temperature"}:
        raise ValueError("调用参数字段不完整或包含未知字段，请重新加载界面。")
    if not isinstance(settings["model"], str) or not settings["model"].strip():
        raise ValueError("请填写模型 ID。")
    for name, (lower, upper) in integer_limits.items():
        value = settings[name]
        if type(value) is not int or not lower <= value <= upper:
            unit = " 毫秒" if name == "interval_seconds" else ""
            raise ValueError(f"{name} 必须为 {lower}–{upper}{unit}之间的整数。")
    temperature = settings["temperature"]
    if type(temperature) not in (int, float) or not 0 <= temperature < 2:
        raise ValueError("temperature 必须满足 0 ≤ 值 < 2。")
    return dict(settings)


@dataclass
class EventState:
    session_id: str | None = None
    ready: bool = False
    closed: bool = False
    cleanup_pending: bool = False
    creation_rejected: bool = False
    fatal_error: str = ""
    notice: str = ""
    source_status: str = ""
    buffers: dict = field(default_factory=dict)
    finished: set = field(default_factory=set)
    seen: set = field(default_factory=set)
    history: deque = field(default_factory=lambda: deque(maxlen=30))
    trace: deque = field(default_factory=lambda: deque(maxlen=200))
    current: dict = field(default_factory=dict)
    last_analysis: dict = field(default_factory=dict)
    completed_rounds: int = 0
    empty_rounds: int = 0
    tokens: int = 0
    usage_known: bool = False
    usage_final: bool = False
    analysis_seen: bool = False
    questions: dict = field(default_factory=dict)
    inquiries: dict = field(default_factory=dict)
    inquiry_finished: set = field(default_factory=set)

    def register_question(self, request_id, prompt):
        self.questions[request_id] = {"question": prompt, "status": "sending", "response_id": None}

    @property
    def question_pending(self):
        return any(q["status"] not in ("completed", "failed", "cancelled") for q in self.questions.values())

    def end_questions(self):
        for question in self.questions.values():
            if question["status"] not in ("completed", "failed", "cancelled"):
                question["status"] = "unknown"
        for row in self.inquiries.values():
            if row["status"] == "generating":
                row["status"] = "unknown"

    def _inquiry(self, event, rid, data, response, raw_time):
        if rid in self.inquiry_finished:
            return
        row = self.inquiries.setdefault(rid, {
            "id": rid, "text": "", "question": "", "status": "generating",
            "raw_time": raw_time, "timestamp_ms": None, "text_final": False,
        })
        if raw_time is not None:
            row["raw_time"] = raw_time
        if data.get("timestamp_ms") is not None:
            row["timestamp_ms"] = data["timestamp_ms"]
        if event == "response.text.delta" and not row["text_final"]:
            row["text"] += str(data.get("delta") or "")
        elif event == "response.text.done" and isinstance(data.get("text"), str):
            row["text"] = data["text"]
            row["text_final"] = True
        elif event == "error":
            row["error"] = str(data.get("error") or data.get("message") or "追问异常")
        elif event == "response.done":
            row["status"] = str(response.get("status") or data.get("status", "unknown"))
            self.inquiry_finished.add(rid)
            usage = token_count(response.get("usage"))
            if usage is not None and not self.usage_final:
                self.tokens += usage
                self.usage_known = True
        for question in self.questions.values():
            if question["response_id"] == rid:
                row["question"] = question["question"]
                question["status"] = row["status"]

    def consume(self, message):
        event = message.get("event", "")
        data = message.get("data") or {}
        if not isinstance(data, dict):
            return
        sid = message.get("session_id")
        if isinstance(sid, str) and sid.startswith("vrs_"):
            self.session_id = sid
        event_id = message.get("event_id")
        if event_id:
            if event_id in self.seen:
                return
            self.seen.add(event_id)
        response = data.get("response") or {}
        if not isinstance(response, dict):
            response = {}
        rid = data.get("response_id") or response.get("id") or response.get("response_id")
        raw_time = data.get("frameTime", response.get("frameTime"))
        question = self.questions.get(message.get("request_id"))
        if question is not None:
            if event in ("system.error", "error") or (event == "command.result" and data.get("error")):
                question["status"] = "failed"
                question["error"] = str(data.get("error") or data.get("message") or "追问被拒绝")
            elif event == "command.result" and rid:
                question["response_id"] = rid
                row = self.inquiries.get(rid)
                question["status"] = row["status"] if row else "queued"
                if row:
                    row["question"] = question["question"]
        self.trace.append({
            "event": event, "type": message.get("type"), "response_id": rid,
            "frameTime": raw_time, "timestamp_ms": data.get("timestamp_ms"),
            "delta": data.get("delta"), "text": data.get("text"),
            "status": response.get("status", data.get("status")),
        })
        if event == "session.ready":
            self.ready = True
        elif event in ("session.closed", "session.cleanup_pending"):
            self.closed = event == "session.closed"
            self.cleanup_pending = not self.closed
            usage = token_count(data.get("usage"))
            if usage is not None:
                self.tokens = usage
                self.usage_known = self.usage_final = True
        elif event == "source.status":
            self.source_status = str(data.get("status", "unknown"))
            if self.source_status == "completed":
                self.notice = "视频源已结束，等待尾部回答；到演示时限自动关闭。"
        elif event in ("system.error", "error"):
            error = data.get("error") or data.get("message") or data
            self.notice = str(error)
            if data.get("fatal"):
                self.fatal_error = str(error)
                # This narrowly handles the observed pre-creation lookup failure.
                self.creation_rejected = (
                    not self.ready and isinstance(error, dict)
                    and error.get("code") == "invalid_request"
                    and "ability code" in str(error.get("message", ""))
                    and "not found" in str(error.get("message", ""))
                )
        if message.get("type") == "algorithm.inquiry" and rid:
            self._inquiry(event, rid, data, response, raw_time)
            return
        if message.get("type") == "algorithm.analysis" and rid:
            self.analysis_seen = True
        if message.get("type") != "algorithm.analysis" or not rid or rid in self.finished:
            return
        row = self.buffers.setdefault(rid, {
            "id": rid, "text": "", "raw_time": None, "timestamp_ms": None,
            "status": "generating",
            "text_final": False,
        })
        if raw_time is not None:
            row["raw_time"] = raw_time
        if data.get("timestamp_ms") is not None:
            row["timestamp_ms"] = data["timestamp_ms"]
        if event == "response.text.delta" and not row["text_final"]:
            row["text"] += str(data.get("delta") or "")
        elif event == "response.text.done" and isinstance(data.get("text"), str):
            row["text"] = data["text"]
            row["text_final"] = True
        elif event == "response.alert":
            self.notice = "告警：" + str(data.get("text") or "")
        elif event == "response.done":
            self.finished.add(rid)
            self.completed_rounds += 1
            row["status"] = str(response.get("status") or data.get("status", "unknown"))
            usage = token_count(response.get("usage"))
            if usage is not None and not self.usage_final:
                self.tokens += usage
                self.usage_known = True
            if useful_text(row["text"]):
                self.history.appendleft(dict(row))
            else:
                self.empty_rounds += 1
            self.buffers.pop(rid, None)
        # Blank/punctuation-only responses never overwrite a useful description.
        self.last_analysis = dict(row)
        if useful_text(row["text"]):
            self.current = dict(row)


def verify_upload(response) -> str:
    response.raise_for_status()
    result = response.json()
    data = result.get("data")
    url = data.get("fileUrl") if isinstance(data, dict) else None
    if result.get("success") is False or not isinstance(url, str):
        raise RuntimeError("上传未返回 data.fileUrl：" + str(result.get("message", "未知错误")))
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise RuntimeError("上传接口返回的视频地址无效。")
    return url


async def upload_video(endpoint, api_key, path, *, use_proxy=True):
    """Explicit user-run upload. Never retries or starts inference."""
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != ".mp4":
        raise ValueError("请选择存在的 MP4 文件。")
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(300, connect=30), trust_env=use_proxy,
    ) as client:
        with path.open("rb") as video:
            response = await client.post(
                api_root(endpoint) + "/os/uploadFile",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (path.name, video, "video/mp4")},
                data={"type": "video/mp4"},
            )
    return verify_upload(response)


class RealtimeSession:
    """One WebSocket, one receiver, independent state and explicit cleanup."""

    def __init__(self, *, endpoint, api_key, video_url,
                 model="VLX-Flow-1.5-10B", duration_seconds=60,
                 instruction="持续观看视频画面, 并描述画面内容",
                 interval_seconds=1000, batch_size=1, window_size=4,
                 temperature=0.2, max_tokens=32,
                 use_proxy=True, on_change=None, runner=None):
        settings = validate_settings({
            "model": model, "duration_seconds": duration_seconds,
            "interval_seconds": interval_seconds, "batch_size": batch_size,
            "window_size": window_size, "temperature": temperature,
            "max_tokens": max_tokens,
        })
        self.endpoint = api_root(endpoint)
        self.api_key = api_key  # Plain Python fields: NOT synced to the frontend.
        self.video_url = video_url
        self._apply_settings(settings)
        self.instruction_text = instruction
        self.use_proxy = use_proxy
        self.state = EventState()
        self.task = None
        self.stop_event = None
        self.cleanup_blocked = False
        self.status = "准备就绪"
        self.failure = ""
        self.started_at = None
        self.elapsed = 0
        self.playback_id = 0
        self._last_publish = 0
        self.on_change = on_change
        self.runner = runner
        self.ws = None
        self.commands = asyncio.Queue()
        self._publish()

    @property
    def running(self):
        return self.task is not None and not self.task.done()

    @property
    def can_ask(self):
        return bool(self.running and self.state.ready and self.state.analysis_seen
                    and self.ws is not None and not self.cleanup_blocked
                    and not self.state.cleanup_pending and not self.state.fatal_error
                    and not self.stop_event.is_set() and not self.state.closed
                    and self.status not in ("正在关闭", "正在停止")
                    and not self.state.question_pending)

    def prepare_question(self, prompt):
        if not self.can_ask:
            raise ValueError("请等待首轮分析和上一条追问完成；结束后的会话需重新开始。")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2000:
            raise ValueError("追问请输入 1–2000 字符。")
        request = {"type": "response.create", "request_id": uuid.uuid4().hex,
                   "data": {"prompt": prompt}}
        self.state.register_question(request["request_id"], prompt)
        self._publish()
        return request

    def ask(self, prompt):
        request = self.prepare_question(prompt)
        self.commands.put_nowait(request)
        return request["request_id"]

    def _apply_settings(self, settings):
        settings = dict(settings)
        self.remote_model = settings.pop("model")
        self.duration_seconds = settings.pop("duration_seconds")
        self.parameters = settings

    def _settings(self):
        return {"model": self.remote_model, "duration_seconds": self.duration_seconds,
                **self.parameters}

    def _safe_message(self, value):
        value = str(value)
        for secret in (self.api_key, self.video_url):
            if secret:
                value = value.replace(secret, "[已隐藏]")
        return re.sub(r"((?:https?|socks\w*)://)[^\s/@]+:[^\s/@]+@", r"\1[已隐藏]@", value)[:700]

    def _publish(self, *, force=True):
        now = time.monotonic()
        if not force and now - self._last_publish < 0.1:
            return
        self._last_publish = now
        def public_row(row):
            if not row:
                return {}
            return {
                "id": row["id"], "text": row["text"], "status": row["status"],
                "seconds": timestamp_seconds(row.get("timestamp_ms")),
            }
        self.snapshot = {
            "status": self.status, "running": self.running,
            "ready": self.state.ready, "cleanup_blocked": self.cleanup_blocked,
            "elapsed": round(self.elapsed, 1), "limit": self.duration_seconds,
            "model": self.remote_model, "playback_id": self.playback_id,
            "settings": self._settings(),
            "instruction": self.instruction_text, "source": self.state.source_status,
            "current": public_row(self.state.current),
            "history": [public_row(row) for row in self.state.history],
            "rounds": self.state.completed_rounds, "empty_rounds": self.state.empty_rounds,
            "tokens": self.state.tokens if self.state.usage_known else None,
            "usage_final": self.state.usage_final,
            "notice": self._safe_message(self.state.notice),
            "error": self._safe_message(self.failure),
            "can_ask": self.can_ask,
            "questions": [{**q, "error": self._safe_message(q.get("error", ""))}
                          for q in list(self.state.questions.values())[-20:]],
            "inquiries": [{**public_row(row), "question": row["question"],
                           "error": self._safe_message(row.get("error", ""))}
                          for row in list(self.state.inquiries.values())[-20:]],
        }
        if self.on_change is not None:
            self.on_change(self)

    def start(self, *, instruction=None, settings=None):
        if self.running or self.cleanup_blocked:
            return
        prompt = self.instruction_text if instruction is None else instruction
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 16384:
            self.failure = "请输入 1–16384 字符的描述指令。"
            self._publish()
            return
        try:
            if settings is not None and not isinstance(settings, dict):
                raise ValueError("调用参数必须为对象，请重新加载界面。")
            updated = validate_settings({**self._settings(), **(settings or {})})
        except ValueError as exc:
            self.failure = str(exc)
            self._publish()
            return
        self._apply_settings(updated)
        # The UI value is the exact instruction sent to the API; no hidden prefix.
        self.instruction_text = prompt
        self.stop_event = asyncio.Event()
        self.state = EventState()
        self.commands = asyncio.Queue()
        self.failure = ""
        self.status = "正在连接"
        self.elapsed = 0
        self.task = asyncio.create_task(self.runner(self) if self.runner else self._run())
        self.task.add_done_callback(self._task_finished)
        self._publish()

    def _task_finished(self, task):
        # Retrieve exceptions so background failures cannot disappear silently.
        if not task.cancelled() and task.exception() is not None:
            self.failure = str(task.exception())
            self.status = "运行异常"
        self._publish()

    def stop(self):
        if self.running and self.stop_event:
            self.stop_event.set()
            self.status = "正在停止"
            self._publish()

    async def shutdown(self):
        self.stop()
        if self.running:
            await asyncio.wait_for(asyncio.shield(self.task), timeout=45)
        if self.cleanup_blocked:
            await self._recheck_cleanup()
        if self.cleanup_blocked:
            raise RuntimeError("旧会话关闭尚未确认，请再次检查关闭状态。")

    async def _send_command(self, ws, command, data):
        await ws.send(json.dumps({
            "type": command, "request_id": uuid.uuid4().hex, "data": data,
        }, ensure_ascii=False))

    async def _confirm_cleanup(self):
        if self.state.closed or not self.state.session_id:
            return True
        url = f"{self.endpoint}/kernel-rs/v1/realtime/sessions/{self.state.session_id}"
        async with httpx.AsyncClient(timeout=8, trust_env=self.use_proxy) as client:
            response = await client.delete(url, headers={"Authorization": f"Bearer {self.api_key}"})
        if response.status_code == 204:
            self.state.closed = True
            return True
        # A 404 after a known rejected model lookup isn't evidence of a live session.
        # Do NOT treat every 404 (wrong route, wrong identity, etc.) as a successful close.
        if response.status_code == 404 and self.state.creation_rejected and not self.state.ready:
            return True
        self.state.notice = f"关闭尚未确认（HTTP {response.status_code}），可点击“检查关闭”。"
        return False

    async def _recheck_cleanup(self):
        try:
            self.cleanup_blocked = not await self._confirm_cleanup()
            self.status = "等待关闭确认" if self.cleanup_blocked else "会话已结束"
            if not self.cleanup_blocked:
                self.state.notice = "已确认无需继续清理。"
        except Exception as exc:
            self.failure = str(exc)
        self._publish()

    async def _run(self):
        self.started_at = time.monotonic()
        close_at = None
        parsed = urlsplit(self.endpoint)
        ws_url = urlunsplit(("wss", parsed.netloc, "/kernel-rs/v1/realtime/sessions", "", ""))
        try:
            async with connect(
                ws_url, additional_headers={"Authorization": f"Bearer {self.api_key}"},
                proxy=True if self.use_proxy else None,
                open_timeout=20, close_timeout=5, ping_interval=20, ping_timeout=20,
            ) as ws:
                self.ws = ws
                if self.stop_event.is_set():
                    return
                await self._send_command(ws, "session.create", {
                    "model": self.remote_model,
                    "source": {"type": "2", "path": self.video_url},
                    "instruction": self.instruction_text,
                    **self.parameters,
                })
                self.status = "会话创建中"
                while True:
                    self.elapsed = time.monotonic() - self.started_at
                    if (self.stop_event.is_set() or self.elapsed >= self.duration_seconds) and close_at is None:
                        self.status = "正在关闭"
                        if not self.state.ready:
                            break
                        await self._send_command(ws, "session.close", {})
                        close_at = time.monotonic()
                    if close_at is not None and time.monotonic() - close_at >= 8:
                        break
                    if close_at is None:
                        while not self.commands.empty():
                            await ws.send(json.dumps(self.commands.get_nowait(), ensure_ascii=False))
                    self._publish(force=False)
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue
                    message = json.loads(raw)
                    was_ready = self.state.ready
                    self.state.consume(message)
                    if self.state.ready and not was_ready:
                        self.playback_id += 1
                        self.status = "持续分析中"
                    if self.state.fatal_error:
                        raise RuntimeError(self.state.fatal_error)
                    if self.state.closed or self.state.cleanup_pending:
                        break
        except ConnectionClosed as exc:
            if not self.state.closed and close_at is None:
                self.failure = f"连接已断开（{type(exc).__name__}），正在检查会话关闭状态。"
        except asyncio.CancelledError:
            self.failure = "任务已取消，正在清理会话。"
        except Exception as exc:
            self.failure = f"{type(exc).__name__}: {exc}"
        finally:
            self.ws = None
            self.state.end_questions()
            self.elapsed = time.monotonic() - self.started_at
            try:
                self.cleanup_blocked = not await self._confirm_cleanup()
            except Exception as exc:
                self.cleanup_blocked = True
                self.state.notice = f"关闭确认失败：{exc}"
            if self.cleanup_blocked:
                self.status = "等待关闭确认"
            elif self.state.creation_rejected:
                self.status = "创建失败，未进入视频分析"
            elif self.state.closed:
                self.status = "会话已关闭"
            else:
                self.status = "连接已结束"
            self._publish()

    def diagnostic_events(self):
        """Small field whitelist; no credentials, input URL, or request headers."""
        return list(self.state.trace)
