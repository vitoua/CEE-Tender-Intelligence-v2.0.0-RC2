import asyncio,zipfile,tempfile,json
from datetime import timedelta
from app.core import now,matching,profiles
from app.connectors.common import ocds
URL='https://oeffentlichevergabe.de/api/notice-exports'
def releases(doc):
 if isinstance(doc,list):
  for x in doc:yield from releases(x)
 elif isinstance(doc,dict):
  if doc.get('compiledRelease'):yield doc['compiledRelease']
  elif 'releases' in doc:
   for x in doc['releases']:yield from releases(x)
  elif 'records' in doc:
   for x in doc['records']:yield from releases(x)
  elif 'tender' in doc:yield doc

def parse_zip(raw,url,profile=None):
 out=[];stats={'files':0,'records':0,'oversize_members':0};total=0
 with tempfile.SpooledTemporaryFile(max_size=2_000_000) as tmp:
  tmp.write(raw);tmp.seek(0)
  with zipfile.ZipFile(tmp) as z:
   for info in z.infolist()[:6000]:
    if not info.filename.endswith(('.json','.jsonl')):continue
    if info.file_size>4_000_000 or total+info.file_size>100_000_000:stats['oversize_members']+=1;continue
    total+=info.file_size;stats['files']+=1
    try:
     with z.open(info) as f:
      if info.filename.endswith('.jsonl'):
       docs=(json.loads(line) for line in f if line.strip())
      else:docs=[json.load(f)]
      for doc in docs:
       for d in releases(doc):
        stats['records']+=1
        if stats['records']>15000:stats['record_cap_reached']=True;return out,stats
        t=ocds(d,'germany','DEU',url)
        if matching(t,profile):out.append(t)
    except (ValueError,KeyError,TypeError):stats['parse_errors']=stats.get('parse_errors',0)+1
 return out,stats
async def fetch(net,countries,start,limits):
 out=[];stats={'days':0,'records':0,'coverage':'bounded OCDS archive scan; missing fields are review, never fabricated'}
 days=min(limits['days'],max(1,(now()-start).days+1))
 for offset in range(days):
  day=(now().date()-timedelta(days=offset)).isoformat()
  try:r=await net.request('GET',URL,params={'pubDay':day,'format':'ocds.zip'},cap=20_000_000)
  except Exception as e:stats.setdefault('day_errors',[]).append({'day':day,'error':str(e)[:180]});continue
  items,s=await asyncio.to_thread(parse_zip,r.content,str(r.url),profiles()['germany']);out+=items;stats['days']+=1;stats['records']+=s['records'];stats.setdefault('archive_stats',[]).append(s)
 stats['day_cap_reached']=days<(now()-start).days+1
 return out,stats
