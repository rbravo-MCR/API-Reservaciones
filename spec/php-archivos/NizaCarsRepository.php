<?php

namespace App\Repositories;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Arr;
use Cache;
use Carbon\Carbon;

class NizaCarsRepository
{
    private string $baseUrl;
    private string $company;
    private string $customer;
    private string $user;
    private string $pass;
    private int $timeout;
    private const PROVIDER_ID = 126;

    /** Si el ?WSDL falla, activamos NON-WSDL */
    private bool $nonWsdl = false;

    /**
     * Mapa de servicios:
     *  - path: nombre del archivo .asmx (sin extensión)
     *  - op:   nombre de la operación SOAP (método)
     *  - ns:   namespace/URI del servicio (para NON-WSDL y SOAPAction)
     *  - wrap: si true, envuelve payload en <objRequest>...</objRequest>
     */
    private array $services = [
        // Catálogos (con objRequest)
        'getCountries' => [
            'path' => 'getCountries',
            'op'   => 'getCountries',
            'ns'   => 'http://www.jimpisoft.pt/Rentway_Reservations_WS/getCountries',
            'wrap' => true,
        ],
        'getCities' => [
            'path' => 'getCities',
            'op'   => 'getCities',
            'ns'   => 'http://www.jimpisoft.pt/Rentway_Reservations_WS/getCities',
            'wrap' => true,
        ],
        // En algunas instalaciones getStations va plano; en otras pide objRequest.
        // Déjalo en true; si tu servidor lo rechaza, cámbialo a false.
        'getStations' => [
            'path' => 'getStations',
            'op'   => 'getStations',
            'ns'   => 'http://www.jimpisoft.pt/Rentway_Reservations_WS/getStations',
            'wrap' => true,
        ],

        // ****** Niza – Multiple Prices (archivo y operación DIFERENTES) ******
        // Página pública: /Rentway_WS/getmultipleprices.asmx?op=MultiplePrices
        'multiplePrices' => [
            'path' => 'getmultipleprices',
            'op'   => 'MultiplePrices',
            'ns'   => 'http://www.jimpisoft.pt/Rentway_Reservations_WS/getMultiplePrices',
            'wrap' => true,
        ],

        // Price Quote estándar
        'getPriceQuote' => [
            'path' => 'getPriceQuote',
            'op'   => 'getPriceQuote',
            'ns'   => 'http://www.jimpisoft.pt/Rentway_Reservations_WS/getPriceQuote',
            'wrap' => false,
        ],

        // Create Reservation
        'Create_Reservation' => [
            'path' => 'Create_Reservation',
            'op'   => 'Create_Reservation',
            'ns'   => 'http://www.jimpisoft.pt/Rentway_Reservations_WS/Create_Reservation',
            'wrap' => false,
        ],

        // Extras útiles
        'getStationDetails' => [
            'path' => 'getStationDetails',
            'op'   => 'getStationDetails',
            'ns'   => 'http://www.jimpisoft.pt/Rentway_Reservations_WS/getStationDetails',
            'wrap' => false,
        ],
        'getGroups' => [
            'path' => 'getGroups',
            'op'   => 'getGroups',
            'ns'   => 'http://www.jimpisoft.pt/Rentway_Reservations_WS/getGroups',
            'wrap' => false,
        ],
        'getExtras' => [
            'path' => 'getExtras',
            'op'   => 'getExtras',
            'ns'   => 'http://www.jimpisoft.pt/Rentway_Reservations_WS/getExtras',
            'wrap' => false,
        ],
        'getOneWay' => [
            'path' => 'getOneWay',
            'op'   => 'getOneWay',
            'ns'   => 'http://www.jimpisoft.pt/Rentway_Reservations_WS/getOneWay',
            'wrap' => false,
        ],
    ];

    public function __construct()
    {
        $this->baseUrl  = rtrim(config('niza_cars.base_url'), '/');
        $this->company  = (string) config('niza_cars.company');
        // default al customer de FF; podrás cambiar por plan en cada llamada
        $this->customer = (string) (config('niza_cars.customers')['FF'] ?? '');
        $this->user     = (string) config('niza_cars.user', '');
        $this->pass     = (string) config('niza_cars.pass', '');
        $this->timeout  = (int)    config('niza_cars.timeout', 20);
    }

    /* ==================== Bootstrap SOAP ==================== */

    private function soapBy(string $key): \SoapClient
    {
        $svc = $this->services[$key] ?? null;
        if (!$svc) {
            throw new \InvalidArgumentException("Service map not found for {$key}");
        }

        $wsdl = "{$this->baseUrl}/{$svc['path']}.asmx?WSDL";

        try {
            $this->nonWsdl = false;
            return new \SoapClient($wsdl, [
                'connection_timeout' => $this->timeout,
                'exceptions'         => true,
                'trace'              => true,
                'cache_wsdl'         => WSDL_CACHE_BOTH,
                'soap_version'       => SOAP_1_1,
            ]);
        } catch (\Throwable $e) {
            // Fallback NON-WSDL
            $this->nonWsdl = true;
            $location = "{$this->baseUrl}/{$svc['path']}.asmx";
            return new \SoapClient(null, [
                'location'           => $location,
                'uri'                => $svc['ns'],
                'use'                => SOAP_LITERAL,
                'style'              => SOAP_DOCUMENT,
                'exceptions'         => true,
                'trace'              => true,
                'connection_timeout' => $this->timeout,
                'soap_version'       => SOAP_1_1,
            ]);
        }
    }

    /** Invoca respetando wrapper/namespace/soapaction */
    private function call(string $key, array $payload)
    {
        $svc    = $this->services[$key] ?? null;
        if (!$svc) {
            throw new \InvalidArgumentException("Service map not found for {$key}");
        }

        $client = $this->soapBy($key);
        $params = $svc['wrap'] ? [[ 'objRequest' => $payload ]] : [$payload];

        if ($this->nonWsdl) {
            return $client->__soapCall($svc['op'], $params, [
                'soapaction' => "{$svc['ns']}/{$svc['op']}",
            ]);
        }
        return $client->__soapCall($svc['op'], $params);
    }

    /* ==================== Utilidades ==================== */

    private function resolveCustomer(string $plan): ?string
    {
        $map = (array) config('niza_cars.customers', []);
        $key = strtoupper($plan);
        return $map[$key] ?? null;
    }

    /* ==================== PRECIOS ==================== */

    /**
     * Variación Niza:
     *  - Archivo:  getmultipleprices.asmx
     *  - Operación: MultiplePrices
     *  - Wrapper:  <objRequest>
     */
    // public function getMultiplePrices(array $params): array
    // {
    //     $plan     = strtoupper($params['plan'] ?? 'FF');
    //     $customer = $this->resolveCustomer($plan) ?? $this->customer;

    //     // OJO con el case del ASMX de Niza (pickUp/dropOff + rentalStation)
    //     $payload = array_merge([
    //         'companyCode'        => $this->company,
    //         'customerCode'       => $customer,
    //         // 'rateCode'           => $params['rateCode'] ?? $plan, // FF/FFF
    //         'onlyDynamicRate'    => "true", //preguntar que es
    //         // En algunas instalaciones lo piden como 'true'/'false' (string)
    //         'includeHourlyRates' => 'false',
    //         'username'           => $this->user ?: null,
    //         'password'           => $this->pass ?: null,
    //         'pickUp' => [
    //             'Date'          => $params['pickup_date']       ?? now()->addDays(3)->format('Y-m-d H:i'),
    //             'rentalStation' => $params['pickup_location_id'] ?? 'MEX1',
    //         ],
    //         'dropOff' => [
    //             'Date'          => $params['dropoff_date']       ?? now()->addDays(6)->format('Y-m-d H:i'),
    //             'rentalStation' => $params['dropoff_location_id'] ?? 'MEX1',
    //         ],
    //     ], $params);

    //     // dd($payload);

    //     $res = $this->call('multiplePrices', $payload);
    //     return json_decode(json_encode($res), true);
    // }



    public function getAvailability(array $searchParams, bool $includeRaw = false): array
    {
        // 1) Resolver oficinas
        $locations = $this->resolveLocations($searchParams);
        if (!$locations['pickupLocation'] || !$locations['dropoffLocation']) {
            return [];
        }

        // 2) Construir payload Niza
        // // Ajustamos a lo que Niza espera (pickUp/dropOff con Date + rentalStation)
        $payload = [
            'companyCode'        => $this->company,
            'customerCode'       => $this->resolveCustomer(strtoupper($params['plan'] ?? 'FF')) ?? $this->customer,
            'onlyDynamicRate'    => 'true',
            'includeHourlyRates' => 'false',
            'username'           => $this->user ?: null,
            'password'           => $this->pass ?: null,
            'pickUp' => [
                'Date'          => $searchParams['pickupDate'] . ' ' . $searchParams['pickupTime'],
                'rentalStation' => $locations['pickupLocation'],
            ],
            'dropOff' => [
                'Date'          => $searchParams['dropoffDate'] . ' ' . $searchParams['dropoffTime'],
                'rentalStation' => $locations['dropoffLocation'],
            ],
        ];

        // dd($payload);

        // 3) Llamada a Niza
        $resArr = json_decode(json_encode($this->call('multiplePrices', $payload)), true);
        // dd($resArr);
        $anyXml = Arr::get($resArr, 'MultiplePricesResult.getMultiplePrices.any');
        if (!$anyXml || !is_string($anyXml)) {
            return [];
        }

        $xml = @simplexml_load_string($anyXml);
        if ($xml === false) {
            return [];
        }
        $xpath = fn($ctx, $exp) => $ctx->xpath($exp) ?: [];
        $mpNodes = $xpath($xml, '//*[local-name()="MultiplePrices"]');
        if (!$mpNodes) {
            return [];
        }

        // 4) Índice (car_name + acriss) desde tu DB
        $vehiclesDb = $this->getVehicles();
        $normalize = function (?string $s) {
            $s = $s ?? '';
            $s = preg_replace('/\s+/', ' ', trim($s));
            return mb_strtolower($s);
        };
        $makeKey = function ($name, $acriss) use ($normalize) {
            if (!$name || !$acriss) return null;
            return $normalize($name).'|'.$normalize($acriss);
        };
        $byNameAcriss = [];
        $byAcriss = []; // fallback por ACRISS solo (si falla el nombre)
        foreach ($vehiclesDb as $v) {
            $name  = $v->car_name ?? null;
            $acr   = $v->acriss ?? ($v->cAcriss ?? null);
            $k     = $makeKey($name, $acr);
            if ($k) $byNameAcriss[$k] = $v;
            if ($acr) $byAcriss[$normalize($acr)][] = $v;
        }

        // 5) Utilidades de cast
        $txt  = fn($n) => isset($n) ? trim((string)$n) : null;
        $dec  = function($n, $scale=2){ if(!isset($n))return null; $v=(string)$n; return is_numeric($v)? round((float)$v,$scale):null; };
        $bool = function($n){ if(!isset($n))return null; $v=strtolower(trim((string)$n)); return in_array($v,['1','true','yes'],true)?1:0; };

        // 6) Heurística de nombre desde imageURL (e.g. fiat_500.png => Fiat 500)
        $nameFromImage = function(?string $url): ?string {
            if (!$url) return null;
            $base = pathinfo($url, PATHINFO_FILENAME);
            $base = preg_replace('/[_\-]+/',' ', $base ?? '');
            $base = trim($base);
            if ($base === '') return null;
            // capitalizar palabras
            return mb_convert_case($base, MB_CASE_TITLE, "UTF-8");
        };

        // 7) Días totales
        $totalDays = $this->calculateFullDays(
            ($searchParams['pickupDate'] ?? '') . ' ' . ($searchParams['pickupTime'] ?? ''),
            ($searchParams['dropoffDate'] ?? '') . ' ' . ($searchParams['dropoffTime'] ?? '')
        );

        $matchList = [];
        $addedCategories = []; // opcional: 1 por categoría
        foreach ($mpNodes as $node) {
            $sipp        = $txt($node->SIPP ?? null);
            $groupName   = $txt($node->group_Name ?? null);
            $imageURL    = $txt($node->imageURL ?? null);
            $rateCode    = $txt($node->rateCode ?? null);
            $nrDays      = (int) ($node->nrDays ?? 0);
            $totalPerDay = $dec($node->totalDayValueWithTax ?? null, 2);
            $preview     = $dec($node->previewValue ?? null, 2);
            $previewDisc = $dec($node->previewValueWithDiscount ?? null, 2);

            // Candidato de nombre para machear con tu catálogo
            $candidate = $nameFromImage($imageURL);
            if (!$candidate) {
                // Limpiar "GRUPO X / MBMR" => intentar dejar solo la parte textual antes del slash
                if (strpos($groupName ?? '', '/') !== false) {
                    [$left, $right] = array_map('trim', explode('/', $groupName, 2));
                    // Si right parece ACRISS, usa left; si no, usa groupName completo
                    $candidate = (preg_match('/^[A-Z0-9]{4}$/', $right ?? '') ? $left : $groupName);
                } else {
                    $candidate = $groupName; // como último recurso
                }
            }

            // Intento principal: nombre + ACRISS
            $key = $makeKey($candidate, $sipp);
            $vehicle = ($key && isset($byNameAcriss[$key])) ? $byNameAcriss[$key] : null;

            // Fallback: por ACRISS y escoger el primero cuya car_name aparezca en candidate (aprox.)
            if (!$vehicle && $sipp && isset($byAcriss[$normalize($sipp)])) {
                foreach ($byAcriss[$normalize($sipp)] as $v) {
                    $n = $normalize($v->car_name ?? '');
                    if ($n && $candidate && str_contains($normalize($candidate), $n)) {
                        $vehicle = $v; break;
                    }
                }
                // Si no hubo coincidencia por substring, toma el primero por ACRISS (opcional)
                if (!$vehicle) {
                    $vehicle = $byAcriss[$normalize($sipp)][0] ?? null;
                }
            }

            if (!$vehicle) {
                continue; // si quieres solo vehículos mapeados por tu catálogo
            }

            // “Uno por categoría” (opcional)
            if (!empty($vehicle->category) && in_array($vehicle->category, $addedCategories, true)) {
                continue;
            }
            if (!empty($vehicle->category)) {
                $addedCategories[] = $vehicle->category;
            }

            // Totales
            // previewValue(WithDiscount) ≈ total con impuestos; si no viene, usa totalDayValueWithTax*nrDays
            $grandTotal = $previewDisc ?? $preview ?? (
                ($totalPerDay !== null && $nrDays > 0) ? ($totalPerDay * $nrDays) : 0.0
            );
            $netPerDay = $totalDays > 0 ? ($grandTotal / $totalDays) : ($totalPerDay ?? 0.0);

            // Extras por día: Niza no manda costo de extras obligatorios aquí → 0
            $extrasTotalEstim = 0.0;

            $item = (object) [
                'vehicleName'      => $vehicle->car_name_mcr ?? $vehicle->car_name ?? $candidate,
                'vehicleCategory'  => $vehicle->category ?? null,
                'vehicleDescription'=> $vehicle->descripccion ?? null,
                'vehicleAcriss'    => $vehicle->cAcriss ?? ($vehicle->acriss ?? $sipp),
                'providerId'       => self::PROVIDER_ID,      // ajusta si usas ID distinto para Niza
                'providerName'     => 'NIZA CARS',
                'pickupOfficeId'   => $locations['pickupOfficeId'],
                'dropoffOfficeId'  => $locations['dropoffOfficeId'],
                'totalDays'        => $totalDays,
                'netRate'          => $netPerDay,             // por día
                'extrasIncluded'   => ($totalDays > 0 ? $extrasTotalEstim / $totalDays : 0),
                'vehicleImage'     => $vehicle->image ?? $imageURL,
                'vehicleId'        => $vehicle->vehicle_id ?? null,
                'vehicleType'      => $vehicle->vehicle_type ?? null,
                'rateCode'         => (string) ($rateCode ?? ''),
                // 'rateId'           => null,                   // Niza no manda rateID aquí
                'classType'        => $sipp,                  // equivalente a ACRISS
                // 'corporateSetup'   => Arr::get($params, 'corporate_setup'),
            ];

            if ($includeRaw) {
                $item->availabilityRequest  = json_encode($payload, JSON_UNESCAPED_UNICODE);
                // guarda solo una “vista” ligera del nodo para no inflar
                $item->availabilityResponse = json_encode([
                    'SIPP' => $sipp,
                    'group_Name' => $groupName,
                    'imageURL' => $imageURL,
                    'rateCode' => $rateCode,
                    'nrDays' => $nrDays,
                    'totalDayValueWithTax' => $totalPerDay,
                    'previewValue' => $preview,
                    'previewValueWithDiscount' => $previewDisc,
                ], JSON_UNESCAPED_UNICODE);
            }

            $matchList[] = $item;
        }

        return $matchList;
    }


        /**
     * Resuelve códigos de oficina (pickup / dropoff) a partir de IATA o params directos.
     * @return array{pickupLocation:?string,dropoffLocation:?string,pickupOfficeId:?int,dropoffOfficeId:?int}
     */
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

        // Caso 2: resolver por IATA + tipo de ubicación
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


            /**
     * Cachea y retorna vehículos del proveedor mapeados a categorías MCR.
     */
    private function getVehicles(): \Illuminate\Support\Collection
    {
        return Cache::remember('group_niza_vehicles', now()->addDays(7), function () {
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


    public function getMultiplePrices(array $params): array
    {
        $plan     = strtoupper($params['plan'] ?? 'FF');
        $customer = $this->resolveCustomer($plan) ?? $this->customer;

        $payload = array_merge([
            'companyCode'        => $this->company,
            'customerCode'       => $customer,
            // 'rateCode'        => $params['rateCode'] ?? $plan, // FF/FFF (opcional)
            'onlyDynamicRate'    => 'true',
            'includeHourlyRates' => 'false',
            'username'           => $this->user ?: null,
            'password'           => $this->pass ?: null,
            'pickUp' => [
                'Date'          => $params['pickup_date']        ?? now()->addDays(3)->format('Y-m-d H:i'),
                'rentalStation' => $params['pickup_location_id'] ?? 'MEX1',
            ],
            'dropOff' => [
                'Date'          => $params['dropoff_date']        ?? now()->addDays(6)->format('Y-m-d H:i'),
                'rentalStation' => $params['dropoff_location_id'] ?? 'MEX1',
            ],
        ], $params);

        // 1) Llamada al servicio
        $res = $this->call('multiplePrices', $payload);
        $arr = json_decode(json_encode($res), true);

        // 2) Tomar el XML diffgram en "any"
        $anyXml = Arr::get($arr, 'MultiplePricesResult.getMultiplePrices.any');
        if (!$anyXml || !is_string($anyXml)) {
            return []; // nada mapeable
        }

        // 3) Parsear XML de forma segura (ignorando namespaces)
        $xml = @simplexml_load_string($anyXml);
        if ($xml === false) {
            return [];
        }

        // Helper: búsqueda por nombre local ignorando namespace
        $xpath = function($ctx, $exp) {
            return $ctx->xpath($exp) ?: [];
        };

        // 4) Extraer nodos <MultiplePrices> (pueden ser varios)
        $mpNodes = $xpath($xml, '//*[local-name()="MultiplePrices"]');
        $mapped  = [];
        $now     = now();

        foreach ($mpNodes as $node) {
            // Helpers para castear
            $txt = fn($n) => isset($n) ? trim((string)$n) : null;
            $dec = function($n, $scale = 2) {
                if (!isset($n)) return null;
                $v = (string)$n;
                return is_numeric($v) ? round((float)$v, $scale) : null;
            };
            $bool = function($n) {
                if (!isset($n)) return null;
                $v = strtolower(trim((string)$n));
                return in_array($v, ['1','true','yes'], true) ? 1 : 0;
            };
            $int = function($n) {
                if (!isset($n)) return null;
                $v = (string)$n;
                return is_numeric($v) ? (int)$v : null;
            };

            dd($node);

            // Campos principales
            $stationId    = $txt($node->stationID ?? null);
            $station      = $txt($node->station ?? null);
            $supplierCode = $txt($node->supplier_Code ?? null);
            $groupId      = $txt($node->groupID ?? null);
            $groupName    = $txt($node->group_Name ?? null);
            $sipp         = $txt($node->SIPP ?? null);
            $imageURL     = $txt($node->imageURL ?? null);
            $rateCode     = $txt($node->rateCode ?? null);
            $dynamicRate  = $bool($node->dynamicRate ?? null);
            $nrDays       = $int($node->nrDays ?? null);

            $dayValue                      = $dec($node->dayValue ?? null, 2);
            $dayValueWithoutRounding       = $dec($node->dayValueWithoutRounding ?? null, 5);
            $currencyRaw                   = $txt($node->currency ?? null);
            $currency                      = $currencyRaw ? substr(trim($currencyRaw), 0, 3) : null;
            $totalDayValueWithTax          = $dec($node->totalDayValueWithTax ?? null, 2);
            $kmsValue                      = $dec($node->kmsValue ?? null, 5);
            $kmsIncluded                   = $bool($node->kmsIncluded ?? null);
            $kmsByDay                      = $bool($node->kmsByDay ?? null);
            $kmsFreePerDay                 = $dec($node->kmsFreePerDay ?? null, 2);
            $previewValue                  = $dec($node->previewValue ?? null, 2);
            $valueWithoutTax               = $dec($node->valueWithotTax ?? null, 2);
            $taxRate                       = $dec($node->taxRate ?? null, 2);
            $otherTaxValue                 = $dec($node->otherTaxValue ?? null, 2);
            $taxValue                      = $dec($node->taxValue ?? null, 2);
            $extrasIncluded                = $txt($node->extrasIncluded ?? null);
            $extrasRequired                = $txt($node->extrasRequired ?? null);
            $extrasAccepted                = $txt($node->extrasAccepted ?? null);
            $extrasAvailable               = $txt($node->extrasAvailable ?? null);
            $package                       = $txt($node->package ?? null);
            $dayValueWithDiscount          = $dec($node->dayValueWithDiscount ?? null, 2);
            $previewValueWithDiscount      = $dec($node->previewValueWithDiscount ?? null, 2);
            $valueWithDiscountWithoutTax   = $dec($node->valueWithDiscountWithoutTax ?? null, 2);
            $taxValueWithDiscount          = $dec($node->taxValueWithDiscount ?? null, 2);
            $percentualDiscount            = $dec($node->percentualDiscount ?? null, 2);
            $prepaidRate                   = $bool($node->prepaidRate ?? null);
            $hourlyRate                    = $bool($node->hourlyRate ?? null);
            $nrHours                       = $int($node->nrHours ?? null);
            $hourValue                     = $dec($node->hourValue ?? null, 2);
            $totalHourValueWithTax         = $dec($node->totalhourValueWithTax ?? null, 2);
            $hourValueWithDiscount         = $dec($node->hourValueWithDiscount ?? null, 2);

            // 5) Extras: dentro de <allExtras> hay un diffgram con múltiples <AllExtras>
            $allExtrasArr = [];
            $allExtrasNodes = $xpath($node, './/*[local-name()="AllExtras"]');
            foreach ($allExtrasNodes as $ex) {
                $allExtrasArr[] = [
                    'groupID'             => $txt($ex->groupID ?? null),
                    'extraID'             => $txt($ex->extraID ?? null),
                    'extra'               => $txt($ex->extra ?? null),
                    'description'         => $txt($ex->description ?? null),
                    'value'               => $dec($ex->value ?? null, 2),
                    'taxRate'             => $dec($ex->taxRate ?? null, 2),
                    'valueWithoutRounding'=> $dec($ex->valueWithoutRounding ?? null, 5),
                    'extraCurrency'       => ($c = $txt($ex->extraCurrency ?? null)) ? substr($c,0,3) : null,
                    'extra_Included'      => $bool($ex->extra_Included ?? null),
                    'extra_Required'      => $bool($ex->extra_Required ?? null),
                    'extra_Accepted'      => $bool($ex->extra_Accepted ?? null),
                    'accept_quantity'     => $bool($ex->accept_quantity ?? null),
                    'insurance'           => $bool($ex->insurance ?? null),
                    'excess'              => $dec($ex->excess ?? null, 2),
                    'must_include'        => $txt($ex->must_include ?? null),
                    'must_not_include'    => $txt($ex->must_not_include ?? null),
                    'extraByDay'          => $bool($ex->extraByDay ?? null),
                ];
            }

            // 6) Nombre para mostrar (temporal): usamos group_name si no hay otro campo
            $carName = $groupName ?: null;

            // 7) Guardar/Upsert en api_niza_cars
            $key = [
                'station_id' => $stationId,
                'sipp'       => $sipp,
                'rate_code'  => $rateCode,
                'group_id'   => $groupId,
            ];

            $data = [
                'station'                        => $station,
                'supplier_code'                  => $supplierCode,
                'group_name'                     => $groupName,
                'image_url'                      => $imageURL,
                'dynamic_rate'                   => $dynamicRate,
                'nr_days'                        => $nrDays,
                'day_value'                      => $dayValue,
                'day_value_without_rounding'     => $dayValueWithoutRounding,
                'currency'                       => $currency,
                'total_day_value_with_tax'       => $totalDayValueWithTax,
                'kms_value'                      => $kmsValue,
                'kms_included'                   => $kmsIncluded,
                'kms_by_day'                     => $kmsByDay,
                'kms_free_per_day'               => $kmsFreePerDay,
                'preview_value'                  => $previewValue,
                'value_without_tax'              => $valueWithoutTax,
                'tax_rate'                       => $taxRate,
                'other_tax_value'                => $otherTaxValue,
                'tax_value'                      => $taxValue,
                'extras_included'                => $extrasIncluded,
                'extras_required'                => $extrasRequired,
                'extras_accepted'                => $extrasAccepted,
                'extras_available'               => $extrasAvailable,
                'package'                        => $package,
                'day_value_with_discount'        => $dayValueWithDiscount,
                'preview_value_with_discount'    => $previewValueWithDiscount,
                'value_with_discount_without_tax'=> $valueWithDiscountWithoutTax,
                'tax_value_with_discount'        => $taxValueWithDiscount,
                'percentual_discount'            => $percentualDiscount,
                'prepaid_rate'                   => $prepaidRate,
                'hourly_rate'                    => $hourlyRate,
                'nr_hours'                       => $nrHours,
                'hour_value'                     => $hourValue,
                'total_hour_value_with_tax'      => $totalHourValueWithTax,
                'hour_value_with_discount'       => $hourValueWithDiscount,
                'all_extras_json'                => $allExtrasArr ? json_encode($allExtrasArr) : null,
                'pickup_datetime'                => Arr::get($payload, 'pickUp.Date')  ? date('Y-m-d H:i:s', strtotime($payload['pickUp']['Date']))  : null,
                'dropoff_datetime'               => Arr::get($payload, 'dropOff.Date') ? date('Y-m-d H:i:s', strtotime($payload['dropOff']['Date'])) : null,
                'car_name'                       => $carName,
                'updated_at'                     => $now,
            ];

            // Para created_at en updateOrInsert: si no existe el registro, lo agrega con created_at
            DB::table('api_niza_cars')->updateOrInsert(
                $key,
                array_merge($data, ['created_at' => $now])
            );

            $mapped[] = array_merge($key, $data);
        }

        return $mapped;
    }

    public function getPriceQuote(array $params): array
    {
        $plan     = strtoupper($params['plan'] ?? 'FF');
        $customer = $this->resolveCustomer($plan) ?? $this->customer;

        // En PriceQuote el “case” suele ser el estándar (PickUp/DropOff con RentalStation)
        $payload = array_merge([
            'companyCode'        => $this->company,
            'customerCode'       => $customer,
            'rateCode'           => $params['rateCode'] ?? $plan,
            'includeHourlyRates' => $params['includeHourlyRates'] ?? false,
            // Si vienes de MultiplePrices y te devolvió un "package", pásalo aquí:
            // 'package' => $params['package'] ?? null,
            'PickUp' => [
                'Date'          => $params['PickUp']['Date']          ?? now()->addDays(3)->format('Y-m-d H:i'),
                'RentalStation' => $params['PickUp']['RentalStation'] ?? 'MEX1',
            ],
            'DropOff' => [
                'Date'          => $params['DropOff']['Date']          ?? now()->addDays(6)->format('Y-m-d H:i'),
                'RentalStation' => $params['DropOff']['RentalStation'] ?? 'MEX1',
            ],
        ], $params);

        $res = $this->call('getPriceQuote', $payload);
        return json_decode(json_encode($res), true);
    }

    /* ==================== RESERVAS ==================== */

    public function createReservation(array $params): array
    {
        $plan     = strtoupper($params['plan'] ?? 'FF');
        $customer = $this->resolveCustomer($plan) ?? $this->customer;

        $payload = array_merge([
            'CompanyCode' => $this->company,
            'ClienteCode' => $customer,
            'Username'    => $this->user,
            'Password'    => $this->pass,
            'MessageType' => 'N', // N=New
            'Group'       => $params['Group']    ?? 'A',
            'RateCode'    => $params['RateCode'] ?? $plan,
            // Si traes package de precios, pásalo también:
            // 'Package'     => $params['Package'] ?? null,
            'PickUp' => [
                'Date'           => $params['PickUp']['Date']           ?? now()->addDays(3)->format('Y-m-d H:i'),
                'Rental_Station' => $params['PickUp']['Rental_Station'] ?? 'MEX1',
            ],
            'DropOff' => [
                'Date'           => $params['DropOff']['Date']           ?? now()->addDays(6)->format('Y-m-d H:i'),
                'Rental_Station' => $params['DropOff']['Rental_Station'] ?? 'MEX1',
            ],
            'Driver' => $params['Driver'] ?? [
                'Name'          => 'Sanchez,Adrian',
                'Email'         => 'adrian@example.com',
                'Date_of_Birth' => '1990-01-01',
            ],
            // 'Extras' => 'CDW,ADD', // ejemplo
        ], $params);

        $res = $this->call('Create_Reservation', $payload);
        return json_decode(json_encode($res), true);
    }

    /* ==================== CATÁLOGOS ==================== */

    public function getCountries(bool $allCountries = false): array
    {
        $payload = [
            'companyCode'  => (string) $this->company,
            'allCountries' => (bool) $allCountries,
        ];
        $res = $this->call('getCountries', $payload);
        return json_decode(json_encode($res), true);
    }

    public function getCities(?int $countryID = null): array
    {
        $payload = array_filter([
            'companyCode' => (string) $this->company,
            'countryID'   => $countryID,
        ], fn($v) => $v !== null && $v !== '');
        $res = $this->call('getCities', $payload);
        return json_decode(json_encode($res), true);
    }

    public function getStations(array $filters = []): array
    {
        $payload = array_filter([
            'companyCode'    => (string) $this->company,
            'customerCode'   => (string) $this->customer,
            'countryID'      => $filters['countryID'] ?? null,
            'City'           => $filters['City'] ?? null,
            'onlyVLSEnabled' => $filters['onlyVLSEnabled'] ?? null,
        ], fn($v) => $v !== null && $v !== '');
        $res = $this->call('getStations', $payload);
        return json_decode(json_encode($res), true);
    }

    public function getStationDetails(string $stationID): array
    {
        $payload = [
            'companyCode' => (string) $this->company,
            'stationID'   => (string) $stationID,
        ];
        $res = $this->call('getStationDetails', $payload);
        return json_decode(json_encode($res), true);
    }

    public function getGroups(): array
    {
        $payload = [
            'companyCode'  => (string) $this->company,
            'customerCode' => (string) $this->customer,
        ];
        $res = $this->call('getGroups', $payload);
        return json_decode(json_encode($res), true);
    }

    public function getExtras(): array
    {
        $payload = [
            'companyCode'  => (string) $this->company,
            'customerCode' => (string) $this->customer,
        ];
        $res = $this->call('getExtras', $payload);
        return json_decode(json_encode($res), true);
    }

    public function getOneWay(array $filters = []): array
    {
        $payload = array_filter([
            'companyCode' => (string) $this->company,
            'countryID'   => $filters['countryID'] ?? null,
            'city'        => $filters['city'] ?? null,
            'stationID'   => $filters['stationID'] ?? null,
        ], fn($v) => $v !== null && $v !== '');
        $res = $this->call('getOneWay', $payload);
        return json_decode(json_encode($res), true);
    }

    /* ==================== Helpers de sincronización (opcionales) ==================== */

    /** Guarda Countries en tu tabla local (ejemplo de parseo diffgram) */
    public function syncCountriesToDb(bool $allCountries = true): int
    {
        $arr = $this->getCountries($allCountries);
        $xml = data_get($arr, 'getCountriesResult.countries.any');
        if (!$xml || !is_string($xml)) return 0;

        $diff = @simplexml_load_string($xml);
        if ($diff === false) return 0;

        $rows = $diff->xpath("//*[local-name()='Table']");
        if (!$rows) return 0;

        $now = now();
        $toBool = static fn($v) => in_array(strtolower(trim((string) $v)), ['1','true','yes'], true);

        $batch = [];
        foreach ($rows as $row) {
            $id   = (int) ((string) ($row->countryID ?? 0));
            $name = trim((string) ($row->Country ?? $row->country ?? ''));
            if (!$id || $name === '') continue;

            $iso  = trim((string) ($row->ISOCode ?? '')) ?: null;
            $vpc  = $toBool($row->ValidatePostalCode ?? 'false');
            $dtm  = $toBool($row->DriverTaxNumberMandatory ?? 'false');
            $pcc  = (string) ($row->PhoneCountryCode ?? '');
            $pcc  = strlen($pcc) ? (int) $pcc : null;

            $batch[] = [
                'country_id'                  => $id,
                'country'                     => $name,
                'iso_code'                    => $iso,
                'validate_postal_code'        => $vpc,
                'driver_tax_number_mandatory' => $dtm,
                'phone_country_code'          => $pcc,
                'created_at'                  => $now,
                'updated_at'                  => $now,
            ];
        }

        if (!$batch) return 0;

        foreach (array_chunk($batch, 500) as $chunk) {
            DB::table('api_niza_countries')->upsert(
                $chunk,
                ['country_id'],
                ['country','iso_code','validate_postal_code','driver_tax_number_mandatory','phone_country_code','updated_at']
            );
        }
        return count($batch);
    }

    /** Ejemplo de sincronización de Stations (usa getStations tal cual regresa el diffgram) */
    public function syncStationsToDb(array $filters = []): int
    {
        $arr = $this->getStations($filters);

        $xml = data_get($arr, 'getStationsResult.stations.any');
        if (!$xml || !is_string($xml)) return 0;

        $diff = @simplexml_load_string($xml);
        if ($diff === false) return 0;

        $rows = $diff->xpath("//*[local-name()='Table']");
        if (!$rows) return 0;

        $now = now();
        $toBool = static fn($v) => in_array(strtolower(trim((string) $v)), ['1','true','yes'], true);
        $toNum  = static fn($v) => is_numeric((string) $v) ? (float) $v : null;
        $toInt  = static fn($v) => strlen(trim((string) $v)) ? (int) $v : null;

        $batch = [];
        foreach ($rows as $row) {
            $sid = trim((string) ($row->StationID ?? ''));
            $st  = trim((string) ($row->Station   ?? ''));
            if ($sid === '' || $st === '') continue;

            $batch[] = [
                'station_id'   => $sid,
                'station'      => $st,
                'zone'         => $toInt($row->Zone ?? null),
                'station_type' => $toInt($row->StationType ?? null),
                'country_id'   => $toInt($row->CountryID ?? null),
                'city'         => trim((string) ($row->City ?? '')) ?: '',
                'supplier_id'  => $toInt($row->SupplierID ?? null),
                'latitude'     => $toNum($row->Latitude ?? null),
                'longitude'    => $toNum($row->Longitude ?? null),
                'vls_enabled'  => $toBool($row->VLSEnabled ?? 'false') ? 1 : 0,
                'fsv_enabled'  => $toBool($row->FSVEnabled ?? 'false') ? 1 : 0,
                'created_at'   => $now,
                'updated_at'   => $now,
            ];
        }

        if (!$batch) return 0;

        foreach (array_chunk($batch, 500) as $chunk) {
            DB::table('api_niza_stations')->upsert(
                $chunk,
                ['station_id'],
                ['station','zone','station_type','country_id','city','supplier_id','latitude','longitude','vls_enabled','fsv_enabled','updated_at']
            );
        }
        return count($batch);
    }

        /** Días completos (ceil). */
    public function calculateFullDays(string $startDate, string $endDate): int
    {
        $start = Carbon::parse($startDate);
        $end   = Carbon::parse($endDate);
        $minutes = $start->diffInMinutes($end);
        return (int) ceil($minutes / 1440);
    }

}
