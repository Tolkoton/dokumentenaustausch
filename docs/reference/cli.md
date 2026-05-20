# CLI reference

Invocation: `uv run python -m belegmeister <subcommand> [args]`.
Source: [`src/belegmeister/__main__.py`](../../src/belegmeister/__main__.py).

## `create-request`

Create a document-request against an existing DATEV Vorgangsmappe (VGM):
uploads the request letter into the binder and prints the Mandant-facing
magic-link URL.

```text
uv run python -m belegmeister create-request \
  --vgm-id <GUID> \
  --to <recipient-email> \
  [--cc <email>] \
  --subject <text> \
  --body-file <path> \
  [--questions-file <path>] \
  [--ttl-days <int>]
```

| Argument | Required | Default | Notes |
|---|---|---|---|
| `--vgm-id` | yes | — | VGM (binder) GUID. Must resolve to a binder whose extension is `VGM`. |
| `--to` | yes | — | Recipient email (the `To:` header on the request). |
| `--cc` | no | `""` | Cc email (optional). |
| `--subject` | yes | — | Email subject line. |
| `--body-file` | yes | — | Path to a UTF-8 text file with the letter body. |
| `--questions-file` | no | none | UTF-8 file with one question per line; blank lines skipped. Omit for zero questions. |
| `--ttl-days` | no | `7` | Magic-link lifetime in days. Hard-capped at 7. |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success; magic-link URL printed to stdout. |
| 1 | User-facing error (missing env var, invalid args, file not found, invalid upload target, upload failed). Message printed to stderr as `error: …`. |
| 2 | Unknown subcommand (unreachable under argparse). |

### Standard output

On success, exactly one line: the magic-link URL the Steuerbüro forwards to
the Mandant. Anything else (validation messages, exception trailers) goes to
stderr.

### Behavioural contract

- Argparse runs first, so `--help` / `-h` short-circuit before env validation.
- Env validation is fail-fast and shared with the web app entry points
  (see `src/belegmeister/env_validation.py`).
- Domain errors (`InvalidUploadTarget`, `UploadFailed`, validation errors)
  print `error: …` and exit `1`. Unknown exceptions surface as tracebacks —
  those are bugs.
