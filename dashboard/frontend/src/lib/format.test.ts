import { describe, expect, it } from "vitest";
import {
  average,
  DASH,
  formatAgo,
  formatDate,
  formatMinutes,
  formatNumber,
  formatValue,
  scaleMass,
  tickInterval,
} from "./format";

describe("formatNumber", () => {
  it("adds separators and picks decimals by magnitude", () => {
    expect(formatNumber(12345.6)).toBe("12,346");
    expect(formatNumber(56.78)).toBe("56.8");
    expect(formatNumber(0.1234)).toBe("0.12");
    expect(formatNumber(0)).toBe("0");
    expect(formatNumber(3.14159, 3)).toBe("3.142");
  });
  it("renders missing values as a dash", () => {
    expect(formatNumber(null)).toBe(DASH);
    expect(formatNumber(undefined)).toBe(DASH);
    expect(formatNumber(NaN)).toBe(DASH);
    expect(formatNumber(Infinity)).toBe(DASH);
  });
});

describe("scaleMass (nutrition stored in grams)", () => {
  it("keeps grams for normal amounts", () => expect(scaleMass(42)).toEqual({ value: 42, unit: "g" }));
  it("uses mg below 1 g", () => {
    const s = scaleMass(0.25);
    expect(s.unit).toBe("mg");
    expect(s.value).toBeCloseTo(250);
  });
  it("uses µg below 1 mg", () => {
    const s = scaleMass(0.0000024);
    expect(s.unit).toBe("µg");
    expect(s.value).toBeCloseTo(2.4);
  });
  it("leaves zero alone", () => expect(scaleMass(0)).toEqual({ value: 0, unit: "g" }));
});

describe("formatValue", () => {
  it("auto-scales grams", () => {
    expect(formatValue(30, "g")).toBe("30 g");
    expect(formatValue(0.012, "g")).toBe("12 mg");
    expect(formatValue(0.0000024, "g")).toBe("2.4 µg");
  });
  it("formats percent (already ×100 by the backend)", () => {
    expect(formatValue(96.53, "%")).toBe("96.5%");
  });
  it("shows minutes as h/m and bpm with a unit", () => {
    expect(formatValue(452, "min")).toBe("7h 32m");
    expect(formatValue(61.4, "bpm")).toBe("61.4 bpm");
  });
  it("shows metres as km above 1000", () => {
    expect(formatValue(5234, "m")).toBe("5.23 km");
    expect(formatValue(800, "m")).toBe("800 m");
  });
  it("counts have no unit", () => {
    expect(formatValue(9876.4, "steps")).toBe("9,876");
    expect(formatValue(3, "")).toBe("3");
  });
  it("dashes missing values", () => expect(formatValue(null, "kg")).toBe(DASH));
});

describe("formatMinutes", () => {
  it.each([
    [452, "7h 32m"],
    [45, "45m"],
    [120, "2h"],
    [0, "0m"],
    [0.5, "30s"],
    [59.6, "1h"],
  ])("%s -> %s", (min, out) => expect(formatMinutes(min)).toBe(out));
  it("dashes null", () => expect(formatMinutes(null)).toBe(DASH));
});

describe("dates", () => {
  it("formats ISO dates without time-zone drift", () => {
    expect(formatDate("2026-11-03")).toBe("Nov 3");
    expect(formatDate("2026-01-31", true)).toBe("Jan 31, 2026");
    expect(formatDate("2026-03-08T07:00:00+00:00")).toBe("Mar 8");
  });
  it("formats relative times", () => {
    const now = new Date("2026-11-11T12:00:00Z");
    expect(formatAgo("2026-11-11T11:53:00Z", now)).toBe("7 min ago");
    expect(formatAgo("2026-11-11T09:00:00Z", now)).toBe("3 h ago");
    expect(formatAgo("2026-11-10T12:00:00Z", now)).toBe("yesterday");
    expect(formatAgo("2026-11-01T12:00:00Z", now)).toBe("10 days ago");
    expect(formatAgo(null, now)).toBe("never");
  });
});

describe("helpers", () => {
  it("averages ignoring gaps", () => {
    expect(average([1, null, 3, undefined])).toBe(2);
    expect(average([null])).toBeNull();
  });
  it("picks tick intervals", () => {
    expect(tickInterval(7)).toBe(0);
    expect(tickInterval(30)).toBe(4);
    expect(tickInterval(365)).toBe(52);
  });
});
