const dispatchUrl = "https://api.github.com/repos/CmsChase/INIT_Website/actions/workflows/init-daily.yml/dispatches";

export default {
  async scheduled(_event, env) {
    const token = env.GITHUB_DISPATCH_TOKEN;
    if (!token) throw new Error("Configure the GITHUB_DISPATCH_TOKEN Worker secret");

    const dryRun = env.LIVE_PUBLISH !== "true";
    let response;
    try {
      response = await fetch(dispatchUrl, {
        method: "POST",
        redirect: "error",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "X-GitHub-Api-Version": "2026-03-10",
          "User-Agent": "INIT-Daily-Scheduler",
        },
        signal: AbortSignal.timeout(15_000),
        body: JSON.stringify({
          ref: "main",
          inputs: { dry_run: dryRun, no_ai: false, scheduled_delivery: true },
          return_run_details: true,
        }),
      });
    } catch {
      throw new Error("Could not confirm GitHub dispatch. Check INIT Daily runs and Cloudflare connectivity.");
    }
    if (!response.ok) throw new Error(`GitHub dispatch failed (HTTP ${response.status})`);
    const details = await response.json().catch(() => null);
    const runId = details?.workflow_run_id;
    const run = Number.isSafeInteger(runId) ? ` · run ${runId}` : "";
    console.log(`GitHub accepted INIT Daily ${dryRun ? "preview" : "scheduled delivery"}${run}`);
  },
};
