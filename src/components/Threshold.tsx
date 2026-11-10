/** Original vector artwork: an open directory, rendered as a spatial threshold. */
export default function Threshold() {
  return (
    <figure className="threshold">
      <svg viewBox="0 0 540 520" fill="none" aria-hidden="true">
        <defs>
          <pattern
            id="dot-grid"
            width="18"
            height="18"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="1" cy="1" r=".7" fill="#b5b7af" />
          </pattern>
          <linearGradient
            id="plane"
            x1="155"
            y1="320"
            x2="420"
            y2="80"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#eceee5" />
            <stop offset="1" stopColor="#f7f7f2" />
          </linearGradient>
          <linearGradient
            id="dark-plane"
            x1="170"
            y1="120"
            x2="350"
            y2="370"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#343831" />
            <stop offset="1" stopColor="#151713" />
          </linearGradient>
        </defs>
        <rect
          x="30"
          y="20"
          width="480"
          height="480"
          fill="url(#dot-grid)"
          opacity=".65"
        />
        <path
          d="m47 367 227 131 227-131M274 498V234"
          stroke="#d4d6cb"
          strokeDasharray="3 5"
        />
        <path
          d="m74 350 200 115 200-115-200-115L74 350Z"
          fill="#f0f1e9"
          fillOpacity=".6"
          stroke="#c8cbbf"
        />
        <g className="portal-back">
          <path
            d="m303 75 138 79v220l-138-79V75Z"
            fill="url(#plane)"
            stroke="#a9ad9f"
          />
          <path d="m317 99 110 63v188l-110-63V99Z" stroke="#bfc2b6" />
          <path d="m330 122 84 48v157l-84-48V122Z" stroke="#d2d5c9" />
        </g>
        <path
          d="m269 96 138 79v220l-138-79V96Z"
          fill="#eff0e8"
          fillOpacity=".8"
          stroke="#a9ad9f"
        />
        <path
          d="m235 116 138 79v220l-138-79V116Z"
          fill="#e6e9dd"
          fillOpacity=".8"
          stroke="#979d8d"
        />
        <path
          d="m201 136 138 79v220l-138-79V136Z"
          fill="#dde2d1"
          stroke="#858e78"
        />
        <g className="portal-front">
          <path
            d="m166 116 139 80v239l-139-80V116Z"
            fill="url(#dark-plane)"
            stroke="#20231c"
          />
          <path d="m166 116 14-8 139 80-14 8-139-80Z" fill="#53594a" />
          <path d="m305 196 14-8v239l-14 8V196Z" fill="#424938" />
          <path
            d="m187 154 97 56v189l-97-56V154Z"
            stroke="#929a85"
            strokeWidth=".8"
          />
          <path
            d="m207 233 54 31m-23-41 23 41-23 15"
            stroke="#d7e4be"
            strokeWidth="3"
            strokeLinecap="square"
          />
          <path d="m188 320 26 15m-26-7 39 23" stroke="#777f6c" />
        </g>
        <path
          d="m166 116-43-25H71M441 374l32 19h35"
          stroke="#919787"
          strokeWidth=".8"
        />
        <circle cx="166" cy="116" r="3" fill="#25291f" />
        <circle cx="441" cy="374" r="3" fill="#25291f" />
        <path
          d="M61 86v10m-5-5h10M502 54v12m-6-6h12M52 443v12m-6-6h12"
          stroke="#9da491"
        />
        <text
          x="71"
          y="78"
          fill="#656c5c"
          fontSize="9"
          fontFamily="monospace"
          letterSpacing="1"
        >
          A NEW START
        </text>
        <text
          x="396"
          y="415"
          fill="#656c5c"
          fontSize="9"
          fontFamily="monospace"
          letterSpacing="1"
        >
          UNDEFINED, YET.
        </text>
      </svg>
      <figcaption>
        <span>FIG. 001 — THE OPEN POSSIBILITY</span>
        <span>[ ↗ ]</span>
      </figcaption>
    </figure>
  );
}
