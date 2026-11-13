from pathlib import Path
from .common import WorkflowError, event, load, now, required, save
from .data import verify_datasets
from .experiments import verify_run, verify_reproduction
from .literature import verify_evidence, audit_corpus

STAGES = ["intake", "literature", "protocol", "experiments", "manuscript", "review", "submission"]

TASKS = {
    "intake": "Read research/project.json; obtain direction at invocation; discover public data before choosing topics.",
    "literature": "Use paper-lookup and literature-review; read full texts; register evidence and compare data-feasible topics.",
    "protocol": "Write protocol/plan.json with hypothesis, baseline, metric, split, datasets, evidence_ids and selected_topic. Fetch and verify data.",
    "experiments": "Implement baseline and method; run, reproduce, inspect failures and publish approved code via github-sync. Write protocol/results.json.",
    "manuscript": "Use scientific-writing; draft manuscript/paper.md and claims.json mapping evidence_ids and run_ids. Preserve negative findings.",
    "review": "Use peer-review for author-requested internal review; record issues, fix them and populate reviews/review.json.",
    "submission": "Compare current journal scope, fees and policies; prepare submission/journals.json and materials. Actual submission needs user instruction."
}


def initialize(root, direction=None, github_url=None):
    root = Path(root)
    config_path = root / "research/project.json"
    config = load(config_path) if config_path.exists() else {
        "schema_version": 1, "direction": None,
        "data_policy": "agent-acquired-public-data; no fabricated observations",
        "github": {"url": None, "branch": "main"},
        "budgets": {"max_run_seconds": 600, "max_total_seconds": 7200, "max_runs": 20},
        "language": "zh-CN", "target_venue": None,
        "literature_policy": {"min_analyzed_papers": 100, "min_fulltext_papers": 100, "trend_max_age_days": 30},
        "autonomy": "research and local execution within budget; no paid services or submission by default"
    }
    if direction:
        if (root / "research/state.json").exists() and load(root / "research/state.json")["stage"] != "intake" and direction != config["direction"]:
            raise WorkflowError("Create a separate project for a new research direction")
        config["direction"] = direction
    if github_url:
        config["github"]["url"] = github_url
    save(config_path, config)
    if not (root / "research/state.json").exists():
        save(root / "research/state.json", {"schema_version": 1, "stage": "intake", "updated_at": now(), "history": []})
    for directory in ("literature", "data/manifests", "protocol", "src", "configs", "runs", "analysis", "manuscript", "reviews", "submission", "reports"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    event(root, "project_initialized", {"direction": config["direction"]})
    return status(root)


def status(root):
    config = load(Path(root) / "research/project.json")
    state = load(Path(root) / "research/state.json")
    return {"project": str(Path(root).resolve()), "direction": config["direction"], "stage": state["stage"],
            "next_task": TASKS[state["stage"]], "github": config["github"], "budgets": config["budgets"]}


def check_gate(root, stage):
    root = Path(root)
    if stage == "intake":
        required(load(root / "research/project.json"), ["direction"], "project")
    elif stage == "literature":
        audit_corpus(root, enforce=True)
        summary = load(root / "literature/selection.json")
        required(summary, ["candidates", "selected_topic", "selection_reason", "evidence_ids", "data_sources", "gap_paper_ids", "counterevidence_paper_ids"], "topic selection")
        from .literature import verify_fulltext
        paper_ids = set(summary["gap_paper_ids"] + summary["counterevidence_paper_ids"])
        for item in summary["candidates"] + summary.get("excluded_or_deferred", []):
            paper_ids.update(item.get("closest_precedents", []))
            paper_ids.update(item.get("evidence_paper_ids", []))
        for paper_id in paper_ids:
            verify_fulltext(root, paper_id)
        for evidence_id in summary["evidence_ids"]:
            verify_evidence(root, evidence_id)
    elif stage == "protocol":
        plan = load(root / "protocol/plan.json")
        required(plan, ["selected_topic", "hypothesis", "baseline", "metric", "split", "datasets", "evidence_ids", "experiments", "acceptance"], "protocol")
        verify_datasets(root, plan["datasets"])
        for evidence_id in plan["evidence_ids"]:
            verify_evidence(root, evidence_id)
    elif stage == "experiments":
        results = load(root / "protocol/results.json")
        required(results, ["run_ids", "reproduction_ids", "interpretation", "limitations"], "results")
        verified = set()
        for run_id in results["run_ids"]:
            verify_run(root, run_id)
        for replay in results["reproduction_ids"]:
            verified.add(verify_reproduction(root, replay))
        if not set(results["run_ids"]).issubset(verified):
            raise WorkflowError("Every reported run needs a passing replay")
        sync = load(root / "research/sync.json")
        if not sync.get("verified_remote_commit"):
            raise WorkflowError("Code must be synchronized to GitHub before manuscript results")
        from .github_sync import verify_published_run
        for run_id in results["run_ids"]:
            verify_published_run(root, run_id, sync)
    elif stage == "manuscript":
        paper = root / "manuscript/paper.md"
        if not paper.is_file() or not paper.read_text(encoding="utf-8").strip():
            raise WorkflowError("A manuscript is required")
        claims = load(root / "manuscript/claims.json")
        if not isinstance(claims, list) or not claims:
            raise WorkflowError("Provide claim-evidence mappings")
        for claim in claims:
            required(claim, ["claim", "location"], "manuscript claim")
            if not claim.get("evidence_ids") and not claim.get("run_ids"):
                raise WorkflowError("Each factual claim needs evidence or runs")
            for evidence_id in claim.get("evidence_ids", []):
                verify_evidence(root, evidence_id)
            for run_id in claim.get("run_ids", []):
                verify_run(root, run_id)
    elif stage == "review":
        review = load(root / "reviews/review.json")
        required(review, ["reviewer", "round", "assessment"], "review")
        if "issues" not in review or not isinstance(review["issues"], list):
            raise WorkflowError("review.issues must be a list")
        for issue in review["issues"]:
            required(issue, ["id", "severity", "status", "response"], "review issue")
            if issue["severity"] in ("critical", "major") and issue["status"] != "resolved":
                raise WorkflowError("Resolve major review issues before submission preparation")
    else:
        raise WorkflowError("Submission is the last preparation stage; never auto-submit")


def advance(root):
    state_path = Path(root) / "research/state.json"
    state = load(state_path)
    stage = state["stage"]
    for prior in STAGES[:STAGES.index(stage) + 1]:
        check_gate(root, prior)
    next_stage = STAGES[STAGES.index(stage) + 1]
    state["history"].append({"from": stage, "to": next_stage, "at": now()})
    state.update(stage=next_stage, updated_at=now())
    save(state_path, state)
    event(root, "stage_advanced", {"from": stage, "to": next_stage})
    return status(root)
