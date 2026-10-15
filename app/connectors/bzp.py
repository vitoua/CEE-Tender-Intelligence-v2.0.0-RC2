import asyncio
from datetime import timedelta
from app.core import Tender,iso,clean,now
from app.connectors.common import cpvs,text
URL='https://ezamowienia.gov.pl/mo-board/api/v1/notice'
def parse(d):
 pid=str(d.get('noticeNumber') or d.get('objectId') or '');obj=d.get('objectId');url=d.get('noticeUrl') or (f'https://ezamowienia.gov.pl/mo-client-board/bzp/notice-details/id/{obj}' if obj else '')
 t=Tender(pid,'bzp','POL',clean(d.get('orderObject')),clean(d.get('organizationName')),iso(d.get('publicationDate')),iso(d.get('submittingOffersDate')),url=url,description=text(d.get('htmlBody') or '',60000)[:16000],cpv=cpvs(d.get('cpvCode') or d.get('cpvCodes') or []))
 raw_deadline=d.get('submittingOffersDate')
 if raw_deadline and len(str(raw_deadline))<=10:t.notes.append('Date-only deadline: '+str(raw_deadline))
 return t
async def fetch(net,countries,start,limits):
 stats={'pages':0,'scanned':0,'windows':0,'coverage':'bounded daily windows; SearchAfter cursor is beta'};out=[];seen=set()
 days=min(limits['days'],max(1,(now()-start).days+1))
 for offset in range(days):
  day=now().date()-timedelta(days=offset);stats['windows']+=1
  params={'NoticeType':'ContractNotice','PublicationDateFrom':day.isoformat()+'T00:00:00','PublicationDateTo':day.isoformat()+'T23:59:59','PageSize':20,'OrderType':'Delivery'}
  for page in range(limits['bzp_pages']):
   b=await net.json(URL,params=params,cap=3_000_000);rows=b if isinstance(b,list) else b.get('items',b.get('data',[]));stats['pages']+=1;fresh=0
   for d in rows:
    pid=str(d.get('noticeNumber') or d.get('objectId') or '')
    if not pid or pid in seen:continue
    seen.add(pid);fresh+=1;stats['scanned']+=1
    out.append(await asyncio.to_thread(parse,d))
   if not fresh:
    if rows:stats['repeated_page']=True
    break
   if len(rows)<20:break
   cursor=rows[-1].get('objectId')
   if not cursor:stats['missing_cursor']=True;break
   params['SearchAfter']=cursor
   if page==limits['bzp_pages']-1:stats['page_cap_reached']=True
 if days<(now()-start).days+1:stats['day_cap_reached']=True
 return out,stats
