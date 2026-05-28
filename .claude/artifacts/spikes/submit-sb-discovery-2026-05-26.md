# Spike #2 — SB discovery of Mandant-uploaded docs (A4 verification)

**Date**: 2026-05-26
**VGM**: #395357 (binder GUID 4c83e94e-24e7-4866-809c-5e983ad7f485)
**Verification method**: Colleague-eyeball (owner lacks direct DATEV-UO access)

**Uploaded files visible in VGM**:
- Confirmed by SB-equivalent colleague: files ARE present in VGM contents
- Includes spike #1 PDF + JPG, today's request letters, token-binding smoke letters, size envelope probe blobs
- Colleague able to navigate to VGM by Dokumentnummer 395357 and see contents

**Notification observed**: NONE reported by colleague — files appear in VGM contents without any push/badge/email alert

**A4 verdict**: ✅ CONFIRMED

**Implications**:
- "no email to SB" stays rejected; submit-handler slice does NOT need notification mechanism
- SB workflow assumes periodic check of active VGMs; this is the existing MVP-acceptable pattern
- Future enhancement (post-MVP): notification channel as a separate optional slice if SBs report friction

**Caveats**:
- Verified via colleague proxy, not direct owner observation
- Detailed UX observations (refresh requirements, filter behavior, hierarchy display) deferred — out of scope for binary A4 verdict
