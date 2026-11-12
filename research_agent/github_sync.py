"""Explicit publication allowlist; no force push or automatic remote replacement."""
from pathlib import Path
import re
import hashlib
import json
import subprocess
from .common import WorkflowError, event, git, load, now, save

ROOT_FILES = {"AGENTS.md", "README.md", "paper.py", "pyproject.toml", ".gitignore", ".gitattributes", "skills.lock.json", "THIRD_PARTY_NOTICES.md", "workspace.config.json"}
PREFIXES = ("research_agent/", "tests/", "examples/", "configs/", "src/", "analysis/", "scripts/", ".agents/skills/", ".github/workflows/", "data/manifests/", "reports/")
SECRET_PATTERNS = [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", r"gh[pousr]_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{30,}", r"AKIA[A-Z0-9]{16}", r"sk-[A-Za-z0-9_-]{32,}"]


def allowed(path):
    if path.startswith("papers/"):
        parts = path.split("/", 2)
        if len(parts) != 3:
            return False
        # A paper publishes only code, configs, approved manifests and exported evidence.
        path = parts[2]
        if not path.startswith(("src/", "configs/", "analysis/", "scripts/", "data/manifests/", "reports/")):
            return False
    return (path in ROOT_FILES or path.startswith(PREFIXES)) and not any(part in ("__pycache__", ".env", ".git", "raw", "node_modules") for part in path.split("/")) and not path.endswith((".pem", ".key", ".pyc"))


def canonical(url):
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", url):
        raise WorkflowError("Configure an HTTPS GitHub repository URL without credentials")
    return url.removesuffix(".git")


def preflight(root):
    selected = Path(root).resolve()
    root = Path(git(selected, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    scope = selected.relative_to(root).as_posix() + "/" if selected != root else None
    config = load(selected / "research/project.json")["github"] if scope else load(root / "workspace.config.json")["github"]
    if not config.get("url"):
        raise WorkflowError("GitHub repository is not configured")
    target = canonical(config["url"])
    actual = git(root, "remote", "get-url", "origin").stdout.strip()
    if canonical(actual) != target:
        raise WorkflowError("origin differs from configured repository; no remote was changed")
    branch = git(root, "branch", "--show-current").stdout.strip()
    if branch != config["branch"]:
        raise WorkflowError("Current branch differs from configured publication branch")
    tracked = git(root, "ls-files", "-z").stdout.split("\0")
    forbidden = [p for p in tracked if p and not allowed(p)]
    if forbidden:
        raise WorkflowError(f"Tracked paths outside publication allowlist: {forbidden}")
    candidates = sorted({p for p in git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").stdout.split("\0") if p and allowed(p) and (p.startswith(scope) if scope else not p.startswith("papers/"))})
    staged = [p for p in git(root, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if p]
    if any(p not in candidates for p in staged):
        raise WorkflowError("Staged changes belong to a different scope; commit or unstage them first")
    for path in candidates:
        file = root / path
        if not file.exists():
            continue  # tracked deletion
        if file.is_symlink():
            raise WorkflowError(f"Publication symlink rejected: {path}")
        if file.stat().st_size > 5_000_000:
            raise WorkflowError(f"Large file needs separate storage: {path}")
        text = file.read_bytes().decode("utf-8", errors="replace")
        if any(re.search(pattern, text) for pattern in SECRET_PATTERNS):
            raise WorkflowError(f"Possible credential in {path}; inspect locally before publishing")
    return {"repository": target, "branch": branch, "files": candidates, "git_root": str(root), "scope": scope or "framework",
            "note": "Path allowlist and credential patterns do not replace review of intended public content"}


def sync(root, message):
    plan = preflight(root)
    selected = Path(root)
    root = Path(plan["git_root"])
    if not plan["files"]:
        raise WorkflowError("No publishable files")
    # Explicit filenames avoid staging local manuscripts, raw data or logs.
    # Small batches avoid the Windows command-line length limit.
    for start in range(0, len(plan["files"]), 40):
        git(root, "add", "--", *plan["files"][start:start + 40])
    if git(root, "diff", "--cached", "--quiet", check=False).returncode:
        git(root, "commit", "-m", message)
    commit = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "push", "--set-upstream", "origin", f"HEAD:refs/heads/{plan['branch']}")
    output = git(root, "ls-remote", "origin", f"refs/heads/{plan['branch']}").stdout.strip()
    remote_commit = output.split()[0] if output else None
    if remote_commit != commit:
        raise WorkflowError("Push finished but remote commit does not match; investigate before continuing")
    result = {"repository": plan["repository"], "branch": plan["branch"], "commit": commit,
              "verified_remote_commit": remote_commit, "at": now()}
    save(selected / "research/sync.json", result)
    event(selected, "github_synced", result)
    return result


def verify_published_run(root, run_id, sync_record):
    """Bind a reported experiment to the exact source snapshot in the pushed commit."""
    from .experiments import verify_run
    root = Path(root).resolve()
    repository = Path(git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    prefix = root.relative_to(repository).as_posix()
    commit = sync_record.get("verified_remote_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit) or commit != sync_record.get("commit"):
        raise WorkflowError("Missing verified GitHub commit")
    run_record = verify_run(root, run_id)
    def read_committed(relative):
        p = subprocess.run(["git", "-C", str(repository), "show", f"{commit}:{prefix}/reports/runs/{run_id}/{relative}"], capture_output=True)
        if p.returncode:
            raise WorkflowError(f"Run {run_id} has not been exported and pushed at the recorded commit")
        return p.stdout
    exported = json.loads(read_committed("run.json"))
    for key in ("id", "metrics", "inputs_sha256", "artifacts_sha256", "config_sha256"):
        if exported.get(key) != run_record[key]:
            raise WorkflowError("Published run evidence differs from local verified run")
    for relative, expected in run_record["inputs_sha256"].items():
        if relative.startswith("source/") and hashlib.sha256(read_committed(relative)).hexdigest() != expected:
            raise WorkflowError("Published source does not match the executed source snapshot")
    return True
