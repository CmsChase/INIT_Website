import { Arrow } from "../components/Icons";
import { PathLink } from "../components/Shared";
import {
  EditorialJoinStrip,
  Halftone,
  ReferenceArrow,
  RevealLines,
} from "../components/editorial/Editorial";
import { editorialAssets } from "../components/editorial/assets";
import "./root.css";

const directories = [
  { to: "about", title: "Our manifesto", description: "What we believe AI makes possible for our generation." },
  { to: "builds", title: "Community builds", description: "A space for prototypes, experiments, and work in progress." },
  { to: "community", title: "Find your people", description: "Meet people who think in code, circuits, sketches, and stories." },
] as const;

export default function Root() {
  return (
    <div className="ed-root">
      <header className="ed-root-cover">
        <div aria-hidden="true" className="ed-root-field">
          <Halftone src={editorialAssets.backdrop} width={1512} height={670} soft />
        </div>
        <div className="ed-root-cover-copy">
          <p className="ed-kicker">( Initialize something new. )</p>
          <h1><RevealLines lines={["The future is", "ours to build."]} /></h1>
          <p className="ed-root-lead">
            A global community for young builders turning ideas into software,
            robots, and tools with AI.
          </p>
          <div className="ed-root-actions">
            <PathLink to="join" className="ed-button"><span>Join INIT://</span><ReferenceArrow /></PathLink>
            <PathLink to="about" className="text-link">Read the manifesto <Arrow /></PathLink>
          </div>
        </div>
      </header>

      <section className="ed-root-essay" aria-labelledby="root-essay-title">
        <div className="ed-root-essay-art" aria-hidden="true">
          <Halftone src={editorialAssets.eye} width={440} height={272} />
        </div>
        <div className="ed-root-essay-copy">
          <h2 id="root-essay-title">What can one curious<br />person <em>make now?</em></h2>
          <p>With AI and a laptop, a young builder can try an idea that once
            needed a whole team. A sketch can become a working tool while the
            question that started it is still fresh.</p>
          <p>INIT:// is where you can bring that first attempt, ask for a second
            pair of eyes, and find someone who wants to build it with you.</p>
        </div>
      </section>

      <nav className="ed-root-directory" aria-labelledby="root-directory-title">
        <h2 id="root-directory-title">Explore the directory</h2>
        <ul>
          {directories.map(({ to, title, description }) => (
            <li key={to}><PathLink to={to} className="ed-root-entry">
              <span className="ed-label">/{to}</span>
              <span className="ed-root-entry-title">{title}</span>
              <span className="ed-root-entry-description">{description}</span>
              <Arrow diagonal />
            </PathLink></li>
          ))}
        </ul>
      </nav>
      <EditorialJoinStrip />
    </div>
  );
}
