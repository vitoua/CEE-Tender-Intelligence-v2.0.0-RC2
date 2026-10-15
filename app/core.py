import os,re,json,hashlib,sqlite3,threading
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from dataclasses import dataclass,field,asdict
VERSION='2.0.0-RC2'
BUILD='v200-native-rc2'
DATA=Path(os.getenv('DATA_DIR','data'));DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'tenders.sqlite3'
LOCK=threading.RLock()
def now():return datetime.now(timezone.utc)
def clean(v):return ' '.join(str(v or '').split())
def date(v,zone='UTC'):
 if isinstance(v,datetime):d=v
 else:
  s=clean(v)
  if not s:return None
  if re.fullmatch(r'\d{8}',s):s=s[:4]+'-'+s[4:6]+'-'+s[6:]
  try:d=datetime.fromisoformat(s.replace('Z','+00:00'))
  except ValueError:
   d=None
   for fmt in ('%d.%m.%Y %H:%M','%d/%m/%Y %H:%M','%d.%m.%Y','%Y.%m.%d. %H:%M'):
    try:d=datetime.strptime(s,fmt);break
    except ValueError:pass
   if d is None:
    m=re.search(r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})',s)
    if m:
     try:d=datetime(int(m[3]),int(m[2]),int(m[1]),int(m[4]),int(m[5]))
     except ValueError:return None
    else:return None
 if not d.tzinfo:d=d.replace(tzinfo=ZoneInfo(zone))
 return d.astimezone(timezone.utc)
def iso(v,zone='UTC'):
 d=date(v,zone);return d.isoformat() if d else ''
def safeurl(v):
 from urllib.parse import urlsplit
 s=clean(v)
 try:p=urlsplit(s)
 except ValueError:return ''
 return s if p.scheme in ('https','http') and p.hostname and not p.username else ''
def redact(v):
 s=str(v)
 for k in ('APIFY_API_TOKEN','ADMIN_TOKEN','AZURE_TRANSLATOR_KEY','LIBRETRANSLATE_API_KEY'):
  x=os.getenv(k,'')
  if x:s=s.replace(x,'[REDACTED]')
 s=re.sub(r'apify_api_[A-Za-z0-9_-]+','[REDACTED]',s)
 s=re.sub(r'(?i)([?&](?:token|api_key|apikey)=)[^&\s\"\']+',r'\1[REDACTED]',s)
 return re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9_.-]+',r'\1[REDACTED]',s)
def init():
 with connect() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS tenders(key TEXT PRIMARY KEY,source TEXT,country TEXT,state TEXT,payload TEXT,seen TEXT);
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT,status TEXT,stats TEXT,error TEXT,created TEXT);
CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS quota(day TEXT PRIMARY KEY,used INTEGER);
''')
def connect():
 c=sqlite3.connect(DB,timeout=20);c.execute('PRAGMA journal_mode=WAL');return c
@dataclass
class Tender:
 id:str;source:str;country:str;title:str;buyer:str='';published:str='';deadline:str='';value:float|None=None;currency:str='';url:str='';description:str='';cpv:list=field(default_factory=list);kind:str='contract';portal_status:str='';provenance:str='direct';notes:list=field(default_factory=list);matches:list=field(default_factory=list);translations:dict=field(default_factory=dict);links:dict=field(default_factory=dict);stale:bool=False
 @property
 def key(self):return hashlib.sha256((self.source+'\0'+self.id).encode()).hexdigest()[:24]
 def state(self):
  if self.kind in ('award','cancelled','completed'):return 'closed'
  if self.kind in ('consultation','prior'):return 'planning'
  ddl=date(self.deadline)
  if ddl and ddl<=now():return 'expired'
  if 'value_threshold_unverified' in self.notes or any(n.startswith('Date-only deadline:') for n in self.notes):return 'review'
  if self.kind not in ('contract','correction') or not ddl or not self.buyer or not self.published or not safeurl(self.url):return 'review'
  return 'active'
 def title_for(self,lang):return self.translations.get(lang,{}).get('title') or self.title
 def desc_for(self,lang):return self.translations.get(lang,{}).get('description') or self.description
 def to_dict(self):return asdict(self)
def profiles():
 with connect() as c:row=c.execute("SELECT value FROM config WHERE key='profiles'").fetchone()
 return json.loads(row[0]) if row else json.loads(Path('data/profiles.json').read_text())
def save_profiles(p):
 with connect() as c:c.execute('INSERT OR REPLACE INTO config VALUES (?,?)',('profiles',json.dumps(p,ensure_ascii=False)))
def matching(t,profile=None):
 f=profile or profiles().get(t.source,profiles()['ted']);text=(t.title+' '+t.description).casefold().replace('’',"'")
 words=[x for x in f['keywords'] if re.search(r'(?<!\w)'+re.escape(x.casefold().replace('’',"'"))+r'(?!\w)',text)]
 codes={re.sub(r'\D','',str(x))[:8] for x in t.cpv};broad={'30200000','30210000','30230000','30236000','30237000','32420000'}
 exact=[x for x in f['codes'] if x in codes and x not in broad]
 return ['keyword:'+x for x in words]+['cpv:'+x for x in exact]
def save_run(source,items,stats,status='partial',error=''):
 counts={};dups=0;seen=set()
 with LOCK,connect() as c:
  # Failed or incomplete scans never delete the last successful snapshot.
  c.execute("UPDATE tenders SET payload=json_set(payload,'$.stale',json('true')) WHERE source=?",(source,))
  for t in items:
   if not t.id or not t.title:continue
   if t.key in seen:dups+=1;continue
   seen.add(t.key);t.url=safeurl(t.url);t.stale=False
   t.notes=list(dict.fromkeys(t.notes+[k+' missing' for k in ('buyer','published','deadline','url') if not getattr(t,k)]))
   state=t.state();counts[state]=counts.get(state,0)+1
   old=c.execute('SELECT payload FROM tenders WHERE key=?',(t.key,)).fetchone()
   if old:t.translations=json.loads(old[0]).get('translations',{}) if json.loads(old[0]).get('title')==t.title and json.loads(old[0]).get('description')==t.description else {}
   c.execute('INSERT OR REPLACE INTO tenders VALUES (?,?,?,?,?,?)',(t.key,source,t.country,state,json.dumps(t.to_dict(),ensure_ascii=False),now().isoformat()))
  stats={**stats,'stored':counts,'duplicates':dups,'snapshot_policy':'unseen records retained as stale'}
  c.execute('INSERT INTO runs(source,status,stats,error,created) VALUES (?,?,?,?,?)',(source,status,json.dumps(stats,ensure_ascii=False),redact(error)[:1200],now().isoformat()))
  c.execute('DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY id DESC LIMIT 240)')
def rows():
 with connect() as c:data=c.execute('SELECT payload FROM tenders').fetchall()
 return [Tender(**json.loads(x[0])) for x in data]
def runs():
 with connect() as c:data=c.execute('SELECT source,status,stats,error,created FROM runs ORDER BY id DESC LIMIT 120').fetchall()
 out={}
 for s,status,stats,error,created in data:
  if s not in out:out[s]={'source':s,'status':status,'stats':json.loads(stats),'error':error,'created':created}
 return out
def update(t):
 with connect() as c:c.execute('UPDATE tenders SET payload=? WHERE key=?',(json.dumps(t.to_dict(),ensure_ascii=False),t.key))
init()
