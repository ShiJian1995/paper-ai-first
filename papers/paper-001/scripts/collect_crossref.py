"""Complementary bounded DOI metadata discovery, not full-text analysis."""
from collect_literature import retrieve, save, RAW
import urllib.parse
import json
import time
from datetime import datetime, timezone

queries=['machine learning power flow','graph neural network power flow','physics informed power flow']
log=[]
for i, query in enumerate(queries):
    params={'query.bibliographic':query,'rows':50,'filter':'from-pub-date:2024-11-13,until-pub-date:2026-11-12','sort':'relevance'}
    url='https://api.crossref.org/works?'+urllib.parse.urlencode(params)
    item={'provider':'Crossref','query':query,'url':url,'at':datetime.now(timezone.utc).isoformat(),'limit':50}
    try:
        body,final=retrieve(url)
        data=json.loads(body)
        if data.get('status')!='ok' or 'items' not in data.get('message',{}):
            raise ValueError('Not a successful work-list payload')
        save(RAW/f'crossref-{i:02}.json',data)
        item.update(status='ok',total=data['message']['total-results'],retrieved=len(data['message']['items']))
    except Exception as e:
        item.update(status='failed',error=str(e))
    log.append(item)
    save(RAW/'crossref-log.json',log)
    print(json.dumps(item),flush=True)
    time.sleep(1.1)
