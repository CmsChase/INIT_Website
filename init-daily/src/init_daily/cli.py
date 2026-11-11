import argparse
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess

import httpx

from .config import load_settings
from .history import GitHistory, History, publication_lock
from .pipeline import run_pipeline

log = logging.getLogger(__name__)


class ArgumentError(ValueError):
    """Actionable, credential-free CLI error text safe to display."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="INIT:// daily AI briefing. Default: preview only.")
    result.add_argument("--config", type=Path, default=Path("config.toml"))
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--publish", action="store_true", help="Send only if INIT_DAILY_PUBLISH_ENABLED=true")
    mode.add_argument("--dry-run", action="store_true", help="Preview only; never write history or call Discord")
    result.add_argument("--no-ai", action="store_true", help="Use source excerpts without a paid API call")
    result.add_argument("--fixture", type=Path, help="Offline demo directory; forces no AI, no Discord")
    result.add_argument("--git-state", action="store_true", help="Use origin/init-daily-state as durable ledger")
    result.add_argument("--output-dir", type=Path)
    commands = result.add_subparsers(dest="command")
    history = commands.add_parser("history", help="Inspect or manually resolve an uncertain delivery")
    history.add_argument("--resolve", metavar="PUBLICATION_ID")
    history.add_argument("--status", choices=["sent", "released"])
    history.add_argument("--message-id", default="")
    history.add_argument("--confirm-not-sent", action="store_true")
    return result


def _repository() -> Path:
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                            text=True, encoding="utf-8", timeout=10)
    if result.returncode:
        raise ArgumentError("--git-state requires a Git checkout with origin configured")
    return Path(result.stdout.strip())


def execute(args) -> int:
    if args.fixture and (args.publish or args.git_state or args.command):
        raise ArgumentError("--fixture cannot be combined with publishing, remote history, or history commands")
    if args.command and args.publish:
        raise ArgumentError("History commands do not publish")
    if args.publish and os.environ.get("INIT_DAILY_PUBLISH_ENABLED", "").lower() != "true":
        raise ArgumentError("Publishing is disabled. Set INIT_DAILY_PUBLISH_ENABLED=true and pass --publish to enable it")
    config_path = args.fixture / "config.toml" if args.fixture else args.config
    settings = load_settings(config_path)
    if args.output_dir:
        settings = replace(settings, output_dir=args.output_dir.resolve())
    repository = _repository() if args.git_state else None
    mutating = args.publish or (args.command == "history" and args.resolve)
    lock_path = settings.history_path.with_suffix(".lock")
    guard = publication_lock(lock_path) if mutating else nullcontext()
    with guard:
        history = GitHistory(repository) if repository else History(settings.history_path)
        if args.command == "history":
            if args.resolve:
                if not args.status:
                    raise ArgumentError("Resolving history requires --status")
                if args.status == "released" and not args.confirm_not_sent:
                    raise ArgumentError("Inspect Discord first, then pass --confirm-not-sent to release a reservation")
                history.resolve(args.resolve, args.status, args.message_id)
                log.info("Publication reservation resolved as %s", args.status)
            else:
                # Payloads contain public news only; webhook/key are never persisted.
                print(json.dumps(history.data, indent=2, ensure_ascii=False))
            return 0
        now = datetime.now(timezone.utc)
        if args.fixture:
            now = datetime.fromisoformat((args.fixture / "clock.txt").read_text(encoding="utf-8").strip())
        if not now.tzinfo:
            raise ValueError("A timezone-aware clock is required")
        with httpx.Client(headers={"User-Agent": "INITDaily/1.0 (RSS briefing)"},
                          follow_redirects=False, trust_env=False) as client:
            report = run_pipeline(settings, history, client, now, send=args.publish,
                                  api_key=None if args.no_ai else os.environ.get("DEEPSEEK_API_KEY"),
                                  webhook=os.environ.get("DISCORD_WEBHOOK_URL", ""), fixture=args.fixture)
        log.info("Result: %s; %s stories. Preview: %s", report["status"], report["stories"], settings.output_dir)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as stream:
                stream.write(f"## INIT:// Daily\n\nStatus: **{report['status']}** · Stories: {report['stories']}\n\n")
                if "processing" in report:
                    stream.write("### Processing diagnostics\n\n```json\n")
                    stream.write(json.dumps(report["processing"], indent=2) + "\n```\n\n")
                stream.write((settings.output_dir / "briefing.md").read_text(encoding="utf-8"))
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        return execute(parser().parse_args(argv))
    except Exception as exc:
        # Avoid traceback/HTTP request rendering: webhook URLs are credentials.
        safe = type(exc).__name__
        from .history import HistoryError
        from .collect import CollectionError
        from .publishing import PublishError
        if isinstance(exc, (HistoryError, CollectionError, PublishError, ArgumentError)):
            safe += f": {exc}"
        elif isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError):
            safe += ": configuration or validation error; check arguments and config.toml"
        log.error("%s. No automatic resend will be attempted.", safe)
        return 1
