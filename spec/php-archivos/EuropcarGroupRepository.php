<?php

declare(strict_types=1);

namespace App\Repositories;

use Carbon\Carbon;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * EuropcarGroupRepository (Europcar / Keddy / Fox)
 * - Login por marca y estado (DPE/DPA) con retry/timeout
 * - Disponibilidad por proveedor, por todos, o por "cheapest" (pool)
 * - Mapeo contra catálogo MCR por modelo (car_name)
 * - Sólo adjunta payloads crudos si $includeRaw = true
 * - Confirmación usa SessionId + BookId; si falta cotización, deriva de disponibilidad
 */
class EuropcarGroupRepository
{
    private const PROVIDERS = [
        'europcar' => ['id' => 1,   'name' => 'EUROPCAR'],
        'keddy'    => ['id' => 93,  'name' => 'KEDDY'],
        'fox'      => ['id' => 109, 'name' => 'FOX RENT A CAR'],
    ];

    private string $endpoint; // JSON-RPC endpoint

    private array $credsStd; // credenciales normales (DPE)
    private array $credsDpa; // credenciales DPA

    private int $httpTimeout;
    private int $httpRetries;
    private int $httpRetrySleepMs;

    public function __construct()
    {
        $this->endpoint = rtrim((string) config('europcargroup.endpoint'), '/');

        $this->credsStd = [
            'europcar' => [
                'user' => (string) config('europcargroup.europcar.user'),
                'pass' => (string) config('europcargroup.europcar.password'),
            ],
            'keddy' => [
                'user' => (string) config('europcargroup.keddy.user'),
                'pass' => (string) config('europcargroup.keddy.password'),
            ],
            'fox' => [
                'user' => (string) config('europcargroup.fox.user'),
                'pass' => (string) config('europcargroup.fox.password'),
            ],
        ];

        $this->credsDpa = [
            'europcar' => [
                'user' => (string) config('europcargroup.europcar.userDpa'),
                'pass' => (string) config('europcargroup.europcar.passwordDpa'),
            ],
            'keddy' => [
                'user' => (string) config('europcargroup.keddy.userDpa'),
                'pass' => (string) config('europcargroup.keddy.passwordDpa'),
            ],
            'fox' => [
                'user' => (string) config('europcargroup.fox.userDpa'),
                'pass' => (string) config('europcargroup.fox.passwordDpa'),
            ],
        ];

        $this->httpTimeout      = (int) (config('europcargroup.timeout_seconds') ?? 6);
        $this->httpRetries      = (int) (config('europcargroup.retry_times') ?? 2);
        $this->httpRetrySleepMs = (int) (config('europcargroup.retry_sleep_ms') ?? 300);
    }

    // ------------------------------- Auth -------------------------------

    /**
     * Login por marca y estado, devuelve SessionId. Cache corto por 5 minutos.
     */
    private function login(string $brand, bool $isDpa): ?string
    {
        $brand = strtolower($brand);
        $cacheKey = sprintf('europcargrp_session_%s_%s', $brand, $isDpa ? 'dpa' : 'std');
        if ($sid = Cache::get($cacheKey)) {
            return is_string($sid) ? $sid : null;
        }

        $creds = $isDpa ? ($this->credsDpa[$brand] ?? null) : ($this->credsStd[$brand] ?? null);
        if (!$creds || ($creds['user'] === '' || $creds['pass'] === '')) {
            Log::warning('Europcar login: missing credentials', ['brand' => $brand, 'dpa' => $isDpa]);
            return null;
        }

        $payload = [
            'method' => 'isCarRental_BookingInterface_Service.LogIn',
            'params' => [
                'ContractId' => $creds['user'],
                'Password'   => $creds['pass'],
                'LanguageId' => 'EN',
            ],
        ];

        try {
            $res = Http::retry($this->httpRetries, $this->httpRetrySleepMs)
                ->timeout($this->httpTimeout)
                ->withHeaders(['Content-Type' => 'application/json'])
                ->post($this->endpoint, $payload);

            if (!$res->successful()) {
                Log::warning('Europcar login non-success', ['brand' => $brand, 'status' => $res->status(), 'body' => $res->json() ?? $res->body()]);
                return null;
            }

            $json = $res->json();
            $sid = Arr::get($json, 'result.SessionId');
            if (!$sid) return null;

            Cache::put($cacheKey, $sid, now()->addMinutes(5));
            return $sid;
        } catch (\Throwable $e) {
            Log::error('Europcar login exception', ['brand' => $brand, 'error' => $e->getMessage()]);
            return null;
        }
    }

    /** Devuelve map brand=>SessionId para un set de marcas. */
    private function loginMany(array $brands, bool $dpaFlags = false): array
    {
        $out = [];
        foreach ($brands as $brand) {
            $out[$brand] = $this->login($brand, $dpaFlags);
        }
        return $out;
    }

    // --------------------------- Disponibilidad ---------------------------

    /**
     * Disponibilidad para el proveedor de la reservación (europcar|keddy|fox).
     * Si $quotation está presente: filtra por modelo exacto; si no, map por categoría MCR.
     * $includeRaw: adjunta availabilityRequest/Response en cada item para persistencia.
     * @return array<int, array|string|object>
     */
    public function getAvailability(array $searchParams, object $reservation, ?object $quotation = null, bool $includeRaw = false): array
    {
        $brand = $this->brandKeyByProviderId((int) $reservation->provider_id);
        if (!$brand) return [];

        $sessionId = $this->login($brand, ($reservation->reservation_state ?? 'dpe') !== 'dpe');
        if (!$sessionId) return [];

        $locations = $this->resolveLocations($searchParams);
        if (!$locations['pickupLocation'] || !$locations['dropoffLocation']) return [];

        $request = [
            'method' => 'isCarRental_BookingInterface_Service.GetCarAvailability',
            'params' => [
                'SessionId'        => $sessionId,
                'CheckOutStationId'=> $locations['pickupLocation'],
                'CheckOutDate'     => sprintf('%sT%s:00', $searchParams['pickupDate'], $searchParams['pickupTime']),
                'CheckInStationId' => $locations['dropoffLocation'],
                'CheckInDate'      => sprintf('%sT%s:00', $searchParams['dropoffDate'], $searchParams['dropoffTime']),
                'Currency'         => 'MXN',
                'DealId'           => 0,
                'BookingNumber'    => '',
            ],
        ];

        $data = $this->rpc($request);
        if (!$data || empty($data['result'])) return [];

        // Guarda o actualiza la "cotización" cruda
        DB::table('europcar_group_quotations')->updateOrInsert(
            ['client_id' => $reservation->client_id],
            [
                'client_id'   => $reservation->client_id,
                'identifier'  => $sessionId,
                'provider_id' => $reservation->provider_id,
                'content'     => json_encode($data['result'], JSON_UNESCAPED_UNICODE),
                'created_date'=> now()->toDateString(),
                'created_time'=> now()->format('H:i:s'),
            ]
        );

        $vehiclesDb = $this->getVehicles();
        $vehiclesByModel = [];
        foreach ($vehiclesDb as $v) { $vehiclesByModel[$v->car_name] = $v; }

        $totalDays = $this->calculateFullDays(
            $searchParams['pickupDate'] . ' ' . $searchParams['pickupTime'],
            $searchParams['dropoffDate'] . ' ' . $searchParams['dropoffTime']
        );

        $items = [];
        $addedCategories = [];
        $available = Arr::get($data, 'result.AvailableCarList', []);

        foreach ($available as $p) {
            $carModel = (string) Arr::get($p, 'Group.CarModel');
            if ($quotation && $carModel !== (string) ($quotation->provider_car_name ?? '')) {
                continue;
            }

            if (!isset($vehiclesByModel[$carModel])) {
                continue; // sólo mapeados a catálogo MCR
            }

            $veh = $vehiclesByModel[$carModel];
            if (in_array($veh->category, $addedCategories, true)) {
                continue; // 1 por categoría
            }
            $addedCategories[] = $veh->category;

            $item = (object) [
                'vehicleName'        => $veh->car_name_mcr,
                'vehicleCategory'    => $veh->category,
                'vehicleDescription' => $veh->descripccion,
                'vehicleAcriss'      => $veh->cAcriss,
                'providerId'         => self::PROVIDERS[$brand]['id'],
                'providerName'       => self::PROVIDERS[$brand]['name'],
                'pickupOfficeId'     => $locations['pickupOfficeId'],
                'dropoffOfficeId'    => $locations['dropoffOfficeId'],
                'totalDays'          => $totalDays,
                'netRate'            => (float) Arr::get($p, 'CarValuation.Total', 0) / max(1, $totalDays),
                'vehicleImage'       => $veh->image,
                'vehicleId'          => $veh->vehicle_id,
                'vehicleType'        => $veh->vehicle_type,
                'sessionId'          => $sessionId,
                'bookId'             => Arr::get($p, 'BookId'),
                'providerCarModel'   => $carModel,
            ];

            if ($includeRaw) {
                $item->availabilityRequest  = json_encode($request, JSON_UNESCAPED_UNICODE);
                $item->availabilityResponse = json_encode($data, JSON_UNESCAPED_UNICODE);
            }

            $items[] = $item;
        }

        // Si no hubo filtro por quotation y encontramos un match por modelo, guardamos bookId + modelo
        if (!$quotation && !empty($items)) {
            DB::table('europcar_group_quotations')->updateOrInsert(
                ['client_id' => $reservation->client_id],
                [
                    'book_id'            => $items[0]->bookId,
                    'provider_car_name'  => $items[0]->providerCarModel,
                ]
            );
        }

        return $items;
    }

    /** Disponibilidad para varias marcas a la vez (pool). */
    public function getAvailabilityForAllProviders(array $searchParams, bool $includeRaw = false): array
    {
        $brands = array_keys(self::PROVIDERS);
        $sessionIds = $this->loginMany($brands, false);
        $locations = $this->resolveLocations($searchParams);
        if (!$locations['pickupLocation'] || !$locations['dropoffLocation']) return [];

        $requests = [];
        foreach ($brands as $brand) {
            if (!$sessionIds[$brand]) continue;
            $requests[$brand] = [
                'method' => 'isCarRental_BookingInterface_Service.GetCarAvailability',
                'params' => [
                    'SessionId'         => $sessionIds[$brand],
                    'CheckOutStationId' => $locations['pickupLocation'],
                    'CheckOutDate'      => sprintf('%sT%s:00', $searchParams['pickupDate'], $searchParams['pickupTime']),
                    'CheckInStationId'  => $locations['dropoffLocation'],
                    'CheckInDate'       => sprintf('%sT%s:00', $searchParams['dropoffDate'], $searchParams['dropoffTime']),
                    'Currency'          => 'MXN',
                    'DealId'            => 0,
                    'BookingNumber'     => '',
                ],
            ];
        }

        $responses = $this->rpcPool($requests);
        return $this->buildMatchListsByBrand($responses, $sessionIds, $locations, $searchParams, $includeRaw);
    }

    /** Sólo el provider económico (actualmente FOX en original). */
    public function getAvailabilityForCheapestProvider(array $searchParams, bool $includeRaw = false): array
    {
        $brands    = ['fox']; // se puede ampliar a reglas dinámicas
        $sessionIds= $this->loginMany($brands, false);
        $locations = $this->resolveLocations($searchParams);
        if (!$locations['pickupLocation'] || !$locations['dropoffLocation']) return [];

        $requests = [];
        foreach ($brands as $brand) {
            if (!$sessionIds[$brand]) continue;
            $requests[$brand] = [
                'method' => 'isCarRental_BookingInterface_Service.GetCarAvailability',
                'params' => [
                    'SessionId'         => $sessionIds[$brand],
                    'CheckOutStationId' => $locations['pickupLocation'],
                    'CheckOutDate'      => sprintf('%sT%s:00', $searchParams['pickupDate'], $searchParams['pickupTime']),
                    'CheckInStationId'  => $locations['dropoffLocation'],
                    'CheckInDate'       => sprintf('%sT%s:00', $searchParams['dropoffDate'], $searchParams['dropoffTime']),
                    'Currency'          => 'MXN',
                    'DealId'            => 0,
                    'BookingNumber'     => '',
                ],
            ];
        }

        $responses = $this->rpcPool($requests);
        return $this->buildMatchListsByBrand($responses, $sessionIds, $locations, $searchParams, $includeRaw);
    }

    /** Construye listas por marca a partir de respuestas RPC. */
    private function buildMatchListsByBrand(array $responses, array $sessionIds, array $locations, array $searchParams, bool $includeRaw): array
    {
        $vehiclesDb = $this->getVehicles();
        $vehiclesByModel = [];
        foreach ($vehiclesDb as $v) { $vehiclesByModel[$v->car_name] = $v; }

        $totalDays = $this->calculateFullDays(
            $searchParams['pickupDate'] . ' ' . $searchParams['pickupTime'],
            $searchParams['dropoffDate'] . ' ' . $searchParams['dropoffTime']
        );

        $out = [];
        foreach ($responses as $brand => $payload) {
            $out[$brand] = [];
            if (!$payload || empty($payload['result'])) continue;

            // Persistimos crudo por marca
            // DB::table('europcar_group_quotations')->insert([
            //     'identifier'   => $sessionIds[$brand],
            //     'provider_id'  => self::PROVIDERS[$brand]['id'],
            //     'content'      => json_encode($payload['result'], JSON_UNESCAPED_UNICODE),
            //     'created_date' => now()->toDateString(),
            //     'created_time' => now()->format('H:i:s'),
            // ]);

            $addedCategories = [];
            foreach (Arr::get($payload, 'result.AvailableCarList', []) as $p) {
                Log::info('EUROPCAR - ' . json_encode($p));
                $carModel = (string) Arr::get($p, 'Group.CarModel');
                if (!isset($vehiclesByModel[$carModel])) continue;

                $veh = $vehiclesByModel[$carModel];
                if (in_array($veh->category, $addedCategories, true)) continue;
                $addedCategories[] = $veh->category;

                $dropoff = (float) Arr::get($p, 'DropOff.DropOffWithTaxIncluded', 0);
                $extraFees = 0.0;

                if ($dropoff > 0) {
                    $extraFees += $dropoff;
                }

                $totalDaysSafe = max(1, (int) $totalDays);

                // Base total del provider
                $baseTotal = (float) Arr::get($p, 'CarValuation.Total', 0);

                // Total con extras (dropoff, etc.)
                $totalWithExtras = $baseTotal + $extraFees;

                // netRate = total por día (incluyendo extras)
                $netRatePerDay = $totalWithExtras / $totalDaysSafe;

                $item = (object) [
                    'vehicleName'        => $veh->car_name_mcr,
                    'vehicleCategory'    => $veh->category,
                    'vehicleDescription' => $veh->descripccion,
                    'vehicleAcriss'      => $veh->cAcriss,
                    'providerId'         => self::PROVIDERS[$brand]['id'],
                    'providerName'       => self::PROVIDERS[$brand]['name'],
                    'pickupOfficeId'     => $locations['pickupOfficeId'],
                    'dropoffOfficeId'    => $locations['dropoffOfficeId'],
                    'totalDays'          => $totalDaysSafe,
                    'netRate'            => $netRatePerDay,
                    'extrasIncluded'     => $extraFees,
                    'vehicleImage'       => $veh->image,
                    'vehicleId'          => $veh->vehicle_id,
                    'vehicleType'        => $veh->vehicle_type,
                    'sessionId'          => $sessionIds[$brand],
                    'bookId'             => Arr::get($p, 'BookId'),
                    'providerCarModel'   => $carModel,
                ];

                if ($includeRaw) {
                    $item->availabilityRequest  = json_encode(['brand' => $brand], JSON_UNESCAPED_UNICODE);
                    $item->availabilityResponse = json_encode($payload, JSON_UNESCAPED_UNICODE);
                }

                $out[$brand][] = $item;
            }

        }
        return $out;
    }

    // --------------------------- Confirmación ---------------------------

    /** Confirma todas las reservas pendientes para marcas del grupo. */
    public function confirmBookings(): void
    {
        $reservations = DB::table('reservaciones')
            ->select([
                'clientes.id as client_id',
                'clientes.token_id as token_id',
                'reservaciones.id as reservation_id',
                'clientes.nombre as name',
                'clientes.apellido as lastname',
                'reservaciones.proveedor as provider_id',
                'reservaciones.estado as reservation_state',
                'reservaciones.fechaRecoger as pickup_date',
                'reservaciones.horaRecoger as pickup_time',
                'reservaciones.fechaDejar as dropoff_date',
                'reservaciones.horaDejar as dropoff_time',
                'pickup_provider_location.code as pickup_location',
                'dropoff_provider_location.code as dropoff_location',
                'auto_clientes.categoria as category_id',
            ])
            ->join('clientes', 'clientes.id', '=', 'reservaciones.id_cliente')
            ->join('auto_clientes', 'auto_clientes.id_cliente', '=', 'reservaciones.id_cliente')
            ->leftJoin('provider_locations as pickup_provider_location', 'pickup_provider_location.mcr_office_id', '=', 'reservaciones.id_direccion')
            ->leftJoin('provider_locations as dropoff_provider_location', 'dropoff_provider_location.mcr_office_id', '=', 'reservaciones.id_direccion_dropoff')
            ->where('clientes.token_id', '!=', '')
            ->whereIn('reservaciones.proveedor', array_column(self::PROVIDERS, 'id'))
            ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
            ->where('no_confirmacion', '')
            ->get();

        foreach ($reservations as $reservation) {
            $this->confirmBooking($reservation->token_id, $reservation);
        }
    }

    /** Confirma una reserva por token; opcionalmente recibe la reservación ya cargada. */
    public function confirmBooking(string $tokenId, ?object $reservation = null)
    {
        if (!$reservation) {
            $reservation = DB::table('reservaciones')
                ->select([
                    'clientes.id as client_id',
                    'clientes.token_id as token_id',
                    'reservaciones.id as reservation_id',
                    'clientes.nombre as name',
                    'clientes.apellido as lastname',
                    'reservaciones.proveedor as provider_id',
                    'reservaciones.estado as reservation_state',
                    'reservaciones.fechaRecoger as pickup_date',
                    'reservaciones.horaRecoger as pickup_time',
                    'reservaciones.fechaDejar as dropoff_date',
                    'reservaciones.horaDejar as dropoff_time',
                    'pickup_provider_location.code as pickup_location',
                    'dropoff_provider_location.code as dropoff_location',
                    'auto_clientes.categoria as category_id',
                ])
                ->join('clientes', 'clientes.id', '=', 'reservaciones.id_cliente')
                ->join('auto_clientes', 'auto_clientes.id_cliente', '=', 'reservaciones.id_cliente')
                ->leftJoin('provider_locations as pickup_provider_location', 'pickup_provider_location.mcr_office_id', '=', 'reservaciones.id_direccion')
                ->leftJoin('provider_locations as dropoff_provider_location', 'dropoff_provider_location.mcr_office_id', '=', 'reservaciones.id_direccion_dropoff')
                ->where('clientes.token_id', $tokenId)
                ->whereIn('reservaciones.proveedor', array_column(self::PROVIDERS, 'id'))
                ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
                ->where('no_confirmacion', '')
                ->first();
        }

        if (!$reservation) return '';

        $quotation = DB::table('europcar_group_quotations')
            ->where('provider_id', $reservation->provider_id)
            ->where('client_id', $reservation->client_id)
            ->first();

        $searchParams = [
            'pickupLocation' => $reservation->pickup_location,
            'dropoffLocation'=> $reservation->dropoff_location,
            'pickupDate'     => $reservation->pickup_date,
            'pickupTime'     => $reservation->pickup_time,
            'dropoffDate'    => $reservation->dropoff_date,
            'dropoffTime'    => $reservation->dropoff_time,
        ];

        $availability = $this->getAvailability($searchParams, $reservation, $quotation);
        if (empty($availability)) return '';

        $selected = $availability[0];
        $response = $this->requestBookingConfirmation(
            (string) $selected->sessionId,
            (string) $selected->bookId,
            (string) $reservation->name,
            (string) $reservation->lastname,
            (string) $reservation->token_id
        );

        if (!$response || !Arr::get($response, 'result.BookingNumber')) return '';

        return $this->assignBookingNumber($response, $reservation);
    }

    public function requestBookingConfirmation(string $sessionId, string $bookId, string $name, string $lastname, string $tokenId): ?array
    {
        $payload = [
            'method' => 'isCarRental_BookingInterface_Service.ConfirmBooking',
            'params' => [
                'SessionId'             => $sessionId,
                'BookId'                => $bookId,
                'Title'                 => '-',
                'Name'                  => $name,
                'Surname'               => $lastname,
                'EMail'                 => '-',
                'Telephone'             => '-',
                'Address'               => '-',
                'PostalCode'            => '-',
                'City'                  => '-',
                'State'                 => '-',
                'Country'               => 'MX',
                'Flight'                => '',
                'Remarks'               => '',
                'ExternalBookingNumber' => $tokenId,
            ],
        ];

        $data = $this->rpc($payload);
        return $data ?: null;
    }

    public function assignBookingNumber(array $responseData, object $reservation): string
    {
        $bookingNumber = (string) Arr::get($responseData, 'result.BookingNumber', '');
        if ($bookingNumber === '') return '';

        DB::table('reservaciones')
            ->where('id_cliente', $reservation->client_id)
            ->update(['no_confirmacion' => $bookingNumber]);

        DB::table('europcar_group_quotations')
            ->where('client_id', $reservation->client_id)
            ->update(['confirmation' => json_encode($responseData['result'], JSON_UNESCAPED_UNICODE)]);

        return $bookingNumber;
    }

    public function getStationList(string $stationType /* CheckOut|CheckIn */): ?array
    {

        $sessionId = $this->login('europcar', false);

        $data = $this->rpc([
            'method' => 'isCarRental_BookingInterface_Service.GetStationList',
            'params' => [
                'SessionId'   => $sessionId,
                'StationType' => $stationType,
            ],
        ]);

        return $data['result'] ?? null; // TIStationList
    }

    // --------------------------- Utilidades ---------------------------

    /** JSON-RPC simple. */
    private function rpc(array $payload): ?array
    {
        try {
            $res = Http::retry($this->httpRetries, $this->httpRetrySleepMs)
                ->timeout($this->httpTimeout)
                ->withHeaders(['Content-Type' => 'application/json'])
                ->post($this->endpoint, $payload);

            if (!$res->successful()) {
                Log::warning('Europcar RPC non-success', ['status' => $res->status(), 'body' => $res->json() ?? $res->body()]);
                return null;
            }
            return $res->json();
        } catch (\Throwable $e) {
            Log::error('Europcar RPC exception', ['error' => $e->getMessage()]);
            return null;
        }
    }

    /** Ejecuta múltiples RPC en paralelo usando Http::pool. */
    private function rpcPool(array $requests): array
    {
        $responses = Http::pool(function ($pool) use ($requests) {
            foreach ($requests as $key => $payload) {
                $pool->as($key)
                    ->withHeaders(['Content-Type' => 'application/json'])
                    ->timeout($this->httpTimeout)
                    ->post($this->endpoint, $payload);
            }
        });

        $out = [];
        foreach ($requests as $key => $_) {
            $resp = $responses[$key] ?? null;
            $out[$key] = ($resp && method_exists($resp, 'successful') && $resp->successful()) ? ($resp->json() ?? null) : null;
        }
        return $out;
    }

    /** Resuelve oficinas para el grupo (usa fk_provider=1 ya que comparten red). */
    private function resolveLocations(array $searchParams): array
    {

        // Caso 1: vienen explícitos desde la reservación
        if (isset($searchParams['pickupLocation'], $searchParams['dropoffLocation'], $searchParams['pickupOfficeId'], $searchParams['dropoffOfficeId'])) {
            return [
                'pickupLocation'  => (string) $searchParams['pickupLocation'],
                'dropoffLocation' => (string) $searchParams['dropoffLocation'],
                'pickupOfficeId'  => (int) $searchParams['pickupOfficeId'],
                'dropoffOfficeId' => (int) $searchParams['dropoffOfficeId'],
            ];
        }

        $cacheKey = 'europcargrp_locations_' . md5(json_encode($searchParams));
        return Cache::remember($cacheKey, now()->addDays(7), function () use ($searchParams) {
            if (empty($searchParams['IATA'])) {
                return [
                    'pickupLocation'  => null,
                    'dropoffLocation' => null,
                    'pickupOfficeId'  => null,
                    'dropoffOfficeId' => null,
                ];
            }

            $q = DB::table('provider_locations')
                ->where('fk_provider', 1) // red compartida
                ->where('mcr_code', $searchParams['IATA']);

            $pickupType = ($searchParams['pickupLocation'] ?? 'Aeropuerto') === 'Aeropuerto' ? 'Airport' : 'City';
            $q->where('location', $pickupType);
            $loc = $q->first();

            if (!$loc) {
                return [
                    'pickupLocation'  => null,
                    'dropoffLocation' => null,
                    'pickupOfficeId'  => null,
                    'dropoffOfficeId' => null,
                ];
            }

            return [
                'pickupLocation'  => (string) $loc->code,
                'dropoffLocation' => (string) $loc->code,
                'pickupOfficeId'  => (int) $loc->mcr_office_id,
                'dropoffOfficeId' => (int) $loc->mcr_office_id,
            ];
        });
    }

    /** Cachea vehículos para el grupo (catálogo de mapeo). */
    private function getVehicles(): \Illuminate\Support\Collection
    {
        return Cache::remember('group_europcar_vehicles', now()->addDays(7), function () {
            return DB::table('provider_vehicles')
                ->join('gps_categorias', 'gps_categorias.id', '=', 'provider_vehicles.category_id')
                ->join('gps_autos_copy', 'gps_autos_copy.id_gps_categorias', '=', 'provider_vehicles.category_id')
                ->select(
                    'gps_categorias.categoria as category',
                    'gps_categorias.id as category_id',
                    'gps_categorias.descripccion',
                    'gps_categorias.cAcriss',
                    'provider_vehicles.acriss',
                    'provider_vehicles.auto as car_name',
                    'gps_categorias.tipo as vehicle_type',
                    'gps_autos_copy.auto as car_name_mcr',
                    'gps_autos_copy.camino as image',
                    'gps_autos_copy.id as vehicle_id'
                )
                ->where('fk_provider', '1')
                ->groupBy('provider_vehicles.category_id')
                ->orderBy('gps_categorias.categoria', 'ASC')
                ->get();
        });
    }

    /** Días completos (ceil). */
    public function calculateFullDays(string $startDate, string $endDate): int
    {
        $start = Carbon::parse($startDate);
        $end   = Carbon::parse($endDate);
        return (int) ceil($start->diffInMinutes($end) / 1440);
    }

    // --------------------------- Helpers ---------------------------

    private function brandKeyByProviderId(int $providerId): ?string
    {
        foreach (self::PROVIDERS as $key => $meta) {
            if ($meta['id'] === $providerId) return $key;
        }
        return null;
    }
}
