import { DiscordLink } from "../components/Shared";
import {
  EditorialHero,
  EditorialJoinStrip,
  Halftone,
  Reveal,
} from "../components/editorial/Editorial";
import { editorialAssets } from "../components/editorial/assets";

const disciplines = [
  "AI & machine learning",
  "Software & open source",
  "Robotics & hardware",
  "Design & digital products",
  "Creative experiments",
  "Whatever comes next",
];
const steps = [
  {
    name: "Find a shared curiosity.",
    text: "Introduce yourself. Ask a question you’ve been sitting with. Meet people exploring the things you can’t stop thinking about.",
  },
  {
    name: "Let people see the process.",
    text: "Share an early demo, a small breakthrough, or the part that isn’t working. Useful conversations often start with unfinished work.",
  },
  {
    name: "Turn a conversation into a project.",
    text: "Find someone with a different skill. Try an idea together. Give thoughtful feedback and make your next step a little less solitary.",
  },
];

export default function Community() {
  return (
    <>
      <EditorialHero
        number="03"
        label="THE PEOPLE MAKE IT"
        variant="community"
        lines={["INDEPENDENT MINDS.", "COMMON GROUND."]}
        description="For the ones with too many ideas, a few open tabs, and the urge to make something of their own."
      />
      <section className="community-intro">
        <div className="community-mark" aria-hidden="true">
          <Halftone src={editorialAssets.eye} width={480} height={300} />
          <span className="eyebrow">
            DIFFERENT PERSPECTIVES. NEW POSSIBILITIES.
          </span>
        </div>
        <div>
          <span className="eyebrow">A COMMUNITY, NOT AN AUDIENCE</span>
          <h2>
            You don’t need to have
            <br />
            it all figured out.
          </h2>
          <p>
            You might be writing your first line of code or already shipping
            your own tools. You might think in circuits, sketches, systems, or
            stories. What connects us is curiosity and a willingness to turn it
            into something.
          </p>
          <p>
            INIT:// is a global community for young builders. Discord is where
            we start connecting; what we make of those connections is up to us.
          </p>
          <DiscordLink className="text-link">Find us on Discord</DiscordLink>
        </div>
      </section>
      <section className="disciplines">
        <div className="section-label">
          <span>MANY WAYS TO BE A BUILDER</span>
          <span>NO SINGLE DISCIPLINE REQUIRED</span>
        </div>
        <div className="discipline-grid">
          {disciplines.map((discipline, index) => (
            <div key={discipline}>
              <span className="eyebrow">0{index + 1}</span>
              <h3>{discipline}</h3>
              <span className="discipline-symbol" aria-hidden="true">
                +
              </span>
            </div>
          ))}
        </div>
      </section>
      <section className="connection-section">
        <p className="eyebrow">FROM HELLO TO “LET’S TRY IT”</p>
        <h2>
          Good things start
          <br />
          with a <span className="serif">conversation.</span>
        </h2>
        <div className="steps">
          {steps.map((step, index) => (
            <Reveal key={step.name} delay={index * 0.06}>
              <span className="step-number">0{index + 1}</span>
              <h3>{step.name}</h3>
              <p>{step.text}</p>
            </Reveal>
          ))}
        </div>
      </section>
      <aside className="community-values">
        <span className="small-cross">+</span>
        <p>
          Be curious. Be generous with what you know. Respect the person behind
          the project. Give credit. Make room for people who are just getting
          started.
        </p>
      </aside>
      <EditorialJoinStrip />
    </>
  );
}
