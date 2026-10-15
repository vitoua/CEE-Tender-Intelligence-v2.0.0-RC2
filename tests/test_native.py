"""Synthetic structural fixtures based on observed public page labels. Not live tests."""
import unittest,asyncio,os,tempfile
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('DATA_DIR',tempfile.mkdtemp())
from app.core import date
from app.connectors import slovakia,cvpis,ekr,estonia
from app.connectors.native import label,local_date,permitted,check_page
from app.net import ConnectorError

def table(fields):return '<html><title>Public</title><table>'+''.join('<tr><td>'+k+':</td><td>'+v+'</td></tr>' for k,v in fields.items())+'</table></html>'
SK=table({'Názov zákazky':'SSD test','Obstarávateľ':'Synthetic buyer','Dátum zverejnenia':'15.10.2026, 09:00','Lehota na predkladanie ponúk':'22.10.2026, 12:00','Stav zákazky':'Aktívna','CPV zákazky':'30233100-2'})
LT=table({'Pavadinimas':'SSD test','Pirkimo vykdytojo pavadinimas':'Synthetic buyer','Paskelbimo ir (arba) kvietimo data':'15/10/2026 12:09','Pasiūlymų arba paraiškų dalyvauti pirkime pateikimo terminas':'22/10/2026 08:00','BVPŽ kodai':'30233100-SSD','Numatoma vertė (EUR)':'17300.','Aprašymas':'Storage test'})
EE=table({'Hanke nimetus':'SSD test','Hankija nimi':'Synthetic buyer','Avaldamise kuupäev':'15.10.2026 12:00','Pakkumuste esitamise tähtpäev':'22.10.2026 10:00','CPV kood':'30233100','Hanke eeldatav maksumus':'17300 EUR','Hanke lühikirjeldus':'Storage test'})
HU='<table><tr><td>EKR000273422021/H001</td><td>Nemzeti, Ajánlati / részvételi felhívás</td><td>SSD test</td><td>2026.10.15.</td><td>2026.10.22. 10:00</td><td>- Synthetic buyer</td><td><a href="/portal/kozbeszerzes/eljarasok/EKR000273422021/reszletek">Részletek</a></td></tr></table>'
class NativeTests(unittest.TestCase):
 def test_labels(self):
  self.assertEqual(label(SK,['Obstarávateľ']),'Synthetic buyer');self.assertEqual(label(LT,['Numatoma vertė (EUR)']),'17300.')
 def test_dates(self):
  self.assertEqual(date(local_date('Thu Oct 15 12:09:17 EEST 2026','Europe/Vilnius')).hour,9)
  self.assertEqual(date(local_date('Tue Oct 27 10:00:00 EET 2026','Europe/Vilnius')).hour,8)
  self.assertEqual(date(local_date('2026.10.22. 10:00','Europe/Budapest')).hour,8)
 def test_slovakia(self):
  t=slovakia.parse(SK,{'id':'1','url':'https://www.uvo.gov.sk/vyhladavanie/vyhladavanie-zakaziek/detail/1'})
  self.assertEqual(t.title,'SSD test');self.assertEqual(t.buyer,'Synthetic buyer');self.assertEqual(date(t.deadline).hour,10);self.assertEqual(t.cpv,['30233100-2']);self.assertEqual(t.provenance,'ÚVO / EVO direct')
 def test_slovakia_discovery(self):
  raw='<table><tr><td><a href="/vyhladavanie/vyhladavanie-zakaziek/detail/123?cHash=x">SSD test</a></td><td>Buyer</td></tr></table>'
  refs=slovakia.discover(raw);self.assertEqual(refs[0]['id'],'123');self.assertEqual(refs[0]['buyer'],'Buyer')
 def test_lithuania(self):
  t=cvpis.parse(LT,{'id':'1','url':'https://viesiejipirkimai.lt/epps/cft/prepareViewCfTWS.do?resourceId=1'})
  self.assertEqual(t.buyer,'Synthetic buyer');self.assertEqual(t.value,17300);self.assertEqual(t.currency,'EUR');self.assertEqual(date(t.deadline).hour,5);self.assertEqual(t.description,'Storage test')
 def test_lithuania_discovery(self):
  refs=cvpis.discover('<a href="/epps/cft/prepareViewCfTWS.do?resourceId=123">SSD test</a>');self.assertEqual(refs[0]['id'],'123')
 def test_hungary(self):
  t=ekr.parse_list(HU)[0];self.assertEqual(t.id,'EKR000273422021/H001');self.assertEqual(t.title,'SSD test');self.assertEqual(t.buyer,'Synthetic buyer');self.assertEqual(date(t.deadline).hour,8);self.assertEqual(t.kind,'contract');self.assertTrue(t.url.endswith('reszletek'))
 def test_hungary_award(self):
  raw=HU.replace('Ajánlati / részvételi felhívás','Tájékoztató az eljárás eredményéről');self.assertEqual(ekr.parse_list(raw)[0].kind,'award')
 def test_estonia(self):
  t=estonia.parse(EE,{'id':'1','url':'https://riigihanked.riik.ee/rhr-web/#/procurement/1/general-info'})
  self.assertEqual(t.title,'SSD test');self.assertEqual(t.buyer,'Synthetic buyer');self.assertEqual(t.value,17300);self.assertEqual(date(t.deadline).hour,7);self.assertEqual(t.provenance,'RHR direct')
 def test_estonia_discovery(self):
  refs=estonia.discover('<a href="#/procurement/123/general-info">SSD test</a>');self.assertEqual(refs[0]['id'],'123')
  self.assertEqual(estonia.discover('<a href="https://evil.example/#/procurement/1/general-info">bad</a>'),[])
 def test_missing_data(self):
  t=estonia.parse('<h1>SSD</h1>',{'id':'1','title':'SSD','url':'https://riigihanked.riik.ee/'});self.assertEqual(t.state(),'review');self.assertIsNone(t.value)
 def test_login_detection(self):
  with self.assertRaisesRegex(ConnectorError,'login_required'):check_page('<title>lithuania Login</title>','https://viesiejipirkimai.lt/cas/login')
 def test_fetch_slovakia_no_ted(self):
  class R:
   def __init__(self,raw,url):self.text=raw;self.url=url
  class Fake:
   async def request(self,method,url,**kw):
    if '/detail/' in url:return R(SK,url)
    return R('<a href="/vyhladavanie/vyhladavanie-zakaziek/detail/123">SSD</a>',url)
  items,stats=asyncio.run(slovakia.fetch(Fake(),['SVK'],date('2026-10-01'),{'pages':1,'details':2}));self.assertEqual(len(items),1);self.assertEqual(stats['details_ok'],1)
 def test_fetch_lithuania_no_ted(self):
  class R:
   def __init__(self,raw,url):self.text=raw;self.url=url
  class Fake:
   async def request(self,method,url,**kw):return R(LT if 'resourceId' in url else '<a href="/epps/cft/prepareViewCfTWS.do?resourceId=123">SSD</a>',url)
  items,stats=asyncio.run(cvpis.fetch(Fake(),['LTU'],date('2026-10-01'),{'pages':1,'details':2}));self.assertEqual(len(items),1);self.assertEqual(items[0].value,17300)
if __name__=='__main__':unittest.main(verbosity=2)
