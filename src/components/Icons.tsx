export function Arrow({
  diagonal = false,
  className = "",
}: {
  diagonal?: boolean;
  className?: string;
}) {
  return (
    <svg
      className={`icon ${className}`}
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        d={diagonal ? "M5 19 19 5M5 5h14v14" : "M4 12h16m-6-6 6 6-6 6"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Folder({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`icon ${className}`}
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M3 6a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v10H3V6Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Discord() {
  return (
    <svg
      className="icon"
      width="23"
      height="23"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M19.7 5.3A18.2 18.2 0 0 0 15.2 4l-.6 1.2a16.8 16.8 0 0 0-5.2 0L8.8 4a18.2 18.2 0 0 0-4.5 1.3C1.5 9.4.8 13.4 1.2 17.4a18 18 0 0 0 5.5 2.8l1.1-1.8-1.7-.8.4-.3a13.1 13.1 0 0 0 11 0l.4.3-1.7.8 1.1 1.8a18 18 0 0 0 5.5-2.8c.5-4.6-.8-8.5-3.1-12.1ZM8.4 15.1c-1.1 0-1.9-1-1.9-2.2s.8-2.2 1.9-2.2c1.1 0 1.9 1 1.9 2.2s-.8 2.2-1.9 2.2Zm7.2 0c-1.1 0-1.9-1-1.9-2.2s.8-2.2 1.9-2.2c1.1 0 1.9 1 1.9 2.2s-.8 2.2-1.9 2.2Z" />
    </svg>
  );
}
