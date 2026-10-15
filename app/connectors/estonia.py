import re
from urllib.parse import urljoin
from app.core import Tender,clean,date,now
from app.connectors.common import cpvs,number
from app.connectors.native import soup,label,local_date,date_note,permitted,check_page,Browser
from app.net import ConnectorError
BASE='https://riigihanked.riik.ee';LIST=BASE+'/rhr-web/#/search-links';HOSTS={'riigihanked.riik.ee'}
def discover(raw,base=LIST):
 out=[]
 for a in soup(raw).select('a[href]'):
  u=urljoin(base,a['href']);m=re.search(r'#/procurement/(\d+)(?:/|$)',u)
  if not m or not permitted(u,HOSTS):continue
  # Follow the actual published route. No fabricated search endpoint or notice ID.
  title=clean(a.get_text(' ',strip=True))
  if title:out.append({'id':m[1],'url':u,'title':title})
 return list({x['id']:x for x in out}.values())
def parse(raw,ref):
 s=soup(raw);ddl=label(s,['Pakkumuste esitamise tähtpäev','Pakkumuste esitamise tähtaeg','Taotluste esitamise tähtpäev','Tender submission deadline']);pub=label(s,['Avaldamise aeg','Avaldamise kuupäev','Hanke avaldamise kuupäev','Publication date'])
 status=label(s,['Hanke seisund','Hanke staatus','Status'])
 kind='cancelled' if any(x in status.casefold() for x in ('tühist','cancel')) else ('award' if any(x in status.casefold() for x in ('lõppen','awarded')) else 'contract')
 title=label(s,['Hanke nimetus','Hanke nimi','Procurement name']) or ref.get('title','')
 buyer=label(s,['Hankija nimi','Hankija','Contracting authority'])
 value_raw=label(s,['Hanke eeldatav maksumus','Eeldatav maksumus','Estimated value']);currency='EUR' if 'EUR' in value_raw or '€' in value_raw else ''
 # Currency must be explicit. Never assume EUR solely from country.
 value=number(re.sub(r'[^\d,.]','',value_raw).replace(',','.')) if currency else None
 t=Tender(ref['id'],'estonia','EST',title,buyer,local_date(pub,'Europe/Tallinn'),local_date(ddl,'Europe/Tallinn'),value,currency,ref['url'],label(s,['Hanke lühikirjeldus','Lühikirjeldus','Kirjeldus','Short description']),cpvs(label(s,['CPV kood','CPV koodid','CPV põhikood','CPV code'])),kind,status,provenance='RHR direct')
 date_note(t,ddl);return t
async def fetch(net,countries,start,limits):
 stats={'pages':0,'discovered':0,'details_ok':0,'details_failed':0,'coverage':'Native RHR rendered public search and procurement cards; no TED, no guessed API endpoints'};refs={};out=[]
 async with Browser() as b:
  raw=await b.goto(LIST)
  # The native search route can require an explicit search action before showing rows.
  if not discover(raw,b.page.url):
   button=b.page.get_by_role('button',name=re.compile(r'^(Otsi|Search)$',re.I))
   if await button.count():await button.first.click();await b.page.wait_for_timeout(1400);raw=await b.page.content()
  seen=set()
  for page in range(limits['pages']):
   check_page(raw,b.page.url);found=discover(raw,b.page.url);sig=tuple(x['id'] for x in found)
   if sig in seen:stats['repeated_page']=True;break
   seen.add(sig)
   for x in found:refs[x['id']]=x
   stats['pages']+=1
   if not await b.next(re.compile(r'^(Järgmine|Next|›|»|>)$',re.I)):stats['pagination_unavailable']=True;break
   raw=await b.page.content()
  stats['discovered']=len(refs)
  if not refs:raise ConnectorError('discovery_failed: RHR rendered search has no public procurement links; no TED substitution performed')
  for ref in list(refs.values())[:limits['details']]:
   try:
    raw=await b.goto(ref['url']);t=parse(raw,ref)
    # Buyer may be on a separate public tab. Follow the actual link, never a guessed API.
    if not t.buyer:
     s=soup(raw);u=next((urljoin(ref['url'],a['href']) for a in s.select('a[href]') if '/procurers' in a['href'] and permitted(urljoin(ref['url'],a['href']),HOSTS)),None)
     if u:
      other=await b.goto(u);t.buyer=label(other,['Hankija nimi','Ametlik nimi','Official name']);t.links['Procurers']=u
    stats['details_ok']+=1;out.append(t)
   except Exception as e:stats['details_failed']+=1;stats.setdefault('detail_errors',[]).append(str(e)[:160])
 stats['detail_cap_reached']=len(refs)>limits['details'];stats['missing_publication']=sum(not t.published for t in out);stats['missing_deadline']=sum(not t.deadline for t in out)
 return out,stats
