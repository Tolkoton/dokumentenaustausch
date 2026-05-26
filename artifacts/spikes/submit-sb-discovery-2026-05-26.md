# Spike #2 — SB discovery of Mandant-uploaded docs (A4 verification)

- **Date:** 2026-05-26
- **VGM:** 395357 (binder GUID `4c83e94e-24e7-4866-809c-5e983ad7f485`)
- **SB login:** _<FILL_USER>_
- **Owner-driven.** ~5 min. Visual check inside DATEV-UO.

## Premise under test

**A4** — *"SB sees Mandant-uploaded files in DATEV-UO without any
notification mechanism."*

If CONFIRMED → submit-slice does not need to build a notification channel.
If FALSIFIED → an alerting mechanism (in-app, email, push) is a prerequisite
to shipping the client loop; significant scope change.

## Uploaded by spike #1 (`submit-multi-file-upload-2026-05-26.json`)

- `_spike_pdf_20260526T093302Z.pdf` — 7.2 MB, document_file_id=1164718, structure_item_id=1185687
- `_spike_jpg_20260526T093302Z.jpg` — 5.8 MB, document_file_id=1164719, structure_item_id=1185688

Both already accepted by klardaten (HTTP 200), confirmed by JSON in the
spike #1 artifact.

## Procedure

1. Log into DATEV Unternehmen Online as the SB (Steuerbüro) user.
2. Navigate to VGM #395357 in the client's binder list.
3. Inspect the binder's contents for the two spike files above.
4. Independently — without searching for the filenames — check whether any
   surface (bell badge, notification panel, email inbox, push to mobile)
   indicated the new attachments before you saw them in the binder.

## Observations (fill in)

- Both spike files visible in VGM contents: _<yes/no>_
- Notification received without searching: _<yes/no — describe surface>_
- Location within VGM hierarchy: _<root / register name / subfolder>_
- UX notes: _<anything surprising about how new attachments present>_

## A4 verdict

_<CONFIRMED / FALSIFIED / PARTIAL>_

## Implications

- **CONFIRMED →** "no email to SB" assumption stays. Submit-slice does not
  need a notification mechanism. The SB user's existing DATEV-UO workflow
  is the channel.
- **FALSIFIED →** notification is a prerequisite. Either fold into the
  submit-slice (large scope inflation) or insert a dedicated notification
  slice between token-instance-binding and submit-handler.
- **PARTIAL →** owner must specify which surface satisfies the SB workflow
  and whether building a substitute is in scope.
