import type { TypeEntry } from "../api";

// The order the Health app uses, roughly; anything else goes after, alphabetically.
const GROUP_ORDER = [
  "Fitness",
  "Heart",
  "Sleep",
  "Body Measurements",
  "Vital Signs",
  "Respiratory",
  "Nutrition",
  "Mobility",
  "Mindfulness",
  "Hearing Health",
  "Symptoms",
  "Reproductive Health",
];

export interface TypeGroup {
  group: string;
  types: TypeEntry[];
}

/** Filter by a case-insensitive search over name, id and group, then group and sort. */
export function groupTypes(types: TypeEntry[], query: string): TypeGroup[] {
  const q = query.trim().toLowerCase();
  const hits = q
    ? types.filter((t) => `${t.name} ${t.id} ${t.group}`.toLowerCase().includes(q))
    : types;
  const by = new Map<string, TypeEntry[]>();
  for (const t of hits) {
    const list = by.get(t.group) ?? [];
    list.push(t);
    by.set(t.group, list);
  }
  const rank = (g: string) => {
    const i = GROUP_ORDER.indexOf(g);
    return i === -1 ? GROUP_ORDER.length + (g === "Other" ? 1 : 0) : i;
  };
  return [...by.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([group, list]) => ({ group, types: list.sort((a, b) => a.name.localeCompare(b.name)) }));
}
