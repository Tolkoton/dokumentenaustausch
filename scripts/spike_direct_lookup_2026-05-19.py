"""SPIKE (2026-05-19): does DATEVconnect DMS v2 (via klardaten) expose ANY
usable direct-lookup-by-number, so the O(n) pagination scan in
`belegmeister.datev.resolver` can be replaced?

Single responsibility: ANSWER THAT ONE QUESTION LIVE. This script does NOT
implement a resolver and does NOT pre-commit to an approach. Read-only —
GETs only, no DMS state mutated.

Gate per Step 0: the truth source is real klardaten responses + timings,
NOT TestClient/pytest.

Discriminator
-------------
An ignored unknown query param is indistinguishable from "no filter" when you
only query an EXISTING number (both return a full page). So the decisive
signal is a definitely-ABSENT number:

  * filter WORKS   -> absent-query returns 0 items
  * filter IGNORED -> absent-query returns a full (~cap) page of unrelated docs

Cross-checked against a KNOWN number discovered live this run (not the stale
hardcoded GUID from the schema memory).

Usage
-----
    uv run python scripts/spike_direct_lookup_2026-05-19.py
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import httpx
from dotenv import load_dotenv

DVC = "/datevconnect/dms/v2"
CAP = 50  # small page cap: absent-vs-nonempty contrast holds regardless of size
ABSENT_NUMBER = 999_999_999  # assumed not to exist; asserted != known below


def _client(api_key: str, instance_id: str, profile_id: str | None) -> httpx.Client:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "x-client-instance-id": instance_id,
        "Accept": "application/json",
    }
    if profile_id is not None:
        headers["x-profile-id"] = profile_id
    return httpx.Client(headers=headers, timeout=30.0)


def _get(client: httpx.Client, base: str, path: str) -> tuple[int, Any, float]:
    """GET path, return (status, parsed-body-or-text-or-None, seconds)."""
    url = f"{base.rstrip('/')}{path}"
    t0 = time.perf_counter()
    try:
        r = client.get(url)
    except httpx.HTTPError as exc:
        return -1, f"transport error: {exc!s}", time.perf_counter() - t0
    dt = time.perf_counter() - t0
    if not r.content:
        return r.status_code, None, dt
    if "application/json" in r.headers.get("content-type", ""):
        try:
            return r.status_code, r.json(), dt
        except ValueError:
            return r.status_code, r.text[:500], dt
    return r.status_code, r.text[:500], dt


def _items(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if isinstance(body, dict):
        for k in ("value", "items", "documents", "Documents", "Value"):
            v = body.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def _has_number(items: list[dict[str, Any]], number: int) -> bool:
    return any(it.get("number") == number for it in items)


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("KLARDATEN_API_KEY")
    instance_id = os.environ.get("KLARDATEN_INSTANCE_ID")
    base = os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com")
    profile_id = os.environ.get("KLARDATEN_PROFILE_ID") or None
    missing = [
        n
        for n, v in (
            ("KLARDATEN_API_KEY", api_key),
            ("KLARDATEN_INSTANCE_ID", instance_id),
        )
        if not v
    ]
    if missing:
        print(f"FAIL: missing env vars: {', '.join(missing)}")
        return 2
    assert api_key and instance_id

    with _client(api_key, instance_id, profile_id) as c:
        # --- ground truth: discover a real number/guid live -------------------
        st, body, dt = _get(c, base, f"{DVC}/documents?$top=1")
        first = _items(body)
        if st != 200 or not first:
            print(f"FAIL: baseline list returned status={st}, items={len(first)}")
            print(f"  body excerpt: {str(body)[:300]}")
            return 1
        known_number = first[0].get("number")
        known_guid = first[0].get("id")
        if not isinstance(known_number, int):
            print(f"FAIL: first doc has no int 'number': {first[0]!r}")
            return 1
        assert known_number != ABSENT_NUMBER, "pick a different ABSENT_NUMBER"
        print(f"ground truth: known number={known_number} guid={known_guid}")
        print(f"  ({dt:.2f}s for $top=1)")

        # baseline unfiltered page (timing + size reference)
        st_b, body_b, dt_b = _get(c, base, f"{DVC}/documents?$top={CAP}")
        base_n = len(_items(body_b))
        print(f"baseline $top={CAP}: status={st_b} items={base_n} {dt_b:.2f}s\n")

        # --- candidate direct-lookup forms -----------------------------------
        # query-string forms: probed twice (known number, then absent number)
        q_forms: list[tuple[str, str]] = [
            ("odata_lc", f"{DVC}/documents?$top={CAP}&$filter=number eq {{n}}"),
            ("odata_uc", f"{DVC}/documents?$top={CAP}&$filter=Number eq {{n}}"),
            ("odata_q", f"{DVC}/documents?$top={CAP}&$filter=number eq '{{n}}'"),
            ("number", f"{DVC}/documents?$top={CAP}&number={{n}}"),
            ("document-number", f"{DVC}/documents?$top={CAP}&document-number={{n}}"),
            ("documentNumber", f"{DVC}/documents?$top={CAP}&documentNumber={{n}}"),
        ]
        # path-based forms: single probe each (existence of the route is enough)
        p_forms: list[tuple[str, str]] = [
            ("path_by-number", f"{DVC}/documents/by-number/{{n}}"),
            ("path_number", f"{DVC}/documents/number/{{n}}"),
        ]

        verdict_lines: list[str] = []
        usable_found = False

        print("=" * 72)
        print("QUERY-STRING FORMS  (decisive signal: absent-number result)")
        print("=" * 72)
        for name, tmpl in q_forms:
            sk, bk, tk = _get(c, base, tmpl.format(n=known_number))
            sa, ba, ta = _get(c, base, tmpl.format(n=ABSENT_NUMBER))
            ik, ia = _items(bk), _items(ba)
            n_k, n_a = len(ik), len(ia)
            has_known = _has_number(ik, known_number)
            # WORKS: known-query returns a SMALL set containing the known doc,
            # AND absent-query returns EMPTY. IGNORED: absent-query non-empty.
            works = (n_a == 0) and has_known and (0 < n_k < base_n or n_k == 1)
            tag = "WORKS" if works else ("IGNORED" if n_a > 0 else "INCONCLUSIVE")
            if works:
                usable_found = True
            line = (
                f"  {name:<16} known: st={sk} n={n_k} hasKnown={has_known} "
                f"{tk:.2f}s | absent: st={sa} n={n_a} {ta:.2f}s -> {tag}"
            )
            print(line)
            verdict_lines.append(line)

        print("\n" + "=" * 72)
        print("PATH FORMS  (404 = route absent; 200 with the doc = direct lookup)")
        print("=" * 72)
        for name, tmpl in p_forms:
            sk, bk, tk = _get(c, base, tmpl.format(n=known_number))
            sa, ba, ta = _get(c, base, tmpl.format(n=ABSENT_NUMBER))
            single_ok = (
                sk == 200 and isinstance(bk, dict) and bk.get("number") == known_number
            )
            tag = "WORKS" if single_ok else "ABSENT"
            if single_ok:
                usable_found = True
            line = (
                f"  {name:<16} known: st={sk} {tk:.2f}s | "
                f"absent: st={sa} {ta:.2f}s -> {tag}"
            )
            print(line)
            verdict_lines.append(line)

        print("\n" + "=" * 72)
        print("SPIKE VERDICT")
        print("=" * 72)
        if usable_found:
            print("  USABLE DIRECT LOOKUP EXISTS -> recommend O(1) direct lookup.")
            print("  (see the WORKS row above for the exact form)")
        else:
            print("  NO usable direct-lookup-by-number. Every filter form is")
            print("  ignored (absent-number query returns a full page) or the")
            print("  path route is absent (404). The O(n) scan is the only")
            print("  server-side option -> escalate the FORK to the owner:")
            print("   primary  : cached number->GUID index (fast + correct;")
            print("              staleness window with miss-fallback rescan)")
            print("   safety-net only: deadline-aware resolver (~8-10s ->")
            print('              honest "DATEV antwortet zu langsam", never a')
            print('              fake "nicht gefunden") layered on top, NOT an')
            print("              equal alternative")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
