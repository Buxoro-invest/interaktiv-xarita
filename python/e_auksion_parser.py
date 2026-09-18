#!/usr/bin/env python3
"""Buxoro viloyatidagi e-auksion lotlarini eksport qilish.

Natijalar JSON, CSV va xarita uchun GeoJSON formatida saqlanadi. Skript
e-auksion.uz ochiq web-interfeysi ishlatadigan API bilan ishlaydi.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import mimetypes
import re
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://e-auksion.uz"
LOTS_API = f"{BASE_URL}/api/front/lots"
LOT_INFO_API = f"{BASE_URL}/api/front/lot-info"
PROOF_API = f"{BASE_URL}/api/front/proof/verify"
DEFAULT_REGION_ID = 11  # Buxoro viloyati
REGION_NAMES = {11: "Buxoro viloyati"}
GROUPS = {
    "real_estate": {"id": 1, "name": "Ko'chmas mulk"},
    "mobile_trade": {"id": 23, "name": "Ko'chma savdo joylari"},
    "bank_assets": {"id": -3, "name": "Tijorat bank mulklari"},
    "land": {"id": 6, "name": "Yer uchastkalari"},
}


def compact_json(value: Any) -> str:
    """JavaScript JSON.stringify ga mos JSON matni."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def signed_payload(group_id: int, region_id: int, page: int, per_page: int) -> dict[str, Any]:
    # Kalitlar tartibi sayt JavaScriptidagi tartib bilan bir xil bo'lishi kerak.
    payload: dict[str, Any] = {
        "sort_type": 1,
        "confiscant_groups_id": group_id,
        "confiscant_categories_id": None,
        "regions_id": region_id,
        "areas_id": None,
        "mahallas_id": None,
        "address": "",
        "lot_number": "",
        "hashtag": "",
        "date_from": None,
        "date_to": None,
        "auction_date": None,
        "is_term_order": -1,
        "exec_order_type": 0,
        "lot_type": 0,
        "auction_type": 0,
        "finished_auction_status": 0,
        "filtered_auction_status": 0,
        "is_ownership": -1,
        "orderby_": 0,
        "current_page": page,
        "per_page": per_page,
        "dynamic_filters": [],
        "bank_id": None,
    }
    payload["zz_md5"] = hashlib.md5(compact_json(payload).encode("utf-8")).hexdigest()
    return payload


def solve_proof(challenge: str, difficulty: int) -> str:
    """Saytning pow-worker.js algoritmiga mos SHA-256 proof-of-work."""
    nonce = str(challenge).split(".")[1]
    target_bytes, extra_bits = divmod(int(difficulty), 8)
    for solution in range(50_000_000):
        digest = hashlib.sha256(f"{nonce}:{solution}".encode()).digest()
        if digest[:target_bytes] != b"\0" * target_bytes:
            continue
        if extra_bits and digest[target_bytes] >> (8 - extra_bits) != 0:
            continue
        return str(solution)
    raise RuntimeError("Proof-of-work yechimi belgilangan limitda topilmadi")


def get_proof_token(challenge: str, difficulty: int, timeout: int) -> str:
    solution = solve_proof(challenge, difficulty)
    result = request_json(
        PROOF_API,
        payload={"challenge": challenge, "solution": solution},
        timeout=timeout,
        allow_proof=False,
    )
    token = result.get("token") if isinstance(result, dict) else None
    if not token:
        raise RuntimeError("Proof-of-work tasdiqlanmadi")
    return str(token)


def request_json(url: str, *, payload: dict[str, Any] | None = None, timeout: int = 45,
                 proof_token: str | None = None, allow_proof: bool = True,
                 retries: int = 8) -> Any:
    data = compact_json(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "uz-UZ,uz;q=0.9",
        "Referer": f"{BASE_URL}/lots",
        "User-Agent": "Mozilla/5.0 (compatible; BuxoroEAuksionExporter/1.0)",
    }
    if data is not None:
        headers["Content-Type"] = "application/json;charset=UTF-8"
    if proof_token:
        headers["X-Proof-Token"] = proof_token
    req = Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        if exc.code == 429 and retries > 0:
            retry_after = exc.headers.get("Retry-After")
            try:
                wait_seconds = max(60, int(retry_after or 60))
            except ValueError:
                wait_seconds = 60
            wait_seconds += min(30, (8 - retries) * 5)
            logging.warning("API limiti (429). %s soniya kutiladi, keyin qayta uriniladi.", wait_seconds)
            time.sleep(wait_seconds)
            return request_json(url, payload=payload, timeout=timeout,
                                proof_token=proof_token, allow_proof=allow_proof,
                                retries=retries - 1)
        if exc.code == 428 and allow_proof:
            try:
                challenge_data = json.loads(detail)
                challenge = challenge_data["challenge"]
                difficulty = int(challenge_data["difficulty"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as parse_exc:
                raise RuntimeError(f"Proof-of-work javobi o'qilmadi: {detail}") from parse_exc
            token = get_proof_token(challenge, difficulty, timeout)
            return request_json(url, payload=payload, timeout=timeout,
                                proof_token=token, allow_proof=False, retries=retries)
        raise RuntimeError(f"API xatosi HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Tarmoq xatosi: {exc}") from exc


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(compact_json(value) + "\n")
        stream.flush()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
            except json.JSONDecodeError:
                logging.warning("Buzilgan JSONL qatori o'tkazildi: %s:%s", path, line_number)
    return rows


def fetch_group(group_key: str, region_id: int, per_page: int, delay: float,
                max_pages: int | None, output_dir: Path) -> list[dict[str, Any]]:
    group = GROUPS[group_key]
    rows: list[dict[str, Any]] = []
    page = 1
    total_pages = 1
    while page <= total_pages and (max_pages is None or page <= max_pages):
        page_file = output_dir / "raw_pages" / f"region_{region_id}" / f"{group_key}_page_{page:04d}.json"
        if page_file.exists():
            logging.info("%s: %s-sahifa checkpointdan olindi", group["name"], page)
            result = json.loads(page_file.read_text(encoding="utf-8"))
        else:
            logging.info("%s: %s-sahifa", group["name"], page)
            result = request_json(LOTS_API, payload=signed_payload(group["id"], region_id, page, per_page))
            atomic_json(page_file, result)
        if not isinstance(result, dict):
            raise RuntimeError(f"Kutilmagan API javobi: {type(result).__name__}")
        page_rows = result.get("rows") or []
        if not isinstance(page_rows, list):
            raise RuntimeError("API javobidagi 'rows' ro'yxat emas")
        for row in page_rows:
            if isinstance(row, dict):
                item = dict(row)
                item["source_group_key"] = group_key
                item["source_group_name"] = group["name"]
                item["source_url"] = lot_url(item)
                rows.append(item)
        total_pages = int(result.get("totalPages") or 1)
        page += 1
        if page <= total_pages and delay:
            time.sleep(delay)
    return rows


def enrich_details(rows: list[dict[str, Any]], delay: float, output_dir: Path) -> list[dict[str, Any]]:
    details_file = output_dir / "lots.jsonl"
    failed_file = output_dir / "failed_lots.jsonl"
    saved = {str(row.get("id") or row.get("lot_id")): row for row in read_jsonl(details_file)}
    requested_keys = [str(row.get("id") or row.get("lot_id")) for row in rows]
    total = len(rows)
    for index, row in enumerate(rows, 1):
        lot_id = row.get("id") or row.get("lot_id")
        key = str(lot_id)
        if key in saved:
            logging.info("Lot tafsiloti: %s/%s (ID %s) checkpointdan olindi", index, total, lot_id)
            continue
        if lot_id is None:
            continue
        logging.info("Lot tafsiloti: %s/%s (ID %s)", index, total, lot_id)
        try:
            detail = request_json(f"{LOT_INFO_API}?lot_id={lot_id}")
            if isinstance(detail, dict):
                source_fields = {key: row.get(key) for key in
                                 ("source_group_key", "source_group_name", "source_url")}
                row = {**row, **detail, **source_fields}
                append_jsonl(details_file, row)
                saved[key] = row
        except RuntimeError as exc:
            logging.warning("Lot %s tafsiloti olinmadi: %s", lot_id, exc)
            append_jsonl(failed_file, {"id": lot_id, "error": str(exc), "time": time.time()})
        if delay and index < total:
            time.sleep(delay)
    # JSONL ichida avvalgi boshqa filtr/region ishga tushirishlaridan qolgan
    # lotlar bo'lishi mumkin. Faqat joriy ro'yxatda so'ralgan IDlarni qaytaramiz.
    return [saved[key] for key in requested_keys if key in saved]


def region_name(lot: dict[str, Any]) -> str | None:
    value = lot.get("region_name") or lot.get("region")
    if isinstance(value, dict):
        value = value.get("name_uz") or value.get("name")
    return str(value).strip() if value else None


def is_target_region(lot: dict[str, Any], region_id: int) -> bool:
    """Lot tafsilotidagi authoritative region bo'yicha qat'iy tekshiruv."""
    value = lot.get("regions_id")
    if value is not None:
        try:
            return int(value) == region_id
        except (TypeError, ValueError):
            return False
    expected = REGION_NAMES.get(region_id)
    return bool(expected and region_name(lot) == expected)


def lot_url(lot: dict[str, Any]) -> str:
    lot_id = lot.get("id") or lot.get("lot_id")
    status = lot.get("lot_statuses_id")
    if status in (2, 3, 10):
        path = "/lot-view?lot_id="
    elif status == 11:
        path = "/lot-game-view?lot_id="
    else:
        path = "/auction-result?lots_id="
    return f"{BASE_URL}{path}{lot_id}" if lot_id is not None else f"{BASE_URL}/lots"


def nested_values(value: Any, keys: set[str]) -> Iterable[Any]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in keys:
                yield child
            yield from nested_values(child, keys)
    elif isinstance(value, list):
        for child in value:
            yield from nested_values(child, keys)


def image_urls(lot: dict[str, Any]) -> list[str]:
    keys = {"media_url", "image", "image_url", "photo", "photo_url", "file_url", "url"}
    found: list[str] = []
    for value in nested_values(lot, keys):
        values = value if isinstance(value, list) else [value]
        for candidate in values:
            if isinstance(candidate, dict):
                candidate = candidate.get("url") or candidate.get("media_url")
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            url = urljoin(BASE_URL, candidate.strip())
            path = urlparse(url).path.lower()
            if (path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
                    or "static.e-auksion.uz" in url or "media" in url):
                if url not in found:
                    found.append(url)
    return found


def first_number(lot: dict[str, Any], keys: Iterable[str]) -> float | None:
    for key in keys:
        value = lot.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip().replace(",", "."))
            except ValueError:
                pass
    return None


def coordinates(lot: dict[str, Any]) -> tuple[float, float] | None:
    lon = first_number(lot, ("longitude", "lon", "lng", "x", "long"))
    lat = first_number(lot, ("latitude", "lat", "y"))
    if lon is not None and lat is not None and -180 <= lon <= 180 and -90 <= lat <= 90:
        # Ba'zi manbalarda koordinatalar teskari nomlangan bo'lishi mumkin.
        if 35 <= lon <= 46 and 55 <= lat <= 74:
            lon, lat = lat, lon
        return lon, lat
    for key in ("location", "coordinates", "coordinate", "geo"):
        value = lot.get(key)
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                a, b = float(value[0]), float(value[1])
                return (b, a) if 35 <= a <= 46 and 55 <= b <= 74 else (a, b)
            except (TypeError, ValueError):
                pass
        if isinstance(value, str):
            nums = re.findall(r"-?\d+(?:[.,]\d+)?", value)
            if len(nums) >= 2:
                a, b = (float(x.replace(",", ".")) for x in nums[:2])
                return (b, a) if 35 <= a <= 46 and 55 <= b <= 74 else (a, b)
    return None


def geometry(lot: dict[str, Any]) -> dict[str, Any] | None:
    # Yangi E-auksion javoblarida kontur `polygon_list`, eski javoblarda esa
    # `location_bean_list` maydonida keladi.
    points = lot.get("polygon_list") or lot.get("location_bean_list")
    if isinstance(points, list):
        ring: list[list[float]] = []
        for point in points:
            if isinstance(point, dict):
                try:
                    ring.append([float(point["lng"]), float(point["lat"])])
                except (KeyError, TypeError, ValueError):
                    pass
        if len(ring) >= 3:
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            return {"type": "Polygon", "coordinates": [ring]}
        if ring:
            return {"type": "Point", "coordinates": ring[0]}
    coord = coordinates(lot)
    return {"type": "Point", "coordinates": list(coord)} if coord else None


def normalized_row(lot: dict[str, Any]) -> dict[str, Any]:
    geom = geometry(lot)
    coord = coordinates(lot)
    if coord is None and geom and geom["type"] == "Polygon":
        ring = geom["coordinates"][0][:-1]
        coord = (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
    images = image_urls(lot)
    return {
        "id": lot.get("id") or lot.get("lot_id"),
        "lot_number": lot.get("lot_number"),
        "group": lot.get("source_group_name"),
        "name": lot.get("name") or lot.get("property_name"),
        "region": lot.get("region_name") or lot.get("region"),
        "district": lot.get("area_name") or lot.get("area"),
        "address": lot.get("full_address") or lot.get("address"),
        "start_price": lot.get("start_price"),
        "deposit": lot.get("zaklad_summa"),
        "land_area": lot.get("land_area"),
        "auction_date": lot.get("auction_date_str") or lot.get("auction_date"),
        "order_end_time": lot.get("order_end_time_str") or lot.get("order_end_time"),
        "latitude": coord[1] if coord else None,
        "longitude": coord[0] if coord else None,
        "main_image_url": images[0] if images else None,
        "image_urls": images,
        "source_url": lot.get("source_url"),
        "google_maps_url": (f"https://www.google.com/maps/search/?api=1&query={coord[1]},{coord[0]}" if coord else None),
        "yandex_maps_url": (f"https://yandex.com/maps/?pt={coord[0]},{coord[1]}&z=16&l=map" if coord else None),
        "geometry": geom,
        "raw": lot,
    }


def safe_name(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "lot"))
    return text.strip("._") or "lot"


def download_images(rows: list[dict[str, Any]], output_dir: Path, delay: float) -> None:
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        local_files: list[str] = []
        for index, url in enumerate(row["image_urls"], 1):
            suffix = Path(urlparse(url).path).suffix.lower()
            if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                suffix = mimetypes.guess_extension("image/jpeg") or ".jpg"
            filename = f"{safe_name(row['lot_number'] or row['id'])}_{index}{suffix}"
            target = image_dir / filename
            req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": BASE_URL})
            try:
                with urlopen(req, timeout=45) as response:
                    target.write_bytes(response.read())
                local_files.append(str(target.relative_to(output_dir)).replace("\\", "/"))
                if delay:
                    time.sleep(delay)
            except (HTTPError, URLError, TimeoutError) as exc:
                logging.warning("Rasm yuklanmadi (%s): %s", url, exc)
        row["local_images"] = local_files


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lots.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    csv_fields = [key for key in rows[0] if key not in ("raw", "image_urls", "local_images", "geometry")] if rows else []
    if csv_fields:
        with (output_dir / "lots.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=csv_fields)
            writer.writeheader()
            writer.writerows({key: row.get(key) for key in csv_fields} for row in rows)
    features = []
    for row in rows:
        if row.get("geometry") is None:
            continue
        properties = {k: v for k, v in row.items()
                      if k not in ("raw", "geometry", "latitude", "longitude")}
        features.append({
            "type": "Feature",
            "geometry": row["geometry"],
            "properties": properties,
        })
    geojson = {"type": "FeatureCollection", "features": features}
    (output_dir / "lots.geojson").write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "-o", type=Path, default=Path("output"), help="Natija papkasi")
    parser.add_argument("--region", type=int, default=DEFAULT_REGION_ID, help="Viloyat ID (Buxoro: 11)")
    parser.add_argument("--groups", nargs="+", choices=GROUPS, default=list(GROUPS), help="Toifalar")
    parser.add_argument("--per-page", type=int, default=24, help="Bir so'rovdagi lotlar soni")
    parser.add_argument("--max-pages", type=int, help="Har bir toifa uchun test sahifalari limiti")
    parser.add_argument("--delay", type=float, default=0.5, help="So'rovlar oralig'idagi soniya")
    parser.add_argument("--download-images", action="store_true", help="Rasmlarni images/ papkasiga yuklash")
    parser.add_argument("--no-details", action="store_true", help="Har bir lotning batafsil ma'lumotini olmaslik")
    parser.add_argument("--rebuild-only", action="store_true",
                        help="Mavjud lots.jsonl checkpointdan tarmoqqa chiqmasdan natijalarni qayta qurish")
    parser.add_argument("--max-lots", type=int, help="Sinov uchun umumiy lotlar limiti")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")
    if args.rebuild_only:
        detail_rows = read_jsonl(args.output / "lots.jsonl")
    else:
        raw_rows: list[dict[str, Any]] = []
        for group_key in args.groups:
            raw_rows.extend(fetch_group(group_key, args.region, args.per_page, args.delay,
                                        args.max_pages, args.output))
            if args.max_lots and len(raw_rows) >= args.max_lots:
                raw_rows = raw_rows[:args.max_lots]
                break
        # Bir lot bir nechta toifada uchrasa, ID bo'yicha takrorini olib tashlaymiz.
        unique: dict[str, dict[str, Any]] = {}
        for row in raw_rows:
            unique[str(row.get("id") or row.get("lot_id") or len(unique))] = row
        detail_rows = list(unique.values())
        if not args.no_details:
            detail_rows = enrich_details(detail_rows, args.delay, args.output)
    before_region_filter = len(detail_rows)
    detail_rows = [row for row in detail_rows if is_target_region(row, args.region)]
    rejected = before_region_filter - len(detail_rows)
    if rejected:
        logging.warning("Region tekshiruvi: %s ta begona lot chiqarib tashlandi", rejected)
    rows = [normalized_row(row) for row in detail_rows]
    if args.download_images:
        download_images(rows, args.output, args.delay)
    write_outputs(rows, args.output)
    with_coords = sum(row["latitude"] is not None for row in rows)
    logging.info("Tayyor: %s ta lot, %s tasida koordinata. Natija: %s",
                 len(rows), with_coords, args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
