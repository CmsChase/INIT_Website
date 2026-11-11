"""Write-ahead publication ledger. An uncertain send is never retried blindly."""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from .models import Story

STATE_BRANCH = "init-daily-state"


class HistoryError(RuntimeError):
    pass


def validate_ledger(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("publications"), list):
        raise HistoryError("Invalid history schema; refusing to discard publication history")
    ids = set()
    for entry in data["publications"]:
        if (not isinstance(entry, dict) or entry.get("status") not in {"pending", "sent", "released"}
                or not isinstance(entry.get("id"), str) or entry["id"] in ids
                or not isinstance(entry.get("stories"), list) or not isinstance(entry.get("date"), str)):
            raise HistoryError("Invalid publication record")
        ids.add(entry["id"])
        for story in entry["stories"]:
            if not isinstance(story, dict) or any(not isinstance(story.get(k), str) for k in ("id", "title", "url")):
                raise HistoryError("Invalid story record")
            if "primary_url" in story and not isinstance(story["primary_url"], str):
                raise HistoryError("Invalid primary-source identity")
    return data


@contextmanager
def publication_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise HistoryError("Another publisher holds the lock; inspect it before removing a stale lock") from None
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


class History:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = validate_ledger(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else {
                "version": 1, "publications": []}
        except (ValueError, OSError):
            raise HistoryError("Cannot read history; refusing to start with an empty ledger") from None

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(self.data, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise HistoryError("Cannot persist publication history") from None

    @property
    def pending(self) -> list[dict]:
        return [p for p in self.data["publications"] if p["status"] == "pending"]

    def sent_on(self, date: str) -> bool:
        return any(p["date"] == date and p["status"] == "sent" for p in self.data["publications"])

    def previous_stories(self) -> list[dict]:
        return [story for p in self.data["publications"] if p["status"] != "released" for story in p["stories"]]

    def reserve(self, date: str, stories: list[Story], payload: dict) -> str:
        if self.pending or self.sent_on(date):
            raise HistoryError("Publication already sent or unresolved; refusing to send again")
        publication_id = str(uuid4())
        self.data["publications"].append({
            "id": publication_id, "date": date, "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "stories": [{**s.article.record(), "primary_url": s.verified_url or s.article.url} for s in stories],
            "payload_sha256": sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            "payload": payload,
        })
        self.save()  # Must be durably stored (and pushed with GitHistory) BEFORE POST.
        return publication_id

    def resolve(self, publication_id: str, status: str, message_id: str = ""):
        if status not in {"sent", "released"}:
            raise HistoryError("Resolution must be sent or released")
        if status == "sent" and (not message_id.isdigit() or len(message_id) > 30):
            raise HistoryError("A Discord message ID is required to confirm delivery")
        entries = [p for p in self.pending if p["id"] == publication_id]
        if len(entries) != 1:
            raise HistoryError("Pending publication ID not found")
        entries[0].update(status=status, message_id=message_id,
                          resolved_at=datetime.now(timezone.utc).isoformat())
        self.save()


class GitHistory(History):
    """Git plumbing: update ONLY a dedicated remote branch, never the checkout/index.

    Normal (non-force) push acts as optimistic concurrency control. If two runners
    reserve against the same parent, only one can push and therefore send.
    """

    def __init__(self, repository: Path):
        self.repository = repository.resolve()
        probe = self._git("ls-remote", "--exit-code", "origin", f"refs/heads/{STATE_BRANCH}", allowed=(0, 2))
        self.parent = ""
        if probe.returncode == 2:
            self.data = {"version": 1, "publications": []}
        else:
            self._git("fetch", "--no-tags", "origin",
                      f"+refs/heads/{STATE_BRANCH}:refs/init-daily/state")
            self.parent = self._git("rev-parse", "refs/init-daily/state").stdout.strip()
            raw = self._git("show", f"{self.parent}:history.json").stdout
            try:
                self.data = validate_ledger(json.loads(raw))
            except (ValueError, TypeError):
                raise HistoryError("Remote history is corrupt; refusing an empty ledger") from None

    def _git(self, *args: str, input_text: str | None = None, allowed: tuple = (0,)):
        try:
            # Binary stdin avoids Windows converting LF to CRLF in mktree paths.
            result = subprocess.run(["git", *args], cwd=self.repository,
                                    input=input_text.encode("utf-8") if input_text is not None else None,
                                    capture_output=True, timeout=60,
                                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        except (OSError, subprocess.TimeoutExpired):
            raise HistoryError("Git history operation failed or timed out") from None
        if result.returncode not in allowed:
            # Git stderr can contain authenticated remote URLs. Never expose it.
            raise HistoryError("Git history operation failed; check origin access and state-branch permissions")
        result.stdout = result.stdout.decode("utf-8")
        return result

    def save(self):
        blob = self._git("hash-object", "-w", "--stdin",
                         input_text=json.dumps(self.data, indent=2, ensure_ascii=False) + "\n").stdout.strip()
        tree = self._git("mktree", input_text=f"100644 blob {blob}\thistory.json\n").stdout.strip()
        args = ["-c", "user.name=INIT Daily", "-c", "user.email=init-daily@users.noreply.github.com",
                "commit-tree", tree]
        if self.parent:
            args.extend(["-p", self.parent])
        commit = self._git(*args, input_text="INIT Daily: persist publication ledger\n").stdout.strip()
        self._git("push", "origin", f"{commit}:refs/heads/{STATE_BRANCH}")
        self.parent = commit
