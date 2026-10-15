import re
from urllib.parse import urljoin,urlsplit
from app.core import Tender,clean,profiles,matching
from app.connectors.common import cpvs
from app.connectors.native import soup,label,local_date,date_note,permitted,check_page
from app.net import ConnectorError
BASE='https://www.uvo.gov.sk';LIST=BASE+'/vyhladavanie/vyhladavanie-zakaziek'
HOSTS={'www.uvo.gov.sk','uvo.gov.sk','evo.isepvo.sk'}
def discover(raw,base=LIST):
 s=soup(raw);out=[]
 for a in s.select('a[href]'):
  u=urljoin(base,a['href']);m=re.search(r'/vyhladavanie-zakaziek/detail/(\d+)',u)
  if not m or not permitted(u,HOSTS):continue
  row=a.find_parent('tr');cells=row.find_all('td') if row else []
  out.append({'id':m[1],'url':u,'title':clean(a.get_text(' ',strip=True)),'buyer':clean(cells[1].get_text(' ',strip=True)) if len(cells)>1 else ''})
 return list({x['id']:x for x in out}.values())
def parse(raw,ref):
 s=soup(raw);title=label(s,['Názov zákazky']);buyer=label(s,['Obstarávateľ','Obstarávateľ:']) or ref.get('buyer','')
 ddl=label(s,['Lehota na predkladanie ponúk']);pub=label(s,['Dátum zverejnenia']);status=label(s,['Stav zákazky','Stav zakázky'])
 kind='cancelled' if 'zrušen' in status.casefold() else ('award' if any(x in status.casefold() for x in ('ukončen','zadan')) else 'contract')
 t=Tender(ref['id'],'slovakia','SVK',title or ref.get('title',''),buyer,local_date(pub,'Europe/Bratislava'),local_date(ddl,'Europe/Bratislava'),url=ref['url'],description=label(s,['Stručný opis zákazky','Opis predmetu zákazky','Predmet zákazky']),cpv=cpvs(label(s,['CPV zákazky'])),kind=kind,portal_status=status,provenance='ÚVO / EVO direct')
 date_note(t,ddl);return t
async def fetch(net,countries,start,limits):
 out=[];refs={};stats={'pages':0,'discovered':0,'details_ok':0,'details_failed':0,'coverage':'Native ÚVO list + EVO public details; bounded scan, no TED'};url=LIST;visited=set()
 for page in range(limits['pages']):
  r=await net.request('GET',url,cap=2_000_000);check_page(r.text,str(r.url));stats['pages']+=1
  for ref in discover(r.text,str(r.url)):refs[ref['id']]=ref
  s=soup(r.text);nxt=next((urljoin(str(r.url),a['href']) for a in s.select('a[href]') if clean(a.get_text()).casefold() in ('ďalšia','nasledujúca') or a.get('rel')==['next']),None)
  if not nxt or nxt in visited or not permitted(nxt,HOSTS):break
  visited.add(nxt);url=nxt
  if page==limits['pages']-1:stats['page_cap_reached']=True
 stats['discovered']=len(refs)
 if not refs:raise ConnectorError('discovery_failed: native ÚVO page contains no public detail links')
 for ref in list(refs.values())[:limits['details']]:
  try:
   r=await net.request('GET',ref['url'],cap=2_000_000);check_page(r.text,str(r.url));t=parse(r.text,ref)
   # EVO link is discovered from the real ÚVO page, never constructed from a guessed endpoint.
   links=[urljoin(str(r.url),a['href']) for a in soup(r.text).select('a[href]') if 'evo.isepvo.sk' in a['href'] and '/Public/OrderSearch/Detail' in a['href']]
   if links and (not t.deadline or not t.published):
    u=next((u for u in links if permitted(u,HOSTS)),None)
    if u:
     er=await net.request('GET',u,cap=2_000_000);check_page(er.text,str(er.url));e=parse(er.text,ref)
     for k in ('deadline','published','buyer','description','portal_status'):
      if not getattr(t,k) and getattr(e,k):setattr(t,k,getattr(e,k))
     if not t.cpv:t.cpv=e.cpv
     t.notes+=e.notes;t.links['EVO']=u
   stats['details_ok']+=1;out.append(t)
  except Exception as e:stats['details_failed']+=1;stats.setdefault('detail_errors',[]).append(str(e)[:160])
 stats['detail_cap_reached']=len(refs)>limits['details']
 return out,stats
