import { describe, expect, it } from "vitest";
import type { TypeEntry } from "../api";
import { groupTypes } from "./explore";

const t = (id: string, name: string, group: string): TypeEntry => ({
  id, name, group, kind: "quantity", unit: "g", aggregation: "sum", display_unit: "g", count: 1, latest: null,
});

const TYPES = [
  t("HKQuantityTypeIdentifierDietaryProtein", "Dietary Protein", "Nutrition"),
  t("HKQuantityTypeIdentifierStepCount", "Step Count", "Fitness"),
  t("HKQuantityTypeIdentifierHeartRate", "Heart Rate", "Heart"),
  t("HKQuantityTypeIdentifierUVExposure", "UV Exposure", "Other"),
  t("HKQuantityTypeIdentifierDietaryWater", "Dietary Water", "Nutrition"),
  t("HKCategoryTypeIdentifierHeadache", "Headache", "Symptoms"),
];

describe("groupTypes", () => {
  it("orders groups like the Health app with Other last", () => {
    expect(groupTypes(TYPES, "").map((g) => g.group)).toEqual(["Fitness", "Heart", "Nutrition", "Symptoms", "Other"]);
  });
  it("sorts types by name within a group", () => {
    const nutrition = groupTypes(TYPES, "").find((g) => g.group === "Nutrition")!;
    expect(nutrition.types.map((x) => x.name)).toEqual(["Dietary Protein", "Dietary Water"]);
  });
  it("searches name, id and group case-insensitively", () => {
    expect(groupTypes(TYPES, "WATER").flatMap((g) => g.types.map((x) => x.name))).toEqual(["Dietary Water"]);
    expect(groupTypes(TYPES, "symptoms").flatMap((g) => g.types.map((x) => x.name))).toEqual(["Headache"]);
    expect(groupTypes(TYPES, "HKQuantityTypeIdentifierStep")[0].types[0].name).toBe("Step Count");
    expect(groupTypes(TYPES, "zzz")).toEqual([]);
  });
});
