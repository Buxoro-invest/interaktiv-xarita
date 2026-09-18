# Buxoro E-auksion parseri — operatsion qo‘llanma

Bu hujjat parserni keyinchalik xavfsiz davom ettirish, eksportni qayta qurish va
Laravel xaritasiga import qilish uchun asosiy yo‘riqnomadir.

## 1. Vazifa va qat’iy hudud qoidasi

Parser faqat **Buxoro viloyati** uchun ishlaydi:

- E-auksion region ID: `11`;
- region nomi: `Buxoro viloyati`;
- `regions_id` yoki `region_name.name_uz` yakuniy tekshiruvdan o‘tadi;
- boshqa viloyat lotlari JSON/CSV/GeoJSON fayllariga kiritilmaydi;
- Laravel importeri ham hududni mustaqil qayta tekshiradi.

| Kalit | Group | Nomi |
|---|---:|---|
| `real_estate` | `1` | Ko‘chmas mulk |
| `mobile_trade` | `23` | Ko‘chma savdo joylari |
| `bank_assets` | `-3` | Tijorat bank mulklari |
| `land` | `6` | Yer uchastkalari |

## 2. Tuzilma

```text
bproject/
├─ artisan
├─ app/, database/, public/, resources/, routes/ ...
└─ python/
   ├─ e_auksion_parser.py
   ├─ README.md
   ├─ night_fetch/
   │  ├─ raw_pages/region_11/
   │  ├─ lots.jsonl
   │  ├─ failed_lots.jsonl
   │  ├─ lots.json
   │  ├─ lots.csv
   │  └─ lots.geojson
   └─ output/
```

`python/night_fetch` — amaldagi asosiy dataset. Uni sababsiz o‘chirmang.

## 3. Talablar

- Python 3.10+; tashqi Python paketi kerak emas;
- internetga chiqish;
- katta eksport uchun kamida 2–3 GB bo‘sh disk;
- import uchun PHP 8.1+, `openssl`, `pdo_sqlite`, `sqlite3`, `mbstring`.

Komandalarni `bproject` rootida ishga tushiring.

## 4. To‘liq parse yoki checkpointdan davom ettirish

```powershell
python python\e_auksion_parser.py `
  --region 11 `
  --groups real_estate mobile_trade bank_assets land `
  --per-page 24 `
  --delay 4 `
  --output python\night_fetch
```

Shu komandani qayta ishga tushirish xavfsiz:

- ro‘yxat sahifalari `raw_pages/region_11/` dan olinadi;
- tayyor tafsilotlar `lots.jsonl` dan olinadi;
- faqat yetishmayotgan lotlar API orqali olinadi;
- yakunda JSON, CSV va GeoJSON qayta yaratiladi.

`--delay 4` tavsiya etiladi. Juda kichik delay `HTTP 429` ni ko‘paytiradi.

## 5. Checkpointlar

### `raw_pages/region_11/`

Har bir toifa va sahifa API javobi. Masalan:

```text
raw_pages/region_11/real_estate_page_0001.json
raw_pages/region_11/land_page_0042.json
```

Region raqamisiz eski checkpointlardan foydalanmang.

### `lots.jsonl`

Har bir muvaffaqiyatli lot tafsiloti bitta JSON qatorda saqlanadi. Bu asosiy resume
manbasi. Disk uzilishi oxirgi qatorni buzsa, parser uni ogohlantirish bilan o‘tkazadi.

### `failed_lots.jsonl`

Xato bo‘lgan ID, xabar va vaqt jurnali. Undagi lot keyingi urinishda olingan bo‘lishi
mumkin. Yakuniy holatni `lots.json` va `Tayyor:` logi orqali tekshiring.

## 6. HTTP 429

`429 Too Many Requests` — E-auksion tezlik limiti, ma’lumot buzilishi emas.

Parser kamida 60 soniya kutadi, `Retry-After` ni hisobga oladi va 8 martagacha
qayta urinadi. 429 ko‘paysa:

1. parserni parallel oynalarda ishga tushirmang;
2. `--delay 4` yoki `--delay 6` ishlating;
3. jarayonni to‘xtatib, aynan shu komanda bilan keyin davom ettiring;
4. `lots.jsonl` va `raw_pages` ni o‘chirmang.

## 7. Tarmoqqa chiqmasdan eksportni qayta qurish

```powershell
python python\e_auksion_parser.py `
  --region 11 `
  --output python\night_fetch `
  --rebuild-only
```

Bu APIga chiqmaydi, region tekshiruvini qayta bajaradi va `lots.json`, `lots.csv`,
`lots.geojson` fayllarini mavjud `lots.jsonl` dan yaratadi.

## 8. Sinov va qisman parse

Kichik sinov:

```powershell
python python\e_auksion_parser.py `
  --region 11 `
  --output python\test_output `
  --max-pages 1 `
  --max-lots 10 `
  --delay 0 `
  --verbose
```

Faqat ko‘chmas mulk va yer:

```powershell
python python\e_auksion_parser.py `
  --region 11 `
  --groups real_estate land `
  --delay 4 `
  --output python\night_fetch
```

Rasmlar bilan:

```powershell
python python\e_auksion_parser.py `
  --region 11 `
  --delay 4 `
  --output python\night_fetch `
  --download-images
```

`--download-images` ko‘p disk va vaqt talab qiladi. `--no-details` faqat diagnostika
uchun: koordinata, polygon va xarita linklari to‘liq bo‘lmasligi mumkin.

## 9. Yakuniy fayllar

- `lots.json` — Laravel importi uchun normalizatsiyalangan eksport;
- `lots.csv` — Excel/jadval uchun;
- `lots.geojson` — `Point` va `Polygon` geometriyalar;
- `lots.jsonl` — resume uchun API tafsilotlari;
- `raw_pages/region_11/` — ro‘yxat checkpointlari.

Polygon `polygon_list` yoki `location_bean_list` dan olinadi. Polygon markazi
nuqtalar o‘rtachasidan hisoblanadi. Google/Yandex xarita URLlari ham eksport qilinadi.

## 10. Laravel bazasiga import

Avval backup:

```powershell
Copy-Item database\database.sqlite database\database.before-import.sqlite
```

Oddiy PHP muhiti:

```powershell
php -d memory_limit=3G artisan lots:import python/night_fetch/lots.json
```

OSPanel konfiguratsiyani yuklamasa:

```powershell
php `
  -d "extension_dir=C:\OSPanel\modules\php\PHP_8.1\ext" `
  -d extension=php_openssl.dll `
  -d extension=php_pdo_sqlite.dll `
  -d extension=php_sqlite3.dll `
  -d extension=php_mbstring.dll `
  -d memory_limit=3G `
  artisan lots:import python/night_fetch/lots.json
```

Importer eski `lots` jadvalini almashtiradi va importdan oldin Buxoro regionini yana
tekshiradi. Begona lotlar kiritilmaydi.

## 11. Importdan keyingi tekshiruv

```powershell
curl.exe http://127.0.0.1:8000/api/summary
curl.exe http://127.0.0.1:8000/api/map-lots
```

Tekshiring:

- `catalog_total` — barcha Buxoro lotlari;
- `total` — koordinatali, xaritada ko‘rinadigan lotlar;
- kategoriya sonlari yig‘indisi `total` ga teng;
- boshqa viloyat koordinatalari yo‘q;
- polygon `/api/map-polygons` dan qaytadi;
- `/api/map-lots/{external_id}` marker tafsilotini `200` bilan beradi.

2026-09-18 dagi tekshirilgan bazaviy holat:

| Ko‘rsatkich | Soni |
|---|---:|
| Katalog | 7755 |
| Koordinatali | 7754 |
| Ko‘chma savdo joylari | 1855 |
| Ko‘chmas mulk | 242 |
| Tijorat bank mulklari | 78 |
| Yer uchastkalari | 5579 |

Yangi lotlar sabab bu sonlar keyinchalik o‘zgarishi tabiiy.

## 12. Xavfsiz yangilash tartibi

1. Disk joyini tekshiring.
2. Parserni `--delay 4` bilan `python/night_fetch` ga ishga tushiring.
3. `Tayyor:` logini kuting.
4. Kerak bo‘lsa `--rebuild-only` bajaring.
5. SQLite backupini oling.
6. `php artisan lots:import ...` bilan import qiling.
7. `/api/summary` va kategoriya sonlarini tekshiring.
8. Bir nechta point va polygon lotni E-auksion kartasi bilan solishtiring.

## 13. Xatolar va tiklanish

### `No space left on device`

Diskdan joy bo‘shating, `lots.jsonl` ni o‘chirmang va aynan shu komanda bilan davom
ettiring. Buzilgan oxirgi JSONL qatori avtomatik o‘tkaziladi.

### Noto‘g‘ri viloyat loti

1. `raw.region_name.name_uz` va `raw.regions_id` ni tekshiring;
2. `--rebuild-only` bajaring;
3. qayta import qiling;
4. checkpointlar `raw_pages/region_11/` dan ekanini tekshiring;
5. importer region validatsiyasini chetlab o‘tmang.

### PHP `could not find driver`

`pdo_sqlite` va `sqlite3` ni yoqing yoki yuqoridagi OSPanel komandasidan foydalaning.

### `openssl_cipher_iv_length` topilmadi

`openssl` kengaytmasini yoqing (`php_openssl.dll`).

## 14. Serverga chiqarish

- document root: `bproject/public`;
- `storage` va `bootstrap/cache` yoziladigan bo‘lsin;
- `.env`: `APP_ENV=production`, `APP_DEBUG=false`, haqiqiy `APP_URL`;
- PHP: `openssl`, `pdo_sqlite`, `sqlite3`, `mbstring`;
- deploy oldidan `php artisan optimize:clear`;
- server sozlangach `config:cache`, `route:cache`, `view:cache` mumkin;
- `python/` webdan ochilmasin: faqat `public/` document root bo‘lsin.

## 15. Kod o‘zgarsa muhim funksiyalar

- `signed_payload()` — ro‘yxat filtrlari va imzo;
- `request_json()` — 429/proof-of-work/retry;
- `fetch_group()` — regionga xos sahifa checkpointlari;
- `enrich_details()` — detail resume va joriy IDlar filtri;
- `is_target_region()` — qat’iy region tekshiruvi;
- `coordinates()` va `geometry()` — point/polygon;
- `normalized_row()` — Laravel formati;
- `write_outputs()` — JSON/CSV/GeoJSON.

API formati o‘zgarsa, avval `python/test_output` bilan kichik sinov qiling. To‘liq
`night_fetch` datasetini tajriba uchun ishlatmang.
