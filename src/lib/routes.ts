export const routes = ["root", "about", "builds", "community", "join"] as const;
export type Route = (typeof routes)[number];
export type Page = Route | "not-found";

export function parseRoute(hash: string): Page {
  const path = hash.replace(/^#\/?/, "").replace(/\/$/, "");
  if (!path) return "root";
  return routes.includes(path as Route) ? (path as Route) : "not-found";
}

export const routeTitles: Record<Page, string> = {
  root: "Initialize something new.",
  about: "Our manifesto",
  builds: "Built by our generation",
  community: "Find your people",
  join: "Start something with us",
  "not-found": "Directory not found",
};
