"""Retrieve an explicitly reviewed public full-text URL into this paper only."""
import argparse, hashlib, json, re
from datetime import datetime, timezone
import pymupdf
from collect_literature import ROOT, retrieve, save

def run(identifier,url):
    if not re.fullmatch(r'[a-z0-9-]+',identifier):
        raise ValueError('Invalid local ID')
    body, final = retrieve(url)
    if not body.startswith(b'%PDF'):
        raise ValueError('Not a PDF')
    dest=ROOT/f'literature/fulltext/{identifier}.pdf'
    dest.write_bytes(body)
    with pymupdf.open(dest) as doc:
        content='\n'.join(f'=== PAGE {i+1} ===\n'+p.get_text(sort=True) for i,p in enumerate(doc))
        dest.with_suffix('.txt').write_text(content,encoding='utf-8')
        info={'id':identifier,'source_url':url,'final_url':final,'source_path':dest.relative_to(ROOT).as_posix(),'at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(body).hexdigest(),'pages':len(doc),'status':'full_text_extracted','analysis_status':'not_analyzed'}
    save(ROOT/f'literature/searches/{identifier}-retrieval.json',info)
    print(json.dumps(info))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('identifier');p.add_argument('url');a=p.parse_args();run(a.identifier,a.url)
