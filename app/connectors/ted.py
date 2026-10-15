import re
from app.core import Tender,profiles,iso,clean
from app.connectors.common import scalar,cpvs,number
from app.net import ConnectorError
URL='https://api.ted.europa.eu/v3/notices/search'
FIELDS=['publication-number','notice-title','organisation-name-buyer','organisation-country-buyer','publication-date','deadline-receipt-tender-date-lot','classification-cpv','description-proc','estimated-value-proc','estimated-value-proc-currency','notice-type']
def query(countries,start,codes):
 country=' OR '.join('buyer-country='+c for c in countries)
 return '('+' OR '.join('classification-cpv='+c for c in codes)+') AND publication-date>='+start.strftime('%Y%m%d')+(' AND ('+country+')' if country else '')
def parse(d):
 def pick(*keys):return next((d[k] for k in keys if d.get(k) not in (None,'',[])),None)
 pid=scalar(pick('publication-number','publicationNumber','id'));country=scalar(pick('organisation-country-buyer','buyer-country','country'))
 # Multiple lots: retain earliest parseable deadline, not arbitrary language/list position.
 raw=pick('deadline-receipt-tender-date-lot','deadline');dates=[];date_only=[]
 def walk(v):
  if isinstance(v,dict):
   for x in v.values():walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
  else:
   x=iso(v)
   if x:
    if len(str(v))<=10:date_only.append(str(v))
    else:dates.append(x)
 walk(raw)
 cur=scalar(pick('estimated-value-proc-currency','currency'))
 return Tender(pid,'ted',country,clean(scalar(pick('notice-title','title'))),clean(scalar(pick('organisation-name-buyer','buyer-name','buyerName'))),iso(scalar(pick('publication-date','publicationDate'))),min(dates) if dates else '',number(scalar(pick('estimated-value-proc','value'))),cur,'https://ted.europa.eu/en/notice/-/detail/'+pid,clean(scalar(pick('description-proc','description'))),cpvs(pick('classification-cpv','cpv')),notes=(['Multiple lot deadlines may differ'] if len(set(dates))>1 else [])+(['Date-only deadline: '+', '.join(date_only)] if date_only else []))
async def fetch(net,countries,start,limits):
 stats={'requests':0,'scanned':0,'pages':0,'coverage':'bounded TED CPV search; not complete national coverage'};out={};fields=FIELDS.copy();f=profiles()['ted'];seen=set()
 queries=[query(countries,start,f['codes'][i:i+6]) for i in range(0,len(f['codes']),6)]
 country=' OR '.join('buyer-country='+c for c in countries)
 words=[w.replace('"',' ').replace('\\',' ') for w in f['keywords'][:12]]
 if words:queries.append('('+' OR '.join('FT~"'+w+'"' for w in words)+') AND publication-date>='+start.strftime('%Y%m%d')+(' AND ('+country+')' if country else ''))
 for q in queries:
  for page in range(1,limits['pages']+1):
   payload={'query':q,'fields':fields,'page':page,'limit':100,'scope':'ACTIVE','onlyLatestVersions':True,'paginationMode':'PAGE_NUMBER'}
   try:b=await net.json(URL,method='POST',json=payload)
   except ConnectorError as e:
    msg=getattr(e,'body','') or str(e)
    if 'supported values are:' not in msg:raise
    allowed_text=msg.split('supported values are:',1)[-1]
    allowed=set(re.findall(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)+',allowed_text))
    fields=[x for x in fields if x in allowed]
    if not fields or 'publication-number' not in fields:raise ConnectorError('TED schema negotiation failed; no safe publication ID field')
    payload['fields']=fields
    stats['reduced_fields']=fields;b=await net.json(URL,method='POST',json=payload)
   stats['requests']+=1;stats['pages']+=1;rows=b.get('notices') or b.get('results') or b.get('data') or []
   signature=tuple(scalar(d.get('publication-number')) for d in rows)
   if signature in seen:stats['repeated_page']=True;break
   seen.add(signature);stats['scanned']+=len(rows)
   for d in rows:
    t=parse(d)
    if t.id and t.country in countries:out[t.id]=t
   if len(rows)<100:break
   if page==limits['pages']:stats['page_cap_reached']=True
 return list(out.values()),stats
