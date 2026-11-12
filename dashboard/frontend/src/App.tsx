import { useCallback, useEffect, useState } from "react";
import { useApi, type Health } from "./api";
import { RangePicker } from "./components/ui";
import { formatAgo } from "./lib/format";
import { rangeFromParams, rangeToParams, toISODate, type DateRange } from "./lib/range";
import { Activity } from "./pages/Activity";
import { Body } from "./pages/Body";
import { Explore } from "./pages/Explore";
import { Heart } from "./pages/Heart";
import { Overview } from "./pages/Overview";
import { Sleep } from "./pages/Sleep";
import { Workouts } from "./pages/Workouts";
import { isTab, TABS, type Tab } from "./tabs";

// State lives in the URL hash (#/sleep?range=90d) so reloads and bookmarks keep your place.
interface Route {
  tab: Tab;
  range: DateRange;
  type: string | null;
}

function readRoute(today: string): Route {
  const [path, qs = ""] = window.location.hash.replace(/^#\/?/, "").split("?");
  const params = new URLSearchParams(qs);
  return {
    tab: isTab(path) ? path : "overview",
    range: rangeFromParams(params, today),
    type: params.get("type"),
  };
}

function writeRoute(r: Route) {
  const params = new URLSearchParams(rangeToParams(r.range));
  if (r.tab === "explore" && r.type) params.set("type", r.type);
  const hash = `#/${r.tab}?${params.toString()}`;
  if (window.location.hash !== hash) window.history.replaceState(null, "", hash);
}

function StatusPill() {
  const h = useApi<Health>("/api/health");
  if (h.error) return <span className="pill pill-bad">Backend offline</span>;
  if (!h.data) return <span className="pill">Connecting…</span>;
  if (h.data.demo) return <span className="pill pill-demo" title="DEMO=1: synthetic data, not yours">Demo data</span>;
  if (!h.data.database_reachable) return <span className="pill pill-bad">Can't reach database</span>;
  return (
    <span className="pill pill-ok" title={`Time zone: ${h.data.tz}`}>
      Last sync {formatAgo(h.data.last_upload)}
    </span>
  );
}

export function App() {
  const today = toISODate(new Date());
  const [route, setRoute] = useState<Route>(() => readRoute(today));

  useEffect(() => writeRoute(route), [route]);
  useEffect(() => {
    const onHash = () => setRoute(readRoute(toISODate(new Date())));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = useCallback((tab: Tab) => {
    setRoute((r) => ({ ...r, tab }));
    window.scrollTo({ top: 0 });
  }, []);
  const setRange = useCallback((range: DateRange) => setRoute((r) => ({ ...r, range })), []);

  const { tab, range } = route;
  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="var(--series-1)" />
            <path d="M6 17h5l2-5 4 10 3-7h6" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <h1>Health</h1>
          <StatusPill />
        </div>
        <nav className="tabs" aria-label="Sections">
          {TABS.map((t) => (
            <a
              key={t.id}
              href={`#/${t.id}`}
              aria-current={t.id === tab ? "page" : undefined}
              onClick={(e) => {
                e.preventDefault();
                go(t.id);
              }}
            >
              {t.label}
            </a>
          ))}
        </nav>
      </header>

      <main>
        <div className="toolbar">
          <h2 className="page-title">{TABS.find((t) => t.id === tab)!.label}</h2>
          {tab === "overview" ? (
            <span className="muted">Today</span>
          ) : (
            <RangePicker key={`${range.preset}-${range.from}-${range.to}`} range={range} today={today} onChange={setRange} />
          )}
        </div>
        {tab === "overview" && <Overview onOpen={go} />}
        {tab === "activity" && <Activity range={range} />}
        {tab === "heart" && <Heart range={range} />}
        {tab === "sleep" && <Sleep range={range} />}
        {tab === "body" && <Body range={range} />}
        {tab === "workouts" && <Workouts range={range} />}
        {tab === "explore" && (
          <Explore range={range} selected={route.type} onSelect={(type) => setRoute((r) => ({ ...r, type }))} />
        )}
      </main>
      <footer className="foot">
        Runs locally on this computer. Data comes from your own Supabase database via a read-only login.
      </footer>
    </div>
  );
}
