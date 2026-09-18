<?php

namespace App\Console\Commands;

use App\Models\Lot;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Cache;

class ImportEAuksionLots extends Command
{
    protected $signature = 'lots:import {path=storage/app/data/lots.json}';
    protected $description = 'E-auksion JSON eksportini Laravel bazasiga import qiladi';

    public function handle(): int
    {
        $path = base_path($this->argument('path'));
        if (!is_file($path)) {
            $this->error("Fayl topilmadi: {$path}");
            return self::FAILURE;
        }

        $items = json_decode(file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
        $sourceCount = count($items);
        $items = array_values(array_filter($items, fn (array $item) => $this->isBukharaItem($item)));
        $rejected = $sourceCount - count($items);
        if ($rejected) {
            $this->warn("Hudud tekshiruvi: {$rejected} ta Buxoroga tegishli bo'lmagan lot chiqarildi.");
        }
        $this->info(count($items).' ta Buxoro loti import qilinmoqda...');
        Lot::query()->delete();

        $rows = [];
        foreach ($items as $item) {
            $raw = $item['raw'] ?? [];
            $address = $item['address'] ?? $raw['full_address'] ?? $raw['address'] ?? null;
            $geometry = $item['geometry'] ?? null;
            $latitude = $item['latitude'] ?? null;
            $longitude = $item['longitude'] ?? null;
            $rows[] = [
                'external_id' => (string) ($item['id'] ?? $item['lot_number']),
                'lot_number' => $item['lot_number'] ?? null,
                'group_name' => $item['group'] ?? 'Boshqa',
                'name' => $item['name'] ?? null,
                'address' => $address,
                'start_price' => $item['start_price'] ?? null,
                'deposit' => $item['deposit'] ?? null,
                'land_area' => $item['land_area'] ?? null,
                'auction_date' => $item['auction_date'] ?? null,
                'order_end_time' => $item['order_end_time'] ?? null,
                'image_url' => $item['main_image_url'] ?? null,
                'source_url' => $item['source_url'] ?? null,
                'district' => $this->districtFromItem($item, $raw, $address),
                'latitude' => $latitude,
                'longitude' => $longitude,
                'location_geometry' => $geometry ? json_encode($geometry, JSON_UNESCAPED_UNICODE) : null,
                'location_status' => ($latitude !== null && $longitude !== null) ? 'verified' : 'pending',
                'location_verified_at' => ($latitude !== null && $longitude !== null) ? now() : null,
                'raw' => json_encode($raw, JSON_UNESCAPED_UNICODE),
            ];
            // Keep each multi-row INSERT comfortably below MariaDB's
            // max_allowed_packet even when lots contain large raw/polygon JSON.
            if (count($rows) === 25) {
                DB::table('lots')->insert($rows);
                $rows = [];
            }
        }
        if ($rows) DB::table('lots')->insert($rows);

        Cache::forget('map.summary.v2');
        $this->info('Import tugadi: '.Lot::count().' ta lot.');
        return self::SUCCESS;
    }

    private function isBukharaItem(array $item): bool
    {
        $raw = $item['raw'] ?? [];
        $regionId = $raw['regions_id'] ?? null;
        if ($regionId !== null) return (int) $regionId === 11;

        $region = $raw['region_name'] ?? $item['region'] ?? null;
        if (is_array($region)) $region = $region['name_uz'] ?? $region['name'] ?? null;
        return trim((string) $region) === 'Buxoro viloyati';
    }

    private function districtFromItem(array $item, array $raw, ?string $address): string
    {
        $district = $raw['area_name'] ?? $item['district'] ?? null;
        if (is_array($district)) $district = $district['name_uz'] ?? $district['name'] ?? null;
        if (is_string($district) && trim($district) !== '') {
            return str_replace("'", '‘', trim($district));
        }
        return $this->districtFrom($address);
    }

    private function districtFrom(?string $address): string
    {
        if (!$address) return 'Buxoro viloyati';
        $names = ['Buxoro shahri', 'Kogon shahri', 'Buxoro tumani', 'Kogon tumani',
            'G‘ijduvon tumani', "G'ijduvon tumani", 'Gijduvon tumani', 'Vobkent tumani',
            'Shofirkon tumani', 'Romitan tumani', 'Jondor tumani', 'Qorako‘l tumani',
            "Qorako'l tumani", 'Olot tumani', 'Peshku tumani', 'Qorovulbozor tumani'];
        foreach ($names as $name) {
            if (mb_stripos($address, $name) !== false) return str_replace("'", '‘', $name);
        }
        if (preg_match('/Buxoro\s+sh(?:ahri)?/iu', $address)) return 'Buxoro shahri';
        return 'Buxoro viloyati';
    }
}
