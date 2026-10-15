import re
from urllib.parse import urljoin,parse_qs,urlsplit
from app.core import Tender,clean
from app.connectors.common import cpvs,number
from app.connectors.native import soup,label,local_date,date_note,permitted,check_page,Browser
from app.net import ConnectorError
BASE='https://viesiejipirkimai.lt';LIST=BASE+'/epps/prepareCurrentOpportunities.do?currentType=cft'
HOSTS={'viesiejipirkimai.lt','www.viesiejipirkimai.lt'}
def discover(raw,base=LIST):
 s=soup(raw);out=[]
 for a in s.select('a[href*="prepareViewCfTWS.do"]'):
  url=urljoin(base,a['href']);pid=parse_qs(urlsplit(url).query).get('resourceId',[''])[0]
  if not pid.isdigit() or not permitted(url,HOSTS):continue
  row=a.find_parent('tr');cells=row.find_all('td',recursive=False) if row else []
  out.append({'id':pid,'url':url,'title':clean(a.get_text(' ',strip=True)),'buyer':clean(cells[3].get_text(' ',strip=True)) if len(cells)>=9 else '', 'published':local_date(cells[5].get_text(' ',strip=True),'Europe/Vilnius') if len(cells)>=9 else '', 'deadline':local_date(cells[6].get_text(' ',strip=True),'Europe/Vilnius') if len(cells)>=9 else ''})
 return list({x['id']:x for x in out}.values())
def parse(raw,ref):
 s=soup(raw);ddl=label(s,['Pasiūlymų arba paraiškų dalyvauti pirkime pateikimo terminas']);pub=label(s,['Paskelbimo ir (arba) kvietimo data'])
 val=label(s,['Numatoma vertė (EUR)']);value=number(val.replace(' ','').replace(',','.').rstrip('.')) if val else None
 t=Tender(ref['id'],'cvpis','LTU',label(s,['Pavadinimas']) or ref.get('title',''),label(s,['Pirkimo vykdytojo pavadinimas']) or ref.get('buyer',''),local_date(pub,'Europe/Vilnius') or ref.get('published',''),local_date(ddl,'Europe/Vilnius') or ref.get('deadline',''),value,'EUR' if value is not None else '',ref['url'],label(s,['Aprašymas']),cpvs(label(s,['BVPŽ kodai'])),provenance='CVP IS direct')
 date_note(t,ddl);return t
async def fetch(net,countries,start,limits):
 refs={};stats={'pages':0,'discovered':0,'details_ok':0,'details_failed':0,'coverage':'Native new CVP IS current opportunities + public detail pages; no TED'};out=[]
 r=await net.request('GET',LIST,cap=3_000_000);check_page(r.text,str(r.url));stats['pages']=1
 for x in discover(r.text,str(r.url)):refs[x['id']]=x
 # Browser follows actual paginator controls, preserving session and form state.
 if limits['pages']>1:
  try:
   async with Browser() as b:
    raw=await b.goto(LIST);seen=set()
    for page in range(limits['pages']):
     found=discover(raw,b.page.url);sig=tuple(x['id'] for x in found)
     if sig in seen:stats['repeated_page']=True;break
     seen.add(sig)
     for x in found:refs[x['id']]=x
     stats['pages']=max(stats['pages'],page+1)
     if not await b.next(re.compile(r'^(Next|Kitas|Kitas puslapis|›|»|>)$',re.I)):stats['pagination_unavailable']=True;break
     raw=await b.page.content()
  except Exception as e:stats['pagination_warning']=str(e)[:250]
 stats['discovered']=len(refs)
 if not refs:raise ConnectorError('discovery_failed: CVP IS current opportunities returned no resourceId links')
 for ref in list(refs.values())[:limits['details']]:
  try:
   r=await net.request('GET',ref['url'],cap=2_000_000);check_page(r.text,str(r.url));out.append(parse(r.text,ref));stats['details_ok']+=1
  except Exception as e:stats['details_failed']+=1;stats.setdefault('detail_errors',[]).append(str(e)[:160])
 stats['detail_cap_reached']=len(refs)>limits['details']
 return out,stats
