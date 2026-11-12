"""Execute real experiments in isolated snapshots and verify repeatability."""
from __future__ import annotations

import math
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time
import uuid

from .common import WorkflowError, digest, event, finite_metrics, git_info, identifier, inside, load, now, required, save
from .data import verify_datasets


def validate_config(config):
    required(config, ["name", "command", "sources", "datasets", "timeout_seconds", "comparison"], "experiment")
    identifier(config["name"])
    if not isinstance(config["command"], list) or not all(isinstance(x, str) for x in config["command"]):
        raise WorkflowError("command must be an argv list, not a shell string")
    if config["command"][0] != "{python}":
        raise WorkflowError("v1 supports Python experiments only; command must start with {python}")
    if not all(isinstance(config.get(key), list) and config[key] and all(isinstance(x, str) for x in config[key]) for key in ("sources", "datasets")):
        raise WorkflowError("sources and datasets must be nonempty lists of strings")
    timeout = config["timeout_seconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise WorkflowError("timeout_seconds must be positive and finite")
    comparison = config["comparison"]
    if not isinstance(comparison, dict) or comparison.get("mode") not in ("exact", "metrics"):
        raise WorkflowError("comparison.mode must be exact or metrics")
    for key in ("abs_tol", "rel_tol"):
        value = comparison.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise WorkflowError("Comparison tolerances must be finite and nonnegative")
    if comparison["mode"] == "metrics" and not comparison.get("justification"):
        raise WorkflowError("Non-exact comparison requires a predeclared justification")


def inventory(directory):
    result = {}
    for path in sorted(Path(directory).rglob("*")):
        if path.is_symlink():
            raise WorkflowError("Snapshot/output symlinks are not supported")
        if path.is_file() and "__pycache__" not in path.parts:
            result[path.relative_to(directory).as_posix()] = digest(path)
    return result


def verify_run(root, run_id):
    directory = inside(root, f"runs/{identifier(run_id)}")
    manifest = load(directory / "run.json")
    if manifest["status"] != "succeeded":
        raise WorkflowError(f"Run did not succeed: {run_id}")
    for section in ("inputs", "artifacts"):
        current = inventory(directory / section)
        if current != manifest[f"{section}_sha256"]:
            raise WorkflowError(f"Run {section} were modified: {run_id}")
    if digest(directory / "config.json") != manifest["config_sha256"]:
        raise WorkflowError("Archived experiment configuration was modified")
    if load(directory / "artifacts/metrics.json") != manifest["metrics"]:
        raise WorkflowError("Recorded metrics disagree with artifact")
    return manifest


def stop_tree(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def run(root, config_path=None, replay_id=None):
    root = Path(root).resolve()
    prior = None
    if replay_id:
        prior = verify_run(root, replay_id)
        archived = inside(root, f"runs/{replay_id}")
        config = load(archived / "config.json")
    else:
        config = load(config_path)
    validate_config(config)
    settings = load(root / "research/project.json")
    budgets = settings["budgets"]
    if config["timeout_seconds"] > budgets["max_run_seconds"]:
        raise WorkflowError("Requested timeout exceeds project max_run_seconds")
    old_runs = list((root / "runs").glob("*/run.json"))
    if len(old_runs) >= budgets["max_runs"]:
        raise WorkflowError("Project run budget exhausted; adjust the budget deliberately")
    consumed = sum(load(p).get("duration_seconds", 0) for p in old_runs)
    if consumed + config["timeout_seconds"] > budgets["max_total_seconds"]:
        raise WorkflowError("Insufficient remaining wall-time budget for the requested timeout")
    if config.get("require_clean_git", False) and (git_info(root)["dirty"] or not git_info(root)["commit"]):
        raise WorkflowError("This experiment requires a clean committed Git tree")

    datasets = verify_datasets(root, config["datasets"]) if not prior else prior["datasets"]
    run_id = f"{config['name']}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    directory = root / "runs" / run_id
    inputs = directory / "inputs"
    source = inputs / "source"
    source.mkdir(parents=True)
    artifacts = directory / "artifacts"
    artifacts.mkdir()
    if prior:
        shutil.copytree(archived / "inputs", inputs, dirs_exist_ok=True)
    else:
        for relative in config["sources"]:
            original = inside(root, relative)
            if not original.is_file():
                raise WorkflowError(f"Source must be an existing file: {relative}")
            target = inside(source, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
        for key, record in datasets.items():
            target = inputs / "data" / f"{identifier(key)}.data"
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(inside(root, record["path"]), target)
    input_hashes = inventory(inputs)
    # Execution receives a separate working copy; archived inputs remain unchanged.
    work = directory / "work"
    shutil.copytree(inputs, work)
    save(directory / "config.json", config)
    substitutions = {"{python}": sys.executable, "{output}": str(artifacts)}
    substitutions.update({f"{{data:{key}}}": str(work / "data" / f"{key}.data") for key in datasets})
    command = [substitutions.get(token, token) for token in config["command"]]
    if any(token.startswith("{") for token in command):
        raise WorkflowError("Unknown command placeholder")
    manifest = {"id": run_id, "status": "running", "started_at": now(), "config": config,
                "config_sha256": digest(directory / "config.json"), "inputs_sha256": input_hashes,
                "datasets": datasets, "git": git_info(root), "replay_of": replay_id,
                "environment": {"python": sys.version, "executable": sys.executable,
                                "platform": platform.platform(), "machine": platform.machine()},
                "command": command}
    save(directory / "run.json", manifest)
    started = time.monotonic()
    # Package inventory supplements, but does not replace, checked-in dependency locks.
    try:
        packages = subprocess.run([sys.executable, "-m", "pip", "list", "--format=json", "--disable-pip-version-check"],
                                  capture_output=True, text=True, timeout=30)
        if packages.returncode == 0:
            (directory / "packages.json").write_text(packages.stdout, encoding="utf-8")
    except (OSError, subprocess.TimeoutExpired):
        pass
    process = None
    try:
        env = dict(os.environ, PYTHONHASHSEED=str(config.get("seed", 0)), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        env.pop("PYTHONPATH", None)
        with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=work / "source", env=env, stdout=stdout, stderr=stderr,
                                       start_new_session=os.name != "nt")
            manifest["pid"] = process.pid
            save(directory / "run.json", manifest)
            try:
                code = process.wait(timeout=config["timeout_seconds"])
            except subprocess.TimeoutExpired:
                stop_tree(process)
                raise WorkflowError("Experiment timed out; process tree terminated")
        manifest["returncode"] = code
        if code:
            raise WorkflowError(f"Experiment exited with code {code}; inspect stderr.log")
        metrics = finite_metrics(load(artifacts / "metrics.json"))
        if inventory(inputs) != input_hashes:
            raise WorkflowError("Archived inputs changed during execution")
        if inventory(work) != input_hashes:
            raise WorkflowError("Experiment modified its inputs or source; write outputs only to {output}")
        manifest.update(status="succeeded", metrics=metrics, artifacts_sha256=inventory(artifacts))
    except (Exception, KeyboardInterrupt) as exc:
        if process and process.poll() is None:
            stop_tree(process)
        manifest.update(status="failed", error=str(exc), artifacts_sha256=inventory(artifacts))
    finally:
        manifest.update(finished_at=now(), duration_seconds=time.monotonic() - started)
        save(directory / "run.json", manifest)
        event(root, "experiment_finished", {"id": run_id, "status": manifest["status"]})
    if manifest["status"] != "succeeded":
        raise WorkflowError(f"{run_id}: {manifest.get('error')}")
    return manifest


def reproduce(root, run_id):
    original = verify_run(root, run_id)
    rerun = run(root, replay_id=run_id)
    comparison = original["config"]["comparison"]
    a, b = original["metrics"], rerun["metrics"]
    metrics_equal = set(a) == set(b) and all(math.isclose(a[k], b[k], abs_tol=comparison.get("abs_tol", 0),
                                                      rel_tol=comparison.get("rel_tol", 0)) for k in a)
    artifacts_equal = original["artifacts_sha256"] == rerun["artifacts_sha256"]
    passed = metrics_equal and (artifacts_equal if comparison["mode"] == "exact" else True)
    report = {"original": run_id, "rerun": rerun["id"], "at": now(), "passed": passed,
              "metrics_equal": metrics_equal, "artifacts_equal": artifacts_equal, "comparison": comparison,
              "scope": "snapshot replay on recorded environments; not independent scientific validation",
              "original_environment": original["environment"], "rerun_environment": rerun["environment"]}
    save(Path(root) / f"runs/{rerun['id']}/reproduction.json", report)
    event(root, "reproduction_checked", report)
    if not passed:
        raise WorkflowError(f"Reproduction failed; report: runs/{rerun['id']}/reproduction.json")
    return report


def verify_reproduction(root, replay_id):
    rerun = verify_run(root, replay_id)
    report = load(inside(root, f"runs/{identifier(replay_id)}/reproduction.json"))
    original = verify_run(root, report["original"])
    comparison = original["config"]["comparison"]
    if rerun["replay_of"] != original["id"] or report["rerun"] != replay_id or report.get("passed") is not True:
        raise WorkflowError("Invalid reproduction linkage")
    if rerun["inputs_sha256"] != original["inputs_sha256"] or rerun["config_sha256"] != original["config_sha256"]:
        raise WorkflowError("Reproduction does not use identical archived inputs and configuration")
    a, b = original["metrics"], rerun["metrics"]
    equal = set(a) == set(b) and all(math.isclose(a[k], b[k], abs_tol=comparison.get("abs_tol", 0), rel_tol=comparison.get("rel_tol", 0)) for k in a)
    if not equal or (comparison["mode"] == "exact" and original["artifacts_sha256"] != rerun["artifacts_sha256"]):
        raise WorkflowError("Stored reproduction result does not match actual outputs")
    return original["id"]


def export_run(root, run_id):
    """Explicitly export shareable execution evidence, excluding data and raw logs."""
    run_record = verify_run(root, run_id)
    source = inside(root, f"runs/{run_id}")
    destination = inside(root, f"reports/runs/{run_id}")
    if destination.exists():
        raise WorkflowError("Run evidence already exported; refusing to overwrite")
    destination.mkdir(parents=True)
    public = {key: run_record[key] for key in ("id", "status", "git", "config", "config_sha256", "inputs_sha256", "artifacts_sha256", "metrics", "started_at", "finished_at", "replay_of")}
    public["environment"] = {k: v for k, v in run_record["environment"].items() if k != "executable"}
    public["datasets"] = {key: {k: v for k, v in record.items() if k != "path"} for key, record in run_record["datasets"].items()}
    save(destination / "run.json", public)
    shutil.copy2(source / "config.json", destination / "config.json")
    shutil.copytree(source / "inputs/source", destination / "source")
    for name in ("packages.json", "reproduction.json"):
        if (source / name).exists():
            value = load(source / name)
            if name == "reproduction.json":
                for key in ("original_environment", "rerun_environment"):
                    value[key].pop("executable", None)
            save(destination / name, value)
    return {"exported": str(destination), "note": "Contains code and numeric evidence only; review before public sync"}
