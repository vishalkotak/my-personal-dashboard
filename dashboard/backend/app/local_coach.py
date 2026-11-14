"""The on-device Coach: the same chat, answered by a small fine-tuned model running on this Mac.

The model lives in a separate project (~/workspace/mini-projects/ml/health-llm): Qwen3.5-0.8B with a
LoRA adapter trained to behave like the Claude Coach. Its server runs the same health tools against
the same database and speaks Claude's Messages API format on 127.0.0.1:8800, streaming each tool it
runs as a `server_tool_use` block. Nothing leaves this computer.

This class reuses Coach's conversation store, limits and event format. Only the model call differs:
the conversation is sent as plain text turns, because the tools run inside the local server.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

from .coach import TOOL_LABELS, Coach, CoachUnavailable

LOCAL_URL = os.environ.get("LOCAL_COACH_URL", "http://127.0.0.1:8800").rstrip("/")
LOCAL_LABELS = {**TOOL_LABELS, "search_papers": "Searching the research papers"}
DATE_PREFIX = re.compile(r"^\[Today is [^\]]*\]\n\n")  # the local server adds its own
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class LocalCoach(Coach):
    _status: tuple[float, dict[str, Any] | None] = (0.0, None)

    @staticmethod
    def _loopback() -> bool:
        return urlparse(LOCAL_URL).hostname in _LOOPBACK  # health data never goes to another machine

    @classmethod
    def info(cls) -> dict[str, Any] | None:
        """The local server's /health, or None if it isn't running. Cached for a few seconds."""
        checked, info = cls._status
        if time.monotonic() - checked < 5:
            return info
        info = None
        if cls._loopback():
            import httpx

            try:
                r = httpx.get(f"{LOCAL_URL}/health", timeout=0.5)
                info = r.json() if r.status_code == 200 and r.json().get("ok") else None
            except (httpx.HTTPError, ValueError):
                info = None
        cls._status = (time.monotonic(), info)
        return info

    @classmethod
    def configured(cls) -> bool:  # type: ignore[override]
        return cls.info() is not None

    def _anthropic(self):  # the "client" here is plain HTTP to the local server
        if not self._loopback():
            raise CoachUnavailable("LOCAL_COACH_URL must point at this computer (127.0.0.1).")
        type(self)._status = (0.0, None)  # re-check now rather than trust the cache
        if not self.configured():
            raise CoachUnavailable("The on-device model isn't running. Start it with "
                                   "`uv run python -m healthllm.server` in mini-projects/ml/health-llm.")
        import httpx

        return httpx

    def _run(self, client, messages: list[Any]) -> Iterator[dict[str, Any]]:
        turns = [{"role": m["role"], "content": DATE_PREFIX.sub("", m["content"])} for m in messages]
        text = ""
        body = {"model": "coach", "max_tokens": 600, "stream": True, "temperature": 0.3, "messages": turns}
        with client.stream("POST", f"{LOCAL_URL}/v1/messages", json=body, timeout=300) as r:
            if r.status_code != 200:
                raise RuntimeError(f"local server returned {r.status_code}")
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                e = json.loads(line[6:])
                if e["type"] == "content_block_start" and e["content_block"]["type"] == "server_tool_use":
                    name = e["content_block"]["name"]
                    yield {"type": "tool", "name": name, "label": LOCAL_LABELS.get(name, name)}
                elif e["type"] == "content_block_delta" and e["delta"]["type"] == "text_delta":
                    text += e["delta"]["text"]
                    yield {"type": "text", "text": e["delta"]["text"]}
        messages.append({"role": "assistant", "content": text.strip() or "(no answer)"})
        yield {"type": "done"}
