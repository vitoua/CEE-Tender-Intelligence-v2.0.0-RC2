import asyncio,importlib,os
from collections import Counter
from app.core import now,date,matching,profiles,save_run,redact
from app.net import Net,RateLimited
from app.registry import SOURCES
JOB={'running':False,'progress':0,'message':'Idle','started':'','finished':''};TASK=None
LIMITS={'pages':3,'prozorro_pages':8,'bzp_pages':2,'days':7,'details':30}
async def execute(countries,sources,start,min_eur):
 JOB.update(running=True,progress=0,message='Starting',started=now().isoformat(),finished='')
 try:
  plan=[s for s in sources if s in SOURCES and (SOURCES[s][1] in countries or (s=='ted' and any(c not in ('UKR','TUR') for c in countries)))]
  for i,s in enumerate(plan):
   JOB.update(progress=round(i/max(1,len(plan))*100),message='Loading '+s)
   try:
    async with Net() as net:
     mod=importlib.import_module('app.connectors.'+s);scope=[c for c in countries if c not in ('UKR','TUR')] if s=='ted' else [SOURCES[s][1]]
     items,stats=await asyncio.wait_for(mod.fetch(net,scope,start,LIMITS),180)
    kept=[];reject=Counter();f=profiles().get(s,profiles()['ted'])
    for t in items:
     if t.country not in countries:reject['country']+=1;continue
     if t.published and date(t.published)<start:reject['before_publication_date']+=1;continue
     t.matches=matching(t,f)
     if not t.matches:reject['not_relevant']+=1;continue
     if min_eur>0:
      if t.currency!='EUR' or t.value is None:
       t.notes.append('EUR threshold cannot be verified; no automatic FX conversion')
       # Unknown EUR amounts stay visible for review, not silently dropped.
       t.notes.append('value_threshold_unverified')
      elif t.value<min_eur:reject['below_minimum_eur']+=1;continue
     kept.append(t)
    stats.update(rejected=dict(reject),received=len(items),requests=net.requests)
    status='partial'
    if s in ('latvia','germany') and not stats.get('files',stats.get('days',0)):status='error'
    if s in ('slovakia','cvpis','ekr','estonia'):
     stats['native_only']=True
     if not items and stats.get('details_failed'):status='schema_error'
     if stats.get('requested_period_not_reached'):status='stale_source'
    save_run(s,kept,stats,status)
   except Exception as e:
    status='rate_limited' if isinstance(e,RateLimited) else ('configuration_required' if 'Missing configuration:' in str(e) else ('access_blocked' if '403' in str(e) or 'access_challenge' in str(e) else ('browser_required' if 'browser_' in str(e) else ('login_required' if 'login_required' in str(e) else ('discovery_failed' if 'discovery_failed' in str(e) else 'error')))))
    save_run(s,[],{'coverage':'scan failed; previous snapshot retained as stale'},status,redact(e))
   JOB.update(progress=round((i+1)/max(1,len(plan))*100))
  JOB.update(message='Complete: check source coverage and review counts')
 except Exception as e:JOB.update(message='Refresh failed: '+redact(e)[:300])
 finally:JOB.update(running=False,finished=now().isoformat())
