from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone
import urllib.error
import urllib.request
import time


class WorkflowError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        return json.load(f, parse_constant=lambda x: (_ for _ in ()).throw(WorkflowError(f"Invalid JSON number: {x}")))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inside(root, relative):
    root = Path(root).resolve()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise WorkflowError(f"Expected project-relative path: {relative}")
    result = (root / relative).resolve()
    if not result.is_relative_to(root) or result == root:
        raise WorkflowError(f"Path escapes project: {relative}")
    return result


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise WorkflowError("ID must be 1-80 letters, numbers, underscores or hyphens")
    return value


def required(obj, keys, label):
    if not isinstance(obj, dict):
        raise WorkflowError(f"{label}: expected an object")
    missing = [k for k in keys if obj.get(k) is None or obj.get(k) == "" or obj.get(k) == []]
    if missing:
        raise WorkflowError(f"{label}: missing {', '.join(missing)}")


def finite_metrics(value):
    if not isinstance(value, dict) or not value:
        raise WorkflowError("metrics.json must contain a nonempty object of numeric metrics")
    for key, number in value.items():
        if not isinstance(key, str) or isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise WorkflowError(f"Invalid numeric metric: {key}")
    return value


def git(root, *args, check=True):
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode:
        raise WorkflowError(f"git {args[0]} failed: {p.stderr.strip()}")
    return p


def git_info(root):
    try:
        commit = git(root, "rev-parse", "HEAD", check=False)
        if commit.returncode:
            return {"commit": None, "dirty": True}
        return {"commit": commit.stdout.strip(), "dirty": bool(git(root, "status", "--porcelain").stdout)}
    except FileNotFoundError:
        return {"commit": None, "dirty": True}


@contextlib.contextmanager
def lock(root):
    path = Path(root) / "research/.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise WorkflowError("Another mutation may be running (research/.lock). Inspect its PID before removing a stale lock.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def event(root, action, details):
    path = Path(root) / "research/events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": now(), "action": action, "details": details}, ensure_ascii=False) + "\n")


def request_bytes(url, max_bytes=10_000_000, attempts=3):
    if not url.startswith("https://"):
        raise WorkflowError("Network sources must use HTTPS")
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PaperResearchWorkflow/0.1 (academic retrieval)", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=30) as response:
                if not response.url.startswith("https://"):
                    raise WorkflowError("Refusing HTTPS downgrade")
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise WorkflowError(f"Download exceeds {max_bytes} bytes")
                return body, response.url, dict(response.headers)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise WorkflowError(f"HTTP {exc.code}; source was not retrieved") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise WorkflowError(f"Source unavailable: {exc}") from exc
        time.sleep(2 ** attempt)
    raise WorkflowError("Retrieval failed")
