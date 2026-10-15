import os,time,json,hashlib,asyncio,re
from app.core import connect,now,redact,update
from app.net import Net,RateLimited,ConnectorError
LOCK=asyncio.Lock();STATE={'translated':0,'failed':0,'blocked_until':0,'last_error':''}
LANG={'prozorro':'uk','bzp':'pl','germany':'de','latvia':'lv','nen':'cs','ekap':'tr','tenderned':'nl','slovakia':'sk','cvpis':'lt','ekr':'hu','estonia':'et'}
TERMS=re.compile(r'\b(?:SSD|NVMe|DRAM|DDR[345]|USB|NAS|SAN|PCIe|SATA|microSD)\b',re.I)
def chunks(s):
 out=[];part=''
 for ch in s:
  if len((part+ch).encode())>480:out.append(part);part=''
  part+=ch
 if part:out.append(part)
 return out
def status():
 with connect() as c:
  row=c.execute('SELECT used FROM quota WHERE day=?',(now().date().isoformat(),)).fetchone();count=c.execute('SELECT COUNT(*) FROM cache').fetchone()[0]
 return {**STATE,'daily_used':row[0] if row else 0,'daily_budget':5000,'cache_records':count,'azure_configured':bool(os.getenv('AZURE_TRANSLATOR_KEY')),'legacy_configured':bool(os.getenv('LIBRETRANSLATE_URL')),'notice':'Public text is sent to selected external provider; no quota bypass'}
async def free_text(net,text,source,target):
 if source==target:return text
 if time.time()<STATE['blocked_until']:raise RateLimited('Translation cooldown active')
 out=[]
 async def translate_piece(piece):
  if not piece.strip():return piece
  with connect() as c:
   day=now().date().isoformat();row=c.execute('SELECT used FROM quota WHERE day=?',(day,)).fetchone();used=row[0] if row else 0
   if used+len(piece)>5000:raise RateLimited('Local free daily budget reached; cached translations remain available')
   c.execute('INSERT OR REPLACE INTO quota VALUES (?,?)',(day,used+len(piece)))
  try:b=await net.json('https://api.mymemory.translated.net/get',params={'q':piece,'langpair':source+'|'+target})
  except RateLimited:STATE['blocked_until']=time.time()+3600;raise
  if int(b.get('responseStatus',0))!=200:
   if int(b.get('responseStatus',0)) in (403,429):STATE['blocked_until']=time.time()+3600
   raise ConnectorError(str(b.get('responseDetails') or 'Translation rejected')[:180])
  v=(b.get('responseData') or {}).get('translatedText')
  if not isinstance(v,str) or not v.strip() or 'MYMEMORY WARNING' in v.upper():raise ConnectorError('Invalid translation response')
  import html
  return html.unescape(v)
 pos=0
 for m in TERMS.finditer(text):
  for p in chunks(text[pos:m.start()]):out.append(await translate_piece(p))
  out.append(m.group());pos=m.end()
 for p in chunks(text[pos:]):out.append(await translate_piece(p))
 return ''.join(out)
async def translate(t,target,provider='free',source='auto'):
 async with LOCK:
  try:
   if target not in ('pl','uk','en','es'):raise ConnectorError('Unsupported target language')
   if source=='auto':
    if t.provenance=='TED fallback':raise ConnectorError('Select actual source language for multilingual TED fallback notices')
    source=LANG.get(t.source,'')
    if not source:raise ConnectorError('Select actual source language for multilingual TED notices')
   key=hashlib.sha256(json.dumps([provider,source,target,t.title,t.description],ensure_ascii=False).encode()).hexdigest()
   with connect() as c:row=c.execute('SELECT value FROM cache WHERE key=?',(key,)).fetchone()
   if row:rec=json.loads(row[0])
   else:
    async with Net() as net:
     texts=[t.title,t.description[:6000]]
     if provider=='free':values=[await free_text(net,s,source,target) for s in texts]
     elif provider=='azure':
      if not os.getenv('AZURE_TRANSLATOR_KEY'):raise ConnectorError('Missing AZURE_TRANSLATOR_KEY')
      b=await net.json('https://api.cognitive.microsofttranslator.com/translate',method='POST',params={'api-version':'3.0','to':target,'from':source},headers={'Ocp-Apim-Subscription-Key':os.environ['AZURE_TRANSLATOR_KEY'],'Ocp-Apim-Subscription-Region':os.getenv('AZURE_TRANSLATOR_REGION','')},json=[{'text':s} for s in texts]);values=[x['translations'][0]['text'] for x in b]
     elif provider=='legacy':
      url=os.getenv('LIBRETRANSLATE_URL','')
      if not url.startswith('https://'):raise ConnectorError('Configure HTTPS LIBRETRANSLATE_URL')
      values=[]
      for s in texts:
       b=await net.json(url.rstrip('/')+'/translate',method='POST',json={'q':s,'source':source,'target':target,'format':'text','api_key':os.getenv('LIBRETRANSLATE_API_KEY','')});values.append(b['translatedText'])
     else:raise ConnectorError('Unknown translation provider')
    rec={'title':values[0],'description':values[1]}
    with connect() as c:c.execute('INSERT OR REPLACE INTO cache VALUES (?,?)',(key,json.dumps(rec,ensure_ascii=False)))
   t.translations[target]=rec;update(t);STATE['translated']+=1;STATE['last_error']='';return True
  except Exception as e:STATE['failed']+=1;STATE['last_error']=redact(e)[:400];return False
