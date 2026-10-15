import re
from urllib.parse import urljoin,urlsplit
from app.core import Tender,clean,date,now
from app.connectors.common import cpvs
from app.connectors.native import soup,label,local_date,date_note,permitted,check_page,Browser
from app.net import ConnectorError
BASE='https://ekr.gov.hu';LIST=BASE+'/portal/kozbeszerzes/hirdetmenyek';HOSTS={'ekr.gov.hu','www.ekr.gov.hu'}
def parse_list(raw,base=LIST):
 out=[]
 for row in soup(raw).select('tr'):
  cells=row.find_all('td',recursive=False)
  if len(cells)<6:continue
  values=[clean(x.get_text(' ',strip=True)) for x in cells]
  m=re.search(r'EKR\d{12}(?:/H\d+)?',values[0])
  if not m:continue
  pid=m[0];notice=values[1].casefold()
  kind='award' if 'eredményéről' in notice or 'szerződés' in notice else ('correction' if any(x in notice for x in ('módosítás','helyesbítés','visszavonás')) else ('contract' if 'felhívás' in notice else 'unknown'))
  links=[urljoin(base,a['href']) for a in row.select('a[href]') if permitted(urljoin(base,a['href']),HOSTS)]
  direct=next((u for u in links if '/reszletek' in u or '/eljaras/' in u or '/hirdetmeny' in u),'')
  t=Tender(pid,'ekr','HUN',values[2],values[5].lstrip('- '),local_date(values[3],'Europe/Budapest'),local_date(values[4],'Europe/Budapest'),url=direct,kind=kind,portal_status=values[1],provenance='EKR direct',links={'native search':LIST})
  date_note(t,values[4]);out.append(t)
 return out

def enrich(t,raw):
 s=soup(raw)
 t.description=label(s,['Rövid meghatározás','A közbeszerzés ismertetése','Eljárás tárgya']) or t.description
 t.cpv=cpvs(label(s,['Fő CPV-kód(ok)','CPV kód','Fő CPV-kód']))
 return t
async def fetch(net,countries,start,limits):
 out={};stats={'pages':0,'scanned':0,'details_ok':0,'details_failed':0,'coverage':'Native EKR public notice table + rendered UI; bounded, no TED'}
 # Native HTML is useful even if the JavaScript search UI cannot be rendered.
 r=await net.request('GET',LIST,cap=3_000_000);check_page(r.text,str(r.url));initial=parse_list(r.text,str(r.url))
 for t in initial:out[t.id]=t
 stats['pages']=1
 try:
  async with Browser() as b:
   raw=await b.goto(LIST)
   # Use a real visible date filter if available. No guessed API parameters.
   date_filter=b.page.get_by_label(re.compile('Közzététel dátuma',re.I))
   if await date_filter.count():
    try:
     await date_filter.first.fill(start.strftime('%Y.%m.%d.'))
     button=b.page.get_by_role('button',name=re.compile('^Szűrés$',re.I))
     if await button.count():await button.first.click();await b.page.wait_for_timeout(1200);stats['publication_filter_applied']=True
    except Exception:stats['publication_filter_applied']=False
   # The public default table can start with old notices. Try the actual publication header.
   sort_header=b.page.get_by_role('columnheader',name=re.compile('KÖZZÉTÉTEL DÁTUMA',re.I))
   if await sort_header.count():
    for attempt in range(2):
     before=parse_list(await b.page.content(),b.page.url)
     pubs=[date(t.published) for t in before if date(t.published)]
     if pubs and max(pubs)>=start:break
     try:await sort_header.first.click();await b.page.wait_for_timeout(900);stats['publication_sort_attempts']=attempt+1
     except Exception:break
   seen=set()
   for page in range(limits['pages']):
    raw=await b.page.content();check_page(raw,b.page.url);items=parse_list(raw,b.page.url);sig=tuple(t.id for t in items)
    if sig in seen:stats['repeated_page']=True;break
    seen.add(sig)
    for t in items:out[t.id]=t
    stats['pages']=max(stats['pages'],page+1)
    # Részletek may be a JS button, not an href. Open it and preserve the actual resulting URL.
    detail_rows=b.page.locator('tr').filter(has_text=re.compile(r'EKR\d{12}'))
    for i in range(min(await detail_rows.count(),max(0,limits['details']-stats['details_ok']))):
     row=detail_rows.nth(i);body=await row.inner_text();m=re.search(r'EKR\d{12}(?:/H\d+)?',body)
     if not m or m[0] not in out or out[m[0]].url:continue
     buttons=row.get_by_role('button',name=re.compile('Részletek',re.I)).or_(row.get_by_role('link',name=re.compile('Részletek',re.I)))
     if not await buttons.count():continue
     old=b.page.url
     try:
      await buttons.first.click();await b.page.wait_for_timeout(700)
      if b.page.url!=old and permitted(b.page.url,HOSTS):
       t=out[m[0]];t.url=b.page.url;enrich(t,await b.page.content());stats['details_ok']+=1
       await b.page.go_back(wait_until='domcontentloaded');await b.page.wait_for_timeout(500)
      else:stats['detail_modal_unparsed']=stats.get('detail_modal_unparsed',0)+1
     except Exception:stats['details_failed']+=1;break
    if not await b.next(re.compile(r'^(Következő|Next|›|»|>)$',re.I)):stats['pagination_unavailable']=True;break
 except Exception as e:stats['browser_warning']=str(e)[:250]
 if not out:raise ConnectorError('discovery_failed: EKR native page contains no recognized notice rows; browser/schema diagnostics required')
 stats['scanned']=len(out);pubs=[date(t.published) for t in out.values() if date(t.published)]
 if pubs:
  stats['newest_publication']=max(pubs).isoformat();stats['freshness_lag_days']=(now()-max(pubs)).days
  if max(pubs)<start:stats['requested_period_not_reached']=True
 # Enrich actual href detail pages; never replace missing links with the search homepage.
 for t in list(out.values())[:limits['details']]:
  if not t.url or t.cpv:continue
  try:
   r=await net.request('GET',t.url,cap=2_000_000);check_page(r.text,str(r.url));enrich(t,r.text);stats['details_ok']+=1
  except Exception:stats['details_failed']+=1
 return list(out.values()),stats
