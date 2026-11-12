import json
from pathlib import Path
import urllib.parse
import uuid
from datetime import date, datetime, timedelta, timezone
import re
from .common import WorkflowError, digest, event, identifier, inside, load, now, request_bytes, required, save


def search(root, query, limit=10):
    if not query.strip() or not 1 <= limit <= 100:
        raise WorkflowError("Supply a query and a limit from 1 to 100")
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode({"query.bibliographic": query, "rows": limit})
    body, final_url, _ = request_bytes(url)
    response = json.loads(body)
    if response.get("status") != "ok" or not isinstance(response.get("message", {}).get("items"), list):
        raise WorkflowError("Crossref returned an unexpected response; search is incomplete")
    records = [{"doi": x.get("DOI"), "title": x.get("title", []), "url": x.get("URL"),
                "published": x.get("published"), "authors": x.get("author", []),
                "verification": "metadata-only; full-text claim support not checked"}
               for x in response["message"]["items"]]
    directory = Path(root) / "literature/searches" / uuid.uuid4().hex[:12]
    directory.mkdir(parents=True)
    (directory / "response.json").write_bytes(body)
    result = {"query": query, "provider": "crossref", "url": final_url, "retrieved_at": now(),
              "total_reported": response["message"].get("total-results"), "returned": len(records),
              "coverage": "ranked discovery only; not exhaustive", "records": records,
              "response_sha256": digest(directory / "response.json")}
    save(directory / "search.json", result)
    return {"saved": str(directory), **result}


def add_evidence(root, manifest_path):
    record = load(manifest_path)
    required(record, ["id", "claim", "source_url", "source_path", "locator", "support", "checked_by", "checked_at"], "evidence")
    key = identifier(record["id"])
    source = inside(root, record["source_path"])
    if not source.is_file():
        raise WorkflowError("Evidence requires an actual local source document")
    if record["support"] not in ("supports", "contradicts", "limited"):
        raise WorkflowError("support must be supports, contradicts or limited")
    path = Path(root) / f"literature/evidence/{key}.json"
    if path.exists():
        raise WorkflowError("Evidence ID already exists; create a revision with a new ID")
    record["source_sha256"] = digest(source)
    record["recorded_at"] = now()
    record["verification_scope"] = "checker assertion plus source integrity; script cannot verify semantic entailment"
    save(path, record)
    event(root, "evidence_registered", {"id": key})
    return record


def verify_evidence(root, evidence_id):
    record = load(Path(root) / f"literature/evidence/{identifier(evidence_id)}.json")
    source = inside(root, record["source_path"])
    if not source.is_file() or digest(source) != record["source_sha256"]:
        raise WorkflowError(f"Evidence source missing or changed: {evidence_id}")
    return record


ANALYSIS_FIELDS = ("problem", "method", "data", "findings", "limitations", "gap", "relevance", "evidence_locator")


def normalize_title(title):
    return "".join(c for c in title.casefold() if c.isalnum())


def validate_paper(record):
    required(record, ["id", "canonical_work_id", "title", "published_date", "source_url", "source_path", "reading_level", "analysis", "topics", "checked_by"], "paper analysis")
    identifier(record["id"])
    if record["reading_level"] not in ("full_text", "abstract"):
        raise WorkflowError("reading_level must be full_text or abstract")
    date.fromisoformat(record["published_date"])
    required(record["analysis"], ANALYSIS_FIELDS, "substantive paper analysis")
    for field in ANALYSIS_FIELDS:
        value = record["analysis"][field]
        if not isinstance(value, str) or len(value.strip()) < 8 or value.strip().lower() in ("not applicable", "unknown", "pending", "待分析", "待补充"):
            raise WorkflowError(f"Paper analysis needs a substantive {field}; no placeholder counts")
    if not isinstance(record["topics"], list) or not record["topics"] or not all(isinstance(x, str) and x.strip() for x in record["topics"]):
        raise WorkflowError("Paper topics must be a nonempty list of research themes")


def add_paper(root, manifest_path):
    record = load(manifest_path)
    validate_paper(record)
    path = Path(root) / f"literature/papers/{record['id']}.json"
    if path.exists():
        raise WorkflowError("Paper ID already exists; inspect or explicitly revise its analysis")
    source = inside(root, record["source_path"])
    if not source.is_file():
        raise WorkflowError("Paper analysis requires a retrieved local source")
    record["source_sha256"] = digest(source)
    record["analyzed_at"] = now()
    save(path, record)
    return {"id": record["id"], "reading_level": record["reading_level"], "recorded": str(path)}


def verify_paper(root, paper_id):
    record = load(Path(root) / f"literature/papers/{identifier(paper_id)}.json")
    validate_paper(record)
    if record["id"] != paper_id:
        raise WorkflowError("Paper record ID mismatch")
    source = inside(root, record["source_path"])
    if not source.is_file() or digest(source) != record["source_sha256"]:
        raise WorkflowError(f"Paper source missing or modified: {paper_id}")
    return record


def audit_corpus(root, enforce=False):
    root = Path(root)
    config = load(root / "research/project.json")
    policy = config.get("literature_policy", {})
    # The user requires at least 100 papers; settings cannot silently lower this floor.
    minimum = max(100, policy.get("min_analyzed_papers", 100))
    fulltext_min = max(100, policy.get("min_fulltext_papers", 100))
    records, duplicates, errors = [], [], []
    candidates, links, parents = [], {}, []
    def group(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index
    for path in sorted((root / "literature/papers").glob("*.json")):
        try:
            record = verify_paper(root, path.stem)
        except (WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
            errors.append({"file": path.name, "error": str(exc)})
            continue
        work = record["canonical_work_id"].casefold().strip()
        title = normalize_title(record["title"])
        doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", record.get("doi", "").casefold()).strip()
        arxiv = re.sub(r"v\d+$", "", record.get("arxiv", "").casefold().removeprefix("arxiv:").removeprefix("https://arxiv.org/abs/")).strip()
        index = len(candidates)
        candidates.append(record)
        parents.append(index)
        for kind, value in (("work", work), ("title", title), ("doi", doi), ("arxiv", arxiv)):
            if not value:
                continue
            key = (kind, value)
            if key in links:
                parents[group(index)] = group(links[key])
            links[key] = index
    grouped = {}
    for index, record in enumerate(candidates):
        grouped.setdefault(group(index), []).append(record)
    for items in grouped.values():
        items.sort(key=lambda item: (item["reading_level"] != "full_text", item["id"]))
        records.append(items[0])
        duplicates.extend(item["id"] for item in items[1:])
    today = datetime.now(timezone(timedelta(hours=8))).date()
    recent, prior = {}, {}
    for record in records:
        age = (today - date.fromisoformat(record["published_date"])).days
        if age < 0:
            errors.append({"id": record["id"], "error": "Publication date is in the future"})
        target = recent if 0 <= age < 365 else prior if 365 <= age < 730 else None
        if target is not None:
            for topic in set(record["topics"]):
                target[topic] = target.get(topic, 0) + 1
    trends = {topic: {"last_365_days": recent.get(topic, 0), "previous_365_days": prior.get(topic, 0)} for topic in sorted(set(recent) | set(prior))}
    full_count = sum(x["reading_level"] == "full_text" for x in records)
    report = {"as_of": today.isoformat(), "unique_analyzed": len(records), "full_text": full_count,
              "required": minimum, "required_fulltext": fulltext_min, "duplicates_excluded": duplicates,
              "invalid_records": errors, "topic_counts_in_collected_corpus": trends,
              "limitations": "Counts describe this corpus, not field-wide popularity. Semantic analysis and cross-version linkage require review.",
              "quantity_passed": len(records) >= minimum and full_count >= fulltext_min and not errors}
    save(root / "literature/corpus-audit.json", report)
    if enforce:
        if not report["quantity_passed"]:
            raise WorkflowError(f"Literature gate: {len(records)} unique analyzed / {full_count} full-text; need at least {minimum}/{fulltext_min}; invalid={len(errors)}")
        trend = load(root / "literature/trends.json")
        required(trend, ["as_of", "search_strategy", "coverage", "hot_topics", "unresolved_problems", "counterevidence", "sources", "limitations"], "current research trends")
        age = (today - date.fromisoformat(trend["as_of"])).days
        if age < 0 or age > min(30, policy.get("trend_max_age_days", 30)):
            raise WorkflowError("Trend analysis must be current (within 30 days)")
        valid_ids = {r["id"] for r in records}
        for entry in trend["hot_topics"]:
            required(entry, ["topic", "evidence_paper_ids", "recent_search_source", "reason"], "hot topic")
            if not set(entry["evidence_paper_ids"]).issubset(valid_ids):
                raise WorkflowError("Hot-topic references must exist in the analyzed corpus")
    return report
