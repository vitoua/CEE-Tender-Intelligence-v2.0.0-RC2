"""Native public-page helpers. No guessed API calls and no TED fallback."""
import re,os,asyncio
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
from app.core import clean,iso,safeurl
from app.net import ConnectorError

def soup(raw):
 s=BeautifulSoup(raw,'html.parser')
 for x in s(['script','style','nav','footer']):x.decompose()
 return s

def label(raw,names):
 """Exact label match, then bounded sibling/definition/table value."""
 s=soup(raw) if isinstance(raw,str) else raw
 names={clean(x).rstrip(':').casefold() for x in names}
 for node in s.find_all(['td','th','dt','label','span','div','strong','b']):
  if clean(node.get_text(' ',strip=True)).rstrip(':').casefold() not in names:continue
  if node.name in ('td','th'):
   cells=node.parent.find_all(['td','th'],recursive=False)
   if node in cells and cells.index(node)+1<len(cells):return clean(cells[cells.index(node)+1].get_text(' ',strip=True))
  if node.name=='dt':
   dd=node.find_next_sibling('dd')
   if dd:return clean(dd.get_text(' ',strip=True))
  sib=node.find_next_sibling()
  if sib:
   v=clean(sib.get_text(' ',strip=True))
   if v and len(v)<12000:return v
 # Rendered portals sometimes expose label/value on adjacent text lines.
 lines=[clean(x) for x in s.get_text('\n',strip=True).splitlines() if clean(x)]
 for i,line in enumerate(lines[:-1]):
  if line.rstrip(':').casefold() in names:return lines[i+1]
 return ''

def local_date(value,zone):
 value=clean(value).replace(',',' ')
 value=re.sub(r'\s+',' ',value)
 # Java Date.toString, used by CVP IS list pages; respect explicit EET/EEST offset.
 m=re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(EET|EEST)\s+(\d{4})',value)
 if m:
  months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  if m[1] in months:return iso(f'{m[5]}-{months.index(m[1])+1:02d}-{int(m[2]):02d}T{m[3]}'+('+03:00' if m[4]=='EEST' else '+02:00'))
 # Hungarian dates have a trailing dot after year/month/day.
 m=re.search(r'(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\.(?:\s*(\d{1,2}):(\d{2}))?',value)
 if m:return iso(f'{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}'+(f'T{int(m[4]):02d}:{m[5]}' if m[4] else ''),zone)
 m=re.search(r'\b(\d{1,2})[./](\d{1,2})[./](20\d{2})(?:\s+(\d{1,2}):(\d{2}))?',value)
 if m:return iso(f'{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}'+(f'T{int(m[4]):02d}:{m[5]}' if m[4] else ''),zone)
 return iso(value,zone)

def date_note(t,raw):
 if raw and not re.search(r'\d{1,2}:\d{2}',str(raw)):t.notes.append('Date-only deadline: '+clean(raw))

def permitted(url,hosts):
 url=safeurl(url)
 return bool(url and urlsplit(url).hostname in hosts)

def check_page(raw,url):
 title=clean(soup(raw).title.get_text() if soup(raw).title else '').casefold()
 if '/cas/' in url or 'login' in title or 'prisijungti'==title:raise ConnectorError('login_required: public route redirected to authentication')
 if any(x in raw.casefold() for x in ('g-recaptcha','hcaptcha','cf-chl-')):raise ConnectorError('access_challenge: automation stopped; no challenge bypass')

class Browser:
 """One Chromium per connector; public UI only. Disabled via NATIVE_BROWSER=0."""
 async def __aenter__(self):
  if os.getenv('NATIVE_BROWSER','1')=='0':raise ConnectorError('browser_required: enable NATIVE_BROWSER and install Chromium')
  try:
   from playwright.async_api import async_playwright
   self.pw=await async_playwright().start()
   args={'headless':True,'args':['--disable-dev-shm-usage','--no-sandbox']}
   if os.getenv('CHROMIUM_EXECUTABLE'):args['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
   self.browser=await self.pw.chromium.launch(**args)
   self.context=await self.browser.new_context(locale='en-GB',viewport={'width':1280,'height':900},accept_downloads=False)
   await self.context.route('**/*',lambda route:route.abort() if route.request.resource_type in ('image','font','media') else route.continue_())
   self.page=await self.context.new_page();self.page.set_default_timeout(7000)
   return self
  except BaseException as e:
   if hasattr(self,'browser'):await self.browser.close()
   if hasattr(self,'pw'):await self.pw.stop()
   if isinstance(e,asyncio.CancelledError):raise
   raise ConnectorError('browser_unavailable: '+type(e).__name__+'; check Chromium installation') from None
 async def __aexit__(self,*args):
  await self.context.close();await self.browser.close();await self.pw.stop()
 async def goto(self,url):
  r=await self.page.goto(url,wait_until='domcontentloaded',timeout=35000)
  if r and r.status>=400:raise ConnectorError('Native portal HTTP '+str(r.status))
  try:await self.page.wait_for_load_state('networkidle',timeout=6000)
  except Exception:pass
  raw=await self.page.content();check_page(raw,self.page.url);return raw
 async def next(self,pattern):
  # Follow only actual visible next controls. Never invent page parameters.
  loc=self.page.get_by_role('button',name=pattern).or_(self.page.get_by_role('link',name=pattern))
  for i in range(await loc.count()):
   x=loc.nth(i)
   if await x.is_visible() and await x.is_enabled():
    await x.click();await self.page.wait_for_timeout(900);return True
  return False
