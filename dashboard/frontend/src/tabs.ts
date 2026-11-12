export type Tab = "overview" | "activity" | "heart" | "sleep" | "body" | "workouts" | "explore";

export const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "activity", label: "Activity" },
  { id: "heart", label: "Heart" },
  { id: "sleep", label: "Sleep" },
  { id: "body", label: "Body & Vitals" },
  { id: "workouts", label: "Workouts" },
  { id: "explore", label: "Explore" },
];

export function isTab(s: string): s is Tab {
  return TABS.some((t) => t.id === s);
}
