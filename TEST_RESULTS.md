# RC2 validation report

## Executed checks
- 26 base unittest methods: PASS.
- 14 native parser / discovery / mocked HTTP workflow methods: PASS.
- 2 native Chromium workflow methods: PASS.
- Total: 42 unittest methods passed. Browser methods use intercepted synthetic pages, not live portals.
- RC2 UI browser check: desktop 1440px and mobile 390px; 12 source controls; profile save succeeded; no JavaScript page errors; no mobile horizontal overflow.
- Python compilation: PASS.

## Native coverage tested
Slovakia: public detail-link discovery; exact field labels; Slovak date/time; CPV; mocked list-to-detail retrieval without TED.
Lithuania: current opportunities resourceId discovery; public detail labels; buyer; explicit EUR amount; publication/deadline; EET/EEST date parsing; mocked list-to-detail retrieval without TED.
Hungary: native table row/ID/type/buyer/deadline parsing; award separation; rendered browser list and detail enrichment against intercepted fixtures.
Estonia: native procurement link discovery; same-document hash navigation in Chromium; general-info field extraction; explicit currency; missing-field review; external-host rejection; rendered list-to-detail workflow against intercepted fixtures.
All four source modules checked for absence of TED imports/calls.

## Live evidence and limitations
Direct HTTP probes from the build environment returned HTTP 403 for the four national portal URLs. This does not establish whether Render is blocked. The web retrieval tool read official Slovak list/detail/EVO pages, Lithuanian current-opportunities/detail pages and the Hungarian public notice table. It did not provide raw HTML for an end-to-end run of these adapters.
Estonian rendered search/detail selectors and labels remain unverified on the live site. The official register homepage was readable, but hash navigation through the web retrieval tool returned the homepage. No invented API endpoints were added to compensate.

NOT executed: Docker image build; clean installation of pinned dependencies and Chromium; Render deployment; full live pagination/search validation; populated real-data UI review; memory/load test on Render Free. Tests ran with preinstalled dependencies and an existing Chromium executable.

Synthetic fixtures are isolated in temporary databases. No synthetic tenders or runtime databases are shipped. Screenshots show the empty initial RC2 interface, not successful live collection.
