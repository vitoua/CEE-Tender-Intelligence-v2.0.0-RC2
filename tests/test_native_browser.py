"""Browser integration against intercepted SYNTHETIC portal pages, not live portals.
Run separately with installed Chromium; set CHROMIUM_EXECUTABLE if needed.
"""
import os,tempfile,asyncio,json,unittest
from unittest.mock import patch
os.environ.setdefault('DATA_DIR',tempfile.mkdtemp())
from app.core import date
from app.connectors import estonia,ekr
from app.connectors.native import Browser
from test_native import EE,HU,table
class FixtureBrowser(Browser):
 async def __aenter__(self):
  await super().__aenter__()
  async def intercept(route):
   url=route.request.url
   if 'riigihanked.riik.ee' in url:
    initial='<a href="#/procurement/123/general-info">SSD test</a>'
    raw='<html><title>Public fixture</title><body><div id="content"></div><script>const detail='+json.dumps(EE)+';const initial='+json.dumps(initial)+';function render(){document.getElementById("content").innerHTML=location.hash.includes("/procurement/")?detail:initial}window.addEventListener("hashchange",render);render();</script></body></html>'
   elif 'ekr.gov.hu' in url:
    raw=table({'CPV kód':'30233100','Rövid meghatározás':'SSD storage'}) if 'reszletek' in url else '<html><title>Public fixture</title>'+HU+'</html>'
   else:await route.abort();return
   await route.fulfill(status=200,content_type='text/html',body=raw)
  await self.context.route('**/*',intercept)
  return self
class BrowserTests(unittest.TestCase):
 def test_estonia_rendered_workflow(self):
  async def run():
   with patch.object(estonia,'Browser',FixtureBrowser):return await estonia.fetch(None,['EST'],date('2026-10-01'),{'pages':1,'details':1})
  items,stats=asyncio.run(run());self.assertEqual(len(items),1);self.assertEqual(items[0].buyer,'Synthetic buyer');self.assertEqual(items[0].provenance,'RHR direct');self.assertEqual(stats['details_ok'],1)
 def test_hungary_rendered_workflow(self):
  class R:
   def __init__(self,text,url):self.text=text;self.url=url
  class Net:
   async def request(self,method,url,**kw):return R(table({'CPV kód':'30233100'}) if 'reszletek' in url else HU,url)
  async def run():
   with patch.object(ekr,'Browser',FixtureBrowser):return await ekr.fetch(Net(),['HUN'],date('2026-10-01'),{'pages':1,'details':1})
  items,stats=asyncio.run(run());self.assertEqual(len(items),1);self.assertEqual(items[0].cpv,['30233100']);self.assertEqual(items[0].provenance,'EKR direct')
if __name__=='__main__':unittest.main(verbosity=2)
