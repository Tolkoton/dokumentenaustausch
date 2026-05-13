# DATEV Developer Portal — docs pack for Claude Code

This pack gives Claude Code everything it needs to work productively against
the DATEV developer portal (<https://developer.datev.de>).

## Contents

| File                          | What it is                                                                 |
| ----------------------------- | -------------------------------------------------------------------------- |
| `DATEV-DEVELOPER-PORTAL.md`   | Hand-curated index + concept reference. Read this first.                  |
| `scrape-datev-docs.py`        | Playwright scraper that pulls the full rendered content into `./datev-scraped/*.md`. |
| `README.md`                   | This file.                                                                 |

## Why Markdown and not PDF?

For Claude Code (or any LLM context), Markdown wins:

- **Cheaper context** — no PDF parsing overhead, no extracted-text artifacts.
- **`grep`-able and `rg`-able** from the terminal.
- **Splittable** — multiple small `.md` files load into context selectively;
  a single 200-page PDF doesn't.
- **Diffable** — store the scrape in git and review changes between runs.

If you still want a PDF at the end, convert with one command:

```bash
pandoc DATEV-DEVELOPER-PORTAL.md -o DATEV-DEVELOPER-PORTAL.pdf
# or, for the whole scraped folder:
pandoc datev-scraped/*.md -o datev-full.pdf
```

## How to refresh against the live site

The portal is a JavaScript SPA — a plain `curl` returns an empty shell. The
included Playwright scraper drives a real headless Chromium and waits for the
SPA to render before dumping each page.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install playwright html2text
python -m playwright install chromium

python scrape-datev-docs.py          # seed list only (~33 pages)
python scrape-datev-docs.py --crawl  # also follow in-portal links (slower)
```

Output lands in `./datev-scraped/`:

- one `.md` per page
- an `index.json` mapping URL → filename → byte count

## How to use this with Claude Code

Drop the whole folder into your project (e.g. `docs/datev/`) and reference it:

```bash
claude --add-dir docs/datev
```

Or, in a `CLAUDE.md`, point at the index:

```md
## DATEV integration notes
Read `docs/datev/DATEV-DEVELOPER-PORTAL.md` for the portal map and the
canonical batch-import workflow before writing any DATEV client code.
The full scraped reference lives under `docs/datev/datev-scraped/`.
```

## Caveats

- The seed URL list in the scraper reflects the product catalog at the time
  this pack was generated. New products will not appear unless you re-run with
  `--crawl` or extend `seed_urls()` in the script.
- Production access to DATEV APIs requires a multi-step approval. The docs
  alone won't get you there — see §7 of `DATEV-DEVELOPER-PORTAL.md`.
- Don't lower the 1.5 s scraper delay; the portal sits behind a CDN that will
  rate-limit you.
