"""Behavioral tests use synthetic fixtures, never represented as research evidence."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from research_agent import data, experiments, github_sync, literature, workflow, workspace
from research_agent.cli import main
from research_agent.common import WorkflowError, inside, load, lock, save


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        save(self.base / "workspace.config.json", {"github": {"url": "https://github.com/test/research", "branch": "main"}})
        workspace.create(self.base, "alpha", "论文甲", "测试方向甲")
        workspace.create(self.base, "beta", "论文乙", "测试方向乙")
        self.root = workspace.paper_root(self.base, "alpha")
        self.manifest = {"id": "fixture", "url": "https://example.org/data", "source_page": "https://example.org/source",
                         "license": "CC0", "license_url": "https://example.org/license", "kind": "synthetic",
                         "description": "Synthetic software test fixture only", "generation_method": "constant byte string",
                         "limitations": "Not real research observations"}

    def fetched(self, body=b"test fixture input"):
        path = self.root / "data/manifests/test.json"
        save(path, self.manifest)
        with patch("research_agent.data.request_bytes", return_value=(body, self.manifest["url"], {})):
            return data.fetch(self.root, path)

    def experiment(self, body=None, timeout=3):
        self.fetched()
        path = self.root / "src/model.py"
        default = "import json, pathlib, sys\np=pathlib.Path(sys.argv[2]); p.mkdir(exist_ok=True)\np.joinpath('metrics.json').write_text(json.dumps({'byte_count':len(pathlib.Path(sys.argv[1]).read_bytes())}))\n"
        path.write_text(body or default, encoding="utf-8")
        config = {"name": "fixture", "command": ["{python}", "src/model.py", "{data:fixture}", "{output}"],
                  "sources": ["src/model.py"], "datasets": ["fixture"], "timeout_seconds": timeout,
                  "comparison": {"mode": "exact"}}
        save(self.root / "configs/test.json", config)
        return self.root / "configs/test.json"

    def paper(self, index, **changes):
        record = {"id": f"paper-{index}", "canonical_work_id": f"work-{index}", "title": f"Fixture study {index}",
                  "published_date": "2026-01-01", "source_url": f"https://example.org/{index}",
                  "source_path": f"literature/fixture-{index}.txt", "reading_level": "full_text",
                  "topics": ["test topic"], "checked_by": "synthetic-test-fixture",
                  "analysis": {k: f"Synthetic test explanation for field {k}, not research evidence." for k in literature.ANALYSIS_FIELDS}}
        record.update(changes)
        (self.root / record["source_path"]).write_text(f"Synthetic paper fixture {index}", encoding="utf-8")
        path = self.root / "literature/intake.json"
        save(path, record)
        literature.add_paper(self.root, path)
        return record

    def test_papers_have_independent_state(self):
        workflow.advance(self.root)
        self.assertEqual(workflow.status(self.root)["stage"], "literature")
        self.assertEqual(workflow.status(workspace.paper_root(self.base, "beta"))["stage"], "intake")
        self.assertEqual(len(workspace.list_papers(self.base)), 2)

    def test_no_implicit_paper(self):
        self.assertEqual(main(["--workspace", str(self.base), "status"]), 1)

    def test_restore_preserves_existing_source(self):
        root = self.base / "papers/cloned"
        (root / "src").mkdir(parents=True)
        source = root / "src/existing.py"
        source.write_text("print('published code')")
        workspace.restore(self.base, "cloned", "Cloned paper")
        self.assertEqual(source.read_text(), "print('published code')")
        self.assertIsNone(workflow.status(root)["direction"])

    def test_transitive_preprint_duplicates_count_once(self):
        self.paper(1, doi="10.1000/one", reading_level="abstract")
        self.paper(2, doi="10.1000/one", arxiv="1234.12345v1")
        self.paper(3, arxiv="1234.12345v2")
        result = literature.audit_corpus(self.root)
        self.assertEqual(result["unique_analyzed"], 1)
        self.assertEqual(result["full_text"], 1)

    def test_paper_id_and_path_traversal_blocked(self):
        with self.assertRaises(WorkflowError):
            workspace.create(self.base, "../beta", "bad")
        with self.assertRaises(WorkflowError):
            inside(self.root, "../beta/research/project.json")

    def test_duplicate_paper_not_overwritten(self):
        with self.assertRaises(WorkflowError):
            workspace.create(self.base, "alpha", "replacement")

    def test_lock_prevents_concurrent_mutation(self):
        with lock(self.root):
            with self.assertRaises(WorkflowError):
                with lock(self.root):
                    pass

    def test_first_download_pins_and_cache_is_verified(self):
        result = self.fetched()
        self.assertEqual(result["sha256"], hashlib.sha256(b"test fixture input").hexdigest())
        (self.root / result["path"]).write_bytes(b"modified")
        with self.assertRaises(WorkflowError):
            self.fetched()

    def test_checksum_failure_not_registered(self):
        self.manifest["sha256"] = "0" * 64
        with self.assertRaises(WorkflowError):
            self.fetched()
        self.assertFalse((self.root / "research/datasets.json").exists())

    def test_same_id_cannot_change_provenance(self):
        self.fetched()
        self.manifest["url"] = "https://example.org/changed"
        with self.assertRaises(WorkflowError):
            self.fetched()

    def test_cross_paper_dataset_not_visible(self):
        self.fetched()
        with self.assertRaises((WorkflowError, FileNotFoundError)):
            data.verify_datasets(workspace.paper_root(self.base, "beta"), ["fixture"])

    def test_replay_uses_archived_code(self):
        config = self.experiment()
        run = experiments.run(self.root, config)
        (self.root / "src/model.py").write_text("raise RuntimeError('changed workspace')")
        replay = experiments.reproduce(self.root, run["id"])
        self.assertTrue(replay["passed"])
        self.assertTrue(replay["artifacts_equal"])

    def test_modified_artifact_rejected(self):
        run = experiments.run(self.root, self.experiment())
        save(self.root / f"runs/{run['id']}/artifacts/metrics.json", {"byte_count": 999})
        with self.assertRaises(WorkflowError):
            experiments.verify_run(self.root, run["id"])

    def test_failed_process_never_succeeds(self):
        config = self.experiment("raise RuntimeError('deliberate fixture failure')")
        with self.assertRaises(WorkflowError):
            experiments.run(self.root, config)
        manifest = load(next((self.root / "runs").glob("*/run.json")))
        self.assertEqual(manifest["status"], "failed")

    def test_timeout_terminates_process(self):
        config = self.experiment("import time\ntime.sleep(30)\n", timeout=0.15)
        with self.assertRaises(WorkflowError):
            experiments.run(self.root, config)
        manifest = load(next((self.root / "runs").glob("*/run.json")))
        self.assertIn("timed out", manifest["error"])

    def test_nonfinite_metrics_rejected(self):
        config = self.experiment("import pathlib,sys\npathlib.Path(sys.argv[2],'metrics.json').write_text('{\"bad\": NaN}')\n")
        with self.assertRaises(WorkflowError):
            experiments.run(self.root, config)

    def test_nondeterministic_replay_fails(self):
        config = self.experiment("import json,pathlib,sys,time\npathlib.Path(sys.argv[2],'metrics.json').write_text(json.dumps({'time':time.time_ns()}))\n")
        run = experiments.run(self.root, config)
        with self.assertRaises(WorkflowError):
            experiments.reproduce(self.root, run["id"])

    def test_budget_enforced(self):
        config = self.experiment()
        settings = load(self.root / "research/project.json")
        settings["budgets"]["max_runs"] = 0
        save(self.root / "research/project.json", settings)
        with self.assertRaises(WorkflowError):
            experiments.run(self.root, config)

    def test_less_than_100_blocks_selection(self):
        self.paper(1)
        with self.assertRaises(WorkflowError):
            literature.audit_corpus(self.root, enforce=True)

    def test_duplicates_and_abstracts_do_not_satisfy_requirement(self):
        self.paper(1, doi="10.1000/fixture")
        self.paper(2, doi="https://doi.org/10.1000/FIXTURE")
        self.paper(3, reading_level="abstract")
        report = literature.audit_corpus(self.root)
        self.assertEqual(report["unique_analyzed"], 2)
        self.assertEqual(report["full_text"], 1)
        self.assertFalse(report["quantity_passed"])

    def test_hundred_alone_does_not_pass_without_current_trends(self):
        for i in range(100):
            self.paper(i)
        self.assertTrue(literature.audit_corpus(self.root)["quantity_passed"])
        with self.assertRaises(FileNotFoundError):
            literature.audit_corpus(self.root, enforce=True)

    def test_abstract_cannot_decide_candidate_even_with_passing_corpus(self):
        self.paper(1)
        self.paper(2, reading_level="abstract")
        summary = {"selected_topic": "A", "selection_reason": "fixture", "gap_paper_ids": ["paper-1"],
                   "counterevidence_paper_ids": ["paper-1"], "evidence_ids": ["fixture"],
                   "data_sources": ["fixture"], "candidates": [{"closest_precedents": ["paper-1"]}],
                   "excluded_or_deferred": [{"evidence_paper_ids": ["paper-2"]}]}
        save(self.root / "literature/selection.json", summary)
        with patch("research_agent.workflow.audit_corpus"), self.assertRaisesRegex(WorkflowError, "screening lead only"):
            workflow.check_gate(self.root, "literature")

    def test_literature_floor_cannot_be_lowered_in_config(self):
        settings = load(self.root / "research/project.json")
        settings["literature_policy"] = {"min_analyzed_papers": 1, "min_fulltext_papers": 1}
        save(self.root / "research/project.json", settings)
        self.paper(1)
        self.assertEqual(literature.audit_corpus(self.root)["required"], 100)

    def test_evidence_file_tamper_invalidates_claim(self):
        self.paper(1)
        (self.root / "literature/fixture-1.txt").write_text("changed")
        self.assertEqual(len(literature.audit_corpus(self.root)["invalid_records"]), 1)

    def test_publication_paths_exclude_private_material(self):
        for path in ("papers/alpha/manuscript/paper.md", "papers/alpha/data/raw/x.csv", "papers/alpha/research/project.json", "papers/alpha/runs/x/stdout.log", ".env"):
            self.assertFalse(github_sync.allowed(path), path)
        self.assertTrue(github_sync.allowed("papers/alpha/src/model.py"))

    @unittest.skipUnless(shutil.which("git"), "Git required")
    def test_sync_plan_is_scoped_to_one_paper(self):
        def git(*args):
            subprocess.run(["git", "-C", str(self.base), *args], check=True, capture_output=True)
        git("init", "-b", "main")
        git("remote", "add", "origin", "https://github.com/test/research.git")
        for key in ("alpha", "beta"):
            root = workspace.paper_root(self.base, key)
            (root / "src/model.py").write_text("print('test')")
        plan = github_sync.preflight(self.root)
        self.assertEqual(plan["files"], ["papers/alpha/src/model.py"])
        git("add", "papers/beta/src/model.py")
        with self.assertRaises(WorkflowError):
            github_sync.preflight(self.root)


if __name__ == "__main__":
    unittest.main()
