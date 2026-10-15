import os,re,json
from app.core import Tender,iso,clean,safeurl
from app.connectors.common import number,cpvs
from app.net import ConnectorError
async def fetch(net,countries,start,limits):
 required=['APIFY_API_TOKEN','APIFY_ACTOR_ID','APIFY_INPUT_JSON'];missing=[k for k in required if not os.getenv(k)]
 if missing:raise ConnectorError('Missing configuration: '+', '.join(missing))
 actor=os.environ['APIFY_ACTOR_ID']
 if not re.fullmatch(r'[A-Za-z0-9_~-]+',actor):raise ConnectorError('Invalid APIFY_ACTOR_ID format')
 try:payload=json.loads(os.environ['APIFY_INPUT_JSON'])
 except ValueError:raise ConnectorError('APIFY_INPUT_JSON is not valid JSON') from None
 if not isinstance(payload,dict):raise ConnectorError('APIFY_INPUT_JSON must be an object')
 r=await net.request('POST',f'https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items',headers={'Authorization':'Bearer '+os.environ['APIFY_API_TOKEN']},json=payload,timeout=160,cap=6_000_000)
 rows=r.json()
 if not isinstance(rows,list):raise ConnectorError('Actor did not return a dataset list')
 out=[];skipped=0
 for d in rows[:1000]:
  pid=str(d.get('id') or d.get('tenderNo') or '');title=clean(d.get('title') or d.get('name'))
  if not pid or not title:skipped+=1;continue
  out.append(Tender(pid,'ekap','TUR',title,clean(d.get('buyer')),iso(d.get('publicationDate'),'Europe/Istanbul'),iso(d.get('deadline'),'Europe/Istanbul'),number(d.get('value')),d.get('currency',''),safeurl(d.get('url') or d.get('link')),clean(d.get('description')),cpvs(d.get('cpv')),notes=['Actor-specific field mapping must be verified against actual output']))
 for t,d in zip(out,[d for d in rows[:1000] if (d.get('id') or d.get('tenderNo')) and (d.get('title') or d.get('name'))]):
  if d.get('deadline') and len(str(d['deadline']))<=10:t.notes.append('Date-only deadline: '+str(d['deadline']))
 return out,{'scanned':len(rows),'schema_rejected':skipped,'coverage':'Actor-specific dataset; no guaranteed native EKAP coverage','row_cap_reached':len(rows)>1000}
