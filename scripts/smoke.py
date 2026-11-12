"""End-to-end live public-data smoke check in its own paper directory."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_agent import data, experiments, workspace
from research_agent.common import load, save


def main():
    base = Path(__file__).resolve().parents[1]
    paper_id = sys.argv[1] if len(sys.argv) > 1 else "system-smoke"
    if not (base / "papers" / paper_id).exists():
        workspace.create(base, paper_id, "系统验证示例（非论文）", demo=True)
    elif not (base / "papers" / paper_id / "research/project.json").exists():
        workspace.restore(base, paper_id, "系统验证示例（非论文）", demo=True)
    root = workspace.paper_root(base, paper_id)
    if load(root / "research/project.json")["kind"] != "system-demo":
        raise RuntimeError("Smoke script only operates on system-demo projects")
    record = data.fetch(root, root / "data/manifests/iris.json")
    run = experiments.run(root, root / "configs/iris.json")
    report = experiments.reproduce(root, run["id"])
    for key in ("original_environment", "rerun_environment"):
        report[key].pop("executable", None)
    output = {"paper": paper_id, "dataset_sha256": record["sha256"], "metrics": run["metrics"], "reproduction": report}
    save(root / "reports/smoke.json", output)
    print(__import__("json").dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
