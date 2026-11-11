# INIT:// Daily

A small, serverless AI news briefing for people who build. It collects trusted RSS/Atom feeds, removes stale and repeated stories, selects 3–5 items, explains their practical relevance, and can send **one quiet Discord message per Shanghai calendar day**.

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

- At most **one** paid request per eligible run; no AI retries or repair calls.
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

- `status` should be `preview`, `publishing_requested` must be `false`, and `stories` should be 3–5.
- Successful AI processing has `processing.mode = "deepseek"`, `http_status = 200`, `finish_reason = "stop"`, and `request_attempts = 1`. `usage` contains available numeric token counts.
- `processing.validation.grounding = "source_spans"` means the application inserted verified source text. `editorial_replacements` counts suggestions replaced with trusted local guidance; these replacements do not discard successful AI selection. `ai_selected_stories` counts retained AI choices, `rule_based_additions` counts locally selected replacements, and `policy_skips` counts AI choices skipped to enforce source/research caps. A `deepseek` result can include these explicitly reported local repairs; all final stories still obey the caps.
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

Each briefing is a single message with 3–5 minimalist green-accented embeds: original headline, source excerpt, **Why it matters for builders · editorial**, and original source link. It disables mentions, sanitizes source markdown and links, suppresses notifications, and validates message size limits. An empty or sparse news day produces **no post**, rather than padding the briefing with old or invented material.

## Activate automatic publishing

Deployment has deliberately not been performed during development. To activate it:

1. Commit/push `init-daily/` and `.github/workflows/init-daily.yml` to the repository's **default branch**. Leave the existing website workflow in place.
2. Under **Settings → Secrets and variables → Actions**, add repository **Secrets**:

   | Secret | Required | Purpose |
   | --- | --- | --- |
   | `DISCORD_WEBHOOK_URL` | To post | Discord channel destination |
   | `DEEPSEEK_API_KEY` | Optional | AI ranking and builder guidance; otherwise free fallback |

3. Ensure GitHub Actions is enabled and repository/organization policy allows this workflow's `GITHUB_TOKEN` to have `contents: write` when publishing is eventually enabled. Only the explicitly enabled **publish** job requests that permission; **test** and **preview** use `contents: read`, and previews do not receive the Discord webhook secret. GitHub's contents permission is repository-wide, not branch-scoped; the application writes only its state branch. No personal access token is needed. Branch rules must allow the workflow to create/update **`init-daily-state`**; protect the website's default branch independently.
4. Keep the repository **Variable** `INIT_DAILY_PUBLISH_ENABLED` absent or `false`. In **Actions → INIT Daily → Run workflow**, choose the default branch, leave **dry_run=true**, and inspect the job summary and downloadable `init-daily-preview-*` artifact. Set **no_ai=true** for a free test.
5. When ready, set the repository **Variable** `INIT_DAILY_PUBLISH_ENABLED` to the exact string **`true`**. Scheduled runs can now post. To manually publish, run the workflow with **dry_run=false**; the repository variable must also be true. Do not enable it merely to preview.

The schedule is `15 1 * * *` UTC, equivalent to **09:15 Asia/Shanghai** every day. Disabled publishing still runs a preview on that schedule. Manual runs on other branches are restricted to tests; the briefing job runs only on the default branch.

GitHub scheduling is best effort: runs can be delayed or dropped, and public-repository schedules can be disabled after 60 days without activity. Check the Actions tab periodically; see [GitHub's scheduling notes](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). The application does not backfill missed days or run a continuous server.

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
3. Build the complete message and push a **pending** record, its public story IDs and payload to the state branch.
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

Default feeds:

| Source | Public feed | Role |
| --- | --- | --- |
| OpenAI | `https://openai.com/news/rss.xml` | First-party model/product/research announcements |
| Google DeepMind | `https://deepmind.google/blog/rss.xml` | Models, research, robotics |
| Hugging Face | `https://huggingface.co/blog/feed.xml` | Open models and developer ecosystem |
| GitHub | `https://github.blog/ai-and-ml/feed/` | AI development tools |
| Transformers | `https://github.com/huggingface/transformers/releases.atom` | Curated open-source releases |
| arXiv cs.AI | `https://rss.arxiv.org/rss/cs.AI` | Preliminary AI research |
| arXiv cs.RO | `https://rss.arxiv.org/rss/cs.RO` | Preliminary robotics research |

The collector accepts dated HTTPS links on each source's exact allowed hosts, uses bounded retries/timeouts/response sizes, and continues through individual source failures. All sources failing returns an error. A successful feed with no eligible recent entries is normal. It scans at most 500 entries per feed and uses feed excerpts/abstracts. Hugging Face's title-only RSS uses the `huggingface_markdown` adapter: at most four missing excerpts per run are read from its [official public blog repository](https://github.com/huggingface/blog) through `raw.githubusercontent.com`. That cap is configurable as `[http].max_enrichments_per_source`; failed lookups are skipped. It never scrapes arbitrary linked pages or paywalled content.

Selection uses topic matches, freshness, release signals, publisher weight, a minimum score, and penalties for funding/events/prereleases. Paid processing sees only the bounded deduplicated shortlist. Default limits are 48 hours, at most two stories per source, and at most two preliminary research stories in total. arXiv replacement announcements are excluded so old-paper revisions do not look like new discoveries. Preliminary research is explicitly labeled. New source categories should use one of `models`, `agents`, `tools`, `open_source`, `robotics`, or `research`; omit `category` for automatic classification.

For factual summaries, the application prepares up to three short source spans per article and DeepSeek selects one by `summary_id`. The application inserts the chosen text itself, so the model does not need to reproduce an exact quote or count its characters. Older extractive responses are accepted only when their quote matches the source after whitespace/NFC normalization, then shortened locally to 320 characters if necessary; new facts or paraphrases remain rejected. Validation rejects unknown article/summary IDs, unsupported quotes, duplicate IDs, and invalid counts. Source/research caps are enforced deterministically: over-cap choices are skipped and gaps filled from the existing validated shortlist, preserving the model's retained order and reporting every local addition. It cannot invent source URLs or rewrite headlines because those come from the collector. An unsafe, missing, or stylistically invalid builder suggestion is replaced individually with trusted category guidance without discarding grounded AI selection. The free fallback uses source excerpts and category-specific investigation suggestions. Builder guidance is clearly editorial and constrained to suggestions.

This V1 deliberately uses extractive summaries rather than unrestricted paraphrasing. It reports what a primary publisher or preprint claims; it does not independently reproduce benchmarks or prove those claims. Similarity matching catches identical and near-identical headlines, not every differently worded report about the same event. The AI is instructed to avoid event duplicates too. Curated primary feeds and source caps reduce this risk, but human review of previews is useful when changing sources.

## Project map and verification

```text
init-daily/
  config.toml           # Source trust, ranking limits, API settings
  pyproject.toml        # Python package and console entry point
  requirements.lock    # Pinned runtime dependencies
  src/init_daily/
    cli.py             # Safe defaults and environment/config handling
    collect.py         # Bounded RSS/Atom ingestion and source validation
    models.py          # Domain types, cleaning, URL/headline identity
    ranking.py         # Deterministic shortlist and no-key fallback
    processing.py      # DeepSeek interface and evidence validation
    formatting.py      # Discord payload and readable preview
    history.py         # Atomic local ledger and durable Git ledger
    publishing.py      # One confirmed webhook message, safe retry policy
    pipeline.py        # End-to-end orchestration
  fixtures/             # Explicit synthetic RSS/Atom demo and fixed clock
  tests/                # Offline tests; mock HTTP and a temporary bare Git remote
```

The tests cover the complete preview path, mocked AI and Discord success/failure, source validation and failure isolation, size/date limits, RSS/Atom/permalink parsing, evidence rejection, secrets staying out of error logs, URL/headline/history deduplication, sparse days, publish gates, interrupted delivery, ledger corruption, local locking, and a real local Git reservation race across runs. The Git test uses fresh clones to verify pending reservations, confirmed message IDs, and story deduplication survive runner replacement. CI runs the suite and offline demo before any scheduled/manual briefing.

Available outputs are `briefing.md`, `discord.json`, and `run.json`. Skipped runs replace previews so yesterday's message cannot be mistaken for today's output. The workflow uploads public preview artifacts for 14 days and writes a job summary. Production state persists separately on the history branch.

The automated suite mocks DeepSeek and Discord, including authentication/quota/HTTP failures, timeout/network errors, malformed responses, truncation, evidence rejection, editorial repair, and diagnostics that cannot reflect sensitive provider text. Real DeepSeek access can be verified with the safe dry-run instructions above. Discord posting remains separately gated and is never exercised by the tests or preview job.
