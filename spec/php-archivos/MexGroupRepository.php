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
 * Integración con Mex Rent a Car (providerId = 28)
 * - Token con cache y renovación segura
 * - Llamadas HTTP con retry/timeout
 * - getAvailability con payload "ligero" y opción includeRaw para guardar/confirmar
 * - Normaliza respuesta de tarifas y mapeo a categorías MCR
 * - Flujos de confirmación y cancelación robustos
 */
class MexGroupRepository
{
    private const PROVIDER_ID = 28;

    private string $user;
    private string $password;
    private string $endpoint; // base URL, termina con '/'

    private int $httpTimeout;
    private int $httpRetries;
    private int $httpRetrySleepMs;

    public function __construct()
    {
        $this->user     = (string) config('mexgroup.mex.user');
        $this->password = (string) config('mexgroup.mex.password');
        $this->endpoint = rtrim((string) config('mexgroup.endpoint'), '/') . '/';

        $this->httpTimeout      = (int) (config('mexgroup.timeout_seconds') ?? 6);
        $this->httpRetries      = (int) (config('mexgroup.retry_times') ?? 2);
        $this->httpRetrySleepMs = (int) (config('mexgroup.retry_sleep_ms') ?? 300);
    }

    // ----------------------------- Auth -----------------------------

    /** Obtiene token (cacheado hasta su expiración menos margen). */
    private function getToken(): string
    {
        $cacheKey = 'mex_group_token_v2';
        $cached = Cache::get($cacheKey);
        if (is_string($cached) && $cached !== '') {
            return $cached;
        }

        $login = $this->login();
        if ($login['status'] !== 'success') {
            Log::error('MEX login failed', ['message' => $login['message'] ?? null, 'details' => $login['details'] ?? null]);
            throw new \RuntimeException('Failed to retrieve token');
        }

        $token     = (string) $login['token'];
        $expiredAt = Carbon::parse((string) $login['expired_at']);
        // guarda con margen de 2 minutos
        $ttl = $expiredAt->subMinutes(2);
        Cache::put($cacheKey, $token, $ttl);
        return $token;
    }

    /** Login broker -> token + expiración. */
    public function login(): array
    {
        try {
            $res = Http::retry($this->httpRetries, $this->httpRetrySleepMs)
                ->timeout($this->httpTimeout)
                ->withHeaders(['Content-Type' => 'application/json'])
                ->post($this->endpoint . 'api/brokers/login', [
                    'user'     => $this->user,
                    'password' => $this->password,
                ]);

            if (!$res->successful()) {
                return [
                    'status'  => 'error',
                    'message' => $res->reason(),
                    'details' => $res->json() ?? $res->body(),
                ];
            }

            $json = $res->json();
            if (Arr::get($json, 'type') === 'success') {
                return [
                    'status'     => 'success',
                    'token'      => Arr::get($json, 'data.token'),
                    'expired_at' => Arr::get($json, 'data.expiredAt'),
                ];
            }

            return [
                'status'  => 'error',
                'message' => Arr::get($json, 'message', 'Unexpected error'),
            ];
        } catch (\Throwable $e) {
            Log::error('MEX login exception', ['error' => $e->getMessage()]);
            return ['status' => 'error', 'message' => 'Exception during login'];
        }
    }

    // ------------------------ Disponibilidad ------------------------

    /**
     * Devuelve lista de coincidencias internas (ligero por defecto).
     * Si $includeRaw = true, adjunta availabilityRequest/Response en cada item
     * para persistirlos junto con la reserva.
     * @return array<int, object>
     */
    public function getAvailability(array $searchParams, bool $includeRaw = false): array
    {
        $locations = $this->resolveLocations($searchParams);
        if (!$locations['pickupLocation'] || !$locations['dropoffLocation']) {
            return [];
        }

        $params = $this->buildRatesParams($searchParams, $locations);
        $rates  = $this->getRates($params);
        if ($rates['status'] !== 'success') {
            return [];
        }

        $vehiclesDb = $this->getVehicles();

        // --- Helpers para normalizar y crear llave (name|acriss) ---
        $normalize = function (?string $s) {
            $s = $s ?? '';
            $s = preg_replace('/\s+/', ' ', trim($s));
            return mb_strtolower($s);
        };
        $makeKey = function ($name, $acriss) use ($normalize) {
            // Requerimos AMBOS, como en tu primer ejemplo
            if (!$name || !$acriss) return null;
            return $normalize($name) . '|' . $normalize($acriss);
        };

        // --- Índice por (car_name + acriss) ---
        // Nota: en tu modelo a veces es "acriss" y otras "cAcriss".
        $vehiclesByNameAcriss = []; // key = "<name>|<acriss>" => $vehicle
        foreach ($vehiclesDb as $v) {
            $name   = $v->car_name ?? null;
            $acriss = $v->acriss ?? ($v->cAcriss ?? null);
            $key    = $makeKey($name, $acriss);
            if ($key) {
                $vehiclesByNameAcriss[$key] = $v;
            }
        }

        $totalDays = $this->calculateFullDays(
            $searchParams['pickupDate'] . ' ' . $searchParams['pickupTime'],
            $searchParams['dropoffDate'] . ' ' . $searchParams['dropoffTime']
        );

        $matchList = [];
        $addedCategories = []; // si quieres seguir mostrando 1 por categoría

        $data = $rates['data']; // arreglo de vehículos de la API MEX
        foreach ($data as $pv) {
            $modelDesc = (string) Arr::get($pv, 'class.modelDesc', '');
            $classCode = (string) Arr::get($pv, 'class.classCode', '');

            // validar por nombre + ACRISS
            $key = $makeKey($modelDesc, $classCode);
            if (!$key || !isset($vehiclesByNameAcriss[$key])) {
                continue; // no mapeado
            }

            $vehicle = $vehiclesByNameAcriss[$key];

            // Mantener lógica "1 por categoría"
            if (in_array($vehicle->category, $addedCategories, true)) {
                continue;
            }
            $addedCategories[] = $vehicle->category;

            // Calcular netRate con extras.totalEstimated
            $baseTotal         = (float) Arr::get($pv, 'pricing.total', 0);
            $extrasBreakdown   = Arr::get($pv, 'pricing.extras.breakdown', []);
            $extrasTotalEstim  = 0.0;

            if (is_array($extrasBreakdown)) {
                foreach ($extrasBreakdown as $extra) {
                    $extrasTotalEstim += (float) Arr::get($extra, 'calculations.totalEstimated', 0);
                }
            }

            $grandTotal = $baseTotal;
            // + $extrasTotalEstim; already included in grandTotal
            $netPerDay  = $totalDays > 0 ? ($grandTotal / $totalDays) : 0.0;

            $item = (object) [
                'vehicleName'        => $vehicle->car_name_mcr,
                'vehicleCategory'    => $vehicle->category,
                'vehicleDescription' => $vehicle->descripccion,
                'vehicleAcriss'      => $vehicle->cAcriss ?? ($vehicle->acriss ?? null),
                'providerId'         => self::PROVIDER_ID,
                'providerName'       => 'MEX RENT A CAR',
                'pickupOfficeId'     => $locations['pickupOfficeId'],
                'dropoffOfficeId'    => $locations['dropoffOfficeId'],
                'totalDays'          => $totalDays,
                'netRate'            => $netPerDay, // incluye extras.totalEstimated
                'extrasIncluded'     => ($extrasTotalEstim / $totalDays), 
                'vehicleImage'       => $vehicle->image,
                'vehicleId'          => $vehicle->vehicle_id ?? null,
                'vehicleType'        => $vehicle->vehicle_type ?? null,
                'rateCode'           => (string) Arr::get($pv, 'rateCode'),
                'rateId'             => (string) Arr::get($pv, 'rateID'),
                'classType'          => $classCode,
                'corporateSetup'     => Arr::get($params, 'corporate_setup'),
            ];

            if ($includeRaw) {
                $item->availabilityRequest  = json_encode($params, JSON_UNESCAPED_UNICODE);
                $item->availabilityResponse = json_encode($data, JSON_UNESCAPED_UNICODE);
            }

            $matchList[] = $item;
        }

        return $matchList;
    }


    /** Construye parámetros para rates. */
    private function buildRatesParams(array $searchParams, array $locations): array
    {
        $params = [
            'pickup_location' => $locations['pickupLocation'],
            'dropoff_location'=> $locations['dropoffLocation'],
            'pickup_date'     => sprintf('%sT%s:00', $searchParams['pickupDate'], $searchParams['pickupTime']),
            'dropoff_date'    => sprintf('%sT%s:00', $searchParams['dropoffDate'], $searchParams['dropoffTime']),
            'rate_code'       => $searchParams['rate_code']       ?? 'IPAMOM',
            'currency'        => $searchParams['currency']        ?? 'MXN',
            'corporate_setup' => $searchParams['corporate_setup'] ?? '00108',
        ];

        if (!empty($searchParams['carType'])) {
            $params['class'] = (string) $searchParams['carType'];
        }
        return $params;
    }

    /** Llama a /booking-engine/rates y devuelve status + data. */
    public function getRates(array $params): array
    {
        try {
            $token = $this->getToken();
            $res = Http::retry($this->httpRetries, $this->httpRetrySleepMs)
                ->timeout($this->httpTimeout)
                ->withHeaders([
                    'Content-Type'  => 'application/json',
                    'Accept'        => 'application/json',
                    'Authorization' => 'Bearer ' . $token,
                ])->post($this->endpoint . 'api/brokers/booking-engine/rates', $params);

            if (!$res->successful()) {
                Log::warning('MEX rates non-success', ['status' => $res->status(), 'body' => $res->json() ?? $res->body()]);
                return ['status' => 'error', 'message' => 'API returned error', 'status_code' => $res->status()];
            }

            $json = $res->json();
            if (isset($json['data'])) {
                return ['status' => 'success', 'availability_request' => $params, 'data' => $json['data']];
            }

            return ['status' => 'error', 'message' => 'Unexpected response structure', 'details' => $json];
        } catch (\Throwable $e) {
            Log::error('MEX rates exception', ['error' => $e->getMessage()]);
            return ['status' => 'error', 'message' => 'Exception occurred'];
        }
    }

    // --------------------- Confirmación / Cancelación ---------------------

    /** Confirma todas las reservas pendientes para provider 28. */
    public function confirmBookings(): int
    {
        set_time_limit(0);

        $reservations = $this->findConfirmableReservations();
        $confirmed = 0;

        foreach ($reservations as $reservation) {
            try {
                if ($this->confirmSingleReservation($reservation)) {
                    $confirmed++;
                }
            } catch (\Throwable $e) {
                Log::error('MEX confirmBookings: reservation failed', [
                    'client_id' => $reservation->client_id,
                    'error'     => $e->getMessage(),
                ]);
            }
        }

        return $confirmed;
    }

    /** Confirma una reserva por token. */
    public function confirmBooking(string $tokenId): array
    {
        $reservation = $this->findSingleConfirmableReservationByToken($tokenId);
        if (!$reservation) {
            return ['status' => 'error', 'message' => 'Reservation not found.'];
        }

        try {
            $ok = $this->confirmSingleReservation($reservation, returnPayload: true);
            return is_array($ok) ? $ok : ($ok ? ['status' => 'success'] : ['status' => 'error']);
        } catch (\Throwable $e) {
            Log::error('MEX confirmBooking exception', ['error' => $e->getMessage()]);
            return ['status' => 'error', 'message' => 'Confirmation failed.'];
        }
    }

    /** Cancela por token. */
    public function cancelBooking(string $tokenId): array
    {
        $reservation = DB::table('reservaciones')
            ->select(['reservaciones.no_confirmacion'])
            ->join('clientes', 'clientes.id', 'reservaciones.id_cliente')
            ->where('reservaciones.proveedor', self::PROVIDER_ID)
            ->where('clientes.token_id', $tokenId)
            ->first();

        if (!$reservation || empty($reservation->no_confirmacion)) {
            return ['status' => 'error', 'message' => 'Booking not found or already confirmed.'];
        }

        try {
            $token = $this->getToken();
            $res = Http::retry($this->httpRetries, $this->httpRetrySleepMs)
                ->timeout($this->httpTimeout)
                ->withHeaders([
                    'Accept'       => 'application/json',
                    'Content-Type' => 'application/json',
                    'Authorization'=> 'Bearer ' . $token,
                ])->post($this->endpoint . 'api/brokers/booking-engine/cancel', [
                    'no_confirmation' => $reservation->no_confirmacion,
                ]);

            if (!$res->successful()) {
                return [
                    'status'  => 'error',
                    'message' => 'Unexpected error from API',
                    'details' => $res->json() ?? $res->body(),
                ];
            }

            $json = $res->json();
            return [
                'status'  => 'success',
                'message' => 'Booking cancelled successfully.',
                'data'    => $json['data'] ?? null,
            ];
        } catch (\Throwable $e) {
            Log::error('MEX cancel exception', ['error' => $e->getMessage()]);
            return ['status' => 'error', 'message' => 'Exception occurred'];
        }
    }

    /**
     * Confirmación: intenta usar cotización; si no existe, deriva de disponibilidad por ACRISS.
     * Si $returnPayload = true, devuelve el payload de confirmación en éxito.
     */
    private function confirmSingleReservation(object $reservation, bool $returnPayload = false)
    {
        $quotation = DB::table('mex_group_quotations')->where('client_id', $reservation->client_id)->first();

        if (!$quotation) {
            // Derivar por ACRISS contra disponibilidad
            $carsDb = DB::table('provider_vehicles')
                ->select('acriss')
                ->where('fk_provider', self::PROVIDER_ID)
                ->where('provider_vehicles.category_id', $reservation->category_id)
                ->get();

            if ($carsDb->isNotEmpty()) {
                $searchParams = [
                    'pickupDate'     => $reservation->pickup_date,
                    'pickupTime'     => $reservation->pickup_time,
                    'dropoffDate'    => $reservation->dropoff_date,
                    'dropoffTime'    => $reservation->dropoff_time,
                    'IATA'           => $reservation->destination_code,
                    'pickupLocation' => $reservation->pickup_location_code,
                    'dropoffLocation'=> $reservation->dropoff_location_code,
                    'pickupOfficeId' => $reservation->pickup_location_mcr_office_id,
                    'dropoffOfficeId'=> $reservation->dropoff_location_mcr_office_id,
                ];

                $cars = $this->getAvailability($searchParams); // ligero
                if (!empty($cars)) {
                    foreach ($cars as $car) {
                        foreach ($carsDb as $carDb) {
                            if (($car->classType ?? '') === $carDb->acriss) {
                                $quotation = (object) [
                                    'rate_code' => $car->rateCode,
                                    'class'     => $car->classType,
                                    'rate_id'   => $car->rateId,
                                ];
                                break 2;
                            }
                        }
                    }
                }
            }
        }

        if (!$quotation) {
            Log::warning('MEX: quotation not found', ['client_id' => $reservation->client_id]);
            return false;
        }

        $payload = [
            'pickup_location' => $reservation->pickup_location_code,
            'dropoff_location'=> $reservation->dropoff_location_code,
            'pickup_date'     => sprintf('%sT%s:00', $reservation->pickup_date, $reservation->pickup_time),
            'dropoff_date'    => sprintf('%sT%s:00', $reservation->dropoff_date, $reservation->dropoff_time),
            'rate_code'       => (string) $quotation->rate_code,
            'class'           => (string) $quotation->class,
            'id_rate'         => (string) $quotation->rate_id,
            'email'           => 'noreply@mexicocarrental.com.mx',
            'first_name'      => (string) $reservation->name,
            'last_name'       => (string) $reservation->last_name,
            'airline'         => (string) $reservation->airline,
            'flight'          => (string) $reservation->flight,
            'extras'          => isset($quotation->extras) ? array_filter(array_map('trim', explode(',', (string) $quotation->extras))) : [],
            'chain_code'      => 'MX',
        ];

        if ($reservation->status === 'dpa') {
            $payload['corporate_setup'] = '00108';
        }

        try {
            $token = $this->getToken();
            $res = Http::retry($this->httpRetries, $this->httpRetrySleepMs)
                ->timeout($this->httpTimeout)
                ->withHeaders([
                    'Accept'        => 'application/json',
                    'Authorization' => 'Bearer ' . $token,
                    'Content-Type'  => 'application/json',
                ])->post($this->endpoint . 'api/brokers/booking-engine/reserve', $payload);

            if (!$res->successful()) {
                Log::warning('MEX reserve non-success', ['status' => $res->status(), 'body' => $res->json() ?? $res->body()]);
                return false;
            }

            $json = $res->json();
            $conf = Arr::get($json, 'data.noConfirmation');
            if (!$conf) {
                Log::warning('MEX reserve: missing confirmation id', ['response' => $json]);
                return false;
            }

            DB::table('reservaciones')
                ->where('id_cliente', $reservation->client_id)
                ->update(['no_confirmacion' => $conf]);

            DB::table('mex_group_quotations')
                ->where('client_id', $reservation->client_id)
                ->update([
                    'confirmation_request'  => json_encode($payload, JSON_UNESCAPED_UNICODE),
                    'confirmation_response' => json_encode($json, JSON_UNESCAPED_UNICODE),
                ]);

            if ($returnPayload) {
                return ['status' => 'success', 'data' => $json['data'] ?? $json];
            }

            return true;
        } catch (\Throwable $e) {
            Log::error('MEX reserve exception', ['error' => $e->getMessage()]);
            return false;
        }
    }

    // ----------------------- Vehículos / Oficinas -----------------------

    /** Cachea vehículos MEX mapeados a categorías MCR. */
    private function getVehicles(): \Illuminate\Support\Collection
    {
        return Cache::remember('group_mex_vehicles', now()->addDays(7), function () {
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
                ->where('fk_provider', (string) self::PROVIDER_ID)
                ->groupBy('provider_vehicles.category_id')
                ->orderBy('gps_categorias.categoria', 'ASC')
                ->get();
        });
    }

    /** Obtiene rates y almacena nuevos modelos en provider_vehicles. */
    public function storeVehicles(array $searchParams): array
    {
        $locations = $this->resolveLocations($searchParams);
        if (!$locations['pickupLocation'] || !$locations['dropoffLocation']) {
            return ['status' => 'error', 'message' => 'Invalid locations'];
        }

        $params = $this->buildRatesParams($searchParams, $locations);
        $rates = $this->getRates($params);
        if ($rates['status'] !== 'success') {
            return ['status' => 'error', 'message' => 'Rates error'];
        }

        $vehicles = $rates['data'];
        foreach ($vehicles as $v) {
            $auto  = (string) Arr::get($v, 'class.modelDesc', '');
            $acriss= (string) Arr::get($v, 'class.classCode', '');
            $trans = (string) Arr::get($v, 'class.transmission', '');
            if ($auto === '') continue;

            $exists = DB::table('provider_vehicles')
                ->where('auto', $auto)
                ->where('fk_provider', self::PROVIDER_ID)
                ->exists();

            if (!$exists) {
                DB::table('provider_vehicles')->insert([
                    'acriss'       => $acriss,
                    'auto'         => $auto,
                    'fk_provider'  => self::PROVIDER_ID,
                    'transmission' => $trans,
                ]);
            }
        }

        return ['status' => 'success', 'message' => 'Vehicles stored successfully.'];
    }

    /** Llama a offices (passthrough). */
    public function storeOffices(): array
    {
        try {
            $token = $this->getToken();
            $res = Http::retry($this->httpRetries, $this->httpRetrySleepMs)
                ->timeout($this->httpTimeout)
                ->withHeaders([
                    'Accept'        => 'application/json',
                    'Content-Type'  => 'application/json',
                    'Authorization' => 'Bearer ' . $token,
                ])->post($this->endpoint . 'api/brokers/offices');

            if (!$res->successful()) {
                return ['status' => 'error', 'message' => 'Offices API error', 'details' => $res->json() ?? $res->body()];
            }

            $json = $res->json();
            if (isset($json['data'])) {
                return ['status' => 'success', 'data' => $json['data']];
            }

            return ['status' => 'error', 'message' => 'Unexpected response structure', 'details' => $json];
        } catch (\Throwable $e) {
            return ['status' => 'error', 'message' => 'Exception occurred: ' . $e->getMessage()];
        }
    }

    // ----------------------------- Utils -----------------------------

    /**
     * Resuelve oficinas: usa valores explícitos si vienen de la reservación, 
     * o consulta por IATA + tipo (Aeropuerto/City) en provider_locations.
     * @return array{pickupLocation:?string,dropoffLocation:?string,pickupOfficeId:?int,dropoffOfficeId:?int}
     */
    private function resolveLocations(array $searchParams): array
    {
        if (isset($searchParams['pickupLocation'], $searchParams['dropoffLocation'], $searchParams['pickupOfficeId'], $searchParams['dropoffOfficeId'])) {
            return [
                'pickupLocation'  => (string) $searchParams['pickupLocation'],
                'dropoffLocation' => (string) $searchParams['dropoffLocation'],
                'pickupOfficeId'  => (int) $searchParams['pickupOfficeId'],
                'dropoffOfficeId' => (int) $searchParams['dropoffOfficeId'],
            ];
        }

        if (!empty($searchParams['IATA'])) {
            $query = DB::table('provider_locations')
                ->where('fk_provider', self::PROVIDER_ID)
                ->where('mcr_code', $searchParams['IATA']);

            $pickupType = ($searchParams['pickupLocation'] ?? 'Aeropuerto') === 'Aeropuerto' ? 'Airport' : 'City';
            $query->where('location', $pickupType);

            $location = $query->first();
            if ($location) {
                return [
                    'pickupLocation'  => (string) $location->code,
                    'dropoffLocation' => (string) $location->code,
                    'pickupOfficeId'  => (int) $location->mcr_office_id,
                    'dropoffOfficeId' => (int) $location->mcr_office_id,
                ];
            }
        }

        return [
            'pickupLocation'  => null,
            'dropoffLocation' => null,
            'pickupOfficeId'  => null,
            'dropoffOfficeId' => null,
        ];
    }

    /** Días completos (ceil). */
    public function calculateFullDays(string $startDate, string $endDate): int
    {
        $start = Carbon::parse($startDate);
        $end   = Carbon::parse($endDate);
        $minutes = $start->diffInMinutes($end);
        return (int) ceil($minutes / 1440);
    }

    // ----------------------------- Queries -----------------------------

    private function findConfirmableReservations()
    {
        return DB::table('reservaciones')
            ->select([
                'reservaciones.estado as status',
                'reservaciones.fechaRecoger as pickup_date',
                'reservaciones.fechaDejar as dropoff_date',
                'reservaciones.horaRecoger as pickup_time',
                'reservaciones.horaDejar as dropoff_time',
                'reservaciones.no_vuelo as flight',
                'reservaciones.aereolinea as airline',
                'reservaciones.pagina as destination_code',
                'reservaciones.id_direccion as pickup_location_mcr_office_id',
                'reservaciones.id_direccion_dropoff as dropoff_location_mcr_office_id',
                'clientes.id as client_id',
                'clientes.nombre as name',
                'clientes.token_id as token_id',
                'clientes.apellido as last_name',
                'pickup_location.code as pickup_location_code',
                'dropoff_location.code as dropoff_location_code',
                'auto_clientes.categoria as category_name',
                'gps_categorias.id as category_id',
            ])
            ->join('clientes', 'clientes.id', 'reservaciones.id_cliente')
            ->join('provider_locations as pickup_location', 'pickup_location.mcr_office_id', 'reservaciones.id_direccion')
            ->join('provider_locations as dropoff_location', 'dropoff_location.mcr_office_id', 'reservaciones.id_direccion_dropoff')
            ->join('auto_clientes', 'auto_clientes.id_cliente', 'reservaciones.id_cliente')
            ->join('gps_categorias', 'gps_categorias.categoria', 'auto_clientes.categoria')
            ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
            ->where('reservaciones.no_confirmacion', '')
            ->where('reservaciones.proveedor', self::PROVIDER_ID)
            ->get();
    }

    private function findSingleConfirmableReservationByToken(string $tokenId)
    {
        return DB::table('reservaciones')
            ->select([
                'reservaciones.estado as status',
                'reservaciones.fechaRecoger as pickup_date',
                'reservaciones.fechaDejar as dropoff_date',
                'reservaciones.horaRecoger as pickup_time',
                'reservaciones.horaDejar as dropoff_time',
                'reservaciones.no_vuelo as flight',
                'reservaciones.aereolinea as airline',
                'reservaciones.pagina as destination_code',
                'reservaciones.id_direccion as pickup_location_mcr_office_id',
                'reservaciones.id_direccion_dropoff as dropoff_location_mcr_office_id',
                'clientes.id as client_id',
                'clientes.nombre as name',
                'clientes.token_id as token_id',
                'clientes.apellido as last_name',
                'pickup_location.code as pickup_location_code',
                'dropoff_location.code as dropoff_location_code',
                'auto_clientes.categoria as category_name',
                'gps_categorias.id as category_id',
            ])
            ->join('clientes', 'clientes.id', 'reservaciones.id_cliente')
            ->join('provider_locations as pickup_location', 'pickup_location.mcr_office_id', 'reservaciones.id_direccion')
            ->join('provider_locations as dropoff_location', 'dropoff_location.mcr_office_id', 'reservaciones.id_direccion_dropoff')
            ->join('auto_clientes', 'auto_clientes.id_cliente', 'reservaciones.id_cliente')
            ->join('gps_categorias', 'gps_categorias.categoria', 'auto_clientes.categoria')
            ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
            ->where('reservaciones.no_confirmacion', '')
            ->where('reservaciones.proveedor', self::PROVIDER_ID)
            ->where('clientes.token_id', $tokenId)
            ->first();

    }
}
