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
use Illuminate\Support\Facades\Process;

class AvailabilityRepository
{
    private $europcarGroupRp;
    private $mexGroupRp;
    private $americaGroupRp;
    private $infinityGroupRp;

    /**
     * Create a new repository instance.
     *
     * @return void
     */
    public function __construct(
        EuropcarGroupRepository $europcarGroupRp, 
        MexGroupRepository $mexGroupRp,
        AmericaGroupRepository $americaGroupRp,
        InfinityGroupRepository $infinityGroupRp)
    {
        $this->europcarGroupRp = $europcarGroupRp;
        $this->mexGroupRp = $mexGroupRp;
        $this->americaGroupRp = $americaGroupRp;
        $this->infinityGroupRp = $infinityGroupRp;
    }

    // Return availability with one car by type
    public function getOnlyOnePerCarType($searchParams)
    {
        $searchParams = $this->adaptSearchParams($searchParams);
        $fleet = $this->filterUniqueCarTypes($this->getAvailabilityFromEngine($searchParams));
        $adaptedFleet = $this->adaptVehicles($fleet, $searchParams);
        return $adaptedFleet;
    }

    public function getQuotation($searchParams, $searchType = "PROVEEDOR_GANADOR")
    {
        $searchParams = $this->adaptSearchParams($searchParams);

        $fleet = $this->getAvailabilityFromEngine($searchParams, $searchType);

        $adaptedFleet = $this->adaptVehicles($fleet, $searchParams);

        $quotation = $this->storeQuotation($searchParams, $adaptedFleet);

        if($adaptedFleet) {
            $this->saveSearchHistory($searchParams, $adaptedFleet);
        }

        return $quotation;
    }

    public function getCheapestCategoryByDestination($vehicles, $searchParams)
    {
        // $adaptedFleet = [];
        // if (Cache::has('promotions')) {
        //     $fleetData = Cache::get('promotions', []);
        //     if (count($fleetData) > 0) {
        //         $fleet = collect($fleetData)->take(6);
        //         $searchParams = [
        //             // 'IATA' => $vehicle->clave_destino,
        //             'pickupLocation' => 'Aeropuerto',
        //             'pickupDate' =>  Session::get('defaultPickupDate', Carbon::now()->addDays(2)->format('Y-m-d')),
        //             'dropoffDate' => Session::get('defaultDropoffDate', Carbon::now()->addDays(7)->format('Y-m-d')),
        //             'pickupTime' => '10:00',
        //             'dropoffTime' => '10:00',
        //             'isDebit' => 0
        //         ];
        //         // $searchParams = $this->adaptSearchParams($searchParams);
        //         $adaptedFleet = $this->adaptVehicles($searchParams);
        //     }
        // }
        return $this->adaptVehicles($vehicles, $searchParams);
    }

    public function storeQuotation($searchParams, $fleet)
    {
        $quotation = [
            'quotationId' => (string) Str::uuid(),
            'searchParams' => $searchParams,
            'fleet' => $fleet,
            'filters' => [
                'categories' => []
            ]
        ];

        Cache::put($quotation['quotationId'], $quotation, 10080);

        return $quotation;
    }

    private function adaptSearchParams($searchParams)
    {
        $pickupDate = Carbon::parse($searchParams['pickupDate']);
        $dropoffDate = Carbon::parse($searchParams['dropoffDate']);

        $searchParams['pickupHumanDate'] = $pickupDate->toFormattedDateString();
        $searchParams['dropoffHumanDate'] = $dropoffDate->toFormattedDateString();

        $searchParams['destinationName'] = "";
        $destinationData = DB::table('directorio')
                            ->select(['city_name', 'country_name'])
                            ->where('clave', '=', $searchParams['IATA'])
                            ->first();

        if($destinationData) {
            $searchParams['destinationName'] = $destinationData->city_name;
            $searchParams['countryName'] = $destinationData->country_name;
        }

        return $searchParams;
    }

    private function adaptVehicles($vehicles, $searchParams)
    {
        $hasToValidateCurrency = true;

        // Verificar si 'countryName' no existe o está vacío, y asignar "Mexico" por defecto
        if (!isset($searchParams['countryName']) || empty($searchParams['countryName'])) {
            $searchParams['countryName'] = 'México';
        }

        if($searchParams['countryName'] != 'México') {
            $hasToValidateCurrency = false;
        }

        $currency = $searchParams['currency'] ?? null;
        
        Utilities::setCurrency($searchParams['countryName'], $currency);
        $currency = Session::get('currency');

        // dd($currency);

        if($hasToValidateCurrency) {
            $exchangeRate = $this->getExchangeRate($currency);
        } else {
            $exchangeRate = (object)['amount' => 1];
        }

        
        $user = auth()->check() ? auth()->user(): null;
        $campaign = Session::has('id_campaign') ? $this->checkIfApplyCampaign($searchParams): null;

        if(!isset($searchParams['isDebit'])) $searchParams['isDebit'] = 0;

        if($searchParams['isDebit'] == 0 && $searchParams['pickupLocation'] == 'Aeropuerto') {
            // $europcarFleet = $this->europcarGroupRp->getAvailability($searchParams, 'europcar');

            if (array_key_exists('IATA', $searchParams)) {
                
                $mergedFleet = [];
                $cheapestRates = [];

                // $vehicles = []; //borrar


                $americaFleet = $this->americaGroupRp->getAvailability($searchParams, 'america');
                $mergedFleet = array_merge($mergedFleet, $americaFleet);

                $infinityFleet = $this->infinityGroupRp->getAvailability($searchParams, 'infinity');
                $mergedFleet = array_merge($mergedFleet, $infinityFleet);

                // Mex Rent a Car
                $mexFleet = $this->mexGroupRp->getAvailability($searchParams);
                $mergedFleet = array_merge($mergedFleet, $mexFleet);
                
                // Europcar
                $mergedFleetByProvider = $this->europcarGroupRp->getAvailabilityForCheapestProvider($searchParams);
                foreach ($mergedFleetByProvider as $providerFleet) {
                    $mergedFleet = array_merge($mergedFleet, $providerFleet);
                }

                foreach ($mergedFleet as $item) {
                    $category = $item->vehicleCategory; // Categoría del vehículo

                    // Si no existe la categoría o el netRate es menor, actualizar el resultado
                    if (!isset($cheapestRates[$category]) || $item->netRate < $cheapestRates[$category]->netRate) {
                        $cheapestRates[$category] = $item;
                    }
                }

                // Convertir a un arreglo indexado (remover claves asociativas)
                $cheapestRates = array_values($cheapestRates);

                // Si hay tarifas más baratas, realizar la comparación
                if ($cheapestRates) {
                    $vehicles = $this->europcarGroupRp->compareRates($cheapestRates, $vehicles, $searchParams);
                }

            }
        }

        $adaptedFleet = array_filter(array_map(function ($vehicle) use ($currency, $exchangeRate, $user, $searchParams, $campaign) {
            $adaptedVehicle = $this->adaptVehicle($vehicle, $currency, $exchangeRate, $user, $searchParams, $campaign);

            // Verificamos si el vehículo tiene OFF_SELL como true y lo omitimos
            return $adaptedVehicle->OFF_SELL ? null : $adaptedVehicle;
        }, $vehicles));

        // Eliminar los valores null (vehículos no adaptados) del array
        $adaptedFleet = array_values(array_filter($adaptedFleet));

        return $adaptedFleet;
    }

    private function adaptVehicle($vehicle, $currency = "MXN", $exchangeRate, $user = null, $searchParams, $campaign = null)
    {
        
        $adaptedVehicle = (object) [
            'packageId' => (string) Str::uuid(),
            'OFF_SELL' => ($vehicle->offcell_completo>0 or $vehicle->sinTarifas=='1' or $vehicle->tarifaPublica ==0 or $vehicle->tarifaNeta ==0 ) ? 1: 0,
            'ON_REQUEST' => ($vehicle->onRequest_completo > 0),
            'image' => $vehicle->imagen ?? "",
            'vehicleName' => $vehicle->nombreAuto,
            'vehicleCategory' => $vehicle->categoria,
            'vehicleType' => $vehicle->tipo,
            'vehicleAcriss' => $vehicle->cAcriss,
            'vehicleId' => $vehicle->id_auto,
            'characteristics' => explode('|',str_replace(array("<br>","<br/>","<br />"),"|",$vehicle->descripccion)),
            'providerId' => $vehicle->id_proveedor,
            'pickupOfficeId' => $vehicle->id_datos_directorio_abrir,
            'dropoffOfficeId' => $vehicle->id_datos_directorio_cerrar,
            'currency' => $currency,
            'exchangeRate' => $exchangeRate->amount,
            'netRate' => $vehicle->tarifaNeta,
            'totalDays' => $vehicle->totalDiasReservacion,
            'discount' => $vehicle->descuento,
            'mktRateAmount' => $vehicle->tarifaPublica, // Tarifa sin descuento.
            'mktRate' => number_format($vehicle->tarifaPublica, 2),
            'hasAdditionalPromotion' => false,
            'hasCoupon' => false,
        ];
        
        // Europcar Identifier

        if (isset($adaptedVehicle->providerId) && 
            ($adaptedVehicle->providerId == 1 || $adaptedVehicle->providerId == 93 || $adaptedVehicle->providerId == 109)) {
            
            if (isset($vehicle->sessionId)) {
                $adaptedVehicle->sessionId = $vehicle->sessionId;
            }
            
            if (isset($vehicle->bookId)) {
                $adaptedVehicle->bookId = $vehicle->bookId;
            }

            $adaptedVehicle->providerCarModel = $vehicle->providerCarModel;

        }
        
        if (isset($adaptedVehicle->providerId) && $adaptedVehicle->providerId == 28) {
            
            if (isset($vehicle->availabilityResponse)) {
                $adaptedVehicle->availabilityResponse = $vehicle->availabilityResponse;
            }

            if(isset($vehicle->availabilityRequest)) {
                $adaptedVehicle->availabilityRequest = $vehicle->availabilityRequest;
            }

            if(isset($vehicle->corporateSetup)) {
                $adaptedVehicle->corporateSetup = $vehicle->corporateSetup;
            }
            
            if (isset($vehicle->classType)) {
                $adaptedVehicle->classType = $vehicle->classType;
            }
            
            if (isset($vehicle->rateId)) {
                $adaptedVehicle->rateId = $vehicle->rateId;
            }
            
            if (isset($vehicle->rateCode)) {
                $adaptedVehicle->rateCode = $vehicle->rateCode;
            }
   
        }

        if(isset($adaptedVehicle->providerId) && 
        ($adaptedVehicle->providerId == 32 || $adaptedVehicle->providerId == 106)) {
            
            if (isset($vehicle->availabilityResponse)) {
                $adaptedVehicle->availabilityResponse = $vehicle->availabilityResponse;
            }

            if(isset($vehicle->availabilityRequest)) {
                $adaptedVehicle->availabilityRequest = $vehicle->availabilityRequest;
            }

            if(isset($vehicle->vendorRateId)) {
                $adaptedVehicle->vendorRateId = $vehicle->vendorRateId;
            }

            if(isset($vehicle->carType)) {
                $adaptedVehicle->carType = $vehicle->carType;
            }
        }

        $adaptedVehicle->vehicleDescription = '';
        foreach ($adaptedVehicle->characteristics as $index => $item) {
            $adaptedVehicle->vehicleDescription .= $item . ' | ';
        }
        $adaptedVehicle->vehicleDescription = substr($adaptedVehicle->vehicleDescription, 0, -3);

        if (!array_key_exists('IATA', $searchParams)) {
            $searchParams['IATA'] = $vehicle->clave_destino;
            $adaptedVehicle->destinationCode = $searchParams['IATA'];
            $adaptedVehicle->destinationName = $vehicle->ciudad;
        }

        $adaptedVehicle->fleetUrl = $this->generateFleetUrl($adaptedVehicle, $searchParams);

        if($campaign !== null) {
            $adaptedVehicle = $this->applyCampaign($campaign, $searchParams, $adaptedVehicle); // Revisa si tiene promociones y actualiza descuento.
        }

        $publicRate = round($adaptedVehicle->mktRateAmount * (1 - $adaptedVehicle->discount / 100));
        $adaptedVehicle->publicRateAmount = $publicRate;
        $adaptedVehicle->publicRate = number_format($publicRate, 2); // Tarifa con descuento.

        $adaptedVehicle->mupDiscount = 0;
        $adaptedVehicle->discountPlatinum = $adaptedVehicle->discount;

        if ($user && $user->isPlatinum) {
            $publicRate = $this->calculatePlatinumRate($publicRate, $adaptedVehicle->netRate);
            $adaptedVehicle->publicRateAmount = $publicRate;
            $adaptedVehicle->publicRate = number_format($publicRate, 2);
            $adaptedVehicle->discountPlatinum = $this->calculateDiscountPlatinum($publicRate, $adaptedVehicle->mktRateAmount);
            $adaptedVehicle->mupDiscount = 15;
        }

        // dd($publicRate);

        $prepayment = ($publicRate  * $adaptedVehicle->totalDays) - ($adaptedVehicle->netRate * $adaptedVehicle->totalDays);
        $totalNetRate = ($adaptedVehicle->netRate * $adaptedVehicle->totalDays);
        $adaptedVehicle->total = ($publicRate * $adaptedVehicle->totalDays);

        if($adaptedVehicle->hasAdditionalPromotion && $adaptedVehicle->hasCoupon) { // Landing page promotions

            // $adaptedVehicle->couponAmount = $adaptedVehicle->couponAmount;
            // $couponAmount = $adaptedVehicle->couponAmount;

            $adaptedVehicle->publicRateAmount = ($totalNetRate + $prepayment) / $adaptedVehicle->totalDays;
            $publicRate =  $adaptedVehicle->publicRateAmount;
            $adaptedVehicle->publicRate = number_format($adaptedVehicle->publicRateAmount);
            // dd($prepayment, $adaptedVehicle->couponAmount);
            $prepaymentCoupon = ($prepayment - $adaptedVehicle->couponAmount);
            $adaptedVehicle->publicRateAmountCoupon = ($totalNetRate +  $prepaymentCoupon) / $adaptedVehicle->totalDays;

            $prepayment = $prepayment - $adaptedVehicle->couponAmount;
            $adaptedVehicle->total = $adaptedVehicle->total - $adaptedVehicle->couponAmount;
        }

        // dd($adaptedVehicle->total);
        if ($currency === 'USD') {
            $adaptedVehicle->mktRateAmount = round($adaptedVehicle->mktRateAmount / $exchangeRate->amount);
            $adaptedVehicle->mktRate = number_format($adaptedVehicle->mktRateAmount, 2);
            $adaptedVehicle->publicRateAmount = round($publicRate / $exchangeRate->amount);
            $adaptedVehicle->publicRate = number_format(round($publicRate / $exchangeRate->amount), 2);

            $prepayment = round($prepayment / $exchangeRate->amount);
            $totalNetRate = $totalNetRate / $exchangeRate->amount;
            $publicRate = round($publicRate / $exchangeRate->amount);


            $adaptedVehicle->total = $publicRate * $adaptedVehicle->totalDays;

            if($adaptedVehicle->hasAdditionalPromotion && $adaptedVehicle->hasCoupon) {
                $adaptedVehicle->publicRateAmountCoupon = round($adaptedVehicle->publicRateAmountCoupon / $exchangeRate->amount);
                $adaptedVehicle->couponAmount = round($adaptedVehicle->couponAmount / $exchangeRate->amount);
                $adaptedVehicle->total = ($publicRate * $adaptedVehicle->totalDays) -  $adaptedVehicle->couponAmount;
            }
        }

        // dd($adaptedVehicle);

        $adaptedVehicle->prepayment = $prepayment;
        $adaptedVehicle->totalNetRate = $totalNetRate;

        // dd($adaptedVehicle);



        // CancellationFee Calculations
        $adaptedVehicle->cancellationFee = $this->calculateCancellationFee($adaptedVehicle->total, $adaptedVehicle->totalNetRate);
        $adaptedVehicle->cancellationFeeCheck = true;

        // AdditionalDriverFee Calculations
        $adaptedVehicle->additionalDriver = $this->calculateAdditionalDriver($adaptedVehicle->totalDays, $exchangeRate);
        $adaptedVehicle->additionalDriverCheck = false;

        if($adaptedVehicle->providerId != 1 || $adaptedVehicle->providerId != 93 || $adaptedVehicle->providerId != 109 || $adaptedVehicle->providerId != 32 || $adaptedVehicle->providerId != 28) {
            $adaptedVehicle->ON_REQUEST = $this->recheckOnRequest($searchParams, $adaptedVehicle);
        } else {
            $adaptedVehicle->ON_REQUEST = false;
        }

        // if($currency === 'USD') {

        // }

        return $adaptedVehicle;

    }

    private function calculateCancellationFee($total, $totalNetRate)
    {
        return (((($total - $totalNetRate)) / 100) * 18);
    }

    private function calculateAdditionalDriver($days, $exchangeRate)
    {
        return ($days * 100) / $exchangeRate->amount;
    }

    private function checkIfApplyCampaign($searchParams)
    {
        $campaign = null;
        $today = Carbon::now()->format('Y-m-d');

        $campaignData = DB::table('templates')
        ->where('campaign_code', Session::get('id_campaign'))
        ->where(function($query) use ($today, $searchParams) {
            $query->where(function($subquery) use ($today) {
                $subquery->where('templates.campaign_duration', 'TEMPORARY')
                        ->where('templates.campaign_start_date', '<=', $today)
                        ->where('templates.campaign_end_date', '>=', $today);
            })
            ->orWhere(function($subquery) use ($searchParams) {
                $subquery->where('templates.search_range_dates', 'BETWEEN')
                        ->where('templates.range_start_date', '<=', $searchParams['pickupDate'])
                        ->where('templates.range_end_date', '>=', $searchParams['dropoffDate']);
            })
            ->orWhere(function($subquery) {
                $subquery->where('templates.campaign_duration', 'PERMANENT');
            })
            ->orWhere(function($subquery) {
                $subquery->where('templates.search_range_dates', 'ALL_DATES');
            });
        })
        ->where('status', 'active')
        ->first();

        if ($campaignData) {
            $campaign = $campaignData;
        }

        return $campaign;
    }

    private function applyCampaign($campaign, $searchParams, $adaptedVehicle)
    {

        $adaptedVehicle->hasAdditionalPromotion = false;
        $adaptedVehicle->hasCoupon = false;

        $ad = new \StdClass();
        $ad->categories = explode(',', $campaign->categories);
        $ad->destinations = explode(',', $campaign->destinations);
        $ad->campaignCode = $campaign->campaign_code;
        $ad->discountType = $campaign->discount_type;
        $ad->minDays = $campaign->min_rent_days;
        $ad->hasConfiguration = false;

        if(in_array($searchParams['IATA'], $ad->destinations) || in_array('ALL', $ad->destinations)) {
            $ad->hasConfiguration = true;
            if($ad->discountType != 'NONE') {
                $ad->discount = $campaign->discount;
            }
        }

        if( $ad->hasConfiguration &&
            (in_array($adaptedVehicle->vehicleCategory, $ad->categories) || in_array('ALL', $ad->categories)) &&
            $adaptedVehicle->totalDays >= $ad->minDays
        ) {
            if( $ad->discountType == 'PERCENTAGE') {
                $adaptedVehicle->discount = $ad->discount;
            } else if ($ad->discountType == 'AMOUNT') {
                $adaptedVehicle->hasCoupon = true;
                $adaptedVehicle->couponAmount = $ad->discount;
                $adaptedVehicle->couponCode = $ad->campaignCode;
            }
                $adaptedVehicle->hasAdditionalPromotion = true;
        }

        return $adaptedVehicle;
    }

    private function recheckOnRequest($searchParams, $vehicle)
    {
        $now = Carbon::now();
        $pickup = Carbon::parse($searchParams['pickupDate'] . ' ' . $searchParams['pickupTime']);

        $isOnrequest = $vehicle->ON_REQUEST;

        if($now->diffInHours($pickup) < 24) {
            if (in_array($vehicle->providerId, [41, 47, 33, 34])) {
                if(!($now->diffInHours($pickup) >= 12)) {
                    $isOnrequest = true;
                }
            } else {
                $isOnrequest = true;
            }
        }

        return $isOnrequest;
    }

    private function getExchangeRate($currency)
    {
        if ($currency === 'USD') {
            return DB::table('tipo_cambio')
                ->select('pesos as amount', 'divisa as currency')
                ->where('divisa', 'LIKE', 'USD')
                ->first();
        }

        return (object)['amount' => 1];
    }

    private function calculatePlatinumRate($publicRate, $netRate)
    {
        $mupPerDay = $publicRate - $netRate;
        return round($netRate + ($mupPerDay * (1 - 0.15)));
    }

    private function calculateDiscountPlatinum($publicRate, $mktRateAmount)
    {
        return 100 - (round(($publicRate * 100)/ $mktRateAmount ));
    }

    private function generateFleetUrl($vehicle, $searchParams)
    {
       return '/feed/' . $searchParams['IATA'] .
                        '?pickupDate=' . $searchParams['pickupDate'] .
                        '&dropoffDate=' . $searchParams['dropoffDate'] .
                        '&pickupTime=' .  $searchParams['pickupTime'] .
                        '&dropoffTime=' . $searchParams['dropoffTime'] .
                        '&vehicleCategory=' . $vehicle->vehicleCategory .
                        '&vehicleName=' . $vehicle->vehicleName;
    }


    private function saveSearchHistory(array $searchParams, $fleet)
    {
        if(strtolower(config('app.env')) == 'production') {
            $user = auth()->check() ? auth()->user(): null;
            DB::table('search_history')->insert([
                'date' => now(),
                'destination' => $searchParams['IATA'],
                'month' => date('m', strtotime($searchParams['pickupDate'])),
                'pickup_date' => $searchParams['pickupDate'],
                'pickup_time' => $searchParams['pickupTime'],
                'dropoff_date' => $searchParams['dropoffDate'],
                'dropoff_time' => $searchParams['dropoffTime'],
                'price' => $fleet[0]->publicRateAmount,
                'category' => $fleet[0]->vehicleCategory,
                'cf' => ($user) ? $user->cf: null,
                'currency' => $fleet[0]->currency,
                'origin' => 'MCR',
                'user_id' => ($user) ? $user->id: null
            ]);
        }
    }

     // FIlters
     private function filterUniqueCarTypes($vehicles)
     {
         return collect($vehicles)
         ->unique('tipo')
         ->values()
         ->all();
     }


    // Database access
    public function getAvailabilityFromEngine($params, $searchType = "PROVEEDOR_GANADOR")
    {
        $fleet = [];
        $params['isDebit'] ??= 0;
        $sp = $params['isDebit'] == "1" ? "sp_flota_tarifario_cruce_copy_debit" : "sp_flota_tarifario_cruce_copy";

        // Normalización de parámetros
        $params['dropoffLocation'] = $params['pickupLocation'];
        $params = array_merge($params, [
            'providers' => "",
            'categories' => "",
            'MCRPriority' => "",
            'onlyDPA' => "",
            'includeOnrequest' => "1",
            'specialDiscount' => auth()->check() && auth()->user()->isPlatinum ? '1' : ''
        ]);

        $searchQuery = $this->buildSearchQuery($sp, $params, $searchType);

        try {
            $fleet = DB::select(DB::raw($searchQuery));
        } catch (\Exception $e) {
            Log::info($e->getMessage());
        }

        return $fleet;
    }

    private function buildSearchQuery($sp, $params, $searchType)
    {
        $params['specialDiscount'] = "";

        return "call $sp(
            '$searchType',                                  /* tipo_consulta       */
            '{$params['IATA']}',                            /* IATA                */
            '{$params['pickupDate']}',                      /* fhInicio            */
            '{$params['dropoffDate']}',                     /* fhFin               */
            '{$params['pickupLocation']}',                  /* ubicacion           */
            '{$params['dropoffLocation']}',                 /* ubicacion_do        */
            '{$params['pickupTime']}',                      /* hora_pu             */
            '{$params['dropoffTime']}',                     /* hora_do             */
            '1',                                            /* orderbyTarifaPublica*/
            '{$params['providers']}',                       /* PROVEEDORES         */
            '{$params['categories']}',                      /* CATEGORIAS          */
            '{$params['MCRPriority']}',                     /* quitarPrioridadMCR  */
            '{$params['onlyDPA']}',                         /* soloDpa             */
            '{$params['includeOnrequest']}',                /* Incluir_ONREQUEST   */
            '',                                             /* PeriodosOffcell     */
            '',                                             /* sinOficinas         */
            '',                                             /* ExcluirProveedores  */
            '',                                             /* __PARAM1__          */
            '1',                                            /* __MARCA__           */
            '{$params['specialDiscount']}'                  /* __PARAM3__          */
        );";
    }

    public function prepareAppQuotation($searchParams, $searchType = "PROVEEDOR_GANADOR")
    {
        $searchParams = $this->adaptSearchParams($searchParams);

        $fleet = $this->getAvailabilityFromEngine($searchParams, $searchType);

        $adaptedFleet = $this->adaptVehiclesToMobileApp($fleet, $searchParams);

        $quotation = $this->storeQuotation($searchParams, $adaptedFleet);

        // if($adaptedFleet) {
        //     $this->saveSearchHistory($searchParams, $adaptedFleet);
        // }

        return $quotation;
    }


    
    private function adaptVehiclesToMobileApp($vehicles, $searchParams)
    {
        $currency = $searchParams['currency'] ?? 'MXN';
        $exchangeRate = $this->getExchangeRate($currency);
        $campaign = null;
        $user = null;

        // Obtener la disponibilidad de todos los proveedores simultáneamente
        // $mergedFleetByProvider = $this->europcarGroupRp->getAvailabilityForAllProviders($searchParams);
        $mergedFleetByProvider = [];

        // Aplanar las listas de todos los proveedores en una sola lista
        $mergedFleet = [];
        foreach ($mergedFleetByProvider as $providerFleet) {
            $mergedFleet = array_merge($mergedFleet, $providerFleet);
        }

        // Inicializar las tarifas más baratas por categoría
        $cheapestRates = [];

        foreach ($mergedFleet as $item) {
            $category = $item->vehicleCategory; // Categoría del vehículo

            // Si no existe la categoría o el netRate es menor, actualizar el resultado
            if (!isset($cheapestRates[$category]) || $item->netRate < $cheapestRates[$category]->netRate) {
                $cheapestRates[$category] = $item;
            }
        }

        // Convertir a un arreglo indexado (remover claves asociativas)
        $cheapestRates = array_values($cheapestRates);

        // Si hay tarifas más baratas, realizar la comparación
        if ($cheapestRates) {
            $vehicles = $this->europcarGroupRp->compareRates($cheapestRates, $vehicles, $searchParams);
        }


        $adaptedFleet = array_filter(array_map(function ($vehicle) use ($currency, $exchangeRate, $user, $searchParams, $campaign) {
            $adaptedVehicle = $this->adaptVehicle($vehicle, $currency, $exchangeRate, $user, $searchParams, $campaign);

            // Verificamos si el vehículo tiene OFF_SELL como true y lo omitimos
            return $adaptedVehicle->OFF_SELL ? null : $adaptedVehicle;
        }, $vehicles));

        // Eliminar los valores null (vehículos no adaptados) del array
        $adaptedFleet = array_values(array_filter($adaptedFleet));

        return $adaptedFleet;
    }

}

// 11951 con 200 de markup
// 9861
