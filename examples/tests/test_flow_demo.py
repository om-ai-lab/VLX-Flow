"""Offline checks for event ordering, usage, timestamps, and paid-session cleanup."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flow_api import RealtimeSession, EventState, timestamp_seconds, verify_upload
from flow_demo import InteractivePlayground


def event(name, *, rid="r1", frame=None, category="algorithm.analysis", **extra):
    data = {"response_id": rid, **extra}
    if frame is not None:
        data["frameTime"] = frame
    return {"type": category, "event": name, "session_id": "vrs_test", "data": data}


class EventsTest(unittest.TestCase):
    def test_inquiry_can_finish_before_ack_without_mixing_analysis(self):
        s = EventState()
        s.register_question("ask-1", "山是什么颜色？")
        s.consume(event("response.text.delta", rid="analysis-1", delta="持续描述"))
        s.consume(event("response.text.delta", rid="answer-1", category="algorithm.inquiry", delta="红"))
        s.consume(event("response.text.done", rid="answer-1", category="algorithm.inquiry", text="红色。"))
        done = event("response.done", rid="answer-1", category="algorithm.inquiry", response={"status": "completed", "usage": {"total_tokens": 4}})
        s.consume(done)
        s.consume(done)
        s.consume({**event("command.result", rid="answer-1", category="command"), "request_id": "ask-1"})
        self.assertEqual(s.current["text"], "持续描述")
        self.assertEqual(s.inquiries["answer-1"]["text"], "红色。")
        self.assertEqual(s.inquiries["answer-1"]["question"], "山是什么颜色？")
        self.assertEqual(s.questions["ask-1"]["status"], "completed")
        self.assertFalse(s.question_pending)
        self.assertEqual(s.tokens, 4)
        self.assertEqual(s.completed_rounds, 0)

    def test_rejected_inquiry_and_partial_cancel_are_separate_from_session_failure(self):
        s = EventState()
        s.register_question("rejected", "问题一")
        s.consume({**event("system.error", category="error", error={"code": "source_not_ready"}, fatal=False), "request_id": "rejected"})
        self.assertFalse(s.question_pending)
        self.assertFalse(s.fatal_error)
        s.register_question("accepted", "问题二")
        s.consume({**event("command.result", rid="answer-2", category="command"), "request_id": "accepted"})
        s.consume(event("response.text.delta", rid="answer-2", category="algorithm.inquiry", delta="部分回答"))
        s.consume(event("response.done", rid="answer-2", category="algorithm.inquiry", response={"status": "cancelled", "usage": {"total_tokens": 3}}))
        self.assertEqual(s.inquiries["answer-2"]["text"], "部分回答")
        self.assertEqual(s.questions["accepted"]["status"], "cancelled")
        self.assertEqual(s.tokens, 3)

    def test_command_result_error_with_response_id_does_not_leave_question_pending(self):
        s = EventState()
        s.register_question("ask-rejected", "当前画面有什么？")
        s.consume({**event("command.result", rid="rejected-answer", category="command",
                           error={"code": "source_not_ready"}), "request_id": "ask-rejected"})
        self.assertEqual(s.questions["ask-rejected"]["status"], "failed")
        self.assertFalse(s.question_pending)

    def test_complete_text_replaces_deltas_and_late_delta_is_ignored(self):
        s = EventState()
        s.consume(event("response.text.delta", delta="a"))
        s.consume(event("response.text.done", text="完整回答", frame=12000))
        s.consume(event("response.text.delta", delta="duplicate"))
        s.consume(event("response.done", response={"status": "completed"}))
        self.assertEqual(s.history[0]["text"], "完整回答")
        self.assertEqual(s.history[0]["raw_time"], 12000)

    def test_interleaved_rounds_keep_their_own_frame_times(self):
        s = EventState()
        s.consume(event("response.text.delta", rid="a", delta="前", frame=1000))
        s.consume(event("response.text.delta", rid="b", delta="后", frame=2000))
        s.consume(event("response.done", rid="b", response={"status": "completed"}))
        s.consume(event("response.done", rid="a", response={"status": "completed"}))
        self.assertEqual({r["text"]: r["raw_time"] for r in s.history}, {"前": 1000, "后": 2000})

    def test_placeholders_count_without_overwriting_useful_output_or_usage(self):
        s = EventState()
        for rid, text in (("a", "有人走进画面"), ("b", "..."), ("c", " … "), ("d", "")):
            s.consume(event("response.text.done", rid=rid, text=text))
            s.consume(event("response.done", rid=rid, response={"status": "completed", "usage": {"total_tokens": 7}}))
        self.assertEqual(s.empty_rounds, 3)
        self.assertEqual(s.completed_rounds, 4)
        self.assertEqual(s.tokens, 28)
        self.assertEqual(s.current["text"], "有人走进画面")
        self.assertEqual(len(s.history), 1)

    def test_duplicate_events_and_rounds_do_not_double_count(self):
        s = EventState()
        delta = {**event("response.text.delta", delta="a"), "event_id": "evt1"}
        s.consume(delta)
        s.consume(delta)
        done = event("response.done", response={"status": "completed", "usage": {"total_tokens": 3}})
        s.consume(done)
        s.consume(done)
        self.assertEqual((s.tokens, s.completed_rounds, s.history[0]["text"]), (3, 1, "a"))

    def test_final_usage_replaces_local_total_including_failed_rounds(self):
        s = EventState()
        s.consume(event("response.done", response={"status": "failed", "usage": {"prompt_tokens": 8, "completion_tokens": 2}}))
        s.consume(event("session.closed", category="session", usage={"total_tokens": 12}))
        self.assertEqual(s.tokens, 12)
        self.assertTrue(s.usage_final)

    def test_wall_clock_and_relative_timestamp_are_preserved_separately(self):
        s = EventState()
        s.consume(event("response.text.done", text="hello", frame="2026-11-06 18:40:22.414", timestamp_ms=13015))
        self.assertEqual(s.current["raw_time"], "2026-11-06 18:40:22.414")
        self.assertEqual(s.current["timestamp_ms"], 13015)

    def test_failed_partial_output_keeps_its_status(self):
        s = EventState()
        s.consume(event("response.text.delta", delta="partial", frame=42))
        s.consume(event("response.done", response={"status": "cancelled"}))
        self.assertEqual(s.history[0]["status"], "cancelled")

    def test_only_millisecond_numbers_are_converted(self):
        self.assertEqual(timestamp_seconds(13015), 13.015)
        self.assertEqual(timestamp_seconds(0), 0)
        for raw in (None, True, -1, "NaN", "Infinity", "bad", "2026-11-06 18:40:22.414"):
            self.assertIsNone(timestamp_seconds(raw))

    def test_uploaded_file_url_validation(self):
        req = httpx.Request("POST", "https://example.invalid/os/uploadFile")
        good = httpx.Response(200, request=req, json={"success": True, "data": {"fileUrl": "https://example.invalid/a.mp4"}})
        self.assertEqual(verify_upload(good), "https://example.invalid/a.mp4")
        bad = httpx.Response(200, request=req, json={"success": True, "data": {"fileUrl": "file:///tmp/private"}})
        with self.assertRaises(RuntimeError):
            verify_upload(bad)


class FakeSocket:
    def __init__(self, events):
        self.events = list(events)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def send(self, raw):
        message = json.loads(raw)
        self.sent.append(message)
        if message["type"] == "session.close":
            self.events.append(event("session.closed", category="session", usage={"total_tokens": 9}))
        elif message["type"] == "response.create":
            rid = "answer-" + message["request_id"]
            self.events.extend([
                event("response.text.delta", rid=rid, category="algorithm.inquiry", delta="模拟回答"),
                event("response.done", rid=rid, category="algorithm.inquiry", response={"status": "completed", "usage": {"total_tokens": 2}}),
                {**event("command.result", rid=rid, category="command"), "request_id": message["request_id"]},
            ])

    async def recv(self):
        if self.events:
            await asyncio.sleep(0)
            return json.dumps(self.events.pop(0))
        await asyncio.sleep(30)


class LifecycleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.video = Path(self.tmp.name) / "sample.mp4"
        self.video.write_bytes(b"local-preview")
        self.demo = RealtimeSession(
            endpoint="https://example.invalid", api_key="secret-for-tests",
            video_url="https://example.invalid/private-video",
        )

    def tearDown(self):
        self.tmp.cleanup()

    async def test_start_is_idempotent_and_source_end_does_not_drop_tail(self):
        ws = FakeSocket([
            event("session.ready", category="session"),
            event("source.status", category="algorithm.source", status="completed"),
            event("response.text.done", text="尾部描述", frame=30000),
            event("response.done", response={"status": "completed"}),
        ])
        with patch("flow_api.connect", return_value=ws):
            self.demo.start(instruction="只描述画面里的山和水。")
            first_task = self.demo.task
            self.demo.start()
            self.assertIs(self.demo.task, first_task)
            for _ in range(100):
                if self.demo.state.completed_rounds:
                    break
                await asyncio.sleep(0.005)
            self.assertTrue(self.demo.running)
            self.assertEqual(self.demo.state.current["text"], "尾部描述")
            await self.demo.shutdown()
        self.assertEqual([m["type"] for m in ws.sent], ["session.create", "session.close"])
        self.assertEqual(ws.sent[0]["data"]["instruction"], "只描述画面里的山和水。")
        self.assertTrue(self.demo.state.closed)
        self.assertEqual(self.demo.state.tokens, 9)

    async def test_question_uses_same_socket_and_waits_for_first_analysis(self):
        ws = FakeSocket([event("session.ready", category="session")])
        with patch("flow_api.connect", return_value=ws) as connection:
            self.demo.start()
            await eventually(lambda: self.demo.state.ready)
            with self.assertRaises(ValueError):
                self.demo.ask("还没有首帧")
            ws.events.append(event("response.text.done", text="..."))
            await eventually(lambda: self.demo.can_ask)
            self.demo.ask("当前画面有什么？")
            with self.assertRaises(ValueError):
                self.demo.ask("不能重复提交")
            await eventually(lambda: self.demo.can_ask)
            self.demo.ask("另一个问题")
            await eventually(lambda: len(self.demo.state.inquiry_finished) == 2)
            await self.demo.shutdown()
            connection.assert_called_once()
        self.assertEqual([m["type"] for m in ws.sent], ["session.create", "response.create", "response.create", "session.close"])
        self.assertFalse(self.demo.can_ask)
        self.assertEqual(self.demo.state.tokens, 9)

    async def test_automatic_timeout_closes_without_user_stop(self):
        ws = FakeSocket([event("session.ready", category="session")])
        with patch("flow_api.connect", return_value=ws):
            self.demo.start()
            await eventually(lambda: self.demo.state.ready)
            self.demo.started_at -= 100
            await eventually(lambda: not self.demo.running)
        self.assertEqual(ws.sent[-1]["type"], "session.close")
        self.assertTrue(self.demo.state.closed)

    async def test_question_disabled_while_server_cleanup_is_pending(self):
        reached_cleanup = asyncio.Event()
        allow_cleanup = asyncio.Event()

        async def delayed_cleanup():
            reached_cleanup.set()
            await allow_cleanup.wait()
            return True

        ws = FakeSocket([
            event("session.ready", category="session"),
            event("response.text.done", text="有效分析"),
            event("session.cleanup_pending", category="session"),
        ])
        with patch("flow_api.connect", return_value=ws), patch.object(self.demo, "_confirm_cleanup", side_effect=delayed_cleanup):
            self.demo.start()
            try:
                await asyncio.wait_for(reached_cleanup.wait(), timeout=2)
                self.assertTrue(self.demo.running)
                self.assertFalse(self.demo.can_ask)
                with self.assertRaises(ValueError):
                    self.demo.ask("会话正在释放资源，不能再发问题")
            finally:
                allow_cleanup.set()
                await self.demo.task

    async def test_task_cancellation_attempts_cleanup(self):
        ws = FakeSocket([event("session.ready", category="session")])
        with patch("flow_api.connect", return_value=ws), patch.object(self.demo, "_confirm_cleanup", new_callable=AsyncMock, return_value=True) as cleanup:
            self.demo.start()
            for _ in range(100):
                if self.demo.state.ready:
                    break
                await asyncio.sleep(0.005)
            self.demo.task.cancel()
            await self.demo.task
            cleanup.assert_awaited_once()

    async def test_ui_settings_reach_each_new_session_without_local_timeout(self):
        for batch, interval, window, temperature, tokens in ((2, 1500, 6, 0.25, 24), (1, 2000, 1, 0, 1)):
            settings = {
                "model": "another-deployment", "duration_seconds": 45,
                "batch_size": batch, "interval_seconds": interval,
                "window_size": window, "temperature": temperature, "max_tokens": tokens,
            }
            ws = FakeSocket([event("session.ready", category="session")])
            with patch("flow_api.connect", return_value=ws):
                self.demo.start(instruction="只描述动作。", settings=settings)
                # Duplicate starts while running cannot alter the pending request.
                self.demo.start(settings={"batch_size": 3 - batch})
                for _ in range(100):
                    if self.demo.state.ready:
                        break
                    await asyncio.sleep(0.005)
                self.assertTrue(self.demo.state.ready)
                await self.demo.shutdown()
            self.assertEqual(ws.sent[0]["type"], "session.create")
            expected = {key: value for key, value in settings.items() if key != "duration_seconds"}
            self.assertEqual(ws.sent[0]["data"], {
                **expected, "instruction": "只描述动作。",
                "source": {"type": "2", "path": "https://example.invalid/private-video"},
            })
            self.assertEqual(self.demo.snapshot["settings"], settings)
            self.assertEqual(self.demo.duration_seconds, 45)

    async def test_invalid_ui_settings_never_open_connection_or_mutate_configuration(self):
        original = dict(self.demo.snapshot["settings"])
        invalid = (
            {"batch_size": 3}, {"batch_size": True}, {"batch_size": "2"},
            {"interval_seconds": 999}, {"interval_seconds": 2001},
            {"window_size": 0}, {"window_size": 9}, {"window_size": 1.5},
            {"temperature": 2}, {"temperature": -0.1}, {"temperature": float("nan")},
            {"temperature": float("inf")}, {"temperature": None},
            {"max_tokens": 33}, {"max_tokens": 0}, {"duration_seconds": 601},
            {"model": " "}, {"unknown": 1}, [1, 2],
        )
        with patch("flow_api.connect") as connection:
            for settings in invalid:
                with self.subTest(settings=settings):
                    self.demo.start(instruction="新的提示词", settings=settings)
                    self.assertIsNone(self.demo.task)
                    self.assertTrue(self.demo.snapshot["error"])
                    self.assertEqual(self.demo.snapshot["settings"], original)
                    self.assertNotEqual(self.demo.instruction_text, "新的提示词")
            connection.assert_not_called()

    async def test_404_is_only_tolerated_for_known_rejected_creation(self):
        self.demo.state.session_id = "vrs_test"
        client = AsyncMock()
        client.delete.return_value = httpx.Response(404)
        context = AsyncMock()
        context.__aenter__.return_value = client
        with patch("flow_api.httpx.AsyncClient", return_value=context):
            self.assertFalse(await self.demo._confirm_cleanup())
            self.demo.state.creation_rejected = True
            self.assertTrue(await self.demo._confirm_cleanup())
            self.demo.state.ready = True
            self.assertFalse(await self.demo._confirm_cleanup())

    async def test_pending_cleanup_blocks_new_session(self):
        self.demo.cleanup_blocked = True
        self.demo.start()
        self.assertIsNone(self.demo.task)

    async def test_empty_instruction_does_not_create_a_session(self):
        self.demo.start(instruction="  ")
        self.assertIsNone(self.demo.task)
        self.assertIn("请输入", self.demo.snapshot["error"])

    async def test_description_view_never_includes_absolute_frame_time(self):
        self.demo.state.consume(event("response.text.done", text="山谷", frame="2026-11-06 18:40:22.414", timestamp_ms=13015))
        self.demo._publish()
        row = self.demo.snapshot["current"]
        self.assertEqual(row["seconds"], 13.015)
        self.assertNotIn("2026-11-06", json.dumps(row))
        self.assertEqual(self.demo.diagnostic_events()[-1]["frameTime"], "2026-11-06 18:40:22.414")

    async def test_credentials_and_remote_url_are_not_synced(self):
        self.demo.failure = "secret-for-tests https://example.invalid/private-video"
        self.demo._publish()
        snapshot = json.dumps(self.demo.snapshot)
        self.assertNotIn("secret-for-tests", snapshot)
        self.assertNotIn("private-video", snapshot)


async def eventually(predicate):
    for _ in range(300):
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("Condition did not become true")


class PlaygroundTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.video = Path(self.tmp.name) / "sample.mp4"
        self.video.write_bytes(b"local-preview")
        self.widget = InteractivePlayground(
            endpoint="https://example.invalid", api_key="secret-for-tests",
            video_path=self.video, video_url="https://example.invalid/private-video",
        )

    async def asyncTearDown(self):
        for s in self.widget.sessions.values():
            if s.running:
                s.task.cancel()
        with patch.object(RealtimeSession, "_confirm_cleanup", new_callable=AsyncMock, return_value=True):
            await asyncio.gather(*(s.task for s in self.widget.sessions.values() if s.task), return_exceptions=True)
        self.widget.close()
        self.tmp.cleanup()

    async def test_parallel_separate_instructions_question_target_and_stop_all(self):
        sockets = [FakeSocket([event("session.ready", category="session"), event("response.text.done", text=text)]) for text in ("描述流", "检测流")]
        with patch("flow_api.connect", side_effect=sockets) as connection:
            self.widget._on_action(None, {"action": "start", "mode": "parallel", "instructions": {"describe": "描述指令", "detect": "检测指令"}}, None)
            await eventually(lambda: all(s.snapshot["can_ask"] for s in self.widget.sessions.values()))
            self.assertEqual(self.widget.snapshot["lanes"]["describe"]["current"]["text"], "描述流")
            self.assertEqual(self.widget.snapshot["lanes"]["detect"]["current"]["text"], "检测流")
            self.widget._on_action(None, {"action": "ask", "target": "detect", "prompt": "检测到了什么？"}, None)
            await eventually(lambda: self.widget.sessions["detect"].state.inquiry_finished)
            await self.widget.shutdown()
            self.assertEqual(connection.call_count, 2)
        self.assertEqual(sockets[0].sent[0]["data"]["instruction"], "描述指令")
        self.assertEqual(sockets[1].sent[0]["data"]["instruction"], "检测指令")
        self.assertEqual(sockets[0].sent[0]["data"]["source"], sockets[1].sent[0]["data"]["source"])
        self.assertFalse(any(m["type"] == "response.create" for m in sockets[0].sent))
        self.assertEqual(sockets[1].sent[1]["data"]["prompt"], "检测到了什么？")
        self.assertTrue(all(s.state.closed for s in self.widget.sessions.values()))
        self.assertFalse(self.widget.running)

    async def test_failure_of_one_lane_stops_peer(self):
        failing = FakeSocket([event("system.error", category="error", fatal=True, error={"code": "session_limit_exceeded"})])
        healthy = FakeSocket([event("session.ready", category="session"), event("response.text.done", text="正常")])
        with patch("flow_api.connect", side_effect=[failing, healthy]), patch.object(RealtimeSession, "_confirm_cleanup", new_callable=AsyncMock, return_value=True):
            self.widget.start(mode="parallel")
            await eventually(lambda: not self.widget.running)
        self.assertTrue(self.widget.sessions["detect"].stop_event.is_set())
        self.assertIn("session_limit_exceeded", self.widget.snapshot["lanes"]["describe"]["error"])

    async def test_invalid_second_instruction_never_opens_first_session(self):
        with patch("flow_api.connect") as connect_mock:
            self.widget.start(mode="parallel", instructions={"describe": "正常", "detect": " "})
            self.assertFalse(self.widget.sessions)
            self.assertTrue(self.widget.snapshot["error"])
            connect_mock.assert_not_called()

    async def test_widget_state_does_not_sync_credentials_or_video_url(self):
        self.widget.error = "secret-for-tests https://example.invalid/private-video"
        self.widget._publish()
        state = self.widget.get_state()
        self.assertNotIn("api_key", state)
        self.assertNotIn("video_url", state)
        self.assertNotIn("secret-for-tests", json.dumps(state["snapshot"]))
        self.assertNotIn("private-video", json.dumps(state["snapshot"]))


if __name__ == "__main__":
    unittest.main()
