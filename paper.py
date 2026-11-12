"""Dependency-free entry point: python paper.py --help."""
from research_agent.cli import main
import sys

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
