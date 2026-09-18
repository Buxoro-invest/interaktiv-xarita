<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::table('lots', function (Blueprint $table) {
            $table->decimal('latitude', 10, 7)->nullable()->after('district');
            $table->decimal('longitude', 10, 7)->nullable()->after('latitude');
            $table->string('location_status')->default('pending')->after('longitude')->index();
            $table->timestamp('location_verified_at')->nullable()->after('location_status');
        });
    }

    public function down(): void
    {
        Schema::table('lots', function (Blueprint $table) {
            $table->dropColumn(['latitude', 'longitude', 'location_status', 'location_verified_at']);
        });
    }
};
