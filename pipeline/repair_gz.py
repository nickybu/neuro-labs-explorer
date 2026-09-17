#!/usr/bin/env python3
"""Salvage a multi-member .jsonl.gz cache whose writer was hard-killed.

The crawlers append one gzip member per run and sync-flush after every page.
A SIGKILL skips close(), so that member never gets its trailer; when the
resumed run appends a new member, every reader dies at the boundary with zlib
"invalid block type". A 429 or Ctrl-C closes the file cleanly and never needs
this.

Salvage walks the file member by member. A first pass finds where each member
ends: cleanly, or at a tear (a failing feed is retried in shrinking pieces on a
copy of the decompressor, so the tear is located exactly). A second pass
decodes only trusted bytes and writes complete JSON lines:

* a clean member is trusted whole;
* a torn member is trusted only up to its last sync-flush marker (00 00 FF FF),
  i.e. the end of the last fully written page. Bytes past it are either a
  partial page or the next member's header misread as deflate data, and the
  latter decodes into back-references that copy earlier text - phantom or
  spliced records that still parse as valid JSON. Found in testing; never
  trust output past the last marker.

Records written after the last checkpoint are re-fetched by the resumed run,
so the salvaged file can contain a page of duplicates; `enrich_text.py tag`
drops them by work id.

    python3 pipeline/repair_gz.py data/cache/works_28_world_2024.full.jsonl.gz
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import zlib

MAGIC = b"\x1f\x8b\x08"
CHUNK = 1 << 20


def _feed(d, blob: bytes):
    """Decompress as much of `blob` as possible.

    Returns (output, decompressor, bytes_used, torn). On a zlib error the
    failing piece is retried in smaller steps on a copy, down to single bytes,
    so the output before the tear is never discarded.
    """
    out, i, step = [], 0, len(blob)
    while i < len(blob):
        piece = blob[i:i + step]
        trial = d.copy()
        try:
            out.append(trial.decompress(piece))
        except zlib.error:
            if step == 1:
                return b"".join(out), d, i, True
            step = max(1, step // 8)
            continue
        d = trial
        i += len(piece)
        if d.eof:
            break
    return b"".join(out), d, i, False


def _valid(line: bytes) -> bool:
    try:
        return isinstance(json.loads(line), dict)
    except ValueError:
        return False


SYNC = b"\x00\x00\xff\xff"


def _member_end(data: bytes, hdr: int) -> tuple[int, str, int]:
    """Pass 1: (trusted_end, state, next_pos) for the member starting at `hdr`.

    state is "clean" (trusted_end == member end), "torn" (trusted_end == just
    past the last sync marker before the tear) or "truncated" (file ended
    mid-member; same trust rule as torn).
    """
    d = zlib.decompressobj(31)
    p, torn = hdr, False
    while p < len(data):
        _, d, used, torn = _feed(d, data[p:p + CHUNK])
        p += used
        if torn or d.eof:
            break
    if d.eof:
        end = p - len(d.unused_data)
        return end, "clean", end
    if not torn:
        cut = data.rfind(SYNC, hdr, p)
        return (cut + len(SYNC) if cut >= 0 else hdr), "truncated", len(data)
    # The tear can be detected some way PAST the next member's header (its
    # bytes may decode as deflate for a while), so locate that header
    # independently, then trust only up to the last sync marker before it.
    nxt = _next_member(data, hdr, p)
    limit = min(p, nxt)
    cut = data.rfind(SYNC, hdr, limit)
    return (cut + len(SYNC) if cut >= 0 else hdr), "torn", nxt


def _starts_with_record(data: bytes, c: int) -> bool:
    """True if a gzip member at `c` decodes to a complete JSON record first.

    Filters out false magics inside compressed data: garbage never decodes to
    a valid JSON object at plaintext offset 0.
    """
    try:
        d = zlib.decompressobj(31)
        out, _, _, _ = _feed(d, data[c:c + (1 << 18)])
    except zlib.error:                     # corrupt gzip header
        return False
    nl = out.find(b"\n")
    return nl > 0 and _valid(out[:nl])


def _next_member(data: bytes, hdr: int, tear: int) -> int:
    c = data.find(MAGIC, hdr + 3)
    while 0 <= c <= tear + (1 << 16):
        if _starts_with_record(data, c):
            return c
        c = data.find(MAGIC, c + 1)
    c = data.find(MAGIC, tear)
    return c if c >= 0 else len(data)


def salvage(path: str) -> tuple[int, int, int]:
    """Write `<path>.repaired`. Returns (records kept, members seen, bytes skipped)."""
    data = open(path, "rb").read()
    kept = members = skipped = 0
    pos = 0
    with gzip.open(path + ".repaired", "wt", compresslevel=6) as out:
        while pos < len(data):
            hdr = data.find(MAGIC, pos)
            if hdr < 0:
                skipped += len(data) - pos
                break
            skipped += hdr - pos
            trusted, state, nxt = _member_end(data, hdr)
            members += 1
            skipped += nxt - trusted if state != "clean" else 0

            # Pass 2: decode the trusted span only. A trusted prefix of a valid
            # stream always decodes to a genuine prefix of the plaintext.
            d = zlib.decompressobj(31)
            buf = b""
            for p in range(hdr, trusted, CHUNK):
                buf += d.decompress(data[p:min(p + CHUNK, trusted)])
                nl = buf.rfind(b"\n")
                if nl >= 0:
                    for line in buf[:nl].split(b"\n"):
                        if line and _valid(line):
                            out.write(line.decode("utf-8") + "\n")
                            kept += 1
                    buf = buf[nl + 1:]
            # A clean member ends on "\n"; anything left is a partial line.
            pos = nxt
    return kept, members, skipped


if __name__ == "__main__":
    for path in sys.argv[1:]:
        kept, members, skipped = salvage(path)
        rep = path + ".repaired"
        print(f"{os.path.basename(path)}: {kept:,} records from {members} member(s), "
              f"{skipped:,} bytes skipped -> {os.path.getsize(rep) / 1e6:.1f} MB at {rep}")
