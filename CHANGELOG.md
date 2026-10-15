# 2.0.0-RC2 native adapters
Full standalone package based on RC1; no patches/overlay.
Replaced all four TED fallback modules with native public-portal adapters: Slovakia UVO/EVO; Lithuania new CVP IS; Hungary EKR; Estonia RHR. No imports/calls to TED from these modules. Added public-page browser helper, Chromium Docker installation, portal-specific date parsing, native diagnostics, source metadata, local-language keywords and 16 additional tests (14 parser/workflow + 2 browser fixtures). Preserved TenderNed, UI, exports, analytics, filters, storage and translation.

These are beta implementations, not live-certified repairs. Native requests from the build environment returned HTTP 403. EKR modal detail parsing, RHR exact live labels, dynamic pagination and completeness remain unverified. See README_UA.md and TEST_RESULTS.md.
