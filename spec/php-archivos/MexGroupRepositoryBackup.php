<?php

namespace App\Repositories;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Cache;
use Illuminate\Database\QueryException;
use Carbon\Carbon;
use Log;
use DB;



class MexGroupRepository
{
    private $user;
    private $password;
    private $endpoint;

    public function __construct()
    {
        $this->user = config('mexgroup.mex.user');
        $this->password = config('mexgroup.mex.password');
        $this->endpoint = config('mexgroup.endpoint');
    }

    private function getToken()
    {
        // Verificar si el token ya está en caché y no ha expirado
        if (Cache::has('mex_group_token') && Cache::has('mex_group_token_expiration')) {
            $expiration = Cache::get('mex_group_token_expiration');
            if (Carbon::now()->lt(Carbon::parse($expiration))) {
                return Cache::get('mex_group_token');
            }
        }
    
        // Si no hay token válido, realizar login
        $loginResponse = $this->login();
    
        if ($loginResponse['status'] === 'success') {
            // Guardar token y expiración en caché
            $token = $loginResponse['token'];
            $expiration = $loginResponse['expired_at'];
    
            Cache::put('mex_group_token', $token, Carbon::parse($expiration));
            Cache::put('mex_group_token_expiration', $expiration, Carbon::parse($expiration));
    
            return $token;
        }
    
        // Si el login falla, registrar el error y continuar
        Log::error('Login failed: ' . ($loginResponse['message'] ?? 'Unknown error'), [
            'details' => $loginResponse['details'] ?? [],
        ]);
    
        throw new \Exception('Failed to retrieve token: ' . ($loginResponse['message'] ?? 'Unknown error'));
    }
    
    public function login()
    {
        $response = Http::withHeaders([
            'Content-Type' => 'application/json',
        ])
        ->timeout(3)
        ->post($this->endpoint . 'api/brokers/login', [
            'user' => $this->user,
            'password' => $this->password,
        ]);
    
        if ($response->successful()) {
            $responseData = $response->json();
            if (isset($responseData['type']) && $responseData['type'] === 'success') {
                return [
                    'status' => 'success',
                    'token' => $responseData['data']['token'],
                    'expired_at' => $responseData['data']['expiredAt'],
                ];
            }
    
            return [
                'status' => 'error',
                'message' => $responseData['message'] ?? 'Unexpected error',
            ];
        }
    
        // Manejo de errores
        return [
            'status' => 'error',
            'message' => $response->reason(),
            'details' => $response->json() ?? $response->body(),
        ];
    }


    public function getAvailability($searchParams) 
    {
        $locations = $this->getLocations($searchParams);

         if (!isset($locations['pickupLocation']) || !isset($locations['dropoffLocation'])) {
            return [];
        }
        $response = $this->getResponse($searchParams, $locations);
        $vehicles = $this->getVehicles();

        if($response['status'] == 'success') {

            $addedCategories = [];
            $matchList = [];

            $vehiclesByCarModel = [];
            foreach ($vehicles as $vehicle) {
                $vehiclesByCarModel[$vehicle->car_name] = $vehicle;
            }

            $totalDays = $this->calculateFullDays($searchParams['pickupDate'] . " " .  $searchParams['pickupTime'], $searchParams['dropoffDate'] . " " .  $searchParams['dropoffTime']);

            foreach ($response['availability_response'] as $providerVehicle) {
                $carModel = $providerVehicle['class']['modelDesc'];

                if (isset($vehiclesByCarModel[$carModel])) {
                    $vehicle = $vehiclesByCarModel[$carModel];

                    if (!in_array($vehicle->category, $addedCategories)) {
                        $addedCategories[] = $vehicle->category;
                        $matchList[] = (object)[
                            'vehicleName' => $vehicle->car_name_mcr,
                            'vehicleCategory' => $vehicle->category,
                            'vehicleDescription' => $vehicle->descripccion,
                            'vehicleAcriss' => $vehicle->cAcriss,
                            'providerId' => 28,
                            'providerName' => 'MEX RENT A CAR',
                            'pickupOfficeId' => $locations['pickupOfficeId'],
                            'dropoffOfficeId' => $locations['dropoffOfficeId'],
                            'totalDays' => $totalDays,
                            'netRate' => $providerVehicle['pricing']['total'] / $totalDays,
                            'vehicleImage' => $vehicle->image,
                            'vehicleId' => $vehicle->vehicle_id,
                            'vehicleType' => $vehicle->vehicle_type,
                            'rateCode' => $providerVehicle['rateCode'],
                            'rateId' => $providerVehicle['rateID'],
                            'corporateSetup' => $response['availability_request']['corporate_setup'] ?? null,
                            'classType' => $providerVehicle['class']['classCode'],
                            'availabilityResponse' => json_encode($response['availability_response']),
                            'availabilityRequest' => json_encode($response['availability_request'])
                        ];
                    }
                }
            }
            return $matchList;
        } else {
            return [];
        }

    }

    public function getResponse($searchParams, $locations)
    {


        $params = [
            "pickup_location" => $locations['pickupLocation'],
            "dropoff_location" => $locations['dropoffLocation'],
            "pickup_date" => "{$searchParams['pickupDate']}T{$searchParams['pickupTime']}:00",
            "dropoff_date" => "{$searchParams['dropoffDate']}T{$searchParams['dropoffTime']}:00",
            "rate_code" => "IPAMOM",
            "currency" => "MXN",
            "corporate_setup" => "00108"
        ];

        $carType = $searchParams['carType'] ?? '';
        if (!empty($carType)) {
            $params['class'] = $carType;
        }

        // Case 1:
        // 🧪 Caso de uso 1: Renta por 1 día sin extras, sin descuento
        $case1 = [
            'pickup_location'   => $locations['pickupLocation'], //location 1
            'dropoff_location'  => $locations['dropoffLocation'], //location 1
            'pickup_date'       => "{$searchParams['pickupDate']}T{$searchParams['pickupTime']}:00", //time1
            'dropoff_date'      => "{$searchParams['dropoffDate']}T{$searchParams['dropoffTime']}:00", //time1
            'rate_code'          => 'IPAMOM',
            'corporate_setup'    => '00108',
            "currency" => "MXN",
        ];

        // 

        // Case2:
        // 🧪 Caso de uso 2: Renta por 7 días sin extras, con descuento por cantidad
        // 21-28 mayo, Guadalajara
        $case2 = [
            'pickup_location'   => $locations['pickupLocation'], //location 2
            'dropoff_location'  => $locations['dropoffLocation'], //location 2
            'pickup_date'       => "{$searchParams['pickupDate']}T{$searchParams['pickupTime']}:00", //time 2
            'dropoff_date'      => "{$searchParams['dropoffDate']}T{$searchParams['dropoffTime']}:00", //time 2
            'rate_code'          => Null,
            'corporate_setup'    => '00108',
            // 'extras'             => [],
            // 'code_discount' => "Quantity Discount",
            // 'class'              => 'ECAR',
            "currency" => "MXN",
        ];

        // Case 3:
        // 🔹 Caso 3: Renta por 18 días, con 1 extra, descuento por porcentaje
        // AD = Additional Driver
        // CUN - MID
        $case3 = [
            'pickup_location'   => $locations['pickupLocation'], //location 3
            'dropoff_location'  => 'MID', //location 4
            'pickup_date'       => "{$searchParams['pickupDate']}T{$searchParams['pickupTime']}:00", //time 2
            'dropoff_date'      => "{$searchParams['dropoffDate']}T{$searchParams['dropoffTime']}:00", //time 2
            'rate_code'          => 'IPAMOM',
            'corporate_setup'    => Null,
            // 'extras'             => ['AD'],
            // 'code_discount' => "Percentage Discount",
            // 'class'              => 'MCAR',
            "currency" => "MXN",
        ];

        // 🔹 Case 4: 
        // Renta por 30 días, con 2 extras, descuento por porcentaje
        // CT2 = Full Coverage Vehicle
        // AGE = Young Driver
        //22 mayo - 21 junio, Merida - Chetumal
        $case4 = [
            'pickup_location'   => $locations['pickupLocation'], //location 4
            'dropoff_location'  => 'CTM', //location 5
            'pickup_date'       => "{$searchParams['pickupDate']}T{$searchParams['pickupTime']}:00", //time 2
            'dropoff_date'      => "{$searchParams['dropoffDate']}T{$searchParams['dropoffTime']}:00", //time 2
            'rate_code'          => 'IPAMOM',
            'corporate_setup'    => '00108',
            // 'extras'             => ['CT2', 'AGE'],
            // 'code_discount' => "Percentage Discount",
            // 'class'              => 'ICAR',
            "currency" => "MXN",
        ];

        // 🔹 Caso 5: 
        // Renta +30 días, con 3 extras, descuento por cantidad
        // Cancun - Cozumel
        $case5 = [
            'pickup_location'   => $locations['pickupLocation'], //location 5
            'dropoff_location'  => 'CZM', //location 6
            'pickup_date'       => "{$searchParams['pickupDate']}T{$searchParams['pickupTime']}:00", //time 2
            'dropoff_date'      => "{$searchParams['dropoffDate']}T{$searchParams['dropoffTime']}:00", //time 2
            'rate_code'          => 'IPAMOM',
            'corporate_setup'    => null,
            // 'extras'             => ['AD', 'CT3', 'AGE'],
            // 'code_discount' => "Quantity Discount",
            'class'              => 'IFAR',
            "currency" => "MXN",
        ];        
        

        // $params = $case5;

        try {

            $token = $this->getToken();
    
            $response = Http::withHeaders([
                'Content-Type' => 'application/json',
                'Authorization' => 'Bearer ' . $token,
            ])
            ->timeout(5)
            ->post($this->endpoint . 'api/brokers/booking-engine/rates', $params);
    
            // Manejar la respuesta de la API
            if ($response->successful()) {
                $responseData = $response->json();

                // Log::info(json_encode($responseData));

                // Verificar que el contenido sea válido y esperado
                if (isset($responseData['data'])) {
                    return [
                        'status' => 'success',
                        'availability_request' => $params,
                        'availability_response' => $responseData['data']
                    ];
                }
    
                return [
                    'status' => 'error',
                    'message' => 'Unexpected response structure.',
                    'details' => $responseData
                ];
            }
    
            // Manejar errores de cliente o servidor
            if ($response->clientError() || $response->serverError()) {
                Log::info(json_encode($response->json()));

                return [
                    'status' => 'error',
                    'message' => 'API returned an error.',
                    'status_code' => $response->status(),
                    'details' => $response->json()
                ];
            }
    
            // Respuesta inesperada
            return [
                'status' => 'error',
                'message' => 'Unexpected error occurred.',
            ];
        } catch (\Exception $e) {
            // Manejar excepciones (problemas con el token o la conexión)
            return [
                'status' => 'error',
                'message' => 'Exception occurred: ' . $e->getMessage(),
            ];
        }
    }

    public function confirmBookings()
    {
        // Buscar las reservaciones pendientes de confirmación del proveedor 28
        // $reservations = DB::table('reservaciones')
        //     ->select([
        //         'reservaciones.estado',
        //         'reservaciones.fechaRecoger as pickup_date',
        //         'reservaciones.fechaDejar as dropoff_date',
        //         'reservaciones.horaRecoger as pickup_time',
        //         'reservaciones.horaDejar as dropoff_time',
        //         'reservaciones.no_vuelo as flight',
        //         'reservaciones.aereolinea as airline',
        //         'clientes.id as client_id',
        //         'clientes.nombre as name',
        //         'clientes.apellido as last_name',
        //         'pickup_location.code as pickup_location_code',
        //         'dropoff_location.code as dropoff_location_code'
        //     ])
        //     ->join('clientes', 'clientes.id', 'reservaciones.id_cliente')
        //     ->join('provider_locations as pickup_location', 'pickup_location.mcr_office_id', 'reservaciones.id_direccion')
        //     ->join('provider_locations as dropoff_location', 'dropoff_location.mcr_office_id', 'reservaciones.id_direccion_dropoff')
        //     ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
        //     ->where(function ($query) {
        //         $query->whereNull('reservaciones.no_confirmacion')
        //             ->orWhere('reservaciones.no_confirmacion', '');
        //     })
        //     ->where('reservaciones.proveedor', 28)
        //     ->where('reservaciones.fechaReservacion', '>', '2025-06-09')
        //     ->get();

            $reservations = DB::table('reservaciones')
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
                'gps_categorias.id as category_id'
            ])
            ->join('clientes', 'clientes.id', 'reservaciones.id_cliente')
            ->join('provider_locations as pickup_location', 'pickup_location.mcr_office_id', 'reservaciones.id_direccion')
            ->join('provider_locations as dropoff_location', 'dropoff_location.mcr_office_id', 'reservaciones.id_direccion_dropoff')
            ->join('auto_clientes', 'auto_clientes.id_cliente', 'reservaciones.id_cliente')
            ->join('gps_categorias', 'gps_categorias.categoria', 'auto_clientes.categoria')
            ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
            ->where('reservaciones.no_confirmacion', '')
            ->where('reservaciones.proveedor', 28)
            // ->where('clientes.token_id', $tokenId)
            ->get();

        $confirmReservations = 0;

        foreach ($reservations as $reservation) {

            // Obtener cotización del proveedor
            $providerQuotation = DB::table('mex_group_quotations')
                ->where('client_id', $reservation->client_id)
                ->first();

            // if (!$providerQuotation) {
            //     Log::warning("Cotización no encontrada para cliente ID: " . $reservation->client_id);
            //     continue;
            // }

            if (!$providerQuotation) {
                $carProviderDb = DB::table('provider_vehicles')
                    ->select('acriss')
                    ->where('fk_provider', 28)
                    ->where('provider_vehicles.category_id', $reservation->category_id)
                    ->get();

                if ($carProviderDb->isNotEmpty()) {
                    $searchParams = [
                        'pickupDate' => $reservation->pickup_date,
                        'pickupTime' => $reservation->pickup_time,
                        'dropoffDate' => $reservation->dropoff_date,
                        'dropoffTime' => $reservation->dropoff_time,
                        'IATA' => $reservation->destination_code,
                        'pickupLocation' => $reservation->pickup_location_code,
                        'dropoffLocation' => $reservation->dropoff_location_code,
                        'pickupOfficeId' => $reservation->pickup_location_mcr_office_id,
                        'dropoffOfficeId' => $reservation->dropoff_location_mcr_office_id,
                        // opcionalmente puedes quitar esto si no es solo un acriss
                    ];

                    $cars = $this->getAvailability($searchParams);

                    if (!empty($cars)) {
                        foreach ($cars as $car) {
                            foreach ($carProviderDb as $carDb) {
                                if ($car->classType === $carDb->acriss) {
                                    $providerQuotation = (object) [
                                        'rate_code' => $car->rateCode,
                                        'class' => $car->classType,
                                        'rate_id' => $car->rateId
                                    ];
                                    break 2; // salir de ambos loops
                                }
                            }
                        }
                    }
                }
            }

            if($providerQuotation == null) {
                Log::error("Provider quotation not found for client ID: " . $reservation->client_id);
                continue;
            }

            // Preparar solicitud a API externa
            $url = $this->endpoint . 'api/brokers/booking-engine/reserve';
            $token = $this->getToken();

            $data = [
                'pickup_location' => $reservation->pickup_location_code,
                'dropoff_location' => $reservation->dropoff_location_code,
                'pickup_date' => $reservation->pickup_date . 'T' . $reservation->pickup_time . ':00',
                'dropoff_date' => $reservation->dropoff_date . 'T' . $reservation->dropoff_time . ':00',
                'rate_code' => $providerQuotation->rate_code,
                'class' => $providerQuotation->class,
                'id_rate' => $providerQuotation->rate_id,
                'email' => 'noreply@mexicocarrental.com.mx',
                'first_name' => $reservation->name,
                'last_name' => $reservation->last_name,
                'airline' => $reservation->airline,
                'flight' => $reservation->flight,
                'extras' => explode(',', $providerQuotation->extras ?? ''),
                // 'corporate_setup' => $providerQuotation->corporate_setup,
                'chain_code' => 'MX',
                // 'promo_code' => 'Quantity Discount',
            ];


            if($reservation->status == 'dpa') {
                $data['corporate_setup'] = "00108";
            }

            // Enviar solicitud HTTP
            $response = Http::withHeaders([
                'Accept' => 'application/json',
                'Authorization' => 'Bearer ' . $token,
                'Content-Type' => 'application/json',
            ])->post($url, $data);

            if ($response->successful()) {
                $responseData = $response->json();

                if (isset($responseData['data']['noConfirmation'])) {

                    $confirmReservations++;

                    // Actualizar reservación con número de confirmación
                    DB::table('reservaciones')
                        ->where('id_cliente', $reservation->client_id)
                        ->update([
                            'no_confirmacion' => $responseData['data']['noConfirmation'],
                        ]);

                    // Guardar log de confirmación
                    DB::table('mex_group_quotations')
                        ->where('client_id', $reservation->client_id)
                        ->update([
                            'confirmation_request' => json_encode($data),
                            'confirmation_response' => json_encode($responseData),
                        ]);
                } else {
                    Log::error("Confirmación no recibida para cliente: {$reservation->client_id}", $responseData);
                }
            } else {
                Log::error("Error en reserva API para cliente: {$reservation->client_id}", [
                    'status' => $response->status(),
                    'body' => $response->body(),
                    'data_sent' => $data
                ]);
            }
        }

        return $confirmReservations;
    }

    public function confirmBooking($tokenId)
    {
        try {
            // Buscar la reservación
             $reservation = DB::table('reservaciones')
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
                'gps_categorias.id as category_id'
            ])
            ->join('clientes', 'clientes.id', 'reservaciones.id_cliente')
            ->join('provider_locations as pickup_location', 'pickup_location.mcr_office_id', 'reservaciones.id_direccion')
            ->join('provider_locations as dropoff_location', 'dropoff_location.mcr_office_id', 'reservaciones.id_direccion_dropoff')
            ->join('auto_clientes', 'auto_clientes.id_cliente', 'reservaciones.id_cliente')
            ->join('gps_categorias', 'gps_categorias.categoria', 'auto_clientes.categoria')
            ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
            ->where('reservaciones.no_confirmacion', '')
            ->where('reservaciones.proveedor', 28)
            ->where('clientes.token_id', $tokenId)
            ->first();

            if (!$reservation) {
                return [
                    'status' => 'error',
                    'message' => 'Reservation not found.'
                ];
            }
    
            // Obtener la cotización del proveedor
            $providerQuotation = DB::table('mex_group_quotations')
                ->where('client_id', $reservation->client_id)
                ->first();


            if (!$providerQuotation) {
                $carProviderDb = DB::table('provider_vehicles')
                    ->select('acriss')
                    ->where('fk_provider', 28)
                    ->where('provider_vehicles.category_id', $reservation->category_id)
                    ->get();

                if ($carProviderDb->isNotEmpty()) {
                    $searchParams = [
                        'pickupDate' => $reservation->pickup_date,
                        'pickupTime' => $reservation->pickup_time,
                        'dropoffDate' => $reservation->dropoff_date,
                        'dropoffTime' => $reservation->dropoff_time,
                        'IATA' => $reservation->destination_code,
                        'pickupLocation' => $reservation->pickup_location_code,
                        'dropoffLocation' => $reservation->dropoff_location_code,
                        'pickupOfficeId' => $reservation->pickup_location_mcr_office_id,
                        'dropoffOfficeId' => $reservation->dropoff_location_mcr_office_id,
                        // opcionalmente puedes quitar esto si no es solo un acriss
                    ];

                    $cars = $this->getAvailability($searchParams);

                    if (!empty($cars)) {
                        foreach ($cars as $car) {
                            foreach ($carProviderDb as $carDb) {
                                if ($car->classType === $carDb->acriss) {
                                    $providerQuotation = (object) [
                                        'rate_code' => $car->rateCode,
                                        'class' => $car->classType,
                                        'rate_id' => $car->rateId
                                    ];
                                    $searchParams['carType'] = $car->classType;
                                    break 2; // salir de ambos loops
                                }
                            }
                        }
                    }
                }
            }

            if($providerQuotation == null) {
                Log::error("Provider quotation not found for client ID: " . $reservation->client_id);
                return [
                    'status' => 'error',
                    'message' => 'Provider quotation not found.'
                ];
            }
    
            // Configurar la solicitud a la API
            $url = $this->endpoint . 'api/brokers/booking-engine/reserve';
            $token = $this->getToken();

            // $reservation->dropoff_location_code = 'CZM'; //BORRAR
            // $providerQuotation->extras = "AD,CT3";


            // $reservation->pickup_location_code = "GDL2";

            $data = [
                'pickup_location' => $reservation->pickup_location_code,
                'dropoff_location' => $reservation->dropoff_location_code,
                'pickup_date' => $reservation->pickup_date . 'T' . $reservation->pickup_time . ':00',
                'dropoff_date' => $reservation->dropoff_date . 'T' . $reservation->dropoff_time . ':00',
                'rate_code' => $providerQuotation->rate_code,
                'class' => $providerQuotation->class,
                'id_rate' => $providerQuotation->rate_id,
                'email' => 'noreply@mexicocarrental.com.mx',
                'first_name' => $reservation->name,
                'last_name' => $reservation->last_name,
                'airline' => $reservation->airline,
                'flight' => $reservation->flight,
                'extras' => explode(',', $providerQuotation->extras,),
                // 'corporate_setup' => $providerQuotation->corporate_setup,
                'chain_code' => 'MX',
                // 'promo_code' => 'Quantity Discount', 
            ];


            if($reservation->status == 'dpa') {
                $data['corporate_setup'] = "00108";
            }

            // Log::info(json_encode($data));
    
            // Enviar la solicitud HTTP
            $response = Http::withHeaders([
                'Accept' => 'application/json',
                'Authorization' => 'Bearer ' . $token,
                'Content-Type' => 'application/json',
            ])->post($url, $data);
    
            if ($response->successful()) {
                $responseData = $response->json();

                if (isset($responseData['data'])) {
                    // Actualizar la reservación con el número de confirmación
                    DB::table('reservaciones')
                        ->where('id_cliente', $reservation->client_id)
                        ->update([
                            'no_confirmacion' => $responseData['data']['noConfirmation'],
                        ]);

                    DB::table('mex_group_quotations')
                        ->where('client_id', $reservation->client_id)
                        ->update([
                            'confirmation_request' => json_encode($data),
                            'confirmation_response' => json_encode($responseData),
                        ]);
    
                    return [
                        'status' => 'success',
                        'data' => $responseData['data']
                    ];
                }

                return [
                    'status' => 'success',
                    'data' => $responseData
                ];
            } else {
                Log::error("API Request Failed: " . $response->body());
    
                return [
                    'status' => 'error',
                    'message' => 'Unexpected error from API'
                ];
            }
        } catch (QueryException $e) {
            Log::error("Database Query Exception: " . $e->getMessage());
    
            return [
                'status' => 'error',
                'message' => 'Database error occurred.'
            ];
        } catch (\Exception $e) {
            Log::error("General Exception: " . $e->getMessage());
    
            return [
                'status' => 'error',
                'message' => 'An unexpected error occurred.'
            ];
        }
    }

    public function cancelBooking($tokenId)
    {

        $reservation = DB::table('reservaciones')
                ->select([
                    'reservaciones.no_confirmacion'
                ])
                ->join('clientes', 'clientes.id', 'reservaciones.id_cliente')
                // ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
                ->where('reservaciones.proveedor', 28)
                ->where('clientes.token_id', $tokenId)
                ->first();

        
        if($reservation) {

                     // Configurar la solicitud a la API
            $url = $this->endpoint . 'api/brokers/booking-engine/cancel';
            $token = $this->getToken();

            $data = [
                'no_confirmation' => $reservation->no_confirmacion,
            ];

            // Enviar la solicitud HTTP
            $response = Http::withHeaders([
                'Accept' => 'application/json',
                'Authorization' => 'Bearer ' . $token,
                'Content-Type' => 'application/json',
            ])->post($url, $data);

            if ($response->successful()) {
                $responseData = $response->json();
                return [
                    'status' => 'success',
                    'message' => 'Booking cancelled successfully.',
                    'data' => $responseData['data'] ?? null
                ];
            } else {
                Log::error("API Request Failed: " . $response->body());
                return [
                    'status' => 'error',
                    'message' => 'Unexpected error from API',
                    'details' => $response->json() ?? $response->body()
                ];
            }    
        } else {
            return [
                'status' => 'error',
                'message' => 'Booking not found or already confirmed.',
            ];
        }
        
    }

    private function getVehicles()
    {
        Cache::forget('group_mex_vehicles');
        if(Cache::has('group_mex_vehicles')) {
            return Cache::get('group_mex_vehicles');
        }

        $vehicles = DB::table('provider_vehicles')
        ->join('gps_categorias', 'gps_categorias.id', '=', 'provider_vehicles.category_id')
        ->join('gps_autos_copy', 'gps_autos_copy.id_gps_categorias', '=', 'provider_vehicles.category_id')
        ->select(
            'gps_categorias.categoria as category', 'gps_categorias.id as category_id', 'gps_categorias.descripccion', 
            'gps_categorias.cAcriss', 'provider_vehicles.acriss', 'provider_vehicles.auto as car_name', 'gps_categorias.tipo as vehicle_type',
            'gps_autos_copy.auto as car_name_mcr', 'gps_autos_copy.camino as image', 'gps_autos_copy.id as vehicle_id'
            )
        ->where('fk_provider', '28')
        ->groupBy('provider_vehicles.category_id')
        ->orderBy('gps_categorias.categoria', 'ASC')
        ->get();

        Cache::put('group_mex_vehicles', $vehicles, now()->addDays(7));

        return $vehicles;
    }

    private function getLocations($searchParams)
    {

        // Recheck reservación
        if(isset($searchParams['pickupLocation']) && 
            isset($searchParams['dropoffLocation']) && 
            isset($searchParams['pickupOfficeId']) && 
            isset($searchParams['dropoffOfficeId'])) {

            return [
                'pickupLocation' => $searchParams['pickupLocation'],
                'dropoffLocation' => $searchParams['dropoffLocation'],
                'pickupOfficeId' => $searchParams['pickupOfficeId'],
                'dropoffOfficeId' => $searchParams['dropoffOfficeId'],
            ];
        }


        if (isset($searchParams['IATA'])) {
            $location = DB::table('provider_locations')
                ->where('fk_provider', 28)
                ->where('mcr_code', $searchParams['IATA']);

            if ($searchParams['pickupLocation'] != 'Aeropuerto') {
                $location = $location->where('location', 'City');
            }

            switch ($searchParams['pickupLocation']) {
                case 'Aeropuerto':
                    $location = $location->where('location', 'Airport');
                    break;
                default:
                    $location = $location->where('location', 'City');
                    break;
            }

            $location = $location->first();

            if (!empty($location)) {
                $pickupLocation = $location->code;
                $dropoffLocation = $location->code;
                $pickupOfficeId = $location->mcr_office_id;
                $dropoffOfficeId = $location->mcr_office_id;
                return [
                    'pickupLocation' => $pickupLocation,
                    'dropoffLocation' => $dropoffLocation,
                    'pickupOfficeId' => $pickupOfficeId,
                    'dropoffOfficeId' => $dropoffOfficeId,
                ];
            }
        }
     
         return [
            'pickupLocation' => null,
            'dropoffLocation' => null,
            'pickupOfficeId' => null,
            'dropoffOfficeId' => null,
        ];
    }

    public function storeVehicles($searchParams)
    {
        $fleet = $this->getAvailability($searchParams);

        if($fleet['status'] == 'success') {
            if(isset($fleet['data'])) {
                $vehicles = $fleet['data'];

                foreach ($vehicles as $vehicle) {
                    
                    $vehicleData = [
                        'acriss' => $vehicle['class']['classCode'],
                        'auto' => $vehicle['class']['modelDesc'],
                        'fk_provider' => 28,
                        'transmission' => $vehicle['class']['transmission'],
                    ];
                    
                    $exist = DB::table('provider_vehicles')
                    ->where('auto', $vehicleData['auto'])
                    ->where('fk_provider', $vehicleData['fk_provider'])
                    ->first();
                    
                    if(!$exist) {
                        DB::table('provider_vehicles')->insert($vehicleData);
                    }
                }

                return [
                    'status' => 'success',
                    'message' => 'Vehicles stored successfully.'
                ];
            }
        }
    }

    public function storeOffices()
    {
        $url = $this->endpoint . 'api/brokers/offices';

        try {
            $token = $this->getToken();
            $response = Http::withHeaders([
                'Accept' => 'application/json',
                'Content-Type' => 'application/json',
                'Authorization' => 'Bearer ' . $token,
            ])->post($url);
    
            if ($response->successful()) {
                $responseData = $response->json();
    
                // Verificar que el contenido sea válido y esperado
                if (isset($responseData['data'])) {
                    return [
                        'status' => 'success',
                        'data' => $responseData['data']
                    ];
                }
    
                return [
                    'status' => 'error',
                    'message' => 'Unexpected response structure.',
                    'details' => $responseData
                ];
            }

        } catch (\Exception $e) {
            return [
                'status' => 'error',
                'message' => 'Exception occurred: ' . $e->getMessage(),
            ];
        }
    }

    function calculateFullDays($startDate, $endDate)
    {
        $start = Carbon::parse($startDate);
        $end = Carbon::parse($endDate);

        // Calcula la diferencia en horas
        $hoursDifference = $start->diffInMinutes($end);

        // Divide las horas por 24 para obtener días completos (redondeando hacia arriba)
        $fullDays = (int) ceil($hoursDifference / 1440);

        return $fullDays;
    }
}