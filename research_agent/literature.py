import json
from pathlib import Path
import urllib.parse
import uuid
from datetime import date, datetime, timedelta, timezone
import re
from calendar import monthrange
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
    if record.get("paper_id"):
        paper = verify_fulltext(root, record["paper_id"])
        if paper["source_sha256"] != record["source_sha256"]:
            raise WorkflowError(f"Paper evidence refers to a different source version: {evidence_id}")
    return record


ANALYSIS_FIELDS = ("problem", "method", "data", "findings", "limitations", "gap", "relevance", "evidence_locator")


def normalize_title(title):
    return "".join(c for c in title.casefold() if c.isalnum())


def publication_interval(value):
    if re.fullmatch(r"\d{4}", value):
        return date(int(value), 1, 1), date(int(value), 12, 31)
    if re.fullmatch(r"\d{4}-\d{2}", value):
        y,m=map(int,value.split("-"))
        return date(y,m,1),date(y,m,monthrange(y,m)[1])
    day=date.fromisoformat(value)
    return day,day


def publication_window(value, as_of):
    first,last=publication_interval(value)
    def window(d):
        age=(as_of-d).days
        return "last_365_days" if age<365 else "previous_365_days" if age<730 else "earlier"
    if first>as_of:
        return "future"
    return window(first) if window(first)==window(min(last,as_of)) else "date_spans_windows"


def validate_paper(record):
    required(record, ["id", "canonical_work_id", "title", "published_date", "source_url", "source_path", "reading_level", "analysis", "topics", "checked_by"], "paper analysis")
    identifier(record["id"])
    if record["reading_level"] not in ("full_text", "abstract"):
        raise WorkflowError("reading_level must be full_text or abstract")
    publication_interval(record["published_date"])
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


def verify_fulltext(root, paper_id):
    record = verify_paper(root, paper_id)
    if record["reading_level"] != "full_text":
        raise WorkflowError(f"Completed full-text analysis required; screening lead only: {paper_id}")
    return record


def _domain_journals(root, policy, groups):
    """Join verified full texts to journal metadata. Never count a raw search result."""
    venue_path = root / "literature/venue-priority.json"
    venue = load(venue_path) if venue_path.is_file() else {}
    index = {r["id"]: r for r in venue.get("rows", [])}
    accepted, used = [], set()
    scopes = set(policy["eligible_journal_scopes"])
    excluded_ids = set(policy.get("journal_scope_exclusions", {}))
    for family in groups:
        for paper in family:
            row = index.get(paper["id"], {})
            q = row.get("quartile")
            if (paper["id"] in excluded_ids or q not in ("Q1","Q2") or paper.get("scope_group") not in scopes or paper["reading_level"] != "full_text"
                    or row.get("tier") != {"Q1": 2, "Q2": 3}.get(q, -1)
                    or row.get("study") != paper["canonical_work_id"]
                    or row.get("read_version") != paper["source_path"]
                    or not any(c == row.get("category") and k == q and page > 0
                               for c, k, page in row.get("category_quartiles_pages", []))):
                continue
            doi = row.get("doi", "").casefold().strip()
            if not doi or doi in used or not row.get("metadata"):
                continue
            source = inside(root / "literature", row["metadata"])
            if not source.is_file() or not any(
                x.get("type") == "journal-article" and x.get("DOI","").casefold() == doi
                for x in load(source).get("items", [])
            ):
                continue
            accepted.append({"id":paper["id"], "doi":doi, "quartile":q})
            used.add(doi)
            break
    return accepted


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
        period = publication_window(record["published_date"], today)
        if period == "future":
            errors.append({"id": record["id"], "error": "Publication date is in the future"})
        target = recent if period == "last_365_days" else prior if period == "previous_365_days" else None
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
    if policy.get("min_domain_journal_fulltexts"):
        threshold = max(100, policy["min_domain_journal_fulltexts"])
        eligible = _domain_journals(root, policy, grouped.values())
        report.update(required_domain_journals=threshold, eligible_domain_journals=len(eligible),
                      domain_journal_shortfall=max(0, threshold-len(eligible)), eligible_journal_records=eligible)
        report["quantity_passed"] &= len(eligible) >= threshold
    save(root / "literature/corpus-audit.json", report)
    if enforce:
        if not report["quantity_passed"]:
            journal_msg = (f"; domain Q1/Q2 journals={len(eligible)}/{threshold}" if policy.get("min_domain_journal_fulltexts") else "")
            raise WorkflowError(f"Literature gate: {len(records)} unique analyzed / {full_count} full-text; need at least {minimum}/{fulltext_min}; invalid={len(errors)}{journal_msg}")
        trend = load(root / "literature/trends.json")
        required(trend, ["as_of", "search_strategy", "coverage", "hot_topics", "unresolved_problems", "counterevidence", "sources", "limitations"], "current research trends")
        age = (today - date.fromisoformat(trend["as_of"])).days
        if age < 0 or age > min(30, policy.get("trend_max_age_days", 30)):
            raise WorkflowError("Trend analysis must be current (within 30 days)")
        valid_ids = {r["id"] for r in records if r["reading_level"] == "full_text"}
        for entry in trend["hot_topics"]:
            required(entry, ["topic", "evidence_paper_ids", "recent_search_source", "reason"], "hot topic")
            if not entry["evidence_paper_ids"] or not set(entry["evidence_paper_ids"]).issubset(valid_ids):
                raise WorkflowError("Hot-topic references require completed full-text analyses")
    return report
