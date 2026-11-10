import type { ReactNode } from "react";
import { Arrow, Discord } from "./Icons";
import type { Route } from "../lib/routes";

export const DISCORD_URL = "https://discord.gg/NqeCVdukj6";

export function PathLink({
  to,
  children,
  className = "",
  current = false,
}: {
  to: Route;
  children: ReactNode;
  className?: string;
  current?: boolean;
}) {
  return (
    <a
      className={className}
      href={`#/${to}`}
      aria-current={current ? "page" : undefined}
    >
      {children}
    </a>
  );
}

export function DiscordLink({
  children = "Join the Discord",
  className = "button button-dark",
}: {
  children?: ReactNode;
  className?: string;
}) {
  return (
    <a
      className={className}
      href={DISCORD_URL}
      target="_blank"
      rel="noopener noreferrer"
    >
      <Discord />
      <span>{children}</span>
      <Arrow diagonal />
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

export function PageHeading({
  index,
  label,
  title,
  description,
}: {
  index: string;
  label: string;
  title: ReactNode;
  description: string;
}) {
  return (
    <header className="page-heading">
      <div className="eyebrow">
        <span className="tiny-square" />
        {index} / {label}
      </div>
      <h1>{title}</h1>
      <p className="lead">{description}</p>
    </header>
  );
}

export function JoinStrip() {
  return (
    <section className="join-strip">
      <div>
        <p className="eyebrow">AN OPEN INVITATION</p>
        <h2>Something starts with you.</h2>
      </div>
      <PathLink to="join" className="button button-dark">
        Find your starting point <Arrow diagonal />
      </PathLink>
    </section>
  );
}
