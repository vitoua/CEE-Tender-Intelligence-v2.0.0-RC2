import asyncio,json,time
from urllib.parse import urlsplit
import httpx
from app.core import redact
class ConnectorError(RuntimeError):
 def __init__(self,message,body=''):
  super().__init__(message);self.body=body
class RateLimited(ConnectorError):pass
class Net:
 def __init__(self):self.client=None;self.last={};self.requests=0
 async def __aenter__(self):
  self.client=httpx.AsyncClient(timeout=httpx.Timeout(35),follow_redirects=True,headers={'User-Agent':'GOODRAM-Tender-Intelligence/2.0 public-data-monitor'},limits=httpx.Limits(max_connections=6,max_keepalive_connections=4));return self
 async def __aexit__(self,*args):await self.client.aclose()
 async def request(self,method,url,cap=8_000_000,**kw):
  host=urlsplit(url).hostname
  for attempt in range(2):
   await asyncio.sleep(max(0,0.2-(time.monotonic()-self.last.get(host,0))));self.last[host]=time.monotonic()
   try:
    async with self.client.stream(method,url,**kw) as r:
     self.requests+=1
     if r.status_code==429:raise RateLimited('HTTP 429: source rate limited; no retry storm')
     if r.status_code>=500 and attempt==0:await asyncio.sleep(1);continue
     data=bytearray()
     async for chunk in r.aiter_bytes():
      if len(data)+len(chunk)>cap:raise ConnectorError('Response exceeds resource cap; scan incomplete')
      data.extend(chunk)
     response=httpx.Response(r.status_code,headers=r.headers,content=bytes(data),request=r.request)
     if response.status_code>=400:raise ConnectorError(redact(f'HTTP {response.status_code}: {response.text[:1000]}'),body=response.text[:200000])
     return response
   except (httpx.TimeoutException,httpx.NetworkError) as e:
    if attempt==1:raise ConnectorError(type(e).__name__+'; request failed') from None
  raise ConnectorError('Request failed')
 async def json(self,url,method='GET',**kw):return (await self.request(method,url,**kw)).json()
