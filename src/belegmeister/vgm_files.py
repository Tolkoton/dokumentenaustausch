"""VGM file-naming conventions — the single source of truth for how
files inside a DATEV Vorgangsmappe are named.

Boundary policy (STRICT — keep this module thematic, not a junk drawer):

- Only names that are CROSS-MODULE shared or an EXTERNAL contract belong
  here. Litmus test: would changing the value break 2+ modules? Yes →
  here. No → keep it local to its module.
- The `==BELEGMEISTER==` sentinel / wire-format markers do NOT belong
  here — the codec (`request_format`) conceptually owns them; that is
  their correct home. Do not centralise for centralisation's sake.
- This is a naming/filename module, not a project-wide `constants.py`.
- No speculative entries. The `beantwortete_fragen_` prefix is added
  when the submit slice actually touches it — not before.

Current shared contract: the request-letter filename, written by
`cli.create_request.run_create_request` and matched by the client
handler's filter in `web.request_view._pick_newest_letter`. `.txt`
(not `.md`): SB machines are Windows and open `.txt` in Notepad with
zero admin; `.md` has no configured viewer. The content is plain
wire-format text either way — the extension was never semantic.
See CLAUDE.md "Single source of truth for cross-layer logic".
"""

from __future__ import annotations

REQUEST_LETTER_PREFIX = "_request_letter_"
REQUEST_LETTER_SUFFIX = ".txt"


def request_letter_filename(iso: str) -> str:
    """Full request-letter filename for an ISO-8601 UTC stamp. Both the
    writer and the reader's filter derive from this one place, so they
    can never diverge."""
    return f"{REQUEST_LETTER_PREFIX}{iso}{REQUEST_LETTER_SUFFIX}"
