import argparse
import json
from pathlib import Path
import shutil
import sys

from .common import WorkflowError, inside, load, lock
from . import data, experiments, github_sync, literature, workflow, workspace


def parser():
    p = argparse.ArgumentParser(description="论文研究工作流：每次研究操作显式指定 --paper，隔离不同论文")
    p.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--paper", help="论文唯一 ID；研究命令必须提供，不使用隐式当前论文")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="列出所有论文与各自阶段")
    sub.add_parser("doctor", help="检查运行环境")
    c = sub.add_parser("create", help="新建隔离的论文项目")
    c.add_argument("--id", required=True)
    c.add_argument("--title", required=True)
    c.add_argument("--direction")
    c.add_argument("--demo", action="store_true", help="复制公开 Iris 示例，仅用于工作流验证")
    c = sub.add_parser("restore", help="克隆后为已有论文代码重建本地状态，不恢复未上传的正文")
    c.add_argument("--id", required=True)
    c.add_argument("--title", required=True)
    c.add_argument("--demo", action="store_true")
    c = sub.add_parser("configure", help="设置当前论文方向或 GitHub 目标")
    c.add_argument("--direction")
    c.add_argument("--github")
    sub.add_parser("status")
    sub.add_parser("next", help="给 Codex 的当前阶段指令")
    sub.add_parser("advance", help="检查当前阶段产物后推进一步")
    c = sub.add_parser("search", help="Crossref 元数据检索，不代表已读全文")
    c.add_argument("query")
    c.add_argument("--limit", type=int, default=10)
    c = sub.add_parser("fetch", help="按数据清单下载并校验")
    c.add_argument("manifest")
    c = sub.add_parser("evidence-add")
    c.add_argument("manifest")
    c = sub.add_parser("paper-add", help="登记已完成的单篇论文实质分析")
    c.add_argument("manifest")
    sub.add_parser("corpus-audit", help="去重统计已分析论文并检查至少100篇要求")
    c = sub.add_parser("run")
    c.add_argument("config")
    for action in ("reproduce", "verify-run", "export-run"):
        c = sub.add_parser(action)
        c.add_argument("run_id")
    sub.add_parser("github-plan", help="预览当前论文的发布文件；不上传")
    c = sub.add_parser("github-sync", help="提交并推送当前论文允许发布的文件")
    c.add_argument("--message", required=True)
    sub.add_parser("framework-plan", help="预览共享系统代码，不包含任何论文")
    c = sub.add_parser("framework-sync", help="同步共享系统代码，不包含任何论文")
    c.add_argument("--message", required=True)
    return p


def dispatch(args):
    base = args.workspace.resolve()
    if args.action == "list":
        return workspace.list_papers(base)
    if args.action == "doctor":
        skills = [p.parent.name for p in (base / ".agents/skills").glob("*/SKILL.md")]
        return {"python": sys.version, "git": shutil.which("git"), "codex": shutil.which("codex"),
                "skills": sorted(skills), "workspace": str(base),
                "mode": "Codex-driven; no unattended LLM scheduler or paid API required"}
    if args.action == "create":
        with lock(base):
            return workspace.create(base, args.id, args.title, args.direction, args.demo)
    if args.action == "restore":
        with lock(base):
            return workspace.restore(base, args.id, args.title, args.demo)
    if args.action.startswith("framework-"):
        if args.paper:
            raise WorkflowError("Framework commands do not accept --paper")
        with lock(base):
            return github_sync.preflight(base) if args.action == "framework-plan" else github_sync.sync(base, args.message)
    if not args.paper:
        raise WorkflowError("Specify --paper <ID>; no implicit paper is selected. Use list or create.")
    root = workspace.paper_root(base, args.paper)
    if args.action in ("status", "next"):
        return workflow.status(root)
    with lock(root):
        if args.action == "configure":
            return workflow.initialize(root, args.direction, args.github)
        if args.action == "advance":
            return workflow.advance(root)
        if args.action == "search":
            return literature.search(root, args.query, args.limit)
        if args.action == "fetch":
            return data.fetch(root, inside(root, args.manifest))
        if args.action == "evidence-add":
            return literature.add_evidence(root, inside(root, args.manifest))
        if args.action == "paper-add":
            return literature.add_paper(root, inside(root, args.manifest))
        if args.action == "corpus-audit":
            return literature.audit_corpus(root)
        if args.action == "run":
            return experiments.run(root, inside(root, args.config))
        if args.action == "verify-run":
            return experiments.verify_run(root, args.run_id)
        if args.action == "reproduce":
            return experiments.reproduce(root, args.run_id)
        if args.action == "export-run":
            return experiments.export_run(root, args.run_id)
        if args.action == "github-plan":
            return github_sync.preflight(root)
        if args.action == "github-sync":
            # Git index belongs to the shared repository: serialize across papers.
            with lock(base):
                return github_sync.sync(root, args.message)
    raise WorkflowError("Unknown action")


def main(argv=None):
    try:
        result = dispatch(parser().parse_args(argv))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (WorkflowError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
