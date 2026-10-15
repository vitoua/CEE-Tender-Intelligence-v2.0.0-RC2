from app.core import Tender,iso,clean,date,now,safeurl
from app.connectors.common import cpvs,number
URL='https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties'
def parse(d):
 code=(d.get('typePublicatie') or {}).get('code','');kind={'AAO':'contract','REC':'correction','AGO':'award','MAC':'consultation','VAA':'prior'}.get(code,'unknown')
 if d.get('isVroegtijdigeBeeindiging'):kind='cancelled'
 pid=str(d.get('publicatieId') or '')
 t=Tender(pid,'tenderned','NLD',clean(d.get('aanbestedingNaam')),clean(d.get('opdrachtgeverNaam')),iso(d.get('publicatieDatum'),'Europe/Amsterdam'),iso(d.get('sluitingsDatum') or d.get('sluitingsDatumMarktconsultatie'),'Europe/Amsterdam'),number(d.get('geraamdeWaarde')),d.get('valuta',''),safeurl((d.get('link') or {}).get('href')),clean(d.get('opdrachtBeschrijving')),cpvs(d.get('cpvCodes') or []),kind,(d.get('publicatiestatus') or {}).get('code',''),notes=['CPV/value not guaranteed in TNS list response'],links={'external platform':safeurl(d.get('tsenderLink'))} if safeurl(d.get('tsenderLink')) else {})
 raw_deadline=d.get('sluitingsDatum') or d.get('sluitingsDatumMarktconsultatie')
 if raw_deadline and len(str(raw_deadline))<=10:t.notes.append('Date-only deadline: '+str(raw_deadline))
 return t
async def fetch(net,countries,start,limits):
 out=[];stats={'pages':0,'scanned':0,'coverage':'bounded TNS JSON; sorting/freshness checked, not guaranteed'};seen=set();newest=None;lastdate=None
 for page in range(limits['pages']):
  b=await net.json(URL,params={'page':page,'size':50,'sort':'publicatieDatum,desc'})
  rows=b.get('content') or [];stats['pages']+=1;signature=tuple(str(d.get('publicatieId')) for d in rows)
  if signature in seen:stats['repeated_page']=True;break
  seen.add(signature);stats['scanned']+=len(rows)
  for d in rows:
   t=parse(d);pub=date(t.published)
   if pub:
    if lastdate and pub>lastdate:stats['non_descending_order']=True
    lastdate=pub;newest=max(newest,pub) if newest else pub
   out.append(t)
  if b.get('last') or not rows:break
  if page==limits['pages']-1:stats['page_cap_reached']=True
 if newest:stats.update(newest_publication=newest.isoformat(),freshness_lag_days=(now()-newest).days)
 return out,stats
