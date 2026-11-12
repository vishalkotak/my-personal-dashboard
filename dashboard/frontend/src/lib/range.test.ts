import { describe, expect, it } from "vitest";
import {
  addDays,
  daysInclusive,
  MAX_RANGE_DAYS,
  parseISODate,
  presetRange,
  rangeFromParams,
  rangeToParams,
  toISODate,
  validateRange,
} from "./range";

const TODAY = "2026-11-11";

describe("presets", () => {
  it("are inclusive of today", () => {
    expect(presetRange("7d", TODAY)).toEqual({ preset: "7d", from: "2026-11-05", to: TODAY });
    expect(daysInclusive("2026-11-05", TODAY)).toBe(7);
    expect(daysInclusive(presetRange("1y", TODAY).from, TODAY)).toBe(365);
    expect(daysInclusive(presetRange("90d", TODAY).from, TODAY)).toBe(90);
  });
  it("cross month, year and DST boundaries", () => {
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(addDays("2024-03-01", -1)).toBe("2024-02-29");
    expect(addDays("2026-01-01", -1)).toBe("2025-12-31");
    expect(addDays("2026-03-07", 2)).toBe("2026-03-09"); // spring forward
    expect(daysInclusive("2026-11-01", "2026-11-02")).toBe(2); // fall back
  });
});

describe("parsing", () => {
  it("rejects malformed and impossible dates", () => {
    expect(parseISODate("2026-02-30")).toBeNull();
    expect(parseISODate("2026-2-3")).toBeNull();
    expect(parseISODate("yesterday")).toBeNull();
    expect(toISODate(parseISODate("2026-02-28")!)).toBe("2026-02-28");
  });
});

describe("validateRange", () => {
  it("accepts a normal range", () => expect(validateRange("2026-01-01", "2026-02-01", TODAY)).toBeNull());
  it("rejects reversed, future, ancient and too-long ranges", () => {
    expect(validateRange("2026-02-01", "2026-01-01", TODAY)).toMatch(/after/);
    expect(validateRange("2026-11-01", "2026-11-12", TODAY)).toMatch(/future/);
    expect(validateRange("1999-01-01", "1999-02-01", TODAY)).toMatch(/2000/);
    const from = addDays(TODAY, -MAX_RANGE_DAYS);
    expect(validateRange(from, TODAY, TODAY)).toMatch(/3 years/);
    expect(validateRange(addDays(from, 1), TODAY, TODAY)).toBeNull();
    expect(validateRange("", TODAY, TODAY)).toMatch(/both/);
  });
});

describe("URL round trip", () => {
  it("restores presets and custom ranges", () => {
    for (const r of [presetRange("90d", TODAY), { preset: "custom" as const, from: "2026-01-05", to: "2026-02-10" }]) {
      const back = rangeFromParams(new URLSearchParams(rangeToParams(r)), TODAY);
      expect(back).toEqual(r);
    }
  });
  it("falls back to 30 days on junk", () => {
    expect(rangeFromParams(new URLSearchParams("range=custom&from=2026-05-01&to=2026-01-01"), TODAY).preset).toBe("30d");
    expect(rangeFromParams(new URLSearchParams("range=lol"), TODAY)).toEqual(presetRange("30d", TODAY));
  });
});
