<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('lots', function (Blueprint $table) {
            $table->id();
            $table->string('external_id')->unique();
            $table->string('lot_number')->nullable()->index();
            $table->string('group_name')->index();
            $table->string('name')->nullable();
            $table->text('address')->nullable();
            $table->decimal('start_price', 20, 2)->nullable()->index();
            $table->decimal('deposit', 20, 2)->nullable();
            $table->decimal('land_area', 16, 4)->nullable();
            $table->string('auction_date')->nullable();
            $table->string('order_end_time')->nullable();
            $table->text('image_url')->nullable();
            $table->text('source_url')->nullable();
            $table->string('district')->nullable()->index();
            $table->json('raw')->nullable();
            $table->index(['group_name', 'district']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('lots');
    }
};
