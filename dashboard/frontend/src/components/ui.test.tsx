import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EMPTY_MESSAGE, EmptyState, ErrorState, Load, Stat } from "./ui";

describe("ui components", () => {
  it("empty state tells you what to do", () => {
    const html = renderToStaticMarkup(<EmptyState />);
    expect(html).toContain("No data yet — open the HealthSync app on your iPhone");
    expect(html).toContain('role="status"');
  });

  it("Load shows skeleton, error, empty, then content", () => {
    const render = (state: Parameters<typeof Load<number[]>>[0]["state"]) =>
      renderToStaticMarkup(
        <Load state={state} isEmpty={(d) => d.length === 0}>
          {(d) => <span>items:{d.length}</span>}
        </Load>,
      );
    expect(render({ data: null, error: null, loading: true })).toContain('aria-busy="true"');
    expect(render({ data: null, error: "boom", loading: false })).toContain("boom");
    expect(render({ data: [], error: null, loading: false })).toContain(EMPTY_MESSAGE);
    expect(render({ data: [1, 2], error: null, loading: false })).toContain("items:2");
  });

  it("error and stat render their text", () => {
    expect(renderToStaticMarkup(<ErrorState message="nope" />)).toContain('role="alert"');
    const stat = renderToStaticMarkup(<Stat label="Average" value="7h 32m" hint="last 30 days" />);
    expect(stat).toContain("Average");
    expect(stat).toContain("7h 32m");
    expect(stat).toContain("last 30 days");
  });
});
