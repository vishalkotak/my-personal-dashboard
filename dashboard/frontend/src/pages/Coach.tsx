import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useApi } from "../api";

// Chat with the Coach: a Claude agent that answers from your health data through the
// read-only tools in backend/app/agent_tools.py. Replies stream as server-sent events.

interface Msg {
  role: "user" | "coach";
  text: string;
  activity?: string[]; // tools the Coach ran while answering
  error?: string;
}

type CoachEvent =
  | { type: "conversation"; id: string }
  | { type: "text"; text: string }
  | { type: "tool"; name: string; label: string }
  | { type: "done" }
  | { type: "error"; message: string };

const SUGGESTIONS = [
  "How am I doing against the longevity research?",
  "Is my sleep regular enough?",
  "Compare my HRV in August vs. October.",
  "What should I fix first this week?",
];

/** Reads a text/event-stream body and calls onEvent for each `data:` JSON line. */
async function readEvents(res: Response, onEvent: (e: CoachEvent) => void) {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as CoachEvent);
      }
    }
  }
}

// ------------------------------------------------------------------ tiny, safe markdown

const URL_SPLIT = /(https?:\/\/[^\s)]+)/; // capture group keeps the URLs in split()
const IS_URL = /^https?:\/\//;

function inline(text: string, key: string): ReactNode[] {
  // **bold** and bare URLs; everything else is plain text (no HTML is ever injected).
  return text.split(/(\*\*[^*]+\*\*)/g).flatMap((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return [<strong key={`${key}b${i}`}>{part.slice(2, -2)}</strong>];
    }
    return part.split(URL_SPLIT).map((p, j) =>
      IS_URL.test(p) ? (
        <a key={`${key}u${i}-${j}`} href={p} target="_blank" rel="noreferrer">
          {p}
        </a>
      ) : (
        p
      ),
    );
  });
}

function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const items = list.items.map((it, i) => <li key={i}>{inline(it, `li${blocks.length}-${i}`)}</li>);
    blocks.push(list.ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>);
    list = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const num = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (bullet || num) {
      const ordered = !!num;
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? num)![1]);
      continue;
    }
    flush();
    if (!line.trim()) continue;
    const heading = /^#{1,4}\s+(.*)$/.exec(line);
    blocks.push(
      heading ? (
        <p key={blocks.length} className="chat-h">
          {inline(heading[1], `h${blocks.length}`)}
        </p>
      ) : (
        <p key={blocks.length}>{inline(line, `p${blocks.length}`)}</p>
      ),
    );
  }
  flush();
  return <>{blocks}</>;
}

// ------------------------------------------------------------------ page

export function Coach({ resetSignal }: { resetSignal: number }) {
  const status = useApi<{ configured: boolean }>("/api/coach/status");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const convId = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    abort.current?.abort();
    convId.current = null;
    setMsgs([]);
    setBusy(false);
  }, [resetSignal]);

  useEffect(() => endRef.current?.scrollIntoView({ block: "end" }), [msgs]);

  const updateLast = (f: (m: Msg) => Msg) => setMsgs((all) => [...all.slice(0, -1), f(all[all.length - 1])]);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || busy) return;
      setInput("");
      setBusy(true);
      setMsgs((all) => [...all, { role: "user", text: message }, { role: "coach", text: "", activity: [] }]);
      const ctrl = new AbortController();
      abort.current = ctrl;
      try {
        const res = await fetch("/api/coach/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Coach": "1" },
          body: JSON.stringify({ message, conversation_id: convId.current }),
          credentials: "omit",
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) throw new Error(`The backend returned ${res.status}.`);
        await readEvents(res, (e) => {
          if (e.type === "conversation") convId.current = e.id;
          else if (e.type === "text") updateLast((m) => ({ ...m, text: m.text + e.text }));
          else if (e.type === "tool")
            updateLast((m) => ({ ...m, activity: [...(m.activity ?? []), e.label] }));
          else if (e.type === "error") updateLast((m) => ({ ...m, error: e.message }));
        });
      } catch (err) {
        if (!ctrl.signal.aborted) updateLast((m) => ({ ...m, error: (err as Error).message || "Connection lost." }));
      } finally {
        if (abort.current === ctrl) setBusy(false);
      }
    },
    [busy],
  );

  if (status.data && !status.data.configured) {
    return (
      <div className="card coach-setup">
        <h2>Set up the Coach</h2>
        <p className="card-sub">The Coach is a Claude agent that answers questions from your own health data.</p>
        <ol>
          <li>
            Create an API key at <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">console.anthropic.com</a>.
          </li>
          <li>
            Add it to <code>dashboard/.env</code>: <code>ANTHROPIC_API_KEY=sk-ant-…</code>
          </li>
          <li>Quit and reopen the app.</li>
        </ol>
        <p className="muted">
          Only summaries the Coach asks for (daily totals, averages) are sent to Anthropic, under its API terms: not used
          for training, deleted within 30 days.
        </p>
      </div>
    );
  }

  return (
    <div className="chat">
      <div className="chat-log" aria-live="polite">
        {msgs.length === 0 && (
          <div className="chat-empty">
            <p className="chat-hello">Ask me anything about your health data. I'll check the numbers and the research.</p>
            <div className="chat-suggest">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => send(s)} disabled={busy}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`chat-msg chat-${m.role}`}>
            {m.role === "coach" && m.activity && m.activity.length > 0 && (
              <div className="chat-activity">{[...new Set(m.activity)].join(" · ")}</div>
            )}
            {m.role === "user" ? <p>{m.text}</p> : <Markdown text={m.text} />}
            {m.role === "coach" && !m.text && !m.error && busy && i === msgs.length - 1 && (
              <div className="chat-typing" aria-label="Coach is thinking">
                <span />
                <span />
                <span />
              </div>
            )}
            {m.error && <p className="chat-error">{m.error}</p>}
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send(input);
            }
          }}
          placeholder="Ask about your sleep, steps, heart, workouts…"
          rows={1}
          maxLength={4000}
          aria-label="Message the Coach"
        />
        <button type="submit" disabled={busy || !input.trim()}>
          {busy ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
