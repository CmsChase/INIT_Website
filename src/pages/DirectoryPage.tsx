import type { Route } from "../lib/routes";
import Root from "./Root";
import About from "./About";
import Builds from "./Builds";
import Community from "./Community";
import Join from "./Join";

// Load the directory once. Switching sections then requires only a render.
const pages = { root: Root, about: About, builds: Builds, community: Community, join: Join };

export default function DirectoryPage({ route }: { route: Route }) {
  const Page = pages[route];
  return <Page />;
}
