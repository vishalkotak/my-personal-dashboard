"""The Coach's chat loop, driven by a scripted fake of the Anthropic client."""

from types import SimpleNamespace as NS

import pytest

from app.coach import Coach

from .test_agent_tools import settings, source, tools  # noqa: F401 - fixtures


class FakeStream:
    def __init__(self, events, final):
        self.events, self.final = events, final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self.events)

    def get_final_message(self):
        return self.final


class FakeClient:
    """Plays back one scripted model turn per stream() call and records what it was sent."""

    def __init__(self, turns):
        self.turns, self.sent = list(turns), []
        self.beta = NS(messages=NS(stream=self.stream))

    def stream(self, **kwargs):
        self.sent.append([dict(m) for m in kwargs["messages"]])
        return self.turns.pop(0)


def tool_turn(name, args):
    block = NS(type="tool_use", id="tu_1", name=name, input=args)
    return FakeStream([NS(type="content_block_start", content_block=block)],
                      NS(stop_reason="tool_use", content=[block]))


def text_turn(text):
    return FakeStream([NS(type="text", text=text)],
                      NS(stop_reason="end_turn", content=[NS(type="text", text=text)]))


@pytest.fixture()
def coach(tools, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    return Coach(tools)


def run(coach, client, text, conv=None):
    coach._client = client
    return list(coach.reply(conv, text))


def test_tool_call_then_streamed_answer(coach):
    client = FakeClient([tool_turn("get_metric", {"metric": "steps"}), text_turn("You averaged **8,000**.")])
    events = run(coach, client, "How are my steps?")
    kinds = [e["type"] for e in events]
    assert kinds == ["conversation", "tool", "text", "done"]
    assert events[1]["label"] == "Reading your data"
    # The second model turn received the tool result with real numbers in it.
    result = client.sent[1][-1]["content"][0]
    assert result["type"] == "tool_result" and "summary" in result["content"] and not result.get("is_error")
    # Today's date rides along with the user's message.
    assert client.sent[0][0]["content"].startswith("[Today is ")


def test_bad_tool_input_goes_back_to_the_model_as_an_error(coach):
    client = FakeClient([tool_turn("get_metric", {"metric": "steps", "start": "yesterday"}), text_turn("Fixed.")])
    run(coach, client, "steps?")
    result = client.sent[1][-1]["content"][0]
    assert result["is_error"] and "YYYY-MM-DD" in result["content"]


def test_unknown_arguments_are_rejected_before_running(coach):
    client = FakeClient([tool_turn("forget", {"note_id": 1, "everything": True}), text_turn("ok")])
    run(coach, client, "forget it")
    assert client.sent[1][-1]["content"][0]["is_error"]


def test_conversation_continues_with_history(coach):
    first = run(coach, FakeClient([text_turn("Hi.")]), "hello")
    conv_id = first[0]["id"]
    client = FakeClient([text_turn("Again.")])
    run(coach, client, "and again", conv=conv_id)
    roles = [m["role"] for m in client.sent[0]]
    assert roles == ["user", "assistant", "user"]


def test_api_failure_rolls_back_the_turn(coach):
    class Boom(FakeClient):
        def stream(self, **kw):
            raise RuntimeError("network down")

    events = run(coach, Boom([]), "hello")
    assert events[-1]["type"] == "error"
    conv = coach._convs[events[0]["id"]]
    assert conv["messages"] == [] and not conv["busy"]


def test_message_limits(coach):
    assert run(coach, FakeClient([]), "   ")[-1]["type"] == "error"
    assert "under" in run(coach, FakeClient([]), "x" * 5000)[-1]["message"]
