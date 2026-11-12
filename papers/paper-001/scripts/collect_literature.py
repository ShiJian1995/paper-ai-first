"""Bounded scholarly retrieval. Saves metadata and complete sources; never invents analyses."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
RAW = ROOT / "literature/searches"
RAW.mkdir(parents=True, exist_ok=True)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def retrieve(url, timeout=35):
    request = urllib.request.Request(url, headers={"User-Agent": "Paper001LiteratureReview/0.1 academic-research", "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as r:
        content = r.read(25_000_001)
        if len(content) > 25_000_000:
            raise ValueError("Source exceeds download size budget")
        return content, r.url


def discover():
    queries = [
        '(ti:"power flow" OR ti:"load flow") AND (all:"learning" OR all:"neural" OR all:"data-driven")',
        '(ti:"power flow" OR ti:"load flow") AND (all:"learning" OR all:"neural" OR all:"data-driven")',
        'ti:"power flow" AND (all:"graph" OR all:"physics-informed" OR all:"operator")',
        'ti:"optimal power flow" AND (all:"deep learning" OR all:"neural network")',
        '(ti:"powerflow" OR ti:"powerflownet" OR ti:"load-flow")',
    ]
    records, log = {}, []
    for i, query in enumerate(queries):
        sort = "relevance" if i == 0 else "submittedDate"
        params = {"search_query": query, "start": 0, "max_results": 100, "sortBy": sort, "sortOrder": "descending"}
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
        stamp = {"provider": "arxiv", "query": query, "url": url, "at": datetime.now(timezone.utc).isoformat(), "limit": 100}
        try:
            body, final = retrieve(url)
            path = RAW / f"arxiv-{i:02}.xml"
            path.write_bytes(body)
            parsed = subprocess.run([sys.executable, str(WORKSPACE / ".agents/skills/paper-lookup/scripts/arxiv_atom.py"), str(path)], capture_output=True, text=True, encoding="utf-8")
            if parsed.returncode:
                raise RuntimeError(parsed.stderr)
            data = json.loads(parsed.stdout)
            save(RAW / f"arxiv-{i:02}.json", data)
            entries = data.get("entries", data.get("records", []))
            for entry in entries:
                key = re.sub(r"v\d+$", "", entry["arxiv_id"])
                records[key] = entry
            stamp.update(status="ok", retrieved=len(entries), total=data.get("total_results"), final_url=final)
        except Exception as exc:
            stamp.update(status="failed", error=str(exc))
        log.append(stamp)
        save(RAW / "retrieval-log.json", log)
        save(ROOT / "literature/arxiv-candidates.json", list(records.values()))
        print(json.dumps({"query": i, "unique": len(records), **stamp}, ensure_ascii=False), flush=True)
        time.sleep(3.2)
    return records


def download(limit):
    import pymupdf
    entries = json.loads((ROOT / "literature/selected-for-retrieval.json").read_text(encoding="utf-8"))[:limit]
    result_path = ROOT / "literature/retrieved-sources.json"
    reports = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    for entry in entries:
        key = entry["record_id"]
        if reports.get(key, {}).get("status") == "full_text_extracted":
            continue
        target = ROOT / "literature/fulltext" / f"{key}.pdf"
        text_path = target.with_suffix(".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        report = {"id": key, "title": entry["title"], "at": datetime.now(timezone.utc).isoformat(), "attempts": []}
        for url in entry["pdf_urls"]:
            try:
                body, final = retrieve(url)
                if not body.startswith(b"%PDF"):
                    raise ValueError("Response is not a PDF")
                target.write_bytes(body)
                doc = pymupdf.open(target)
                pages = [f"\n\n=== PAGE {i+1} ===\n" + page.get_text(sort=True) for i, page in enumerate(doc)]
                text = "".join(pages)
                if len(text.strip()) < 5000:
                    raise ValueError("Extracted text too short for substantive analysis; inspect/OCR separately")
                text_path.write_text(text, encoding="utf-8")
                report.update(status="full_text_extracted", pages=len(doc), characters=len(text), final_url=final,
                              source_path=target.relative_to(ROOT).as_posix(), text_path=text_path.relative_to(ROOT).as_posix(),
                              sha256=hashlib.sha256(body).hexdigest(), analysis_status="not_analyzed")
                doc.close()
                break
            except Exception as exc:
                report["attempts"].append({"url": url, "error": str(exc)})
                report["status"] = "not_retrieved"
        reports[key] = report
        save(result_path, reports)
        print(json.dumps({"id": key, "title": entry["title"], "status": report["status"], "pages": report.get("pages")}, ensure_ascii=False), flush=True)
        time.sleep(3.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["discover", "download"])
    parser.add_argument("--limit", type=int, default=150)
    args = parser.parse_args()
    if args.action == "discover":
        discover()
    else:
        download(args.limit)
