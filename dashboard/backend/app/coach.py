"""The in-app Coach: a streaming chat with Claude over the health tools in agent_tools.py.

The browser sends one message at a time; the conversation (including tool calls) lives
here in memory, so it's gone when the app quits. Replies stream back as server-sent
events: text as it's written, a note whenever a tool runs, then "done" or "error".

Needs ANTHROPIC_API_KEY in dashboard/.env. Requests go to Anthropic's API under its
commercial terms (no training on your data; deleted within 30 days).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any

from .agent_tools import TOOL_SPECS, HealthTools, ToolError, call_tool

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
MAX_STEPS = 12              # model turns per reply (each tool round is one)
MAX_MESSAGE_CHARS = 4000
MAX_TURNS = 60              # user messages per conversation
MAX_CONVERSATIONS = 20      # kept in memory; oldest dropped
IDLE_EXPIRY_S = 6 * 3600

TOOL_LABELS = {
    "list_available_data": "Checking what data you have",
    "get_metric": "Reading your data",
    "compare_periods": "Comparing periods",
    "get_sleep": "Looking at your sleep",
    "get_workouts": "Looking at your workouts",
    "longevity_status": "Checking the longevity markers",
    "get_research": "Pulling up the research",
    "remember": "Saving a note",
    "recall": "Reading your notes",
    "forget": "Deleting a note",
}

SYSTEM = """\
You are Coach, a blunt, funny, evidence-driven health coach inside the person's own health
dashboard. You talk with the person whose Apple Health data this is.

How you work:
- Answer from their data. Call the tools instead of guessing, and quote the numbers you used
  with their dates. Start with list_available_data when you don't know what exists or how fresh
  it is, and say plainly when data is missing or stale instead of reading meaning into gaps.
- Ground advice in longevity_status and get_research and name the study ("Paluch 2022 found…").
  These are observational associations, not guarantees; say so when it matters.
- Check recall before judging a period, and use remember when they mention an illness, injury,
  travel, a goal or an experiment, so a flu week isn't scolded as laziness.
- Be direct and a little drill-sergeant: name the gap, give one concrete next action. Praise
  real wins briefly. No filler, no lectures, no generic wellness advice that ignores their data.
- Keep replies short: a few sentences or a tight list. Use **bold** for key numbers. No tables.
- You are not a doctor. For anything that looks medical (a sudden resting-HR jump, very low blood
  oxygen, irregular rhythm, chest pain, fainting, dizziness), tell them to see a clinician.
"""

# Stream tool inputs as they're generated; call_tool validates them before anything runs.
TOOLS = [{**spec, "eager_input_streaming": True} for spec in TOOL_SPECS]


class CoachUnavailable(RuntimeError):
    pass


class Coach:
    def __init__(self, tools: HealthTools):
        self.tools = tools
        self._client = None
        self._convs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def configured() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    def _anthropic(self):
        if not self.configured():
            raise CoachUnavailable("Add ANTHROPIC_API_KEY to dashboard/.env, then restart the app.")
        if self._client is None:
            import anthropic  # only needed when the Coach is used

            self._client = anthropic.Anthropic()
        return self._client

    def _conversation(self, conv_id: str | None) -> tuple[str, dict[str, Any]]:
        with self._lock:
            now = time.monotonic()
            for k in [k for k, c in self._convs.items() if now - c["used"] > IDLE_EXPIRY_S]:
                del self._convs[k]
            if conv_id and conv_id in self._convs:
                conv = self._convs[conv_id]
                self._convs.move_to_end(conv_id)
            else:
                conv_id = uuid.uuid4().hex
                conv = {"messages": [], "turns": 0, "busy": False, "used": now}
                self._convs[conv_id] = conv
                while len(self._convs) > MAX_CONVERSATIONS:
                    self._convs.popitem(last=False)
            conv["used"] = now
            return conv_id, conv

    def reply(self, conv_id: str | None, text: str) -> Iterator[dict[str, Any]]:
        """Yields events: conversation, text, tool, done, error."""
        text = (text or "").strip()
        if not text:
            yield {"type": "error", "message": "Say something first."}
            return
        if len(text) > MAX_MESSAGE_CHARS:
            yield {"type": "error", "message": f"Keep messages under {MAX_MESSAGE_CHARS} characters."}
            return
        try:
            client = self._anthropic()
        except CoachUnavailable as e:
            yield {"type": "error", "message": str(e)}
            return

        conv_id, conv = self._conversation(conv_id)
        yield {"type": "conversation", "id": conv_id}
        with self._lock:
            if conv["busy"]:
                yield {"type": "error", "message": "Still answering your last message."}
                return
            if conv["turns"] >= MAX_TURNS:
                yield {"type": "error", "message": "This conversation is long enough. Start a new one."}
                return
            conv["busy"], conv["turns"] = True, conv["turns"] + 1

        # Today's date rides along with the message, so the cached system prompt never changes.
        today = self.tools.today()
        messages: list[Any] = conv["messages"]
        checkpoint = len(messages)
        messages.append({"role": "user", "content": f"[Today is {today:%A, %B %-d, %Y}.]\n\n{text}"})
        try:
            yield from self._run(client, messages)
        except Exception as e:  # noqa: BLE001 - report, never leak internals
            del messages[checkpoint:]  # keep the history valid for the next message
            yield {"type": "error", "message": _friendly(e)}
        finally:
            conv["busy"] = False

    def _run(self, client, messages: list[Any]) -> Iterator[dict[str, Any]]:
        retries = 0
        for _ in range(MAX_STEPS):
            try:
                with client.beta.messages.stream(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM,
                    tools=TOOLS,
                    messages=messages,
                    thinking={"type": "adaptive"},
                    output_config={"effort": "medium"},
                    cache_control={"type": "ephemeral"},
                    # If a safety classifier declines, the API retries on a fallback model in-call.
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                ) as stream:
                    for event in stream:
                        if event.type == "text":
                            yield {"type": "text", "text": event.text}
                        elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                            name = event.content_block.name
                            yield {"type": "tool", "name": name, "label": TOOL_LABELS.get(name, name)}
                    response = stream.get_final_message()
                retries = 0
            except ValueError:
                # Tool input the SDK couldn't parse at all; re-issue the turn (bounded).
                retries += 1
                if retries > 2:
                    raise
                continue

            content = _echoable(response.content)
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": content})
                continue
            if response.stop_reason == "refusal":
                messages.append({"role": "assistant", "content": content or [{"type": "text", "text": "(declined)"}]})
                yield {"type": "error", "message": "Claude declined to answer that one. Try rephrasing."}
                return

            tool_uses = [b for b in content if b.type == "tool_use"]
            messages.append({"role": "assistant", "content": content})
            if not tool_uses:
                yield {"type": "done"}
                return
            if response.stop_reason == "max_tokens":
                raise RuntimeError("reply cut off mid tool call")

            results = []
            for block in tool_uses:
                try:
                    out = call_tool(self.tools, block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": json.dumps(out, default=str)})
                except ToolError as e:
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": str(e), "is_error": True})
                except Exception:  # noqa: BLE001 - a crash: no details to the model
                    log.exception("tool %s failed", block.name)
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": "The tool failed; the data may be unavailable right now.",
                                    "is_error": True})
            messages.append({"role": "user", "content": results})
        yield {"type": "error", "message": "That took too many steps. Try a narrower question."}


def _echoable(content: list[Any]) -> list[Any]:
    """After a mid-output fallback, blocks before the last `fallback` marker that the new
    model can't continue from (thinking, tool_use) must not be echoed back."""
    idx = max((i for i, b in enumerate(content) if b.type == "fallback"), default=-1)
    if idx < 0:
        return list(content)
    drop = {"thinking", "redacted_thinking", "tool_use"}
    return [b for i, b in enumerate(content) if i >= idx or b.type not in drop]


def _friendly(e: Exception) -> str:
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        return "Something went wrong."
    if isinstance(e, anthropic.AuthenticationError):
        return "The API key in dashboard/.env was rejected."
    if isinstance(e, anthropic.RateLimitError):
        return "Rate limited by the API. Wait a moment and try again."
    if isinstance(e, anthropic.APIConnectionError):
        return "Couldn't reach the Anthropic API. Check your internet connection."
    if isinstance(e, anthropic.APIStatusError):
        log.warning("anthropic API error %s", e.status_code)
        return f"The Anthropic API returned an error ({e.status_code}). Try again."
    log.exception("coach failed")
    return "Something went wrong answering that. Try again."
