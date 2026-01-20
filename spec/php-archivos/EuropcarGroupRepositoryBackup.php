<?php
namespace App\Repositories;

use Illuminate\Support\Str;
use Illuminate\Support\Facades\Http;
use Session;
use DB;
use Carbon\Carbon;
use Log;
use Cache;
use Utilities;

class EuropcarGroupRepository
{
    private $europcarUser;
    private $europcarPassword;

    private $europcarDpaUser;
    private $europcarDpaPassword;

    private $keddyUser;
    private $keddyPassword;

    private $keddyDpaUser;
    private $keddyDpaPassword;

    private $foxUser;
    private $foxPassword;

    private $foxDpaUser;
    private $foxDpaPassword;

    private $endpoint;

    public function __construct()
    {
        $this->europcarUser = config('europcargroup.europcar.user');
        $this->europcarPassword = config('europcargroup.europcar.password');

        $this->keddyUser = config('europcargroup.keddy.user');
        $this->keddyPassword = config('europcargroup.keddy.password');

        $this->foxUser = config('europcargroup.fox.user');
        $this->foxPassword = config('europcargroup.fox.password');

        // ----------------------------------------------------------------------------

        $this->europcarDpaUser = config('europcargroup.europcar.userDpa');
        $this->europcarDpaPassword = config('europcargroup.europcar.passwordDpa');

        $this->keddyDpaUser = config('europcargroup.keddy.userDpa');
        $this->keddyDpaPassword = config('europcargroup.keddy.passwordDpa');

        $this->foxDpaUser = config('europcargroup.fox.userDpa');
        $this->foxDpaPassword = config('europcargroup.fox.passwordDpa');

        $this->endpoint = config('europcargroup.endpoint');
    }

    public function getAvailability($searchParams, $reservation, $quotation = null)
    {
        $matchList = [];

        try {

            $sessionId = $this->signInByProvider($reservation);

            $params = [
                "method" => "isCarRental_BookingInterface_Service.GetCarAvailability",
                "params" => [
                    "SessionId" => $sessionId,
                    "CheckOutStationId" => $searchParams['pickupLocation'],
                    "CheckOutDate" => "{$searchParams['pickupDate']}T{$searchParams['pickupTime']}:00",
                    "CheckInStationId" => $searchParams['dropoffLocation'],
                    "CheckInDate" => "{$searchParams['dropoffDate']}T{$searchParams['dropoffTime']}:00",
                    "Currency" => "MXN",
                    "DealId" => 0,
                    "BookingNumber" => "",
                ],
            ];

            $jsonParams = json_encode($params);

            $response = Http::withBody($jsonParams, 'application/json')->get($this->endpoint);

            $status = $response->status();

            if ($status == 200) {
                $json = $response->json();

                if (isset($json['result']) && $json['result']) {
                    Log::info(json_encode($json));
                    DB::table('europcar_group_quotations')->updateOrInsert(
                        ['client_id' => $reservation->client_id], // Condición de búsqueda
                        [
                            'client_id' => $reservation->client_id,
                            'identifier' => $sessionId,
                            'provider_id' => $reservation->provider_id,
                            'content' => json_encode($json['result']),
                            'created_date' => Carbon::now()->format('Y-m-d'),
                            'created_time' => Carbon::now()->format('H:i:s'),
                            // 'book_id' => $providerVehicle['BookId'],
                            // 'provider_car_name' => $carModel,
                        ]
                    );
                    foreach ($json['result']['AvailableCarList'] as $providerVehicle) {
                        $carModel = $providerVehicle['Group']['CarModel'];
                        if($quotation) {
                            if($carModel == $quotation->provider_car_name) {
                                $providerVehicle['SessionId'] = $sessionId;
                                $matchList[] = $providerVehicle;
                            }
                        } else {
                            $acceptedVehicles = DB::table('provider_vehicles')
                            ->select('auto')
                            ->join('gps_categorias', 'gps_categorias.id', '=', 'provider_vehicles.category_id')
                            ->where('provider_vehicles.fk_provider', $reservation->provider_id)
                            ->where('gps_categorias.categoria', $reservation->category_id)
                            ->get();

                            foreach($acceptedVehicles as $v) {
                                if($carModel == $v->auto) {
                                    $providerVehicle['SessionId'] = $sessionId;
                                    $matchList[] = $providerVehicle;
                                    DB::table('europcar_group_quotations')->updateOrInsert(
                                        ['client_id' => $reservation->client_id], // Condición de búsqueda
                                        [
                                            'client_id' => $reservation->client_id,
                                            'identifier' => $sessionId,
                                            'provider_id' => $reservation->provider_id,
                                            'content' => json_encode($json['result']),
                                            'created_date' => Carbon::now()->format('Y-m-d'),
                                            'created_time' => Carbon::now()->format('H:i:s'),
                                            'book_id' => $providerVehicle['BookId'],
                                            'provider_car_name' => $carModel,
                                        ]
                                    );
                                    break;
                                }
                            }
                        }
                    }
                }
            }
        } catch (\Exception $e) {
            \Log::error("Error al obtener disponibilidad: " . $e->getMessage());
            return [];
        }

        return $matchList;
    }

        private function signInByCheapestProvider()
    {
        // Credenciales para cada proveedor
        $providers = [
            // 'europcar' => [
            //     'user' => $this->europcarUser,
            //     'password' => $this->europcarPassword,
            // ],
            // 'keddy' => [
            //     'user' => $this->keddyUser,
            //     'password' => $this->keddyPassword,
            // ],
            'fox' => [
                'user' => $this->foxUser,
                'password' => $this->foxPassword,
            ],
        ];

        // Crear el conjunto de peticiones para cada proveedor
        $sessionIds = [];
        foreach ($providers as $provider => $credentials) {
            try {
                $params = [
                    'method' => 'isCarRental_BookingInterface_Service.LogIn',
                    'params' => [
                        'ContractId' => $credentials['user'],
                        'Password' => $credentials['password'],
                        'LanguageId' => 'EN',
                    ],
                ];

                $jsonParams = json_encode($params);

                // Enviar la solicitud HTTP
                $response = Http::withBody($jsonParams, 'application/json')
                    ->timeout(3)
                    ->post($this->endpoint);

                // Verificar si la respuesta es exitosa y procesarla
                if ($response->successful() && isset($response->json()['result']['SessionId'])) {
                    $sessionIds[$provider] = $response->json()['result']['SessionId'];
                } else {
                    $sessionIds[$provider] = null; // Manejo de errores de respuesta no exitosa
                }
            } catch (\GuzzleHttp\Exception\ConnectException $e) {
                // Manejo de errores de conexión
                $sessionIds[$provider] = null;
            } catch (\Exception $e) {
                // Manejo de cualquier otro error
                $sessionIds[$provider] = null;
            }
        }

        return $sessionIds;
    }


    public function getAvailabilityForCheapestProvider($searchParams)
    {
        $sessionIds = $this->signInByCheapestProvider(); // Obtener SessionId de los tres proveedores
        $matchListsByProvider = [];

        try {
            $providers = [
                // 'europcar' => ['providerName' => 'EUROPCAR', 'providerId' => 1],
                // 'keddy' => ['providerName' => 'KEDDY', 'providerId' => 93],
                'fox' => ['providerName' => 'FOX RENT A CAR', 'providerId' => 109],
            ];

            $locations = $this->getLocations($searchParams);
            $vehicles = $this->getVehicles();

            $responses = Http::pool(function ($pool) use ($sessionIds, $providers, $searchParams, $locations) {
                foreach ($providers as $provider => $providerData) {
                    if (isset($sessionIds[$provider]) && $sessionIds[$provider]) {
                        $params = [
                            "method" => "isCarRental_BookingInterface_Service.GetCarAvailability",
                            "params" => [
                                "SessionId" => $sessionIds[$provider],
                                "CheckOutStationId" => $locations['pickupLocation'],
                                "CheckOutDate" => "{$searchParams['pickupDate']}T{$searchParams['pickupTime']}:00",
                                "CheckInStationId" => $locations['dropoffLocation'],
                                "CheckInDate" => "{$searchParams['dropoffDate']}T{$searchParams['dropoffTime']}:00",
                                "Currency" => "MXN",
                                "DealId" => 0,
                                "BookingNumber" => "",
                            ],
                        ];

                        $jsonParams = json_encode($params);

                        $pool->as($provider)
                            ->withBody($jsonParams, 'application/json')
                            ->timeout(3)
                            ->post($this->endpoint);
                    }
                }
            });

            foreach ($providers as $provider => $providerData) {
                $matchListsByProvider[$provider] = [];

                if (
                    isset($responses[$provider]) &&
                    method_exists($responses[$provider], 'successful') &&
                    $responses[$provider]->successful()
                ) {
                    $json = $responses[$provider]->json();

                    DB::table('europcar_group_quotations')->insert([
                        'identifier' => $sessionIds[$provider],
                        'provider_id' => $providerData['providerId'],
                        'content' => json_encode($json['result']),
                        'created_date' => Carbon::now()->format('Y-m-d'),
                        'created_time' => Carbon::now()->format('H:i:s'),
                    ]);

                    if (!empty($json['result'])) {
                        $totalDays = $this->calculateFullDays(
                            $searchParams['pickupDate'] . " " . $searchParams['pickupTime'],
                            $searchParams['dropoffDate'] . " " . $searchParams['dropoffTime']
                        );

                        $addedCategories = [];
                        $vehiclesByCarModel = [];

                        foreach ($vehicles as $vehicle) {
                            $vehiclesByCarModel[$vehicle->car_name] = $vehicle;
                        }

                        foreach ($json['result']['AvailableCarList'] as $providerVehicle) {
                            $carModel = $providerVehicle['Group']['CarModel'];

                            if (isset($vehiclesByCarModel[$carModel])) {
                                $vehicle = $vehiclesByCarModel[$carModel];

                                if (!in_array($vehicle->category, $addedCategories)) {
                                    $addedCategories[] = $vehicle->category;
                                    $matchListsByProvider[$provider][] = (object)[
                                        'vehicleName' => $vehicle->car_name_mcr,
                                        'vehicleCategory' => $vehicle->category,
                                        'vehicleDescription' => $vehicle->descripccion,
                                        'vehicleAcriss' => $vehicle->cAcriss,
                                        'providerId' => $providerData['providerId'],
                                        'providerName' => $providerData['providerName'],
                                        'pickupOfficeId' => $locations['pickupOfficeId'],
                                        'dropoffOfficeId' => $locations['dropoffOfficeId'],
                                        'totalDays' => $totalDays,
                                        'netRate' => $providerVehicle['CarValuation']['Total'] / $totalDays,
                                        'vehicleImage' => $vehicle->image,
                                        'vehicleId' => $vehicle->vehicle_id,
                                        'vehicleType' => $vehicle->vehicle_type,
                                        'sessionId' => $sessionIds[$provider],
                                        'bookId' => $providerVehicle['BookId'],
                                        'providerCarModel' => $carModel,
                                    ];
                                }
                            }
                        }
                    }
                } else {
                    // Loguear el error si la respuesta no fue válida
                    if (isset($responses[$provider]) && $responses[$provider] instanceof \Throwable) {
                        \Log::error("Error con $provider: " . $responses[$provider]->getMessage());
                    } elseif (isset($responses[$provider])) {
                        \Log::warning("Respuesta inesperada de $provider", [
                            'tipo' => get_class($responses[$provider]),
                            'detalle' => method_exists($responses[$provider], 'body') ? $responses[$provider]->body() : null
                        ]);
                    }
                }
            }
        } catch (\Exception $e) {
            \Log::error("Error al obtener disponibilidad: " . $e->getMessage());
        }

        return $matchListsByProvider;
    }

    public function getAvailabilityForAllProviders($searchParams)
    {
        $sessionIds = $this->signIn(); // Obtener SessionId de los tres proveedores
        // \Log::info(json_encode($sessionIds));
        $matchLists = [];
        $matchListsByProvider = [];

        try {
            // Preparar datos básicos para cada proveedor
            $providers = [
                'europcar' => ['providerName' => 'EUROPCAR', 'providerId' => 1],
                'keddy' => ['providerName' => 'KEDDY', 'providerId' => 93],
                'fox' => ['providerName' => 'FOX RENT A CAR', 'providerId' => 109],
            ];

            $locations = $this->getLocations($searchParams);
            $vehicles = $this->getVehicles();

            // Realizar peticiones simultáneamente usando Http::pool
            $responses = Http::pool(function ($pool) use ($sessionIds, $providers, $searchParams, $locations) {
                foreach ($providers as $provider => $providerData) {
                    if (isset($sessionIds[$provider]) && $sessionIds[$provider]) {
                        $params = [
                            "method" => "isCarRental_BookingInterface_Service.GetCarAvailability",
                            "params" => [
                                "SessionId" => $sessionIds[$provider],
                                "CheckOutStationId" => $locations['pickupLocation'],
                                "CheckOutDate" => "{$searchParams['pickupDate']}T{$searchParams['pickupTime']}:00",
                                "CheckInStationId" => $locations['dropoffLocation'],
                                "CheckInDate" => "{$searchParams['dropoffDate']}T{$searchParams['dropoffTime']}:00",
                                "Currency" => "MXN",
                                "DealId" => 0,
                                "BookingNumber" => "",
                            ],
                        ];

                        $jsonParams = json_encode($params);

                        $pool->as($provider) // Asignar un alias único para cada solicitud
                            ->withBody($jsonParams, 'application/json')
                            ->post($this->endpoint);
                    }
                }
            });

            // \Log::info('Responses: ' . json_encode($responses));

            // Procesar las respuestas
            foreach ($providers as $provider => $providerData) {
                // Inicializa la lista para este proveedor
                $matchListsByProvider[$provider] = [];

                if (isset($responses[$provider]) && $responses[$provider]->successful()) {
                    $json = $responses[$provider]->json();

                    DB::table('europcar_group_quotations')
                    ->insert([
                        'identifier' => $sessionIds[$provider],
                        'provider_id' => $providerData['providerId'],
                        'content' => json_encode($json['result']),
                        'created_date' => Carbon::now()->format('Y-m-d'),
                        'created_time' => Carbon::now()->format('H:i:s'),
                    ]);


                    if (isset($json['result']) && $json['result']) {
                        $totalDays = $this->calculateFullDays(
                            $searchParams['pickupDate'] . " " . $searchParams['pickupTime'],
                            $searchParams['dropoffDate'] . " " . $searchParams['dropoffTime']
                        );

                        $addedCategories = [];
                        $vehiclesByCarModel = [];

                        // Mapea los vehículos por su modelo de auto
                        foreach ($vehicles as $vehicle) {
                            $vehiclesByCarModel[$vehicle->car_name] = $vehicle;
                        }

                        // Itera sobre los vehículos disponibles en la respuesta del proveedor
                        foreach ($json['result']['AvailableCarList'] as $providerVehicle) {
                            $carModel = $providerVehicle['Group']['CarModel'];

                            if (isset($vehiclesByCarModel[$carModel])) {
                                $vehicle = $vehiclesByCarModel[$carModel];

                                if (!in_array($vehicle->category, $addedCategories)) {
                                    $addedCategories[] = $vehicle->category;
                                    $matchListsByProvider[$provider][] = (object)[
                                        'vehicleName' => $vehicle->car_name_mcr,
                                        'vehicleCategory' => $vehicle->category,
                                        'vehicleDescription' => $vehicle->descripccion,
                                        'vehicleAcriss' => $vehicle->cAcriss,
                                        'providerId' => $providerData['providerId'],
                                        'providerName' => $providerData['providerName'],
                                        'pickupOfficeId' => $locations['pickupOfficeId'],
                                        'dropoffOfficeId' => $locations['dropoffOfficeId'],
                                        'totalDays' => $totalDays,
                                        'netRate' => $providerVehicle['CarValuation']['Total'] / $totalDays,
                                        'vehicleImage' => $vehicle->image,
                                        'vehicleId' => $vehicle->vehicle_id,
                                        'vehicleType' => $vehicle->vehicle_type,
                                        'sessionId' => $sessionIds[$provider],
                                        'bookId' => $providerVehicle['BookId'],
                                        'providerCarModel' => $carModel,
                                    ];
                                }
                            }
                        }
                    }
                }
            }
        } catch (\Exception $e) {
            \Log::error("Error al obtener disponibilidad: " . $e->getMessage());
        }

        return $matchListsByProvider;
    }


    private function signIn()
    {
        // Credenciales para cada proveedor
        $providers = [
            'europcar' => [
                'user' => $this->europcarUser,
                'password' => $this->europcarPassword,
            ],
            'keddy' => [
                'user' => $this->keddyUser,
                'password' => $this->keddyPassword,
            ],
            'fox' => [
                'user' => $this->foxUser,
                'password' => $this->foxPassword,
            ],
        ];

        // Crear el conjunto de peticiones para cada proveedor
        $sessionIds = [];
        foreach ($providers as $provider => $credentials) {
            try {
                $params = [
                    'method' => 'isCarRental_BookingInterface_Service.LogIn',
                    'params' => [
                        'ContractId' => $credentials['user'],
                        'Password' => $credentials['password'],
                        'LanguageId' => 'EN',
                    ],
                ];

                $jsonParams = json_encode($params);

                // Enviar la solicitud HTTP
                $response = Http::withBody($jsonParams, 'application/json')
                    ->post($this->endpoint);

                // Verificar si la respuesta es exitosa y procesarla
                if ($response->successful() && isset($response->json()['result']['SessionId'])) {
                    $sessionIds[$provider] = $response->json()['result']['SessionId'];
                } else {
                    $sessionIds[$provider] = null; // Manejo de errores de respuesta no exitosa
                }
            } catch (\GuzzleHttp\Exception\ConnectException $e) {
                // Manejo de errores de conexión
                $sessionIds[$provider] = null;
            } catch (\Exception $e) {
                // Manejo de cualquier otro error
                $sessionIds[$provider] = null;
            }
        }

        return $sessionIds;
    }

    private function signInByProvider($reservation)
    {
        $sessionId = "";

        $user = "";
        $password = "";

        switch ($reservation->provider_id) {
            case 1:
                if($reservation->reservation_state == 'dpe') {
                    $user = $this->europcarUser;
                    $password = $this->europcarPassword;
                } else {
                    $user = $this->europcarDpaUser;
                    $password = $this->europcarDpaPassword;
                }
                break;
            case 93:
                if($reservation->reservation_state == 'dpe') {
                    $user = $this->keddyUser;
                    $password = $this->keddyPassword;
                } else {
                    $user = $this->keddyDpaUser;
                    $password = $this->keddyDpaPassword;
                }

                break;
            case 109:
                if($reservation->reservation_state == 'dpe') {
                    $user = $this->foxUser;
                    $password = $this->foxPassword;
                } else {
                    $user = $this->foxDpaUser;
                    $password = $this->foxDpaPassword;
                }
                break;

            default:
                # code...
                break;
        }
        $params = [
            'method' => 'isCarRental_BookingInterface_Service.LogIn',
            'params' => [
                'ContractId' => $user,
                'Password' => $password,
                'LanguageId' => 'EN'
            ]
        ];

        $jsonParams = json_encode($params);

        $response = Http::withBody($jsonParams, 'application/json')
                        // ->timeout(2)
                        ->get($this->endpoint);

        $body = $response->body(); // String
        $json = $response->json(); // Array o null
        $status = $response->status();

        if ($status == 200 && isset($json['result']) && $json['result']) {
            $sessionId = $json['result']['SessionId'];
        }

        return $sessionId;
    }

    // private function getLocations($searchParams)
    // {
    //     $pickupLocation = "";
    //     $dropoffLocation = "";
    //     $pickupOfficeId = "";
    //     $dropoffOfficeId = "";

    //     if(isset($searchParams['IATA'])) {
    //         $location = DB::table('provider_locations')
    //         ->where('fk_provider', 1)
    //         ->where('mcr_code', $searchParams['IATA']);

    //         if($searchParams['pickupLocation'] != 'Aeropuerto') {
    //             $location = $location->where('location', 'City');
    //         }

    //         switch ($searchParams['pickupLocation']) {
    //             case 'Aeropuerto':
    //                 $location = $location->where('location', 'Airport');
    //                 break;
    //             default:
    //                 $location = $location->where('location', 'City');
    //                 break;
    //         }

    //         $location = $location->first();

    //         if(!empty($location)) {
    //             $pickupLocation = $location->code;
    //             $dropoffLocation = $location->code;
    //             $pickupOfficeId = $location->mcr_office_id;
    //             $dropoffOfficeId = $location->mcr_office_id;
    //         }
    //     }

    //     return [
    //         'pickupLocation' => $pickupLocation,
    //         'dropoffLocation' => $dropoffLocation,
    //         'pickupOfficeId' => $pickupOfficeId,
    //         'dropoffOfficeId' => $dropoffOfficeId,
    //     ];

    // }

    private function getLocations($searchParams)
    {
        // Generar una clave única basada en los parámetros de búsqueda
        $cacheKey = 'locations_' . md5(json_encode($searchParams));

        // Intentar recuperar los datos de la caché
        return Cache::remember($cacheKey, now()->addDays(7), function () use ($searchParams) {
            $pickupLocation = "";
            $dropoffLocation = "";
            $pickupOfficeId = "";
            $dropoffOfficeId = "";

            if (isset($searchParams['IATA'])) {
                $location = DB::table('provider_locations')
                    ->where('fk_provider', 1)
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
        });
    }

    private function getVehicles()
    {
        // Cache::forget('group_europcar_vehicles');
        if(Cache::has('group_europcar_vehicles')) {
            return Cache::get('group_europcar_vehicles');
        }

        $vehicles = DB::table('provider_vehicles')
        ->join('gps_categorias', 'gps_categorias.id', '=', 'provider_vehicles.category_id')
        ->join('gps_autos_copy', 'gps_autos_copy.id_gps_categorias', '=', 'provider_vehicles.category_id')
        ->select(
            'gps_categorias.categoria as category', 'gps_categorias.id as category_id', 'gps_categorias.descripccion',
            'gps_categorias.cAcriss', 'provider_vehicles.acriss', 'provider_vehicles.auto as car_name', 'gps_categorias.tipo as vehicle_type',
            'gps_autos_copy.auto as car_name_mcr', 'gps_autos_copy.camino as image', 'gps_autos_copy.id as vehicle_id'
            )
        ->where('fk_provider', '1')
        ->groupBy('provider_vehicles.category_id')
        ->orderBy('gps_categorias.categoria', 'ASC')
        ->get();

        Cache::put('group_europcar_vehicles', $vehicles, now()->addDays(7));

        return $vehicles;
    }

    // public function compareRates($europcarFleet, $engineFleet, $searchParams)
    // {
    //     foreach ($europcarFleet as $key => $europcarVehicle) {
    //         foreach ($engineFleet as $key => $engineVehicle) {
    //             if($europcarVehicle->vehicleCategory == $engineVehicle->categoria) {
    //                 $europcarVehicle->netRate = $europcarVehicle->netRate / $engineVehicle->totalDiasReservacion;
    //                 // Log::info('europcarVehicle->providerName: ' . $europcarVehicle->providerName);
    //                 // Log::info('europcarVehicle->vehicleCategory: ' . $europcarVehicle->vehicleCategory);
    //                 // Log::info('europcarVehicle->netRate: ' . $europcarVehicle->netRate);
    //                 // Log::info('engineVehicle->netRate: ' . $engineVehicle->tarifaNeta);
    //                 // Log::info('---------------------------------------------------------');
    //                 if($europcarVehicle->netRate <= $engineVehicle->tarifaNeta) {

    //                     $currentPublicRate = round($engineVehicle->tarifaPublica * (1 - $engineVehicle->descuento / 100));
    //                     $currentMarkup = $currentPublicRate - $engineVehicle->tarifaNeta;

    //                     $engineVehicle->offcell_completo = 0;
    //                     $engineVehicle->sinTarifas = "";
    //                     $engineVehicle->onRequest_completo = 0;

    //                     $engineVehicle->tarifaNeta = $europcarVehicle->netRate;
    //                     $engineVehicle->id_proveedor = $europcarVehicle->providerId;
    //                     $engineVehicle->id_datos_directorio_abrir = $europcarVehicle->pickupOfficeId;
    //                     $engineVehicle->id_datos_directorio_cerrar = $europcarVehicle->dropoffOfficeId;
    //                     $engineVehicle->nombreProveedor = $europcarVehicle->providerName;

    //                     $newPublicRate = $engineVehicle->tarifaNeta + $currentMarkup;
    //                     $newMktRate = ($newPublicRate * 100) / (100 - $engineVehicle->descuento);
    //                     $engineVehicle->tarifaPublica = $newMktRate;
    //                 }
    //                 break;
    //             }
    //         }
    //     }

    //     return $engineFleet;
    // }
    public function compareRates($europcarFleet, $engineFleet, $searchParams)
    {
        // Obtener las categorías de la caché o de la base de datos si no existen en caché
        if (Cache::has('gps_categories')) {
            $categories = Cache::get('gps_categories');
        } else {
            // Consulta las categorías de la base de datos
            $categories = DB::table('gps_categorias')
                ->select('categoria')
                ->pluck('categoria'); // Usar pluck para obtener solo una columna como array

            // Guarda las categorías en caché para siempre
            Cache::forever('gps_categories', $categories);
        }

        // Convertir ambos fleets en arrays asociativos para búsquedas rápidas
        $europcarFleetByCategory = [];
        foreach ($europcarFleet as $vehicle) {
            $europcarFleetByCategory[$vehicle->vehicleCategory] = $vehicle;
        }

        $engineFleetByCategory = [];
        foreach ($engineFleet as $engineVehicle) {
            // Si hay más de un vehículo por categoría, los almacenamos en un array
            $engineFleetByCategory[$engineVehicle->categoria][] = $engineVehicle;
        }

        // Iterar sobre todas las categorías disponibles
        foreach ($categories as $category) {
            $europcarVehicle = null;
            $engineVehicles = null;

            // Verificar si hay un vehículo en Europcar para la categoría
            if (isset($europcarFleetByCategory[$category])) {
                $europcarVehicle = $europcarFleetByCategory[$category];
            }

            // Verificar si hay vehículos en Engine para la categoría
            if (isset($engineFleetByCategory[$category])) {
                $engineVehicles = $engineFleetByCategory[$category];
            }

            // Si la categoría está en Europcar pero no en Engine, agregar los vehículos de Europcar
            if ($europcarVehicle && !$engineVehicles) {
                $engineFleetByCategory[$category][] = $europcarVehicle;
                $engineVehicles = [$europcarVehicle]; // Ahora tenemos el vehículo en engineFleet
            }

            // Si se encontró la categoría en ambas flotas, hacer la comparación
            if ($europcarVehicle && $engineVehicles) {
                foreach ($engineVehicles as $engineVehicle) {
                    if(isset($engineVehicle->tarifaNeta)) { // Existe propiedad en engineVehicle
                        if ($europcarVehicle->netRate <= $engineVehicle->tarifaNeta) {
                            $currentPublicRate = round($engineVehicle->tarifaPublica * (1 - $engineVehicle->descuento / 100));
                            $currentMarkup = $currentPublicRate - $engineVehicle->tarifaNeta;

                            $engineVehicle->offcell_completo = 0;
                            $engineVehicle->sinTarifas = "";
                            $engineVehicle->onRequest_completo = 0;

                            $engineVehicle->tarifaNeta = $europcarVehicle->netRate;
                            $engineVehicle->id_proveedor = $europcarVehicle->providerId;
                            $engineVehicle->id_datos_directorio_abrir = $europcarVehicle->pickupOfficeId;
                            $engineVehicle->id_datos_directorio_cerrar = $europcarVehicle->dropoffOfficeId;
                            $engineVehicle->nombreProveedor = $europcarVehicle->providerName;
                            // $engineVehicle->totalDiasReservacion = $europcarVehicle->totalDays;


                            $newPublicRate = $engineVehicle->tarifaNeta + $currentMarkup;
                            $newMktRate = ($newPublicRate * 100) / (100 - $engineVehicle->descuento);
                            $engineVehicle->tarifaPublica = $newMktRate;


                            if($engineVehicle->id_proveedor == '1' || $engineVehicle->id_proveedor == '93' || $engineVehicle->id_proveedor == '109') {
                                $engineVehicle->sessionId = $europcarVehicle->sessionId;
                                $engineVehicle->bookId = $europcarVehicle->bookId;
                                $engineVehicle->providerCarModel = $europcarVehicle->providerCarModel;
                            }

                            if($engineVehicle->id_proveedor == 28) {
                                $engineVehicle->rateCode = $europcarVehicle->rateCode;
                                $engineVehicle->rateId = $europcarVehicle->rateId;
                                $engineVehicle->classType = $europcarVehicle->classType;
                                $engineVehicle->availabilityResponse = $europcarVehicle->availabilityResponse;
                                $engineVehicle->availabilityRequest = $europcarVehicle->availabilityRequest;
                                $engineVehicle->corporateSetup = $europcarVehicle->corporateSetup;
                            }

                            if($engineVehicle->id_proveedor == 32 || $engineVehicle->id_proveedor == 106) {
                                $engineVehicle->carType = $europcarVehicle->carType;
                                $engineVehicle->availabilityResponse = $europcarVehicle->availabilityResponse;
                                $engineVehicle->availabilityRequest = $europcarVehicle->availabilityRequest;
                                $engineVehicle->vendorRateId = $europcarVehicle->vendorRateId;
                            }

                        }
                    } else {

                        // dd($engineVehicle);
                            // $currentPublicRate = round($engineVehicle->tarifaPublica * (1 - $engineVehicle->descuento / 100));
                            // $currentMarkup = $currentPublicRate - $engineVehicle->tarifaNeta;

                            $mupByCategory = [
                                'A' => 150,
                                'B' => 170,
                                'B1' => 200,
                                'B2' => 200,
                                'C1' => 210,
                                'D' => 220,
                                'D1' => 220,
                                'F' => 240,
                                'G' => 240,
                                'H1' => 300,
                                'H2' => 320,
                                'H3' => 340,
                                'K' => 500,
                                'L3' => 500,
                                'N' => 500,
                                'N2' => 500,
                                'O' => 500,
                                'P' => 500,
                                'P2' => 500,
                                'S1' => 500
                            ];

                            $engineVehicle->offcell_completo = 0;
                            $engineVehicle->sinTarifas = "";
                            $engineVehicle->onRequest_completo = 0;

                            $engineVehicle->tarifaNeta = $europcarVehicle->netRate;
                            $engineVehicle->id_proveedor = $europcarVehicle->providerId;
                            $engineVehicle->id_datos_directorio_abrir = $europcarVehicle->pickupOfficeId;
                            $engineVehicle->id_datos_directorio_cerrar = $europcarVehicle->dropoffOfficeId;
                            $engineVehicle->nombreProveedor = $europcarVehicle->providerName;
                            $engineVehicle->totalDiasReservacion = $europcarVehicle->totalDays;
                            $engineVehicle->descuento = $this->getDiscountByDays($europcarVehicle->totalDays);
                            $newPublicRate = $engineVehicle->tarifaNeta + $mupByCategory[$europcarVehicle->vehicleCategory];
                            $newMktRate = ($newPublicRate * 100) / (100 - $engineVehicle->descuento);
                            $engineVehicle->tarifaPublica = $newMktRate;

                            $engineVehicle->descripccion = $europcarVehicle->vehicleDescription;
                            $engineVehicle->cAcriss = $europcarVehicle->vehicleAcriss;
                            $engineVehicle->tipo = $europcarVehicle->vehicleType;
                            $engineVehicle->id_auto = $europcarVehicle->vehicleId;
                            $engineVehicle->imagen = $europcarVehicle->vehicleImage;
                            $engineVehicle->nombreAuto = $europcarVehicle->vehicleName;
                            $engineVehicle->categoria = $europcarVehicle->vehicleCategory;


                            if($engineVehicle->id_proveedor == '1' || $engineVehicle->id_proveedor == '93' || $engineVehicle->id_proveedor == '109') {
                                $engineVehicle->sessionId = $europcarVehicle->sessionId;
                                $engineVehicle->bookId = $europcarVehicle->bookId;
                                $engineVehicle->providerCarModel = $europcarVehicle->providerCarModel;
                            }


                            if($engineVehicle->id_proveedor == 28) {
                                $engineVehicle->rateCode = $europcarVehicle->rateCode;
                                $engineVehicle->rateId = $europcarVehicle->rateId;
                                $engineVehicle->classType = $europcarVehicle->classType;
                                $engineVehicle->availabilityResponse = $europcarVehicle->availabilityResponse;
                                $engineVehicle->availabilityRequest = $europcarVehicle->availabilityRequest;
                                $engineVehicle->corporateSetup = $europcarVehicle->corporateSetup;
                            }

                            if($engineVehicle->id_proveedor == 32 || $engineVehicle->id_proveedor == 106) {
                                $engineVehicle->carType = $europcarVehicle->carType;
                                $engineVehicle->availabilityResponse = $europcarVehicle->availabilityResponse;
                                $engineVehicle->availabilityRequest = $europcarVehicle->availabilityRequest;
                                $engineVehicle->vendorRateId = $europcarVehicle->vendorRateId;
                            }
                    }
                }
            }
        }

            // Aplanar el array de categorías en una sola lista
        $flattenedFleet = [];
        foreach ($engineFleetByCategory as $categoryVehicles) {
            $flattenedFleet = array_merge($flattenedFleet, $categoryVehicles);
        }

        return $flattenedFleet;
    }

    function getDiscountByDays($days)
    {
        // return 65;

        if ($days > 3 && $days < 14) {
            return 70; // 70% de descuento
        } elseif ($days > 1 && $days < 4) {
            return 70; // 65% de descuento
        } elseif ($days == 1) {
            return 60; // 55% de descuento
        } else {
            return 75; // Sin descuento si no cumple ninguna condición
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

    public function confirmBookings()
    {
        $reservations = DB::table('reservaciones')
            ->select([
                'clientes.id as client_id',
                'clientes.token_id as token_id',
                'reservaciones.id as reservation_id',
                'clientes.nombre as name',
                'clientes.apellido as lastname',
                'reservaciones.proveedor as provider_id',
            ])
            ->join('clientes', 'clientes.id', '=', 'reservaciones.id_cliente')
            ->where('clientes.token_id', '!=', '')
            ->whereIn('reservaciones.proveedor', [1, 93, 109])
            ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
            ->where('no_confirmacion', '')
            ->get();

        foreach ($reservations as $reservation) {
            $this->confirmBooking($reservation->token_id, $reservation);
        }

    }

    public function confirmBooking($tokenId, $reservation = null)
    {
        try {

            if(!$reservation) {
                // Buscar la reservación y el cliente asociado
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
                    'auto_clientes.categoria as category_id'
                ])
                ->join('clientes', 'clientes.id', '=', 'reservaciones.id_cliente')
                ->join('auto_clientes', 'auto_clientes.id_cliente', '=', 'reservaciones.id_cliente')
                ->leftjoin('provider_locations as pickup_provider_location', 'pickup_provider_location.mcr_office_id', '=', 'reservaciones.id_direccion')
                ->leftjoin('provider_locations as dropoff_provider_location', 'dropoff_provider_location.mcr_office_id', '=', 'reservaciones.id_direccion_dropoff')
                ->where('clientes.token_id', $tokenId)
                ->whereIn('reservaciones.proveedor', [1, 93, 109])
                ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
                ->where('no_confirmacion', '')
                ->first();
            }

            if (!$reservation) {
                return ""; // Retorna vacío si no hay reservación
            }

            // Buscar cotización asociada
            $quotation = DB::table('europcar_group_quotations')
                ->where('provider_id', $reservation->provider_id)
                ->where('client_id', $reservation->client_id)
                ->first();

            // if (!$quotation) {
            //     return ""; // Retorna vacío si no hay cotización
            // }

            // $responseData = $this->requestBookingConfirmation(
            //     $quotation->identifier,
            //     $quotation->book_id,
            //     $reservation->name,
            //     $reservation->lastname,
            //     $reservation->token_id
            // );

            // Validar la respuesta de la API externa
            // if (is_null($responseData) || !isset($responseData['result']['BookingNumber'])) {
            //     $searchParams = [
            //         'pickupLocation' => $reservation->pickup_location,
            //         'dropoffLocation' => $reservation->dropoff_location,
            //         'pickupDate' => $reservation->pickup_date,
            //         'pickupTime' => $reservation->pickup_time,
            //         'dropoffDate' => $reservation->dropoff_date,
            //         'dropoffTime' => $reservation->dropoff_time
            //     ];

            //     $availability = $this->getAvailability($searchParams, $reservation, $quotation);

            //     if(count($availability) > 0) {
            //         $selectedVehicle = $availability[0];
            //         $responseData = $this->requestBookingConfirmation(
            //             $selectedVehicle['SessionId'],
            //             $selectedVehicle['BookId'],
            //             $reservation->name,
            //             $reservation->lastname,
            //             $reservation->token_id
            //         );
            //     }

            //     if (is_null($responseData) || !isset($responseData['result']['BookingNumber'])) {
            //         return ""; // Retorna vacío si no se obtiene número de confirmación
            //     }

            // }

            $searchParams = [
                'pickupLocation' => $reservation->pickup_location,
                'dropoffLocation' => $reservation->dropoff_location,
                'pickupDate' => $reservation->pickup_date,
                'pickupTime' => $reservation->pickup_time,
                'dropoffDate' => $reservation->dropoff_date,
                'dropoffTime' => $reservation->dropoff_time
            ];

            $availability = $this->getAvailability($searchParams, $reservation, $quotation);

            $responseData = null;

            if(count($availability) > 0) {
                $selectedVehicle = $availability[0];
                $responseData = $this->requestBookingConfirmation(
                    $selectedVehicle['SessionId'],
                    $selectedVehicle['BookId'],
                    $reservation->name,
                    $reservation->lastname,
                    $reservation->token_id
                );

                Log::info(json_encode($responseData));
            }

            if (is_null($responseData) || !isset($responseData['result']['BookingNumber'])) {
                return ""; // Retorna vacío si no se obtiene número de confirmación
            }

            $bookingNumber = $this->assignBookingNumber($responseData, $reservation);


            return $bookingNumber; // Retorna el número de confirmación si todo fue exitoso

        } catch (\Exception $e) {
            Log::info($e->getMessage());
            // Manejo de errores en caso de fallo en la base de datos o API externa
            return ""; // En caso de error, retorna vacío
        }
    }

    public function requestBookingConfirmation($sessionId, $bookId, $name, $lastname, $tokenId)
    {
        // Construcción de parámetros para la API externa
        $params = [
            "method" => "isCarRental_BookingInterface_Service.ConfirmBooking",
            "params" => [
                "SessionId" => $sessionId,
                "BookId" => $bookId,
                "Title" => '-',
                "Name" => $name,
                "Surname" => $lastname, // Se corrigió "last_name" a "lastname"
                "EMail" => "-",
                "Telephone" => "-",
                "Address" => "-",
                "PostalCode" => "-",
                "City" => "-",
                "State" => "-",
                "Country" => "MX",
                "Flight" => "",
                "Remarks" => "",
                "ExternalBookingNumber" => $tokenId
            ]
        ];

        // Enviar la solicitud HTTP
        $response = Http::withBody(json_encode($params), 'application/json')->get($this->endpoint);

        // Verificar si la respuesta es exitosa
        if (!$response->successful()) {
            Log::info(json_encode($response->json()));
            return null; // Retorna vacío si hay un error en la petición
        }

        $responseData = $response->json();
        Log::info(json_encode($responseData));

        return $responseData;
    }

    public function assignBookingNumber($responseData, $reservation)
    {
        $bookingNumber = $responseData['result']['BookingNumber'];

        // Actualizar la reservación con el número de confirmación
        DB::table('reservaciones')
            ->where('id_cliente', $reservation->client_id)
            ->update(['no_confirmacion' => $bookingNumber]);


        DB::table('europcar_group_quotations')
            ->where('client_id', $reservation->client_id)
            ->update(['confirmation' => json_encode($responseData['result'])]);

        return $bookingNumber;
    }

}
