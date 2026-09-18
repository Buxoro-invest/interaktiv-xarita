<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::table('lots', function (Blueprint $table) {
            $table->index(['latitude', 'longitude'], 'lots_map_coordinates_index');
        });
    }

    public function down(): void
    {
        Schema::table('lots', fn (Blueprint $table) => $table->dropIndex('lots_map_coordinates_index'));
    }
};
