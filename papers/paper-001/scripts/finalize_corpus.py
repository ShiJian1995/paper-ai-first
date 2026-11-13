"""Register explicitly authored full-text reviews and render their local catalogue.

This script does not write scientific findings or decide eligibility from abstracts.
Run only after reviewers complete their batches and QC corrections are resolved.
"""
from pathlib import Path
import argparse
import collections
import json
import sys
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from research_agent.literature import add_paper, audit_corpus, verify_paper, validate_paper, publication_window


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--register', action='store_true')
    args = parser.parse_args()
    records = []
    for path in sorted((ROOT/'literature/analysis-batches').glob('*/*.json')):
        item = json.loads(path.read_text(encoding='utf-8-sig'))
        validate_paper(item)
        source = (ROOT/item['source_path']).resolve()
        source.relative_to(ROOT.resolve())
        if not source.is_file():
            raise ValueError(f'Missing source for {item["id"]}')
        records.append(item)
        if args.register:
            registered = ROOT/f'literature/papers/{item["id"]}.json'
            if registered.exists():
                old = verify_paper(ROOT, item['id'])
                if any(old.get(k) != v for k, v in item.items()):
                    raise ValueError(f'Changed analysis requires explicit review: {item["id"]}')
            else:
                add_paper(ROOT, path)
    if not args.register:
        print(json.dumps({'validated_staging_records':len(records),'registered':False}))
        return
    audit = audit_corpus(ROOT)
    excluded = set(audit['duplicates_excluded'])
    unique = [x for x in records if x['id'] not in excluded]
    periods = collections.Counter()
    scope = collections.Counter()
    as_of = date.fromisoformat(audit['as_of'])
    for item in unique:
        periods[publication_window(item['published_date'],as_of)] += 1
        scope[item.get('scope_group', 'PF-core-or-enabling' if 'PF' in item['topics'] else 'OPF-adjacent')] += 1
    retrieved = json.loads((ROOT/'literature/retrieved-sources.json').read_text(encoding='utf-8'))
    unread = sorted(set(retrieved)-{r['id'] for r in records})
    summary = {'as_of':audit['as_of'],'fulltext_reports_read':len(records),'unique_studies':len(unique),'scope':dict(scope),'periods_first_public_date':dict(periods),'duplicates_excluded':sorted(excluded),'retrieved_but_not_counted_as_read':unread,'quantity_passed':audit['quantity_passed'],'definition':'Counts are of this bounded scoping corpus, not field-wide publication or popularity estimates.'}
    (ROOT/'literature/corpus-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    labels={'problem':'问题','method':'方法','data':'数据与复现入口','findings':'作者结果与阅读发现','limitations':'局限与证据风险','gap':'待检验缺口','relevance':'与本研究关系','evidence_locator':'全文定位'}
    lines=['# paper-001 逐篇全文分析目录', '', f'核查日：{audit["as_of"]}。已读报告 {len(records)} 份，保守去重后 {len(unique)} 项。', '', '这是AI全文阅读及抽样交叉核验记录，不是人工同行评审，也不是实验复现。结果数字均须结合原文限定条件；正文与全文文件保持本地。', '', '已下载但未完成阅读的材料不计数；摘要/网页补充线索见 external-sources.json。', '', '## 索引','', '| ID | 首次公开日期 | 范围 | 题目 |','|---|---|---|---|']
    for item in sorted(records,key=lambda x:(x['published_date'],x['id'])):
        label='重复报告，不计数' if item['id'] in excluded else item.get('scope_group','PF-core-or-enabling' if 'PF' in item['topics'] else 'OPF-adjacent')
        lines.append(f'| [{item["id"]}](#{item["id"]}) | {item["published_date"]} | {label} | {item["title"].replace("|", "/")} |')
    for item in sorted(records,key=lambda x:(x['published_date'],x['id'])):
        lines.extend(['',f'## {item["id"]}', '',f'**{item["title"]}**', '',f'[来源]({item["source_url"]}) · [本地全文]({(ROOT/item["source_path"]).as_posix()}) · [登记记录]({(ROOT/"literature/papers"/(item["id"]+".json")).as_posix()})', '',f'阅读者：{item["checked_by"]}；首次公开日期：{item["published_date"]}；研究族：{item["canonical_work_id"]}。'])
        for key,label in labels.items():
            lines.extend(['',f'**{label}：** {item["analysis"][key]}'])
    (ROOT/'literature/annotated-catalog.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if not audit['quantity_passed']:
        raise SystemExit('Full-text quantity/integrity gate not passed.')


if __name__ == '__main__':
    main()
