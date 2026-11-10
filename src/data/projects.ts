export type Project = {
  id: string;
  name: string;
  description: string;
  makers: string;
  category: "AI" | "Software" | "Robotics" | "Design" | "Experiments";
  url: `https://${string}`;
  /** Optional file in public/, e.g. projects/my-project.webp. */
  image?: string;
  imageAlt?: string;
};

// Add only real projects, with permission from their makers. See README.md.
// An empty collection intentionally renders the invitation to contribute.
export const projects: Project[] = [];
