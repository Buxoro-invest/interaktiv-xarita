#!/usr/bin/env python3
"""Build a compact Laravel preview import from the live night_fetch JSONL checkpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
sys.path.insert(0, str(ROOT))

from e_auksion_parser import normalized_row  # noqa: E402

source = ROOT / "night_fetch" / "lots.jsonl"
target = PROJECT / "storage" / "app" / "data" / "night_preview.json"

rows: list[dict] = []
seen: set[str] = set()
with source.open("r", encoding="utf-8") as stream:
    for line in stream:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        row = normalized_row(raw)
        lot_id = str(row.get("id") or "")
        lat, lng = row.get("latitude"), row.get("longitude")
        if not lot_id or lot_id in seen or lat is None or lng is None:
            continue
        if not (38 <= float(lat) <= 42 and 61 <= float(lng) <= 67):
            continue
        seen.add(lot_id)
        row.pop("raw", None)
        row.pop("image_urls", None)
        row.pop("local_images", None)
        rows.append(row)

target.parent.mkdir(parents=True, exist_ok=True)
temporary = target.with_suffix(".json.tmp")
temporary.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
temporary.replace(target)
print(json.dumps({"source_lines": len(seen), "preview_lots": len(rows), "target": str(target)}))
