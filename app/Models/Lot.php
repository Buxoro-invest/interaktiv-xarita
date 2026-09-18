<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Lot extends Model
{
    public $timestamps = false;

    protected $fillable = [
        'external_id', 'lot_number', 'group_name', 'name', 'address',
        'start_price', 'deposit', 'land_area', 'auction_date',
        'order_end_time', 'image_url', 'source_url', 'district', 'latitude', 'longitude',
        'location_geometry', 'location_status', 'location_verified_at', 'raw',
    ];

    protected $casts = [
        'start_price' => 'float',
        'deposit' => 'float',
        'land_area' => 'float',
        'raw' => 'array',
    ];
}
