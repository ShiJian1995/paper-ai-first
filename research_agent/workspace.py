from pathlib import Path
import shutil
from .common import WorkflowError, identifier, inside, load, save
from .workflow import initialize, status


def paper_root(workspace, paper_id):
    root = inside(workspace, f"papers/{identifier(paper_id)}")
    if not (root / "research/project.json").is_file():
        raise WorkflowError(f"Unknown paper: {paper_id}. Run list or create first.")
    config = load(root / "research/project.json")
    if config.get("paper_id") != paper_id:
        raise WorkflowError("Paper identity does not match its directory")
    return root


def create(workspace, paper_id, title, direction=None, demo=False):
    root = inside(workspace, f"papers/{identifier(paper_id)}")
    if root.exists():
        raise WorkflowError("Paper directory already exists; never overwrite another paper")
    settings = load(Path(workspace) / "workspace.config.json")
    initialize(root, direction=direction, github_url=settings["github"]["url"])
    config = load(root / "research/project.json")
    config.update(paper_id=paper_id, title=title, kind="system-demo" if demo else "research")
    config["github"]["branch"] = settings["github"]["branch"]
    save(root / "research/project.json", config)
    if demo:
        assets = Path(__file__).resolve().parents[1]
        for source, target in (("examples/iris_baseline.py", "src/iris_baseline.py"),
                               ("examples/iris.dataset.json", "data/manifests/iris.json"),
                               ("examples/iris.experiment.json", "configs/iris.json")):
            shutil.copy2(assets / source, root / target)
    return status(root)


def restore(workspace, paper_id, title, demo=False):
    """Recreate local state after cloning code, without claiming to restore private research."""
    root = inside(workspace, f"papers/{identifier(paper_id)}")
    if not root.is_dir() or not (root / "src").is_dir():
        raise WorkflowError("Restore requires an existing published paper code directory")
    if (root / "research/project.json").exists():
        raise WorkflowError("Local project state already exists; use status instead")
    settings = load(Path(workspace) / "workspace.config.json")
    initialize(root, github_url=settings["github"]["url"])
    config = load(root / "research/project.json")
    config.update(paper_id=paper_id, title=title, kind="system-demo" if demo else "research")
    config["github"]["branch"] = settings["github"]["branch"]
    save(root / "research/project.json", config)
    return {**status(root), "note": "Initialized fresh local state; private literature, manuscript and run history are not in GitHub"}


def list_papers(workspace):
    result = []
    for path in sorted((Path(workspace) / "papers").glob("*/research/project.json")):
        root = paper_root(workspace, path.parents[1].name)
        config = load(path)
        result.append({"id": config["paper_id"], "title": config["title"], "kind": config["kind"], **status(root)})
    return result
