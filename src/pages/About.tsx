import {
  EditorialHero,
  EditorialJoinStrip,
  Reveal,
} from "../components/editorial/Editorial";
import HumanStory from "../components/editorial/HumanStory";

const beliefs = [
  {
    title: "A beginning, not a barrier.",
    body: "You no longer need a title, a large team, or years of permission to start. AI is making it possible to move from a question to a prototype faster than ever. We want more young people to discover what they can do with that possibility.",
  },
  {
    title: "Technology is a tool. People are the point.",
    body: "Better tools don’t decide what is worth making. That takes human curiosity, judgment, and care. We value projects that solve real problems, thoughtful experiments, and the people learning behind them.",
  },
  {
    title: "Build in the open. Grow together.",
    body: "An unfinished idea can start a conversation. A failed experiment can save someone a week. Sharing the process makes us better builders—and helps the right collaborators find each other.",
  },
  {
    title: "Different perspectives, greater possibilities.",
    body: "Software meets design. Robotics meets art. A person on one side of the world sees something another has missed. We want to make those connections possible, across borders and disciplines.",
  },
];

export default function About() {
  return (
    <>
      <EditorialHero
        number="01"
        label="OUR MANIFESTO"
        variant="about"
        lines={["A GENERATION", "IN THE MAKING."]}
        description="A belief in our generation. A place to put it into practice."
      />
      <HumanStory />
      <section className="manifesto-intro">
        <p className="eyebrow">README / WHY WE EXIST</p>
        <div>
          <h2>
            We grew up with technology.
            <br />
            Now we get to help shape it.
          </h2>
          <p>
            We are living at the beginning of a new technological era. The
            distance between an idea and a working product is shrinking. What
            once required significant resources can now begin with curiosity,
            ambition, and a laptop.
          </p>
          <p>
            That opportunity matters. But it can be hard to know where to
            start—or to find people who take your ideas seriously. INIT://
            exists to connect young builders around the world, so that starting
            doesn’t have to mean starting alone.
          </p>
        </div>
      </section>
      <section className="beliefs" aria-label="Our beliefs">
        {beliefs.map((belief, index) => (
          <Reveal className="belief" key={belief.title}>
            <span className="belief-number">0{index + 1}</span>
            <h2>{belief.title}</h2>
            <p>{belief.body}</p>
          </Reveal>
        ))}
      </section>
      <figure className="manifesto-quote">
        <span className="eyebrow">THE BELIEF THAT CONNECTS US</span>
        <blockquote>
          “We don’t want to be a generation that simply watches the future
          unfold.
          <br />
          <span>We want to be part of building it.</span>”
        </blockquote>
        <figcaption>INIT:// — OUR SHARED STARTING POINT</figcaption>
      </figure>
      <section className="long-view">
        <p className="eyebrow">THE LONG VIEW</p>
        <h2>
          A community that grows
          <br />
          with the people inside it.
        </h2>
        <p>
          We’re starting with a place to meet, share work, and find
          collaborators. Over time, we want INIT:// to become a lasting network
          of people who help each other turn ambitious ideas into meaningful
          work. That future will be shaped by what we build together.
        </p>
      </section>
      <EditorialJoinStrip />
    </>
  );
}
