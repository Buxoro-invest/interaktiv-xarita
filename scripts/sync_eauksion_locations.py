#!/usr/bin/env python3
"""E-auksion lot kartalaridan aniq koordinatalarni bazaga ketma-ket yozadi."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT.parent))

from e_auksion_parser import LOT_INFO_API, coordinates, geometry, request_json  # noqa: E402


def exact_point(detail: dict) -> tuple[float, float] | None:
    coord = coordinates(detail)
    if coord:
        lng, lat = coord
    else:
        geom = geometry(detail)
        if not geom:
            return None
        if geom["type"] == "Point":
            lng, lat = geom["coordinates"]
        else:
            ring = geom["coordinates"][0]
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring = ring[:-1]
            lng = sum(point[0] for point in ring) / len(ring)
            lat = sum(point[1] for point in ring) / len(ring)
    if not (38 <= lat <= 42 and 61 <= lng <= 67):
        raise ValueError(f"Buxoro hududidan tashqari koordinata: {lat}, {lng}")
    return lat, lng


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--all", action="store_true", help="Barcha kutilayotgan lotlarni tekshirish")
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()

    db = sqlite3.connect(PROJECT / "database" / "database.sqlite", timeout=30)
    db.row_factory = sqlite3.Row
    statuses = ["pending"] + (["error"] if args.retry_errors else [])
    marks = ",".join("?" for _ in statuses)
    limit_sql = "" if args.all else " LIMIT ?"
    params: list[object] = statuses + ([] if args.all else [max(1, args.limit)])
    lots = db.execute(
        f"SELECT id, external_id FROM lots WHERE location_status IN ({marks}) ORDER BY id{limit_sql}",
        params,
    ).fetchall()

    verified = missing = failed = 0
    for index, lot in enumerate(lots, 1):
        lot_id = str(lot["external_id"])
        try:
            detail = request_json(f"{LOT_INFO_API}?lot_id={lot_id}")
            point = exact_point(detail) if isinstance(detail, dict) else None
            shape = geometry(detail) if isinstance(detail, dict) else None
            now = datetime.now(timezone.utc).isoformat()
            if point:
                lat, lng = point
                db.execute(
                    "UPDATE lots SET latitude=?, longitude=?, location_geometry=?, location_status='verified', location_verified_at=? WHERE id=?",
                    (lat, lng, json.dumps(shape, ensure_ascii=False) if shape else None, now, lot["id"]),
                )
                verified += 1
                print(f"[{index}/{len(lots)}] {lot_id}: VERIFIED {lat:.7f},{lng:.7f}", flush=True)
            else:
                db.execute(
                    "UPDATE lots SET location_status='no_coordinates', location_verified_at=? WHERE id=?",
                    (now, lot["id"]),
                )
                missing += 1
                print(f"[{index}/{len(lots)}] {lot_id}: NO_COORDINATES", flush=True)
        except Exception as exc:
            db.execute("UPDATE lots SET location_status='error' WHERE id=?", (lot["id"],))
            failed += 1
            print(f"[{index}/{len(lots)}] {lot_id}: ERROR {exc}", flush=True)
        db.commit()
        if index < len(lots) and args.delay:
            time.sleep(args.delay)

    print(json.dumps({"checked": len(lots), "verified": verified, "no_coordinates": missing, "errors": failed}))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
