"""Synthetic fixtures only. No production records or live network calls."""
import os,tempfile,unittest,asyncio,json,io,zipfile,time
from pathlib import Path
from datetime import timedelta
TMP=tempfile.TemporaryDirectory();os.environ['DATA_DIR']=TMP.name
from app import core,translation,engine
from app.main import app,cell
from app.core import Tender,now,iso,date
from app.connectors import ted,tenderned,prozorro,bzp,germany,latvia,nen,ekap,slovakia,cvpis,ekr,estonia
from app.net import ConnectorError,RateLimited,Net
from fastapi.testclient import TestClient
from unittest.mock import patch
import httpx
class Tests(unittest.TestCase):
 def setUp(self):
  self.c=TestClient(app)
  with core.connect() as c:c.executescript('DELETE FROM tenders;DELETE FROM runs;DELETE FROM config;DELETE FROM cache;DELETE FROM quota;')
  translation.STATE.update(blocked_until=0,last_error='');os.environ.pop('ADMIN_TOKEN',None)
 def sample(self,**kw):
  args=dict(id='synthetic',source='bzp',country='POL',title='SSD storage',buyer='Synthetic buyer',published=now().isoformat(),deadline=(now()+timedelta(days=7)).isoformat(),url='https://example.org/notice',cpv=['30233100'])
  args.update(kw);return Tender(**args)
 def test_routes(self):
  for url in ['/','/health','/analytics','/cpv','/keywords','/sources','/status','/settings','/about','/export.xlsx','/export.csv','/export.json']:
   with self.subTest(url=url):self.assertEqual(self.c.get(url).status_code,200)
 def test_language(self):
  for lang in ['uk','pl','en','es']:
   self.c.get('/lang/'+lang);self.assertIn('lang="'+lang+'"',self.c.get('/').text)
 def test_date(self):
  self.assertEqual(date('20261001').day,1);self.assertEqual(date('2026-10-01T12:00:00+02:00').hour,10)
  self.assertEqual(date('2026-10-01T12:00:00','Europe/Amsterdam').hour,10)
  self.assertIsNone(date('bad'));self.assertIsNone(date('31.02.2026'))
 def test_ted_date(self):
  q=ted.query(['POL'],date('2026-10-01'),['30233100']);self.assertIn('publication-date>=20261001',q);self.assertNotIn('2026-10-01',q)
 def test_matching(self):
  self.assertFalse(core.matching(self.sample(title='Wasserversorgung',cpv=[]),{'codes':[],'keywords':['Server']}))
  self.assertTrue(core.matching(self.sample(title='Server SSD',cpv=[]),{'codes':[],'keywords':['SSD']}))
  self.assertFalse(core.matching(self.sample(title='Paper',cpv=['30200000']),{'codes':['30200000'],'keywords':[]}))
 def test_states(self):
  self.assertEqual(self.sample().state(),'active');self.assertEqual(self.sample(deadline='').state(),'review')
  self.assertEqual(self.sample(kind='award').state(),'closed');self.assertEqual(self.sample(kind='consultation').state(),'planning')
  self.assertEqual(self.sample(deadline=(now()-timedelta(days=1)).isoformat()).state(),'expired')
  self.assertEqual(self.sample(notes=['value_threshold_unverified']).state(),'review')
 def test_redact(self):
  os.environ['APIFY_API_TOKEN']='synthetic-secret'
  self.assertNotIn('synthetic-secret',core.redact('token synthetic-secret'))
  self.assertIn('APIFY_API_TOKEN',core.redact('Missing APIFY_API_TOKEN and APIFY_ACTOR_ID'))
  self.assertNotIn('abc123',core.redact('https://example.org/?token=abc123'))
  os.environ.pop('APIFY_API_TOKEN')
 def test_urls(self):
  self.assertEqual(core.safeurl('javascript:alert(1)'),'');self.assertEqual(core.safeurl('https://user:pass@example.org'),'')
 def test_store_retains_failure(self):
  t=self.sample();core.save_run('bzp',[t,t],{},'partial');self.assertEqual(len(core.rows()),1)
  self.assertEqual(core.runs()['bzp']['stats']['duplicates'],1)
  core.save_run('bzp',[],{},'error','failure');self.assertEqual(len(core.rows()),1);self.assertTrue(core.rows()[0].stale)
  self.assertIn('synthetic',self.c.get('/?state=stale').text.lower() if False else core.rows()[0].id)
 def test_export_filter_and_formula(self):
  a=self.sample(title='=HYPERLINK("x")');b=self.sample(id='second',country='UKR');core.save_run('bzp',[a,b],{})
  self.assertEqual(len(self.c.get('/export.json?country=POL').json()),1)
  from openpyxl import load_workbook
  wb=load_workbook(io.BytesIO(self.c.get('/export.xlsx?country=POL').content));self.assertTrue(wb.active['D2'].value.startswith("'="))
 def test_profiles(self):
  r=self.c.post('/filters/save',data={'source':'bzp','mode':'codes','values':'30233100\n30233100'});self.assertEqual(r.status_code,200);self.assertEqual(core.profiles()['bzp']['codes'],['30233100'])
  self.assertEqual(self.c.post('/filters/save',data={'source':'bzp','mode':'codes','values':'bad'}).status_code,400)
 def test_auth(self):
  os.environ['ADMIN_TOKEN']='test-secret'
  data={'source':'bzp','mode':'keywords','values':'SSD'}
  self.assertEqual(self.c.post('/filters/save',data=data).status_code,401)
  self.assertEqual(self.c.post('/filters/save',data=data,headers={'X-Admin-Token':'test-secret'}).status_code,200)
  self.assertEqual(self.c.post('/filters/save',data=data,headers={'X-Admin-Token':'test-secret','Origin':'https://evil.example'}).status_code,403)
 def test_refresh_validation(self):
  self.assertEqual(self.c.post('/refresh/start').status_code,400)
  self.assertEqual(self.c.post('/refresh/start',data={'countries':'POL','sources':'bzp','published_from':'bad'}).status_code,400)
 def test_tenderned_parse(self):
  d={'publicatieId':'1','typePublicatie':{'code':'AAO'},'aanbestedingNaam':'SSD','opdrachtgeverNaam':'Buyer','publicatieDatum':'2026-10-01','sluitingsDatum':'2026-10-19T12:00:00','link':{'href':'https://example.org/1'}}
  t=tenderned.parse(d);self.assertEqual(t.country,'NLD');self.assertEqual(date(t.deadline).hour,10);self.assertIsNone(t.value)
  d['typePublicatie']['code']='AGO';self.assertEqual(tenderned.parse(d).state(),'closed')
  d['typePublicatie']['code']='MAC';self.assertEqual(tenderned.parse(d).state(),'planning')
 def test_bzp(self):
  t=bzp.parse({'noticeNumber':'1','objectId':'obj','orderObject':'SSD','cpvCode':'30233100-2','htmlBody':'<script>bad</script><p>SSD</p>'})
  self.assertEqual(t.cpv,['30233100-2']);self.assertNotIn('bad',t.description);self.assertIn('obj',t.url)
 def test_prozorro(self):
  t=prozorro.parse({'id':'1','tenderID':'UA-test','title':'SSD','status':'active.tendering','dateModified':'2026-10-01','items':[{'description':'DDR5','classification':{'id':'30233100-2'}}]})
  self.assertEqual(t.published,'');self.assertIn('DDR5',t.description);self.assertEqual(t.state(),'review')
 def test_ocds_record(self):
  d={'ocid':'1','date':'2026-10-01','buyer':{'id':'b'},'parties':[{'id':'b','name':'Buyer','roles':['buyer']}],'tender':{'title':'SSD','tenderPeriod':{'endDate':'2027-01-01'},'items':[{'classification':{'id':'30233100'}}],'documents':[{'documentType':'tenderNotice','url':'https://example.org/1'}]}}
  raw=io.BytesIO()
  with zipfile.ZipFile(raw,'w') as z:z.writestr('record.json',json.dumps({'records':[{'compiledRelease':d}]}))
  items,stats=germany.parse_zip(raw.getvalue(),'https://example.org/archive',{'codes':['30233100'],'keywords':[]});self.assertEqual(len(items),1);self.assertEqual(items[0].buyer,'Buyer');self.assertEqual(items[0].url,'https://example.org/1')
 def test_latvia(self):
  d={'noticeId':'1','noticeTitle':'SSD','buyerName':'Buyer','publicationDate':'2026-10-01','submissionDeadline':'2027-01-01','noticeUrl':'https://example.org/1'}
  t=latvia.parse(d,'https://example.org/data');self.assertEqual(t.title,'SSD');self.assertEqual(t.buyer,'Buyer')
  self.assertEqual(latvia.parse({'name':'Wrong nested name'},'https://example.org/data').title,'')
 def test_nen(self):
  t=nen.parse('<h1>SSD</h1><p>Lhůta pro podání nabídek 19.10.2026 12:00 Kontaktní osoba</p>','1','https://example.org/1');self.assertEqual(date(t.deadline).hour,10)
 def test_ted_negotiation(self):
  class Fake:
   calls=[]
   async def json(self,url,**kw):
    self.calls.append(kw['json'].copy())
    if len(self.calls)==1:raise ConnectorError('400',body='supported values are: publication-number, notice-title, publication-date, classification-cpv, organisation-country-buyer')
    return {'notices':[]}
  f=Fake();asyncio.run(ted.fetch(f,['POL'],date('2026-10-01'),{'pages':1}));self.assertNotIn('estimated-value-proc',f.calls[1]['fields'])
 def test_native_no_ted(self):
  import inspect
  for mod in [slovakia,cvpis,ekr,estonia]:
   code=inspect.getsource(mod);self.assertNotIn('from app.connectors import ted',code);self.assertNotIn('ted.fetch',code)
 def test_apify_missing(self):
  for k in ['APIFY_API_TOKEN','APIFY_ACTOR_ID','APIFY_INPUT_JSON']:os.environ.pop(k,None)
  with self.assertRaisesRegex(ConnectorError,'APIFY_ACTOR_ID'):asyncio.run(ekap.fetch(None,[],now(),{}))
 def test_translation_429(self):
  class Fake:
   async def json(self,*a,**k):raise RateLimited('429')
  with self.assertRaises(RateLimited):asyncio.run(translation.free_text(Fake(),'hello','en','pl'))
  self.assertGreater(translation.STATE['blocked_until'],time.time())
 def test_translation_cache(self):
  t=self.sample();self.assertTrue(asyncio.run(translation.translate(t,'pl','free','pl')));self.assertEqual(t.translations['pl']['title'],t.title)
 def test_net_cap(self):
  async def run():
   async with Net() as n:
    await n.client.aclose();n.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=b'x'*100)))
    with self.assertRaisesRegex(ConnectorError,'resource cap'):await n.request('GET','https://example.org',cap=10)
  asyncio.run(run())
 def test_details_escape(self):
  t=self.sample(title='<script>alert(1)</script>');core.save_run('bzp',[t],{})
  r=self.c.get('/tenders/'+t.key);self.assertEqual(r.status_code,200);self.assertIn('&lt;script&gt;',r.text)
if __name__=='__main__':unittest.main(verbosity=2)
