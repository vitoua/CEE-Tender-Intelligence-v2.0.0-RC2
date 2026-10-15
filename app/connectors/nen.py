import re,asyncio
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from app.core import Tender,iso,clean
from app.connectors.common import text,cpvs
BASE='https://nen.nipez.cz'
def field(body,label,stops):
 start=body.casefold().find(label.casefold())
 if start<0:return ''
 tail=body[start+len(label):];ends=[tail.casefold().find(x.casefold()) for x in stops];ends=[x for x in ends if x>=0]
 return clean(tail[:min(ends) if ends else 350])
def parse(raw,pid,url):
 soup=BeautifulSoup(raw,'html.parser');body=text(raw)
 title=field(body,'Název zadávacího postupu',['Zadavatel','Systémové číslo NEN']) or clean(soup.h1.get_text() if soup.h1 else '')
 buyer=field(body,'Zadavatel',['Systémové číslo NEN','Aktuální stav'])
 pub=iso(field(body,'Datum uveřejnění ZP na profil',['Specifikace podání','Kontaktní osoba']),'Europe/Prague')
 ddl=iso(field(body,'Lhůta pro podání nabídek',['Kontaktní osoba','Předmět']),'Europe/Prague')
 status=field(body,'Aktuální stav ZP',['Rozdělení na části','Evidenční číslo'])
 kind='cancelled' if 'zrušen' in status.casefold() else ('award' if any(x in status.casefold() for x in ('zadán','ukončen')) else 'contract')
 return Tender(pid,'nen','CZE',title,buyer,pub,ddl,url=url,description=field(body,'Popis předmětu',['Kód z číselníku','Hlavní místo plnění']),cpv=cpvs(body),kind=kind,portal_status=status,notes=['HTML label parser beta; missing dates require review'])
async def fetch(net,countries,start,limits):
 links={};out=[];stats={'pages':0,'ids':0,'details_ok':0,'details_failed':0,'missing_deadline':0,'coverage':'bounded public HTML; not full NEN coverage'}
 for page in range(1,min(3,limits['pages'])+1):
  url=BASE+'/verejne-zakazky'+('' if page==1 else f'/p:vz:page={page}')
  r=await net.request('GET',url,cap=2_000_000);stats['pages']+=1;soup=BeautifulSoup(r.text,'html.parser')
  for a in soup.select('a[href*="/detail-zakazky/"]'):
   href=urljoin(BASE,a['href']);pid=href.split('/detail-zakazky/')[-1].split('?')[0];links[pid]=href
 stats['ids']=len(links)
 for pid,url in list(links.items())[:limits['details']]:
  try:r=await net.request('GET',url,cap=2_000_000);t=await asyncio.to_thread(parse,r.text,pid,url)
  except Exception:stats['details_failed']+=1;continue
  stats['details_ok']+=1
  if not t.deadline:stats['missing_deadline']+=1
  out.append(t)
 stats['detail_cap_reached']=len(links)>limits['details']
 return out,stats
