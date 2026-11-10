import { useState } from "react";
import { DiscordLink, DISCORD_URL, PathLink } from "../components/Shared";
import { Arrow } from "../components/Icons";
import { DesignCanvas } from "../components/editorial/Canvas";
import {
  GridArtwork,
  Halftone,
  RevealLines,
} from "../components/editorial/Editorial";
import { editorialAssets } from "../components/editorial/assets";

export default function Join() {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">(
    "idle",
  );
  async function copyInvite() {
    try {
      await navigator.clipboard.writeText(DISCORD_URL);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <>
      <section className="ed-contact-hero">
        <DesignCanvas height={850}>
          <GridArtwork />
          <div className="ed-contact-topline">
            <span className="ed-label">[ 04 — YOUR STARTING POINT ]</span>
            <span className="ed-label">OPEN TO POSSIBILITY.</span>
          </div>
          <div className="ed-contact-title">
            <p className="ed-kicker">( Every future starts somewhere )</p>
            <h1>
              <RevealLines lines={["INITIALIZE", "SOMETHING NEW."]} />
            </h1>
          </div>
          <div className="ed-contact-tile tile-eye">
            <Halftone src={editorialAssets.eye} width={240} height={150} />
          </div>
          <div className="ed-contact-tile tile-pegasus">
            <Halftone src={editorialAssets.pegasus} width={180} height={225} />
          </div>
          <div className="ed-contact-center">
            <p>
              Bring your curiosity, your unfinished projects, and your “what
              ifs.” There’s room for you here.
            </p>
            <DiscordLink className="ed-discord-card">
              JOIN THE DISCORD
            </DiscordLink>
            <span className="ed-label">
              A NEW CONVERSATION. A PLACE TO BEGIN.
            </span>
          </div>
          <div className="ed-contact-bottomline">
            <span className="ed-label">
              YOUNG BUILDERS.
              <br />
              SHARED POSSIBILITIES.
            </span>
            <span className="ed-label">
              BASED EVERYWHERE.
              <br />
              BUILDING WHAT’S NEXT.
            </span>
          </div>
        </DesignCanvas>
      </section>
      <section className="join-guide">
        <div>
          <p className="eyebrow">ONCE YOU’RE IN</p>
          <h2>
            Start with
            <br />a simple <span className="serif">hello.</span>
          </h2>
        </div>
        <ol>
          <li>
            <span>01</span>
            <div>
              <h3>Tell us a little about yourself.</h3>
              <p>What are you curious about? What would you like to build?</p>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <h3>Show something, or ask something.</h3>
              <p>
                A prototype, a sketch, a question. You don’t need a finished
                project.
              </p>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <h3>Follow a conversation.</h3>
              <p>
                Offer an idea. Share what you know. Find someone to try
                something with.
              </p>
            </div>
          </li>
        </ol>
      </section>
      <section className="invite-section">
        <div>
          <h2>A good beginning is worth sharing.</h2>
          <p>
            Know someone who would feel at home here? Send them an invitation.
          </p>
        </div>
        <div className="invite-copy">
          <span className="invite-url">
            {DISCORD_URL.replace("https://", "")}
          </span>
          <button type="button" onClick={copyInvite}>
            {copyState === "copied" ? "Copied ✓" : "Copy invite"}
            <span aria-hidden="true">⧉</span>
          </button>
          <span className="copy-status" role="status">
            {copyState === "copied"
              ? "Invitation link copied."
              : copyState === "failed"
                ? `Copy this link: ${DISCORD_URL}`
                : ""}
          </span>
        </div>
      </section>
      <div className="join-postscript">
        <span>Still getting to know us?</span>
        <PathLink to="about" className="text-link">
          Start with what we believe <Arrow />
        </PathLink>
      </div>
    </>
  );
}
