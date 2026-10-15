import asyncio
from urllib.parse import urlsplit
from app.core import Tender,iso,clean,date
from app.connectors.common import cpvs,number
BASE='https://public-api.prozorro.gov.ua/api/2.5'
def parse(d):
 status=d.get('status','');kind='contract' if status in ('active.enquiries','active.tendering') else ('award' if status in ('active.awarded','complete') else ('cancelled' if status in ('cancelled','unsuccessful') else 'unknown'))
 items=d.get('items') or [];val=d.get('value') or {};pid=d.get('tenderID') or d.get('id','');codes=[]
 for i in items:codes+=cpvs((i.get('classification') or {}).get('id'))
 t=Tender(str(pid),'prozorro','UKR',clean(d.get('title')),clean((d.get('procuringEntity') or {}).get('name')),iso(d.get('dateCreated')),iso((d.get('tenderPeriod') or {}).get('endDate')),number(val.get('amount')),val.get('currency',''),'https://prozorro.gov.ua/tender/'+str(pid),clean(' '.join([d.get('description','')]+[i.get('description','') for i in items])),list(dict.fromkeys(codes)),kind,status,notes=['Feed ordered by modification, not publication; bounded scan'])
 raw_deadline=(d.get('tenderPeriod') or {}).get('endDate')
 if raw_deadline and len(str(raw_deadline))<=10:t.notes.append('Date-only deadline: '+str(raw_deadline))
 return t
async def fetch(net,countries,start,limits):
 stats={'pages':0,'scanned':0,'details_ok':0,'details_failed':0,'missing_publication':0,'status_counts':{},'missing_deadline':0,'coverage':'bounded modification feed, not all tenders in date range'};out=[];seen=set();url=BASE+'/tenders';params={'limit':100,'descending':1}
 sem=asyncio.Semaphore(4)
 async def load(ref):
  async with sem:
   try:return (await net.json(BASE+'/tenders/'+ref['id'])).get('data',{})
   except Exception:stats['details_failed']+=1;return None
 for page in range(limits['prozorro_pages']):
  b=await net.json(url,params=params);refs=[x for x in b.get('data',[]) if x.get('id') and x['id'] not in seen]
  stats['pages']+=1;stats['scanned']+=len(refs);seen.update(x['id'] for x in refs)
  if not refs:break
  for offset in range(0,len(refs),12):
   details=await asyncio.gather(*(load(x) for x in refs[offset:offset+12]))
   for d in filter(None,details):
    stats['details_ok']+=1;status=d.get('status','unknown');stats['status_counts'][status]=stats['status_counts'].get(status,0)+1
    t=parse(d)
    if not t.published:stats['missing_publication']+=1
    if not t.deadline:stats['missing_deadline']+=1
    out.append(t)
  nxt=(b.get('next_page') or {}).get('uri')
  if not nxt:break
  if urlsplit(nxt).hostname!=urlsplit(BASE).hostname:stats['unsafe_next_url']=True;break
  url=nxt;params=None
  if page==limits['prozorro_pages']-1:stats['page_cap_reached']=True
 return out,stats
