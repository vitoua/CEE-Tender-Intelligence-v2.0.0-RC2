import json,hashlib
from datetime import timedelta
from app.core import Tender,now,iso,clean,safeurl
from app.connectors.common import ocds,cpvs,number,xml_notice
BASE='https://open.iub.gov.lv/data/notice'
def find(o,names):
 if not isinstance(o,dict):return ''
 # Priority by field name, not traversal order. Never accept arbitrary nested 'name' as buyer/title.
 for name in names:
  for k,v in o.items():
   if k.casefold()==name.casefold() and isinstance(v,(str,int,float)):return v
 for v in o.values():
  if isinstance(v,dict):
   x=find(v,names)
   if x!='':return x
  elif isinstance(v,list):
   for d in v:
    x=find(d,names)
    if x!='':return x
 return ''
def parse(d,url):
 if isinstance(d.get('tender'),dict):return ocds(d,'latvia','LVA',url)
 for k in ('xml','noticeXml','xmlContent'):
  if isinstance(d.get(k),str) and d[k].lstrip().startswith('<'):return xml_notice(d[k],'latvia','LVA',url)
 pid=str(find(d,['noticeId','noticeIdentifier','publicationId','id','BT-701-notice']))
 title=clean(find(d,['noticeTitle','title','procurementName','BT-21-Procedure']))
 buyer=clean(find(d,['buyerName','organisationName','organizationName','contractingAuthorityName','pasutitajs']))
 pub=iso(find(d,['publicationDate','published','datePublished','publication_date']),'Europe/Riga');ddl=iso(find(d,['submissionDeadline','tenderDeadline','deadline','BT-131(d)-Lot']),'Europe/Riga')
 value=number(find(d,['estimatedValue','totalValue','valueAmount']));currency=str(find(d,['currency','valueCurrency']))
 direct=safeurl(find(d,['noticeUrl','publicationUrl','url']))
 result=Tender(pid or hashlib.sha256(json.dumps(d,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24],'latvia','LVA',title,buyer,pub,ddl,value,currency,direct,clean(find(d,['description','shortDescription','BT-24-Procedure'])),cpvs(find(d,['cpvCode','cpvCodes','cpv','classification'])),links={'dataset':url})
 raw_deadline=find(d,['submissionDeadline','tenderDeadline','deadline','BT-131(d)-Lot'])
 if raw_deadline and len(str(raw_deadline))<=10:result.notes.append('Date-only deadline: '+str(raw_deadline))
 return result
async def fetch(net,countries,start,limits):
 out=[];stats={'files':0,'scanned':0,'schema_incomplete':0,'coverage':'date-targeted JSON; unsupported fields remain explicitly missing'}
 for offset in range(min(limits['days'],max(1,(now()-start).days+1))):
  day=now().date()-timedelta(days=offset);url=f'{BASE}/{day.year}/{day.month:02d}/{day:%d-%m-%Y}.json'
  try:b=await net.json(url,cap=8_000_000)
  except Exception as e:stats.setdefault('day_errors',[]).append({'date':str(day),'error':str(e)[:180]});continue
  stats['files']+=1;rows=b if isinstance(b,list) else b.get('notices') or b.get('data') or b.get('items') or [b]
  for d in rows:
   if not isinstance(d,dict):continue
   stats['scanned']+=1
   try:t=parse(d,url)
   except Exception:stats['schema_incomplete']+=1;continue
   if not t.title:stats['schema_incomplete']+=1;continue
   if not t.buyer or not t.deadline:stats['schema_incomplete']+=1
   out.append(t)
 stats['day_cap_reached']=(now()-start).days+1>limits['days']
 return out,stats
