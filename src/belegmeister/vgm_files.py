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
    """Build the request-letter filename for a given ISO-8601 UTC stamp.

    The single producer is
    ``belegmeister.cli.create_request.run_create_request`` (writes the
    file into the Vorgangsmappe via klardaten ``POST /document-files`` +
    ``POST /documents/{binder}/structure-items``); the single consumer
    is ``belegmeister.web.request_view._pick_newest_letter`` (filters
    the VGM's children to find this slice's letter). Routing both
    through this helper means a rename of the prefix or extension is a
    one-line change with no risk of a writer/reader split.

    Args:
        iso: An ISO-8601 UTC timestamp string (the producer uses
            ``"%Y-%m-%dT%H%M%SZ"`` to keep the filename portable across
            Windows file systems — no colons). Passed through verbatim;
            no validation here. A monotonic stamp gives lexicographic
            sort = chronological sort, which is how the reader picks the
            newest letter inside a binder.

    Returns:
        ``"_request_letter_<iso>.txt"`` — the full filename to write into
        the VGM. ``.txt`` (not ``.md``) so the SB on Windows can open it
        in Notepad with zero admin; the body is plain wire-format text
        regardless of extension.
    """
    return f"{REQUEST_LETTER_PREFIX}{iso}{REQUEST_LETTER_SUFFIX}"
