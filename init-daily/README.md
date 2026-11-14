# INIT:// Daily

A small, serverless briefing on the mainstream AI industry for young builders. It prioritizes significant model launches, product changes, capabilities and strategic developments at major AI companies, with important ecosystem news in second place. It aims for 3–5 meaningful headlines, allows fewer on quiet days, and can send **one quiet Discord message per Shanghai calendar day**. It never pads the briefing with academic papers to reach a quota.

**Publishing is disabled by default.** Development, tests, and offline demos require no credentials. No real Discord messages are sent by the test suite.

This project is isolated in `init-daily/`. Its only file outside that folder is the new `.github/workflows/init-daily.yml`. It does not modify the website, its dependencies, or its deployment workflow. The workflow file must remain at the repository root for GitHub Actions to discover it.

## Quick start

Requires Python 3.11+ and Git. CI uses Python 3.12. Run commands from this folder:

```powershell
cd init-daily
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pip install --no-deps -e .
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m init_daily --fixture fixtures --dry-run
```

On macOS/Linux, replace `.\.venv\Scripts\python` with `.venv/bin/python`.

The offline demo parses RSS and Atom, applies ranking and deduplication, creates five source-grounded stories, and renders the exact Discord JSON structure. Its synthetic input and output are clearly marked **DEMO**. It uses a fixed clock, never accesses the network, ignores any API key, and rejects `--publish` even when publishing is enabled.

Read `output/demo/briefing.md`, `output/demo/discord.json`, and `output/demo/run.json`. For a live feed test with no AI charges or Discord calls:

```powershell
.\.venv\Scripts\python -m init_daily --dry-run --no-ai --output-dir output/live
```

To include DeepSeek processing in a preview, set `DEEPSEEK_API_KEY` and omit `--no-ai`. A dry run may call DeepSeek and incur API charges, but **never calls Discord, reserves a publication, or updates history**. `--fixture` is the fully offline option. No flag defaults to preview mode.

## DeepSeek configuration

1. Sign in at [DeepSeek Platform](https://platform.deepseek.com/).
2. Open **API keys**, create a key, and store it securely. Configure billing/balance as required by your account; API usage is separate from the consumer chat interface.
3. Add it to the environment as `DEEPSEEK_API_KEY`, or to the GitHub repository secret of that name.

Local PowerShell example, using your actual key only in your private shell:

```powershell
$env:DEEPSEEK_API_KEY = "YOUR_PRIVATE_KEY"
.\.venv\Scripts\python -m init_daily --dry-run
```

The application reads process environment variables. `.env.example` documents the names; copying it to `.env` does **not** load it automatically. Never commit a real key or paste it into a chat/log. Local environment and output/state folders are gitignored.

The implementation posts the official OpenAI-compatible Chat Completions JSON format directly to `https://api.deepseek.com/chat/completions` using HTTPX; no OpenAI account or proxy is involved. Default model: `deepseek-flash`, with thinking disabled. Verified against the official documentation on **2026-11-11**: this ID is served by DeepSeek-V4.1-Flash-1017. Change `[deepseek].model` in `config.toml` if DeepSeek changes its model names. See the [official integration guide](https://api-docs.deepseek.com/) and [current pricing](https://api-docs.deepseek.com/quick_start/pricing/).

Cost controls:

- At most **one** paid request per eligible run; no AI retries or repair calls. Selected-story factual checks use bounded public HTTP reads, never another model request.
- At most 20 candidates by default (configurable up to 40), each with an excerpt capped at 1,800 characters and up to three source-controlled summary options of at most 320 characters each.
- Output capped at 2,200 tokens by default; thinking disabled and JSON output requested.
- History, minimum story count, and diversity are checked before an API call.
- Missing key, authentication failure, timeout, malformed JSON, fabricated IDs/summaries, duplicate selections, or exceeded caps trigger the free fallback.
- `run.json` and the job summary record the processing mode, safe diagnostics, and validated token counts returned by DeepSeek, never credentials or raw API responses.

### Diagnose a DeepSeek dry run

Use **Actions → INIT Daily → Run workflow**, select **main**, set **dry_run=true** and **no_ai=false**. This makes at most one paid DeepSeek request, runs the read-only preview job, and never passes the Discord webhook secret to it. Keep `INIT_DAILY_PUBLISH_ENABLED` absent or `false`. With GitHub CLI:

```powershell
gh workflow run init-daily.yml --repo CmsChase/INIT_Website --ref main -f dry_run=true -f no_ai=false
```

Choose a **new** workflow run after pulling the fix; re-running an older run uses its older commit. Download the `init-daily-preview-RUN_ID-ATTEMPT` artifact and open `run.json`:

- `publishing_requested` must be `false`. `preview` means a message is ready and a short briefing can contain one or two stories. `insufficient_news` means editorial selection found too little to publish. `insufficient_verified_news` means too few stories passed primary-source verification. Neither status attempts delivery.
- Successful AI processing has `processing.mode = "deepseek"`, `http_status = 200`, `finish_reason = "stop"`, and `request_attempts = 1`. `usage` contains available numeric token counts.
- `processing.validation.grounding = "source_spans"` means the application inserted verified source text. `summary_defaults` counts omitted optional summary selectors filled with the article's default source span. `editorial_replacements` counts suggestions replaced with trusted local guidance; these replacements do not discard successful AI selection. `ai_selected_stories` counts retained AI choices, `rule_based_additions` counts locally selected replacements, and `policy_skips` counts AI choices skipped to enforce source/research caps. A `deepseek` result can include these explicitly reported local repairs; all final stories still obey the caps.
- With production configuration, confirm that the stories in the briefing appear as `primary_body_checked` in `verification.stories`, with current primary URLs, check timestamps, body hashes and exact evidence quotes. `verification.alternates_used` records replacements that passed the same checks. The `code` on each `withheld` record explains why that candidate could not be used.
- On fallback, inspect `processing.reason`, `processing.diagnostics.code`, and `processing.diagnostics.action`. Available safe metadata includes HTTP status, recognized API error code/parameter, finish reason, token counts, and the zero-based index of a rejected story. A missing API key makes zero requests.

| `processing.reason` | Meaning / next step |
| --- | --- |
| `authentication_error` | HTTP 401 or recognized authentication error: check the key secret and key status. |
| `permission_error` | HTTP 403: check account/model access. |
| `quota_error` | HTTP 402 or recognized balance/quota error: check the API account's balance/quota. |
| `rate_limit_error` | HTTP 429: wait before another manual run; check concurrency/rate limits. |
| `invalid_request` | HTTP 400/404/422: check the configured model and request parameters; an allowlisted `parameter` may identify the field. |
| `api_error` | Other HTTP/API errors, including server failures: try a later dry run. |
| `timeout` / `network_error` | Request timeout or DNS/TLS/connectivity failure; no automatic paid retry. |
| `malformed_response` | Invalid outer JSON, completion schema, blank content, invalid model JSON, or story schema. `diagnostics.code` distinguishes them. |
| `incomplete_response` | Output was truncated, filtered, or aborted. Check `finish_reason`; increase `max_tokens` within its bound only for `length`. |
| `evidence_validation_error` | Unknown article/summary ID or quote absent from its source. Grounding is still enforced. |
| `selection_validation_error` | Duplicate article, insufficient/excessive count, or insufficient eligible stories after enforcing caps. |
| `no_api_key` | AI was not attempted; configure the API key to use it. |

Logs and artifacts deliberately exclude provider error messages, arbitrary error codes, request/response headers, raw model output, and exception text. Diagnostic codes/actions are generated locally; provider codes and parameter names are allowlisted. Incomplete or rejected completions still retain safe usage and finish-reason metadata. A successful workflow can contain a fallback: always check `processing.mode`, not just the green workflow status.

## Discord configuration

1. In the INIT Discord server, choose a normal text channel for briefings.
2. Open **Edit Channel → Integrations → Webhooks → New Webhook**. You need the server/channel permission to manage webhooks.
3. Name it `INIT Daily`, choose the channel, and copy its webhook URL.
4. Save the complete URL as `DISCORD_WEBHOOK_URL` in your environment or GitHub Secrets. Treat the whole URL as a password.

This V1 supports standard text-channel webhooks, not forum/media channels requiring thread parameters. There is no bot to host or invite. See [Discord's official webhook documentation](https://docs.discord.com/developers/resources/webhook).

Each briefing is a single message with up to five minimalist green-accented embeds: original headline, source excerpt, **Why it matters · editorial**, and original source link. Implications should be accessible to AI users and small teams, covering access, competition, adoption, or building opportunities. It disables mentions, sanitizes source markdown and links, suppresses notifications, and validates message size limits. A quiet day can have fewer than three stories; no significant news produces **no post**.

## Activate automatic publishing

For a fresh repository deployment:

1. Commit/push `init-daily/` and `.github/workflows/init-daily.yml` to the repository's **default branch**. Leave the existing website workflow in place.
2. Under **Settings → Secrets and variables → Actions**, add repository **Secrets**:

   | Secret | Required | Purpose |
   | --- | --- | --- |
   | `DISCORD_WEBHOOK_URL` | To post | Discord channel destination |
   | `DEEPSEEK_API_KEY` | Optional | AI ranking and builder guidance; otherwise free fallback |

3. Ensure GitHub Actions is enabled and repository/organization policy allows this workflow's `GITHUB_TOKEN` to have `contents: write` when publishing is eventually enabled. Only the explicitly enabled **publish** job requests that permission; **test** and **preview** use `contents: read`, and previews do not receive the Discord webhook secret. GitHub's contents permission is repository-wide, not branch-scoped; the application writes only its state branch. No personal access token is needed. Branch rules must allow the workflow to create/update **`init-daily-state`**; protect the website's default branch independently.
4. Keep the repository **Variable** `INIT_DAILY_PUBLISH_ENABLED` absent or `false`. In **Actions → INIT Daily → Run workflow**, choose the default branch, leave **dry_run=true**, and inspect the job summary and downloadable `init-daily-preview-*` artifact. Set **no_ai=true** for a free test.
5. When ready, set the repository **Variable** `INIT_DAILY_PUBLISH_ENABLED` to the exact string **`true`**. Scheduled runs can now post. To manually publish, run the workflow with **dry_run=false**; the repository variable must also be true. Do not enable it merely to preview.

The workflow starts preparation at **08:55 Asia/Shanghai (GMT+8)** and holds a completed briefing until the **09:15** delivery target. A second trigger at **09:15** covers a delayed or missed first trigger. The publish jobs share a concurrency group and a durable ledger, so a second run sees the day's prior delivery and exits before collecting news. If the preparation run arrives late, it attempts delivery as soon as the verified briefing is ready. Disabled publishing runs a preview on the 09:15 trigger. Manual publishing runs immediately, and only the default branch has access to the briefing jobs.

GitHub can delay or drop either trigger. The job summary and `run.json` record `scheduled_for` and `schedule_start_offset_seconds`, measured when the briefing pipeline begins. On confirmed delivery they include the Discord `message_id`, and `run.json` records `published_at`. After a missed trigger, use the manual run described above to publish the current day's briefing. See [GitHub's scheduling notes](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

To stop posting, set `INIT_DAILY_PUBLISH_ENABLED=false` in repository Variables. Disable the workflow in Actions if you also want to stop collection and previews. The Python command separately requires **both** `INIT_DAILY_PUBLISH_ENABLED=true` and `--publish` to send.

For an intentional local production run, use the same shared remote ledger as Actions:

```powershell
$env:DISCORD_WEBHOOK_URL = "YOUR_PRIVATE_WEBHOOK_URL"
$env:INIT_DAILY_PUBLISH_ENABLED = "true"
.\.venv\Scripts\python -m init_daily --git-state --publish
```

Do not execute that command during a preview. Local Git must be authenticated to the repository with permission to update the state branch. Omitting `--git-state` uses the local atomic JSON ledger at `.state/history.json`; that is suitable for a single persistent local installation, but it does **not** share history with Actions. Use one ledger consistently for a Discord destination.

## Durable history and delivery failures

GitHub Actions reads and updates a dedicated, orphan **`init-daily-state`** branch containing only `history.json`. It creates the branch on the first actual send. This is durable Git history, not an expiring cache or artifact. Preview runs never create or update it. Do not delete/reset this branch while the system is active.

Delivery sequence:

1. Load history; block if any unresolved reservation exists or this Shanghai date was sent.
2. Remove previously sent URLs and close headline matches, including tracking URL and arXiv version variants.
3. Check the selected stories against current primary article bodies, withhold unchecked stories, then build the complete message and push a **pending** record, its public story IDs and payload to the state branch.
4. Only after that push succeeds, call Discord with `wait=true` and require a returned message ID.
5. Save/push the confirmed ID and mark the record **sent**.

Normal non-force Git pushes reject competing writers. Actions also serializes briefing jobs; local publishers use an exclusive lock. Git operations never switch branches, stage files, or change the website checkout.

Discord webhooks do not provide a transactional exactly-once operation with Git. If a runner crashes, a timeout occurs, or the confirmation push fails after delivery, a **pending** reservation remains and future posting is blocked. This intentionally favors avoiding duplicate messages. A definitive Discord rate-limit rejection may be retried within a small bound; other delivery errors are never retried automatically. Source/API errors do not leak keys or webhook URLs into logs.

To recover, inspect the Actions error/artifact, the state branch, and the actual Discord channel first. From an authenticated local checkout:

```powershell
# Read pending IDs and the exact prepared message. No network posts occur.
.\.venv\Scripts\python -m init_daily --git-state history

# If the message exists, copy its Discord message ID and confirm delivery:
.\.venv\Scripts\python -m init_daily --git-state history --resolve PUBLICATION_ID --status sent --message-id DISCORD_MESSAGE_ID

# ONLY if you verified no message was sent, release the reservation:
.\.venv\Scripts\python -m init_daily --git-state history --resolve PUBLICATION_ID --status released --confirm-not-sent
```

These history commands update Git state only; they cannot send Discord messages. After release, a later explicit/scheduled publishing run may send a freshly prepared briefing. Confirming sent blocks any further message on that date and retains its story history. An unresolved reservation blocks subsequent dates too, until reviewed. For local-ledger recovery, omit `--git-state`.

If a local process was forcibly killed, inspect it before removing a stale `.state/history.lock`. Never remove a lock held by an active process. Do not manually reset corrupt history; repair/restore the branch from Git history instead.

## Sources, editorial rules, and limits

`config.toml` controls the news window, count limits, source weights, source/domain allowlists, model, request limits, and local paths. Relative paths resolve against that configuration file. Add `enabled = false` to a source block to disable it.

Default sources (availability checked 2026-11-11):

| Source | Public feed / index | Role |
| --- | --- | --- |
| OpenAI | `https://openai.com/news/rss.xml` | First-party model/product/research announcements |
| Google DeepMind | `https://deepmind.google/blog/rss.xml` | Models, research, robotics |
| Google AI | `https://blog.google/innovation-and-ai/technology/ai/rss/` | Gemini, product features, partnerships |
| Google Gemini models | `https://blog.google/innovation-and-ai/models-and-research/gemini-models/rss/` | First-party Gemini model announcements missed by the general AI feed |
| Anthropic | `https://www.anthropic.com/news` | Dated official announcement cards; no RSS dependency |
| Microsoft | `https://blogs.microsoft.com/feed/` | Copilot, AI infrastructure, strategic announcements |
| NVIDIA | `https://blogs.nvidia.com/feed/` | AI platforms, hardware and significant ecosystem announcements |
| Meta | `https://about.fb.com/news/feed/` | AI-filtered official company news |
| TechCrunch AI | `https://techcrunch.com/category/artificial-intelligence/feed/` | Reputable secondary coverage across major/emerging companies |
| The Verge AI | `https://www.theverge.com/rss/ai-artificial-intelligence/index.xml` | Mainstream product and industry reporting |
| Ars Technica AI | `https://arstechnica.com/ai/feed/` | Product, industry, and security reporting |
| Hugging Face | `https://huggingface.co/blog/feed.xml` | Open models and developer ecosystem |
| GitHub | `https://github.blog/ai-and-ml/feed/` | AI development tools |

The collector accepts dated HTTPS links on each source's exact allowed hosts, uses bounded retries/timeouts/response sizes, and continues through individual source failures. All sources failing returns an error. A successful source with no recent entries is normal. It scans at most 500 entries per feed. Anthropic's adapter reads one public index and accepts only cards with an explicit publication date, heading, source description and trusted article URL; it executes no scripts and does not infer dates from page updates. The 72-hour window accommodates date-only announcements and slower official feeds, while publication history prevents repeating yesterday's stories.

Hugging Face's title-only RSS uses the `huggingface_markdown` adapter: at most four missing excerpts per run are read from its [official public blog repository](https://github.com/huggingface/blog). Google feed image captions are replaced with the original article's official meta description through `google_description`; if unavailable, the item is skipped. Both adapters use `[http].max_enrichments_per_source`, exact trusted domains, and the same response/request bounds. No arbitrary third-party pages or paywalls are scraped.

There is no verified usable official RSS for xAI or DeepSeek in this configuration: xAI's index blocked the reader, and the tested DeepSeek news RSS path returned documentation HTML. Their significant announcements are covered through the reporting feeds. They remain high-priority company families, alongside OpenAI/ChatGPT, Google/DeepMind/Gemini, Anthropic/Claude, Meta/Llama, Microsoft/Copilot and NVIDIA. Amazon, Apple and Alibaba are also recognized when their AI developments are significant. Coverage is curated and cannot guarantee every announcement appears immediately.

Selection is impact-first before AI processing: major-company model launches, product changes, partnerships, infrastructure and significant security/regulatory developments receive higher scores. Tutorials, customer marketing, speculation, routine patches, deployment recipes and internal/conference updates are penalized. Generic corporate feeds must contain AI-related news. A company name alone does not rescue an academic paper or routine technical update. Original announcements win identical/near-identical reporting duplicates. Only candidates above `min_score` reach the paid model, with at most 20 by default.

Raw arXiv and routine Transformers release feeds are **disabled by default**, although their definitions remain for deliberate future reconfiguration. Standalone preprints receive zero editorial score even when they mention major companies. Significant research can qualify through an official announcement or reputable reporting that establishes broad implications. This avoids treating publication frequency as significance.

Default settings are 72 hours, `min_score = 7`, `min_stories = 1`, and `max_stories = 5`. Three to five is an aim, not a quota. DeepSeek may select fewer or decline all candidates; that decision is not replaced by filler. The old two-per-source ceiling is removed in the production profile (`max_per_source = 5`), so several major same-company stories can coexist. Variety is a small preference among comparable stories, reinforced by the AI prompt, not a company quota. A safety research cap of one remains for explicitly research-tagged custom sources; the default profile has no raw-paper source. Allowed categories also include `industry` and `strategy` for broader implications.

For factual summaries, the application prepares up to three short source spans per article and DeepSeek may select one by `summary_id`. When that optional selector is absent, the application uses the default source span and counts the substitution. The application inserts source text itself, so the model does not need to reproduce an exact quote or count its characters. Older extractive responses are accepted only when their quote matches the source after whitespace/NFC normalization, then shortened locally to 320 characters if necessary; new facts or paraphrases remain rejected. Validation rejects unknown article/summary IDs, unsupported quotes, duplicate IDs, and invalid counts. Source/research caps are enforced deterministically: over-cap choices are skipped and gaps filled from the existing validated shortlist, preserving the model's retained order and reporting every local addition. It cannot invent source URLs or rewrite headlines because those come from the collector. An unsafe, missing, or stylistically invalid builder suggestion is replaced individually with trusted category guidance without discarding grounded AI selection. The free fallback uses source excerpts and category-specific investigation suggestions. Builder guidance is clearly editorial and constrained to suggestions.

This V1 deliberately uses extractive summaries rather than unrestricted paraphrasing. It reports what a primary publisher or preprint claims; it does not independently reproduce benchmarks or prove those claims. Similarity matching catches identical and near-identical headlines, not every differently worded report about the same event. The AI is instructed to avoid event duplicates too. Curated primary feeds and source caps reduce this risk, but human review of previews is useful when changing sources.

### Current primary-body checks for selected stories

The mainstream ranking stage still uses lightweight feeds. The final selected stories undergo a separate, deterministic check **after ranking and before preview or publication**. This closes two gaps found on 2026-11-11: DeepMind's RSS/meta teaser retained an older proof-line count, and a reporting lead omitted Gemini's paid-tier/subscriber restrictions. Exact copying from those snippets did not establish that a claim was current or complete.

Production enables `[verification].enabled = true`. Verification checks selected stories first and can use the remaining budget to check eligible alternates from the same shortlist. The shared limit is 12 total HTTP requests, including redirects and reporting-page lookups, with an eight-second timeout, a 2 MB page limit, and a per-run cache. Offline fixtures keep this step disabled and remain entirely offline.

Official stories use the current linked article body. Reporting stories first use original-source links preserved from the feed's full content; if missing, one bounded read of the reporting article may locate a relevant official link. Only explicit known primary-publisher domains are accepted. Topic matching rejects unrelated references; metadata descriptions, navigation and page teasers are excluded as final evidence.

Final headlines and concise excerpts come from the current primary body. Quantitative excerpts keep the source's units and qualifiers such as **over** or **approximately**. Access excerpts retain paid audiences, subscriber rollout and eligibility conditions. Unqualified public-availability leads are not reused when the primary body provides restrictions. Exact pricing amounts are deliberately omitted from the automated summary rather than stripping introductory/expiry conditions or presenting promotional pricing as permanent; the current original article is linked for the full terms. If a safe short qualified excerpt cannot be selected, the story is withheld. Builder guidance is reset to trusted conditional wording so an obsolete premise such as “widely available” cannot survive in the editorial explanation.

Every retained quote must be an exact span in the fetched primary body. `run.json.verification` records the current primary URL/headline, check time, body SHA-256, exact evidence spans, corrections/omissions and withholding reason codes. These are checks against what a primary publisher currently states, not independent verification of its scientific or commercial claims. Technical PDFs can be reviewed manually when warranted; the daily pipeline does not infer extra precision from a paper it has not fetched.

If a primary page is unavailable, blocked, unrelated or beyond the request budget, the story is withheld. A replacement must pass the same body checks, editorial threshold, source and research caps, and publication-history checks. The briefing can still be shorter than planned when too few alternates pass. An empty editorial selection stays empty. History retains both the original discovery identity and the checked primary URL to prevent follow-up feeds from reposting the same story.

## Project map and verification

```text
init-daily/
  config.toml           # Source trust, ranking limits, API settings
  pyproject.toml        # Python package and console entry point
  requirements.lock    # Pinned runtime dependencies
  src/init_daily/
    cli.py             # Safe defaults and environment/config handling
    collect.py         # Bounded RSS/Atom ingestion and source validation
    news_index.py      # Dated official announcement cards when RSS is unavailable
    editorial.py       # Mainstream company/impact signals and public ranking audit
    models.py          # Domain types, cleaning, URL/headline identity
    ranking.py         # Deterministic shortlist and no-key fallback
    processing.py      # DeepSeek interface and evidence validation
    verification.py    # Selected-story current primary-body checks, no extra AI call
    formatting.py      # Discord payload and readable preview
    history.py         # Atomic local ledger and durable Git ledger
    publishing.py      # One confirmed webhook message, safe retry policy
    pipeline.py        # End-to-end orchestration
  fixtures/             # Explicit synthetic RSS/Atom demo and fixed clock
  tests/                # Offline tests; mock HTTP and a temporary bare Git remote
```

The tests cover the complete preview path, mocked AI and Discord success/failure, source validation and failure isolation, size/date limits, RSS/Atom/permalink parsing, evidence rejection, secrets staying out of error logs, URL/headline/history deduplication, sparse days, publish gates, interrupted delivery, ledger corruption, local locking, and a real local Git reservation race across runs. The Git test uses fresh clones to verify pending reservations, confirmed message IDs, and story deduplication survive runner replacement. CI runs the suite and offline demo before any scheduled/manual briefing.

Available outputs are `briefing.md`, `discord.json`, `run.json`, and `candidates.json`. The latter exposes the bounded shortlist's headlines, URLs, companies, source tiers, editorial scores and signals, without raw model responses. `run.json.editorial` shows the selected headlines, company counts, source tiers, and standalone-research count for review. Skipped runs replace previews so yesterday's message cannot be mistaken for today's output. The workflow uploads public preview artifacts for 14 days and writes a job summary. Production state persists separately on the history branch.

The automated suite mocks DeepSeek and Discord, including authentication/quota/HTTP failures, timeout/network errors, malformed responses, truncation, evidence rejection, editorial repair, and diagnostics that cannot reflect sensitive provider text. Real DeepSeek access can be verified with the safe dry-run instructions above. Discord posting remains separately gated and is never exercised by the tests or preview job.
