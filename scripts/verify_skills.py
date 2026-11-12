"""Verify vendored third-party skill files against the recorded SHA-256 lock."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
lock = json.loads((root / "skills.lock.json").read_text(encoding="utf-8"))
errors = []
for entry in lock["skills"]:
    base = root / entry["path"]
    actual = {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    if actual != entry["files_sha256"]:
        errors.append(entry["name"])
if errors:
    raise SystemExit("Skill drift: " + ", ".join(errors))
print(f"Verified {len(lock['skills'])} pinned upstream skills")
