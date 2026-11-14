import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useApi } from "../api";

// Chat with the Coach, answered by one of two engines over the same read-only health tools
// (backend/app/agent_tools.py):
//   * Claude    - the Claude API (needs ANTHROPIC_API_KEY), backend/app/coach.py
//   * On-device - a small fine-tuned model on this Mac (ml-projects/health-llm), backend/app/local_coach.py
// Replies stream as server-sent events: tool steps as they run, then the answer word by word.

export type Engine = "claude" | "local";

interface CoachStatus {
  configured: boolean; // Claude
  local?: { available: boolean; model: string | null; fine_tuned: boolean };
}

interface Msg {
  role: "user" | "coach";
  text: string;
  engine?: Engine;
  activity?: string[]; // tools the Coach ran while answering, in order
  error?: string;
  started?: number; // ms timestamps, for the "answered in 5.2 s" line
  finished?: number;
  stopped?: boolean;
}

type CoachEvent =
  | { type: "conversation"; id: string }
  | { type: "text"; text: string }
  | { type: "tool"; name: string; label: string }
  | { type: "done" }
  | { type: "error"; message: string };

const SUGGESTIONS: { tag: string; text: string; color: string }[] = [
  { tag: "Longevity", text: "How am I doing against the longevity research?", color: "var(--series-3)" },
  { tag: "Sleep", text: "How did I sleep this week?", color: "var(--series-7)" },
  { tag: "Heart", text: "What's my resting heart rate been lately?", color: "var(--series-8)" },
  { tag: "Focus", text: "What should I fix first this week?", color: "var(--series-2)" },
];

const ENGINE_KEY = "coach.engine";
function savedEngine(): Engine | null {
  try {
    const v = localStorage.getItem(ENGINE_KEY);
    return v === "claude" || v === "local" ? v : null;
  } catch {
    return null;
  }
}

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

// ------------------------------------------------------------------ small pieces

function CoachMark({ size = 28, pulse = false }: { size?: number; pulse?: boolean }) {
  return (
    <span className={`coach-mark${pulse ? " coach-mark-pulse" : ""}`} style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 32 32" width={size * 0.62} height={size * 0.62}>
        <path d="M5 17h5l2.2-5.5L16.5 22l3-7.5H27" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

function Icon({ name }: { name: "send" | "stop" | "copy" | "check" | "lock" | "cloud" }) {
  const paths: Record<string, ReactNode> = {
    send: <path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" />,
    stop: <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none" />,
    copy: (
      <>
        <rect x="8.5" y="8.5" width="11" height="11" rx="2.5" />
        <path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" />
      </>
    ),
    check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
    lock: (
      <>
        <rect x="5" y="10.5" width="14" height="9.5" rx="2.5" />
        <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" />
      </>
    ),
    cloud: <path d="M7.5 18.5h9.25a4.25 4.25 0 0 0 .6-8.46A5.5 5.5 0 0 0 6.9 11.1 3.75 3.75 0 0 0 7.5 18.5Z" />,
  };
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

/** The tools the Coach ran: done steps get a check, the current one a spinner. */
function Steps({ labels, live }: { labels: string[]; live: boolean }) {
  const steps = labels.filter((l, i) => labels.indexOf(l) === i);
  if (!steps.length) return null;
  return (
    <ul className="chat-steps">
      {steps.map((s, i) => {
        const running = live && i === steps.length - 1;
        return (
          <li key={s} className={running ? "running" : "done"}>
            {running ? <span className="chat-spin" aria-hidden="true" /> : <Icon name="check" />}
            {s}
            {running ? "…" : ""}
          </li>
        );
      })}
    </ul>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="chat-tool-btn"
      onClick={() =>
        navigator.clipboard?.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1400);
        })
      }
      aria-label="Copy answer"
      title="Copy"
    >
      <Icon name={done ? "check" : "copy"} />
    </button>
  );
}

const ENGINE_NAME: Record<Engine, string> = { claude: "Claude", local: "On-device" };

// ------------------------------------------------------------------ page

export function Coach({ resetSignal }: { resetSignal: number }) {
  const status = useApi<CoachStatus>("/api/coach/status");
  const claudeOk = !!status.data?.configured;
  const localOk = !!status.data?.local?.available;
  const [picked, setPicked] = useState<Engine | null>(savedEngine);
  // Use the saved choice if that engine is up, otherwise whichever one is available.
  const engine: Engine = picked === "claude" && claudeOk ? "claude" : picked === "local" && localOk ? "local" : localOk ? "local" : "claude";

  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const convId = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const reset = useCallback(() => {
    abort.current?.abort();
    convId.current = null;
    setMsgs([]);
    setBusy(false);
  }, []);
  useEffect(() => {
    reset();
  }, [resetSignal, reset]);
  // Braces matter: newer browsers make scrollIntoView() return a Promise, and an effect must
  // return nothing or a cleanup function. Returning the Promise crashes React.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [msgs]);

  const choose = (e: Engine) => {
    if (e === engine) return;
    try {
      localStorage.setItem(ENGINE_KEY, e);
    } catch {
      /* private window: the choice just won't be remembered */
    }
    setPicked(e);
    reset(); // each engine keeps its own conversation on the backend
    inputRef.current?.focus();
  };

  const updateLast = (f: (m: Msg) => Msg) => setMsgs((all) => [...all.slice(0, -1), f(all[all.length - 1])]);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || busy) return;
      setInput("");
      setBusy(true);
      setMsgs((all) => [
        ...all,
        { role: "user", text: message },
        { role: "coach", text: "", activity: [], engine, started: Date.now() },
      ]);
      const ctrl = new AbortController();
      abort.current = ctrl;
      try {
        const res = await fetch("/api/coach/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Coach": "1" },
          body: JSON.stringify({ message, conversation_id: convId.current, engine }),
          credentials: "omit",
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) throw new Error(`The backend returned ${res.status}.`);
        await readEvents(res, (e) => {
          if (e.type === "conversation") convId.current = e.id;
          else if (e.type === "text") updateLast((m) => ({ ...m, text: m.text + e.text }));
          else if (e.type === "tool") updateLast((m) => ({ ...m, activity: [...(m.activity ?? []), e.label] }));
          else if (e.type === "error") updateLast((m) => ({ ...m, error: e.message }));
        });
      } catch (err) {
        if (ctrl.signal.aborted) updateLast((m) => ({ ...m, stopped: true }));
        else updateLast((m) => ({ ...m, error: (err as Error).message || "Connection lost." }));
      } finally {
        if (abort.current === ctrl) {
          updateLast((m) => ({ ...m, finished: Date.now() }));
          setBusy(false);
        }
      }
    },
    [busy, engine],
  );

  if (status.data && !claudeOk && !localOk) {
    return (
      <div className="card coach-setup">
        <h2>Set up the Coach</h2>
        <p className="card-sub">The Coach answers questions from your own health data. Turn on either engine:</p>
        <ol>
          <li>
            <strong>On-device</strong> (free, private): in <code>~/workspace/ml-projects/health-llm</code> run{" "}
            <code>uv run python -m healthllm.server</code>, then reload this page.
          </li>
          <li>
            <strong>Claude</strong>: create an API key at{" "}
            <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">
              console.anthropic.com
            </a>
            , add <code>ANTHROPIC_API_KEY=sk-ant-…</code> to <code>dashboard/.env</code>, and restart the app.
          </li>
        </ol>
      </div>
    );
  }

  const local = status.data?.local;
  const engineNote =
    engine === "local"
      ? `${local?.model?.split("/").pop() ?? "Local model"}${local?.fine_tuned ? " · fine-tuned" : ""} · nothing leaves this Mac`
      : "Claude · summaries go to Anthropic's API, never used for training";

  return (
    <div className="chat">
      <div className="chat-head">
        <div className="engine-switch" role="radiogroup" aria-label="Coach engine">
          {(["local", "claude"] as Engine[]).map((e) => {
            const ok = e === "local" ? localOk : claudeOk;
            return (
              <button
                key={e}
                type="button"
                role="radio"
                aria-checked={engine === e}
                disabled={!ok || busy}
                title={ok ? undefined : e === "local" ? "Start the health-llm server to use this" : "Add ANTHROPIC_API_KEY to use this"}
                onClick={() => choose(e)}
              >
                <Icon name={e === "local" ? "lock" : "cloud"} />
                {ENGINE_NAME[e]}
                <span className={`engine-dot${ok ? " on" : ""}`} aria-hidden="true" />
              </button>
            );
          })}
        </div>
        <span className="chat-note">{engineNote}</span>
      </div>

      <div className="chat-log" aria-live="polite">
        {msgs.length === 0 && (
          <div className="chat-empty">
            <CoachMark size={52} />
            <h3 className="chat-hello">What do you want to know?</h3>
            <p className="chat-sub">I read your Apple Health data and the studies behind each target, then give you one thing to do.</p>
            <div className="chat-suggest">
              {SUGGESTIONS.map((s) => (
                <button key={s.text} type="button" onClick={() => send(s.text)} disabled={busy}>
                  <span className="chat-suggest-tag" style={{ color: s.color }}>
                    {s.tag}
                  </span>
                  {s.text}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => {
          const live = busy && i === msgs.length - 1;
          if (m.role === "user")
            return (
              <div key={i} className="chat-msg chat-user">
                <p>{m.text}</p>
              </div>
            );
          const secs = m.finished && m.started ? ((m.finished - m.started) / 1000).toFixed(1) : null;
          return (
            <div key={i} className="chat-msg chat-coach">
              <CoachMark pulse={live && !m.text} />
              <div className="chat-body">
                <Steps labels={m.activity ?? []} live={live && !m.text} />
                {m.text ? (
                  <div className={`chat-text${live ? " streaming" : ""}`}>
                    <Markdown text={m.text} />
                  </div>
                ) : (
                  live && !m.error && <p className="chat-thinking">{m.activity?.length ? "Reading the numbers" : "Thinking"}</p>
                )}
                {m.error && <p className="chat-error">{m.error}</p>}
                {m.stopped && <p className="chat-meta">Stopped.</p>}
                {!live && m.text && !m.stopped && (
                  <div className="chat-meta">
                    <span>
                      {ENGINE_NAME[m.engine ?? "claude"]}
                      {secs && ` · ${secs} s`}
                      {m.activity?.length ? ` · ${new Set(m.activity).size} lookup${new Set(m.activity).size > 1 ? "s" : ""}` : ""}
                    </span>
                    <CopyButton text={m.text} />
                  </div>
                )}
              </div>
            </div>
          );
        })}
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
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send(input);
            }
          }}
          placeholder={msgs.length ? "Ask a follow-up…" : "Ask about your sleep, steps, heart, workouts…"}
          rows={1}
          maxLength={4000}
          aria-label="Message the Coach"
        />
        {busy ? (
          <button type="button" className="chat-send stop" onClick={() => abort.current?.abort()} aria-label="Stop answering">
            <Icon name="stop" />
          </button>
        ) : (
          <button type="submit" className="chat-send" disabled={!input.trim()} aria-label="Send">
            <Icon name="send" />
          </button>
        )}
      </form>
      <p className="chat-hint">
        <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line · Not medical advice
      </p>
    </div>
  );
}
