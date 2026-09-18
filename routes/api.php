<?php

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\LotController;

/*
|--------------------------------------------------------------------------
| API Routes
|--------------------------------------------------------------------------
|
| Here is where you can register API routes for your application. These
| routes are loaded by the RouteServiceProvider and all of them will
| be assigned to the "api" middleware group. Make something great!
|
*/

Route::middleware('auth:sanctum')->get('/user', function (Request $request) {
    return $request->user();
});

Route::get('/lots', [LotController::class, 'index']);
Route::get('/summary', [LotController::class, 'summary']);
Route::get('/map-lots', [LotController::class, 'mapLots']);
Route::get('/map-lots/{externalId}', [LotController::class, 'mapLot']);
Route::get('/map-polygons', [LotController::class, 'mapPolygons']);
