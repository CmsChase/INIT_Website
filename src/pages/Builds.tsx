import { projects } from "../data/projects";
import { Arrow, Folder } from "../components/Icons";
import { DiscordLink } from "../components/Shared";
import { EditorialHero, Halftone } from "../components/editorial/Editorial";
import { editorialAssets } from "../components/editorial/assets";

export default function Builds() {
  return (
    <>
      <EditorialHero
        number="02"
        label="THE PROJECT DIRECTORY"
        variant="builds"
        lines={["LESS ONE DAY.", "MORE DAY ONE."]}
        description="Experiments, side projects, and ambitious ideas made real. Built by people in INIT://."
      />
      <section className="build-directory" aria-labelledby="builds-title">
        <div className="directory-toolbar">
          <h2 id="builds-title">
            <Folder /> Community builds
          </h2>
          <span className="eyebrow">
            {projects.length === 0
              ? "THE COLLECTION STARTS HERE"
              : `${projects.length} ${projects.length === 1 ? "PROJECT" : "PROJECTS"}`}
          </span>
        </div>
        {projects.length === 0 ? (
          <div className="empty-builds">
            <div className="ed-empty-art" aria-hidden="true">
              <Halftone
                src={editorialAssets.pegasus}
                width={260}
                height={320}
              />
              <span className="ed-art-label">[ AN IDEA TAKES FLIGHT ]</span>
            </div>
            <span className="eyebrow">AN OPEN DIRECTORY</span>
            <h3>
              The first entry
              <br />
              could be <span className="serif">yours.</span>
            </h3>
            <p>
              No projects on display just yet. We’re making room for real work
              from the community—rough edges and all.
            </p>
            <DiscordLink className="text-link">
              Share what you’re building
            </DiscordLink>
            <span className="empty-note">
              An experiment counts. A work in progress counts. A first attempt
              counts.
            </span>
          </div>
        ) : (
          <div className="project-grid">
            {projects.map((project) => (
              <article className="project-card" key={project.id}>
                {project.image ? (
                  <img
                    src={`${import.meta.env.BASE_URL}${project.image.replace(/^\//, "")}`}
                    alt={project.imageAlt ?? ""}
                    loading="lazy"
                    width="640"
                    height="400"
                  />
                ) : (
                  <div className="project-art" aria-hidden="true">
                    <Folder />
                  </div>
                )}
                <div className="project-copy">
                  <span className="eyebrow">{project.category}</span>
                  <h3>
                    <a
                      href={project.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {project.name}
                      <Arrow diagonal />
                      <span className="sr-only"> (opens in a new tab)</span>
                    </a>
                  </h3>
                  <p>{project.description}</p>
                  <span className="project-makers">By {project.makers}</span>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
      <section className="submission-note">
        <span className="eyebrow">HOW TO BE PART OF IT</span>
        <h2>
          Make something.
          <br />
          Let us in on the process.
        </h2>
        <p>
          Join the Discord and share your project, what you’re learning, and
          what kind of help you’re looking for. It doesn’t have to be polished.
          It just has to be yours.
        </p>
      </section>
    </>
  );
}
