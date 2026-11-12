"""Explicit scoping shortlist; full-text eligibility remains subject to actual reading."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
core = '''2301.12062 2002.00097 2610.05959 1710.10621 2401.07465 1902.06211 2509.25120 2504.11650 2112.10320 2204.07000 2001.01714 2604.08403 2409.13956 2407.19253 2312.15831 2407.02501 2406.06833 2103.10147 2601.09533 1910.08655 2409.09466 1909.05748 2305.00216 2301.02651 2311.06293 2307.02049 2211.07125 1811.09727 1906.06017 2111.02169 2503.15563 2112.08418 2410.22062 2605.11102 2512.01207 2603.16879 2609.16738 2610.13495 2611.14240 2610.38985 2610.27930 2610.13683 2609.30859 2609.26603 2609.23723 2607.12241 2607.09122 2606.07099 2606.03717 2604.00673 2603.28203 2603.21977 2603.05673 2602.19667 2602.18227 2602.17975 2601.01387 2512.14658 2511.22343 2511.20237 2510.22048 2510.22020 2510.04264 2509.22458 2509.19233 2509.12281 2509.03495 2507.02078 2506.12902 2506.11281 2505.12302 2504.21260 2504.17210 2502.19912 2502.05702 2412.02659 2609.00384 2605.14103 2603.21514 2510.17071 2509.22733 2311.03415 1911.03093'''.split()
adjacent = '''2006.00544 2107.00465 2404.09128 2006.11029 2301.03766 2605.23194 2611.13566 1910.08842 2110.02672 1910.01213 2210.09277 2410.04818 2012.09622 2111.01228 2110.00306 2510.06860 2212.03977 2510.23196 2401.06820 2601.02706 2505.22825 2012.11524 2006.16356 2403.17831 2309.12849 2605.02133 1910.09658 1910.14448 2610.04307 2609.30173 2604.23548 2505.22399 2405.06109 2402.00773 2007.06074 2007.01002 1909.10461 1905.04479'''.split()

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def main():
    entries = json.loads((ROOT/'literature/arxiv-candidates.json').read_text(encoding='utf-8'))
    by_id = {e['arxiv_id']: e for e in entries}
    selected = []
    for identifier in core + adjacent:
        e = dict(by_id[identifier])
        if e['published'][:10] > '2026-11-12':
            continue
        e.update(record_id='ax-'+identifier.replace('.', '-'), pdf_urls=[e['pdf_url']],
                 scope='PF-core-or-enabling' if identifier in core else 'OPF-adjacent',
                 eligibility='provisional; verify abstract and entire full text',
                 rationale='Power-flow learning, solver evaluation, uncertainty, topology transfer or enabling benchmarks' if identifier in core else 'Adjacent OPF evidence about feasibility, physics layers, transferable architectures and reproducible benchmarks; not interchangeable with plain PF')
        selected.append(e)
    batches = {name: [] for name in ['reader-a','reader-b','reader-c','root']}
    for i, e in enumerate(selected):
        batches[list(batches)[i % 4]].append(e)
    for name, batch in batches.items():
        save(ROOT/f'literature/assignments/{name}.json', batch)
    save(ROOT/'literature/selected-for-retrieval.json', selected)
    save(ROOT/'literature/initial-screening.json', [{
        'arxiv_id':e['arxiv_id'], 'title':e['title'],
        'decision':'seek-full-text' if e['arxiv_id'] in {x['arxiv_id'] for x in selected} else 'not-prioritized-in-bounded-scoping-search',
        'note':'Not an exhaustive systematic exclusion; final eligibility requires full-text reading.'} for e in entries])
    p = ROOT/'research/project.json'
    project = json.loads(p.read_text(encoding='utf-8'))
    project['title'] = 'AI用于电力系统潮流计算与分析（选题调研）'
    save(p, project)
    print(json.dumps({k:len(v) for k,v in batches.items()}))

if __name__ == '__main__':
    main()
