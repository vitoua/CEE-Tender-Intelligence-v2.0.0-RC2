import re,json
from bs4 import BeautifulSoup
from app.core import clean,date,iso,safeurl,Tender
from defusedxml import ElementTree as ET
def text(html,limit=100000):
 soup=BeautifulSoup(html[:limit],'html.parser')
 for x in soup(['script','style','nav','footer']):x.decompose()
 return clean(soup.get_text(' ',strip=True))
def scalar(v):
 if isinstance(v,str):return v
 if isinstance(v,(int,float)):return str(v)
 if isinstance(v,list):return scalar(v[0]) if v else ''
 if isinstance(v,dict):
  for k in ('eng','en','pol','pl','deu','de','lav','lv','nld','nl','value','name'):
   if v.get(k):return scalar(v[k])
  return scalar(next(iter(v.values()),''))
 return ''
def cpvs(v):return list(dict.fromkeys(re.findall(r'\b\d{8}(?:-\d)?\b',str(v))))
def number(v):
 try:return float(v)
 except (ValueError,TypeError):return None
def ocds(d,source,country,url=''):
 t=d.get('tender') or {};buyer=d.get('buyer') or {};bid=buyer.get('id')
 if not buyer.get('name'):
  buyer=next((p for p in d.get('parties',[]) if p.get('id')==bid or 'buyer' in p.get('roles',[])),buyer)
 codes=[]
 for i in t.get('items') or []:
  codes+=cpvs((i.get('classification') or {}).get('id',''))
  for c in i.get('additionalClassifications') or []:
   if c.get('scheme')=='CPV':codes+=cpvs(c.get('id'))
 period=t.get('tenderPeriod') or {};val=t.get('value') or {};docs=t.get('documents') or []
 direct=safeurl(d.get('url')) or next((safeurl(x.get('url')) for x in docs if x.get('documentType') in ('tenderNotice','biddingDocuments') and safeurl(x.get('url'))),'')
 state=t.get('status','');kind='cancelled' if state in ('cancelled','unsuccessful') else ('award' if state in ('complete','awarded') else 'contract')
 result=Tender(str(d.get('ocid') or d.get('id') or ''),source,country,clean(t.get('title')),clean(buyer.get('name')),iso(d.get('date')),iso(period.get('endDate')),number(val.get('amount')),val.get('currency',''),direct,clean(t.get('description')),list(dict.fromkeys(codes)),kind,state,links={'dataset':url} if url else {})
 if period.get('endDate') and len(str(period['endDate']))<=10:result.notes.append('Date-only deadline: '+str(period['endDate']))
 return result
def xml_notice(raw,source,country,url):
 root=ET.fromstring(raw)
 def local(x):return x.tag.split('}')[-1]
 def vals(name):return [clean(x.text) for x in root.iter() if local(x)==name and clean(x.text)]
 def first(name):return next(iter(vals(name)),'')
 title=first('Title');buyer=''
 for x in root.iter():
  if local(x)=='ContractingParty':
   buyer=next((clean(y.text) for y in x.iter() if local(y)=='Name' and clean(y.text)),'');break
 ddl=''
 for x in root.iter():
  if local(x)=='TenderSubmissionDeadlinePeriod':
   day=next((clean(y.text) for y in x if local(y)=='EndDate'),'');tm=next((clean(y.text) for y in x if local(y)=='EndTime'),'')
   ddl=iso(day+'T'+tm if day and tm else day);break
 return Tender(first('ID'),source,country,title,buyer,iso(first('IssueDate')),ddl,url='',description=' '.join(vals('Description')),cpv=cpvs(vals('ItemClassificationCode')),links={'dataset':url})
