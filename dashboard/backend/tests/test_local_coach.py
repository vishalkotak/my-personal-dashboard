"""The on-device Coach, driven by a fake of the local model server's streaming HTTP response."""

import json

import pytest

from app import local_coach
from app.local_coach import LocalCoach

from .test_agent_tools import settings, source, tools  # noqa: F401 - fixtures


def sse(*events):
    return [f"data: {json.dumps(e)}" for e in events]


class FakeHTTP:
    """Stands in for httpx: records each request body and replays scripted SSE lines."""

    def __init__(self, *replies):
        self.replies, self.sent = list(replies), []

    def stream(self, method, url, json, timeout):  # noqa: A002 - mirrors httpx's signature
        self.sent.append(json)
        lines = self.replies.pop(0)

        class Resp:
            status_code = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def iter_lines(self):
                return iter(lines)

        return Resp()


@pytest.fixture()
def coach(tools):  # noqa: F811
    return LocalCoach(tools)


def run(coach, monkeypatch, http, text, conv=None):
    monkeypatch.setattr(LocalCoach, "_anthropic", lambda self: http)
    return list(coach.reply(conv, text))


def reply(*parts):
    events = [{"type": "message_start"}]
    for p in parts:
        if p.startswith("tool:"):
            events.append({"type": "content_block_start", "index": 0,
                           "content_block": {"type": "server_tool_use", "id": "s", "name": p[5:], "input": {}}})
        else:
            events.append({"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": p}})
    return sse(*events, {"type": "message_stop"})


def test_tools_and_text_stream_as_coach_events(coach, monkeypatch):
    http = FakeHTTP(reply("tool:get_sleep", "tool:search_papers", "You slept ", "**7.1 h**."))
    events = run(coach, monkeypatch, http, "How did I sleep?")
    assert [e["type"] for e in events] == ["conversation", "tool", "tool", "text", "text", "done"]
    assert events[1]["label"] == "Looking at your sleep"
    assert events[2]["label"] == "Searching the research papers"
    # The local server adds today's date itself, so the dashboard's prefix is stripped.
    assert http.sent[0]["messages"] == [{"role": "user", "content": "How did I sleep?"}]


def test_follow_ups_send_the_whole_conversation(coach, monkeypatch):
    http = FakeHTTP(reply("Steady at **56 bpm**."), reply("Yes."))
    conv = run(coach, monkeypatch, http, "Resting HR?")[0]["id"]
    run(coach, monkeypatch, http, "Is that good?", conv)
    assert http.sent[1]["messages"] == [
        {"role": "user", "content": "Resting HR?"},
        {"role": "assistant", "content": "Steady at **56 bpm**."},
        {"role": "user", "content": "Is that good?"},
    ]


def test_refuses_a_non_local_server(coach, monkeypatch):
    monkeypatch.setattr(local_coach, "LOCAL_URL", "https://example.com")
    assert not LocalCoach._loopback()
    events = list(coach.reply(None, "hi"))
    assert events[-1]["type"] == "error" and "127.0.0.1" in events[-1]["message"]
