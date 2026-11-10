# INIT://

**Initialize something new.** The official website for a global community of young, AI-native builders.

A static Vite + React + TypeScript website with plain CSS. React and React DOM power the site, and Framer Motion animates the editorial pages. The opening screen centers `INIT://_` on a pale halftone background for two seconds before revealing Root.

## Run locally

Use **Node.js 24 LTS** (minimum 22.12) and npm.

```sh
npm ci
npm run dev
```

Open the Local URL printed by Vite, normally `http://127.0.0.1:5173/`.

```sh
npm test          # native Node tests for direct links and route recovery
npm run build    # strict TypeScript checks, then a production build
npm run preview  # serve dist/ locally, normally on port 4173
```

The deployable output is `dist/`. Serve it over HTTP; opening `index.html` through `file://` does not run JavaScript modules correctly.

## Deploy to GitHub Pages

The included `.github/workflows/deploy.yml` installs from the lockfile, tests routes, builds the site, and deploys `dist/` using GitHub's Pages actions. It runs on pushes to `main` and can also be run manually. If you use a different default branch, change the workflow's `branches` list.

1. Create a GitHub repository and push this project, including `package-lock.json` and `.github/workflows/deploy.yml`. Do not commit `node_modules/` or `dist/`.
2. In the repository, open **Settings → Pages → Build and deployment**. Set **Source** to **GitHub Actions**.
3. Push to the selected branch, or open **Actions → Deploy to GitHub Pages → Run workflow**.
4. Wait for both `build` and `deploy` jobs to succeed. The deployment URL appears in the workflow's `github-pages` environment and in **Settings → Pages**.
5. Visit the published site and a direct link such as `https://YOUR_USERNAME.github.io/YOUR_REPOSITORY/#/about`. Refresh the direct link to verify it.

No deployment token, secret, or third-party hosting account is needed. The workflow uses the repository's temporary `GITHUB_TOKEN` with Pages permissions. Ensure Actions and Pages are enabled for the repository and the deployment branch is allowed by the `github-pages` environment rules.

### Why refreshes and direct links work

The route is a URL fragment: `#/root`, `#/about`, `#/builds`, `#/community`, or `#/join`. The browser requests the same root HTML file for every route; the fragment is interpreted in React. This avoids GitHub Pages' missing-file response for paths such as `/about`.

Vite uses `base: './'`, so assets resolve relative to the deployed HTML. The same `dist/` works at a project subdirectory, an account's root Pages site, or a custom domain. **No repository name needs to be hard-coded.** Share the hash URLs rather than invented path URLs. Unknown hash routes display a recovery page with a working return link.

Official references: [Vite deployment guidance](https://vite.dev/guide/static-deploy), [Vite relative base configuration](https://vite.dev/guide/build#relative-base), and [GitHub Pages publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

### Custom domain (optional)

Configure your domain and DNS in GitHub's Pages settings, then add a `public/CNAME` file containing only the domain, for example `community.example.com`. Vite copies it into the build. Follow [GitHub's custom domain guide](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site). The relative asset base and hash routes need no changes.

## Content and structure

```text
src/
  App.tsx                 Site frame, route changes, document titles and focus
  components/             Shared links, icons, intro, page headings, SVG artwork
    editorial/            Reference assets, scaled canvases, halftones, motion
  data/projects.ts        Typed collection of real community projects
  lib/routes.ts           Small, dependency-free hash route parser
  pages/                  Root, About, Builds, Community, Join
  styles.css              Design tokens, layouts, interaction and responsive CSS
  editorial.css           Shared editorial typography, navigation and components
  pages/root.css          Home cover, opening essay and directory
public/
  favicon.svg             Brand favicon
  fonts/                  Local Manrope font and license
tests/routes.test.ts      Route and GitHub Pages URL checks
.github/workflows/        Production deployment workflow
```

The Discord invite is defined in `src/components/Shared.tsx`: `https://discord.gg/NqeCVdukj6`. If it changes, also update the no-JavaScript fallback in `index.html`. All React links and the copyable label use the shared constant.

### Add a real project

Edit the `projects` array in `src/data/projects.ts`. It is intentionally empty until real community work is available. No demo projects are presented as real work. When the array has entries, the invitation automatically becomes a responsive project collection.

Copy this **schema example** and replace every placeholder with verified information before adding it to the array:

```ts
{
  id: 'unique-project-slug',
  name: 'Actual project name',
  description: 'What it does and why its makers built it.',
  makers: 'Names the makers have agreed to share',
  category: 'AI', // AI | Software | Robotics | Design | Experiments
  url: 'https://actual-project-url.example',
  image: 'projects/project-preview.webp', // optional; file in public/projects/
  imageAlt: 'A useful description of the project preview',
}
```

Use a unique `id`, a working HTTPS URL, and the makers' permission. Prefer optimized WebP or AVIF images around 640 × 400 pixels. Image paths are relative to `public/`, without a leading slash. Omitting an image uses a neutral folder illustration. Project order follows array order. Run `npm run build` after editing.

## Interaction and accessibility

- The centered `INIT://_` intro runs once per browser session, then fades into the site. Any key or pointer press skips it. Direct links to inner pages bypass it.
- Reduced-motion preferences bypass the intro, disable the inner-page halftone interaction and scroll-linked movement, and reveal text without movement.
- Navigation uses standard anchors with current-page indicators. Route changes update the document title, return to the top, and focus the main content. Browser back/forward works normally.
- A keyboard skip link, visible focus indicators, meaningful headings, labelled navigation, decorative SVG hiding, and accessible copy feedback are included.
- External Discord/project links identify new tabs for assistive technology. Copy failures reveal the invitation URL so it can be selected manually.
- Responsive layouts keep all five navigation destinations visible. Zoom remains enabled; controls use touch feedback and safe-area padding.
- The editorial pages load Fraunces, Instrument Serif, and Fragment Mono from Google Fonts, and artwork directly from `https://qclay.design/lovable/ClassicalSounds/`. The intro pairs the shared Fraunces display face with monospace punctuation.

## Editorial style adaptation

Root, About, Builds, Community, and Join adapt the supplied Classical Sounds visual reference to INIT://. They use light serif display type, monochrome paper surfaces, live halftones, and restrained text entrances. Builds uses an empty directory until real community projects are added.

- Root uses a fluid cover with a full-width interactive halftone. The story and directory follow in normal document flow.
- The five editorial routes load together on first entry so switching pages does not require another JavaScript download. The intro renders independently.
- The illustrated inner-page heroes use 1512px desktop design canvases and a measured, auto-height 440px mobile canvas, with the reference's 1024px breakpoint. Long-form copy uses normal document flow so it can wrap and resize.
- About includes a pinned, scroll-linked human-centered manifesto scene. Small screens receive the same message in a static vertical layout. Reduced motion removes the extra pinned scroll distance.
- Halftones use the supplied canvas renderer and anonymous CORS image loading, with builder symbols in place of music notes. Pointer interaction is limited to a fine mouse pointer; animation loops stop off screen and when idle.
- Grid SVGs are fetched and inlined for stroke animation. Only drawing elements are retained; network failures are handled without interrupting the page.

## Before publishing

1. Run `npm ci`, `npm test`, and `npm run build`.
2. Preview the production output and check all five pages, refresh a direct hash URL, and test back/forward.
3. Use keyboard navigation and your system's reduced-motion setting. Check the first-entry intro in a new browser session.
4. Try the copy-invite button and confirm the Discord invite is still valid.
5. Check the site on a real phone, including landscape, browser chrome, zoom, and touch feedback. Desktop responsive emulation cannot verify physical-device behavior.

This checkout contains the complete first version and a deployment workflow. GitHub publication requires pushing to your chosen repository and enabling its Pages configuration; it is not performed by a local build.

## First-version verification

Verified on 10 November 2026:

- Production build and strict TypeScript checks passed; all three route tests passed.
- All five pages were exercised at 320, 375, 768, and 1440 CSS pixels, with no horizontal page overflow.
- The production output was served by a plain static server under `/INIT_/`. Every hash route opened directly and survived a page refresh; JavaScript, CSS, the favicon, and the local font loaded successfully.
- Current-page indicators, document titles, route focus management, browser back/forward, the keyboard skip link, unknown-route recovery, and copy-invite success feedback were checked in the browser.
- A fresh session displayed `INIT://_`; keyboard input dismissed the introduction immediately. Reduced-motion behavior is implemented and was reviewed in code.
- No production browser console errors were observed. JavaScript is approximately 76.5 kB gzipped; CSS is approximately 5.8 kB gzipped; the font is 24.5 kB.

Physical-device touch behavior and a live GitHub deployment were not tested.

### Editorial revision verification

The checks under **First-version verification** describe the original design. For the latest Root and intro styling, run the production build and route tests, then open `/#/root` in a fresh browser session to see the introductory animation.
