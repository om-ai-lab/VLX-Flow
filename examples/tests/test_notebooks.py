"""Execute the actual notebook cells against in-memory HTTP/WebSocket fakes."""
import ast
import asyncio
import inspect
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from test_flow_demo import FakeSocket, event, eventually

ROOT = Path(__file__).resolve().parents[2]


def read_cells(filename):
    notebook = json.loads((ROOT / "examples/notebooks" / filename).read_text())
    return {c["metadata"]["tags"][0]: "".join(c["source"])
            for c in notebook["cells"] if c["cell_type"] == "code"}


async def execute(source, namespace):
    result = eval(compile(source, "<notebook-cell>", "exec", ast.PyCF_ALLOW_TOP_LEVEL_AWAIT), namespace)
    if inspect.isawaitable(result):
        await result


class TextOutput:
    def __init__(self):
        self.updates = []

    def update(self, data, **kwargs):
        self.updates.append(data)


class NotebookTest(unittest.IsolatedAsyncioTestCase):
    async def prepare(self, filename):
        cells = read_cells(filename)
        namespace = {}
        with patch("pathlib.Path.cwd", return_value=ROOT), patch("builtins.print"):
            await execute(cells["setup"], namespace)
            namespace["getpass"] = lambda _: "offline-test-key"
            namespace["input"] = lambda _: "https://example.invalid"
            namespace["display"] = lambda *a, **k: TextOutput()
            await execute(cells["configure"], namespace)
        requests = []

        def upload(request):
            requests.append(request)
            self.assertEqual(request.url.path, "/os/uploadFile")
            self.assertEqual(request.headers["Authorization"], "Bearer offline-test-key")
            self.assertIn(b'name="file"', request.content)
            self.assertIn(b'name="type"', request.content)
            return httpx.Response(200, json={"data": {"fileUrl": "https://example.invalid/uploaded.mp4"}})

        async_client = httpx.AsyncClient
        with patch("httpx.AsyncClient", side_effect=lambda **kw: async_client(transport=httpx.MockTransport(upload), **kw)), patch("builtins.print"):
            await execute(cells["upload"], namespace)
            await execute(cells["upload"], namespace)
        self.assertEqual(len(requests), 1, "Repeat upload should reuse this kernel's cache")
        return cells, namespace

    async def test_basic_cells_create_question_stop_and_optional_parallel(self):
        cells, ns = await self.prepare("01_api_quickstart.ipynb")
        for tag in ("receiver", "text-display"):
            await execute(cells[tag], ns)
        first = FakeSocket([event("session.ready", category="session"), event("response.text.done", text="...")])
        ns["connect"] = lambda *a, **k: first
        with patch("builtins.print"):
            await execute(cells["start"], ns)
            session = ns["session"]
            try:
                await eventually(lambda: session.can_ask)
                with self.assertRaises(RuntimeError):
                    await execute(cells["start"], ns)
                await execute(cells["ask"].replace('QUESTION = ""', 'QUESTION = "当前是什么场景？"', 1), ns)
                await eventually(lambda: bool(session.state.inquiry_finished))
            finally:
                await execute(cells["stop"], ns)
            await execute(cells["stop"], ns)
            await execute(cells["parallel-start"], ns)  # Default opt-in is false.
            self.assertNotIn("parallel_sessions", ns)
        self.assertEqual([m["type"] for m in first.sent], ["session.create", "response.create", "session.close"])
        self.assertEqual(first.sent[1]["data"]["prompt"], "当前是什么场景？")
        self.assertTrue(session.state.closed)
        self.assertTrue(any("..." in u["text/plain"] for u in session.text_output.updates))

        sockets = [FakeSocket([event("session.ready", category="session"), event("response.text.done", text=text)]) for text in ("描述", "检测")]
        remaining = iter(sockets)
        ns["connect"] = lambda *a, **k: next(remaining)
        with patch("builtins.print"):
            await execute(cells["parallel-start"].replace("RUN_PARALLEL = False", "RUN_PARALLEL = True"), ns)
            try:
                await eventually(lambda: all(s.can_ask for s in ns["parallel_sessions"].values()))
                await execute(cells["parallel-ask"].replace('PARALLEL_QUESTION = ""', 'PARALLEL_QUESTION = "描述路的问题"'), ns)
                await eventually(lambda: ns["parallel_sessions"]["describe"].state.inquiry_finished)
            finally:
                await execute(cells["parallel-stop"], ns)
        self.assertTrue(all(s.state.closed for s in ns["parallel_sessions"].values()))
        self.assertEqual([m["type"] for m in sockets[1].sent], ["session.create", "session.close"])
        ns["API_ENDPOINT"] = "https://changed.example.invalid"
        with self.assertRaisesRegex(RuntimeError, "上传"):
            await execute(cells["parallel-start"].replace("RUN_PARALLEL = False", "RUN_PARALLEL = True"), ns)

    async def test_advanced_cells_widget_then_stop_and_diagnostics(self):
        cells, ns = await self.prepare("02_interactive_playground.ipynb")
        await execute(cells["widget"], ns)
        widget = ns["playground"]
        ws = FakeSocket([event("session.ready", category="session"), event("response.text.done", text="检测事件")])
        try:
            with patch("flow_api.connect", return_value=ws), patch("builtins.print"):
                widget.start(mode="detect")
                await eventually(lambda: widget.sessions["detect"].can_ask)
                with self.assertRaises(RuntimeError):
                    await execute(cells["configure"], ns)
                widget._on_action(None, {"action": "ask", "target": "detect", "prompt": "是什么事件？"}, None)
                await eventually(lambda: widget.sessions["detect"].state.inquiry_finished)
                await execute(cells["stop"], ns)
                await execute(cells["diagnostics"], ns)
        finally:
            widget.close()
        self.assertFalse(widget.running)
        self.assertEqual(ws.sent[0]["data"]["instruction"], ns["DETECTION"])


if __name__ == "__main__":
    unittest.main()
