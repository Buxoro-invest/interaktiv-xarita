<?php

namespace App\Http\Controllers;

use App\Models\Lot;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class LotController extends Controller
{
    private const CENTERS = [
        'Buxoro shahri' => [39.7681, 64.4556], 'Buxoro tumani' => [39.8250, 64.4200],
        'Kogon shahri' => [39.7228, 64.5518], 'Kogon tumani' => [39.7000, 64.6100],
        'G‘ijduvon tumani' => [40.1000, 64.6830], 'Vobkent tumani' => [40.0300, 64.5150],
        'Shofirkon tumani' => [40.1200, 64.5000], 'Romitan tumani' => [39.9300, 64.3800],
        'Jondor tumani' => [39.7400, 64.1800], 'Qorako‘l tumani' => [39.5000, 63.8500],
        'Olot tumani' => [39.4200, 63.8000], 'Peshku tumani' => [40.0000, 64.3000],
        'Qorovulbozor tumani' => [39.5000, 64.7900], 'Buxoro viloyati' => [39.8500, 64.3000],
    ];

    public function index(Request $request): JsonResponse
    {
        $query = Lot::query();
        if ($search = trim((string) $request->query('q'))) {
            $query->where(fn ($q) => $q->where('lot_number', 'like', "%{$search}%")
                ->orWhere('name', 'like', "%{$search}%")
                ->orWhere('address', 'like', "%{$search}%"));
        }
        if ($group = $request->query('group')) $query->where('group_name', $group);
        if ($district = $request->query('district')) $query->where('district', $district);
        if ($min = $request->query('min_price')) $query->where('start_price', '>=', (float) $min);
        if ($max = $request->query('max_price')) $query->where('start_price', '<=', (float) $max);

        $sort = $request->query('sort', 'newest');
        match ($sort) {
            'price_asc' => $query->orderBy('start_price'),
            'price_desc' => $query->orderByDesc('start_price'),
            default => $query->orderByDesc('id'),
        };

        return response()->json($query->paginate(min((int) $request->query('per_page', 24), 60)));
    }

    public function summary(): JsonResponse
    {
        $verified = Lot::query()->whereNotNull('latitude')->whereNotNull('longitude');
        $groups = (clone $verified)->select('group_name', DB::raw('count(*) as count'),
            DB::raw('sum(start_price) as value'))->groupBy('group_name')->get();
        $districts = (clone $verified)->select('district', DB::raw('count(*) as count'),
            DB::raw('sum(start_price) as value'))->groupBy('district')->get()
            ->map(function ($row) {
                [$row->lat, $row->lng] = self::CENTERS[$row->district] ?? self::CENTERS['Buxoro viloyati'];
                return $row;
            });
        return response()->json([
            'total' => (clone $verified)->count(),
            'catalog_total' => Lot::count(),
            'total_value' => (float) (clone $verified)->sum('start_price'),
            'with_images' => (clone $verified)->whereNotNull('image_url')->count(),
            'groups' => $groups,
            'districts' => $districts,
            'updated_at' => now()->toIso8601String(),
        ]);
    }

    public function mapLots(Request $request): JsonResponse
    {
        $query = Lot::query();
        if ($group = $request->query('group')) $query->where('group_name', $group);
        if ($district = $request->query('district')) $query->where('district', $district);
        if ($search = trim((string) $request->query('q'))) {
            $query->where(fn ($q) => $q->where('lot_number', 'like', "%{$search}%")
                ->orWhere('name', 'like', "%{$search}%")
                ->orWhere('address', 'like', "%{$search}%"));
        }

        $verifiedQuery = (clone $query)->whereNotNull('latitude')->whereNotNull('longitude');
        $lots = $verifiedQuery->orderByDesc('id')->get([
            'external_id', 'latitude', 'longitude',
        ])->map(function (Lot $lot) {
            $lot->lat = (float) $lot->latitude;
            $lot->lng = (float) $lot->longitude;
            $lot->makeHidden(['latitude', 'longitude']);
            return $lot;
        });

        return response()->json([
            'data' => $lots,
            'shown' => $lots->count(),
            'total' => $lots->count(),
            'approximate' => false,
            'location_source' => 'e-auksion.uz lot-info',
        ]);
    }

    public function mapLot(string $externalId): JsonResponse
    {
        $lot = Lot::query()->where('external_id', $externalId)->firstOrFail([
            'external_id', 'lot_number', 'group_name', 'name', 'address', 'start_price',
            'auction_date', 'image_url', 'source_url', 'district', 'latitude', 'longitude',
        ]);
        $lot->lat = (float) $lot->latitude;
        $lot->lng = (float) $lot->longitude;
        $lot->makeHidden(['latitude', 'longitude']);
        return response()->json($lot);
    }

    public function mapPolygons(Request $request): JsonResponse
    {
        $south = max(-90, min(90, (float) $request->query('south', -90)));
        $north = max(-90, min(90, (float) $request->query('north', 90)));
        $west = max(-180, min(180, (float) $request->query('west', -180)));
        $east = max(-180, min(180, (float) $request->query('east', 180)));

        $query = Lot::query()
            ->whereBetween('latitude', [min($south, $north), max($south, $north)])
            ->whereBetween('longitude', [min($west, $east), max($west, $east)])
            ->where('location_geometry', 'like', '%"Polygon"%');
        if ($group = $request->query('group')) $query->where('group_name', $group);
        if ($district = $request->query('district')) $query->where('district', $district);
        if ($search = trim((string) $request->query('q'))) {
            $query->where(fn ($q) => $q->where('lot_number', 'like', "%{$search}%")
                ->orWhere('name', 'like', "%{$search}%")
                ->orWhere('address', 'like', "%{$search}%"));
        }

        $total = (clone $query)->count();
        $rows = $query->limit(800)->get(['external_id', 'location_geometry'])->map(fn (Lot $lot) => [
            'external_id' => $lot->external_id,
            'geometry' => json_decode($lot->location_geometry),
        ]);

        return response()->json(['data' => $rows, 'shown' => $rows->count(), 'total' => $total]);
    }
}
