<?php
namespace App\Repositories;

use Illuminate\Support\Facades\Http;
use DB;
use Log;
use Carbon\Carbon;
use Cache;

class AmericaGroupRepository
{
    private $endpoint;

    public function __construct()
    {
        $this->endpoint = config('americagroup.endpoint');
    }

    public function getAvailability($searchParams, $provider = null)
    {
        // dd($searchParams);
        $locations = $this->getLocations($searchParams);


        if (!isset($locations['pickupLocation']) || !isset($locations['dropoffLocation'])) {
            return [];
        }


        $pickupDateTime  = "{$searchParams['pickupDate']}T{$searchParams['pickupTime']}:00";
        $dropoffDateTime = "{$searchParams['dropoffDate']}T{$searchParams['dropoffTime']}:00";
        
        $carType = $searchParams['carType'] ?? '';

        $vehPrefsLine = '';
        if (!empty($carType)) {
            $vehPrefsLine = '<VehPrefs><VehPref Code="' . $carType . '" CodeContext="' . $carType . '" /></VehPrefs>';
        }

        $availabilityXml = '<?xml version="1.0"?>
        <OTA_VehAvailRateRQ Version="1.4.5">
            <POS>
                <Source>
                    <RequestorID ID="13" Type="23"/>
                </Source>
            </POS>
            <VehAvailRQCore Status="Available">
                <VehRentalCore
                    PickUpDateTime="' . $pickupDateTime . '"
                    ReturnDateTime="' . $dropoffDateTime . '">
                    <PickUpLocation LocationCode="' . $locations['pickupLocation'] . '"/>
                    <ReturnLocation LocationCode="' . $locations['dropoffLocation'] . '"/>
                </VehRentalCore>
                ' . $vehPrefsLine . '
            </VehAvailRQCore>
        </OTA_VehAvailRateRQ>';

        $responseXml = $this->sendOtaXmlRequest($availabilityXml);

        // dd($responseXml);

        if ($responseXml === null || stripos(ltrim($responseXml), '<') !== 0) {
            return [];
        }

        if ($responseXml) {

            $vehicles = $this->getVehicles();

            $xmlObj = simplexml_load_string($responseXml, "SimpleXMLElement", LIBXML_NOCDATA);

            // 2. Convertir a JSON
            $json = json_encode($xmlObj);

            // 3. Decodificar a array PHP
            $array = json_decode($json, true);

            // dd($array);

            if (isset($array['Errors'])) {
                // Puedes registrar el error o manejarlo como respuesta vacía
                Log::error('Error en respuesta OTA: ' . json_encode($array['Errors']));
                return []; // o lanza una excepción personalizada si quieres
            }

            $vehAvails = $array['VehVendorAvails']['VehVendorAvail']['VehAvails']['VehAvail'];
            $vehAvails = isset($vehAvails[0]) ? $vehAvails : [$vehAvails];

            // dd($vehAvails);

            $cars = [];

            foreach ($vehAvails as $veh) {
                $vehicle     = $veh['Vehicle'];
                $rentalRate  = $veh['RentalRate'];
                $picture     = $vehicle['PictureURL'] ?? null;
                $status     = $veh['@attributes']['Status'] ?? null;

                if ($status == 'Available') {

                    // Obtener el precio original
                    $totalPrice = (float) ($rentalRate['TotalCharge']['@attributes']['EstimatedTotalAmount'] ?? 0);

                    // Si es PQM, multiplicamos por 18
                    if ($totalPrice <= 100) {
                        $totalPrice *= 18;
                    }

                    $cars[] = [
                        'model_name'    => $vehicle['VehMakeModel']['@attributes']['Name'] ?? null,
                        'display_name'  => $vehicle['VehMakeModel']['Value'] ?? null,
                        'car_type'      => $vehicle['@attributes']['VendorCarType'] ?? null,
                        'transmission'  => $vehicle['@attributes']['TransmissionType'] ?? null,
                        'baggage_qty'   => (int) ($vehicle['@attributes']['BaggageQuantity'] ?? 0),
                        'passengers'    => (int) ($vehicle['@attributes']['PassengerQuantity'] ?? 0),
                        'class'         => $vehicle['VehClass']['@attributes']['Size'] ?? null,
                        'doors'         => (int) ($vehicle['VehType']['@attributes']['DoorCount'] ?? 0),
                        'image_url'     => $picture,
                        'total_price'   => $totalPrice,
                        'currency'      => $rentalRate['TotalCharge']['@attributes']['CurrencyCode'] ?? 'USD',
                        'rate_comment'  => $rentalRate['RateQualifier']['RateComments']['RateComment'] ?? null,
                        'vendor_rate_id'  => $rentalRate['RateQualifier']['@attributes']['VendorRateID'] ?? null,
                        'availabilityRequest' => $availabilityXml,
                        'availabilityResponse' => json_encode($array),
                    ];
                }
            }

            $quoteParams = [
                'pickup_datetime'  => $array['VehRentalCore']['@attributes']['PickUpDateTime'] ?? null,
                'return_datetime'  => $array['VehRentalCore']['@attributes']['ReturnDateTime'] ?? null,
                'pickup_location'  => $array['VehRentalCore']['PickUpLocation']['Value'] ?? null,
                'return_location'  => $array['VehRentalCore']['ReturnLocation']['Value'] ?? null,
                'location_code'    => $array['VehRentalCore']['PickUpLocation']['@attributes']['LocationCode'] ?? null,
            ];


            // Integración

            $matchList = [];

            if(count($cars) > 0) {
                $addedCategories = [];

                $vehiclesByCarModel = [];
                foreach ($vehicles as $vehicle) {
                    $vehiclesByCarModel[$vehicle->car_name] = $vehicle;
                }

                $totalDays = $this->calculateFullDays($searchParams['pickupDate'] . " " .  $searchParams['pickupTime'], $searchParams['dropoffDate'] . " " .  $searchParams['dropoffTime']);

                foreach ($cars as $providerVehicle) {

                    $carModel = $providerVehicle['model_name'];

                    if (isset($vehiclesByCarModel[$carModel])) {
                        $vehicle = $vehiclesByCarModel[$carModel];

                        if (!in_array($vehicle->category, $addedCategories)) {
                            $addedCategories[] = $vehicle->category;
                            $matchList[] = (object)[
                                'vehicleName' => $vehicle->car_name_mcr,
                                'vehicleCategory' => $vehicle->category,
                                'vehicleDescription' => $vehicle->descripccion,
                                'vehicleAcriss' => $vehicle->cAcriss,
                                'vehicleImage' => $vehicle->image,
                                'vehicleId' => $vehicle->vehicle_id,
                                'vehicleType' => $vehicle->vehicle_type,
                                'providerId' => 32,
                                'providerName' => 'AMERICA CAR RENTAL',
                                'pickupOfficeId' => $locations['pickupOfficeId'],
                                'dropoffOfficeId' => $locations['dropoffOfficeId'],
                                'totalDays' => $totalDays,
                                'netRate' => $providerVehicle['total_price'] / $totalDays,
                                'vendorRateId' => $providerVehicle['vendor_rate_id'],
                                'carType' => $providerVehicle['car_type'],
                                'availabilityResponse' => $providerVehicle['availabilityResponse'],
                                'availabilityRequest' => $providerVehicle['availabilityRequest'],
                            ];
                        }
                    } else {
                        // Verificar si ya existe un vehículo con el mismo nombre y proveedor
                        $exists = DB::table('provider_vehicles')
                            ->where('auto', $carModel)
                            ->where('fk_provider', 32)
                            ->exists();

                        // Si no existe, insertar
                        if (!$exists) {
                            DB::table('provider_vehicles')->insert([
                                'auto' => $carModel,
                                'acriss' => $providerVehicle['car_type'],
                                'fk_provider' => 32,
                                'category_id' => 0,
                                'transmission' => ''
                            ]);
                        }
                    }
                }
            }
            return $matchList;
        }

        return [];
    }

    public function cancelBooking($tokenId)
    {
        $reservation = DB::table('reservaciones')
            ->select('reservaciones.no_confirmacion as confirmation_code')
            ->join('clientes', 'clientes.id', '=', 'reservaciones.id_cliente')
            ->whereIn('reservaciones.estado', ['dpe', 'dpa', 'cld'])
            ->where('reservaciones.no_confirmacion', '<>', '')
            ->where('reservaciones.proveedor', 32)
            ->where('clientes.token_id', $tokenId)
            ->first();

        if (!$reservation) {
            return [
                'status' => 'error',
                'message' => 'Reservation not found or already cancelled.'
            ];
        }

        $timestamp = now()->toIso8601String();

        $requestXml = '<?xml version="1.0"?>
            <OTA_VehCancelRQ Version="1.4.5" TimeStamp="' . $timestamp . '"> 
                <POS> 
                    <Source> 
                        <RequestorID ID="13" /> 
                    </Source> 
                </POS> 
                <VehCancelRQCore> 
                    <UniqueID ID="' . $reservation->confirmation_code . '" Instance="' . $tokenId . '" /> 
                </VehCancelRQCore> 
            </OTA_VehCancelRQ>';

        try {
            $response = $this->sendOtaXmlRequest($requestXml);
            if ($response) {
                $xmlObj = simplexml_load_string($response, "SimpleXMLElement", LIBXML_NOCDATA);
                return [
                    'status' => 'success',
                    'message' => 'Booking cancelled successfully.',
                    'data' => json_decode(json_encode($xmlObj), true)
                ];
            }
        } catch (\Exception $e) {
            Log::error("Cancel Booking Error: " . $e->getMessage());
        }

        return [
            'status' => 'error',
            'message' => 'Failed to cancel booking. Please try again later.'
        ];
    }

    public function searchBooking($tokenId)
    {
        $reservation = DB::table('reservaciones')
            ->select('reservaciones.no_confirmacion as confirmation_code')
            ->join('clientes', 'clientes.id', '=', 'reservaciones.id_cliente')
            ->whereIn('reservaciones.estado', ['dpe', 'dpa', 'cld'])
            ->where('reservaciones.no_confirmacion', '<>', '')
            ->where('reservaciones.proveedor', 32)
            ->where('clientes.token_id', $tokenId)
            ->first();

        if (!$reservation) {
            return [
                'status' => 'error',
                'message' => 'Reservation not found or already cancelled.'
            ];
        }

        $requestXml = '<?xml version="1.0"?>
        <OTA_VehRetResRQ Version="1.4.5"> 
            <POS> 
                <Source> 
                    <RequestorID ID="13"></RequestorID> 
                </Source> 
            </POS> 
            <VehRetResRQCore> 
                <UniqueID ID="' . $reservation->confirmation_code . '" Instance="' . $tokenId . '" /> 
            </VehRetResRQCore> 
        </OTA_VehRetResRQ>';

         try {
            $response = $this->sendOtaXmlRequest($requestXml);
            if ($response) {
                $xmlObj = simplexml_load_string($response, "SimpleXMLElement", LIBXML_NOCDATA);
                return [
                    'status' => 'success',
                    'message' => 'Booking retrieved successfully.',
                    'data' => json_decode(json_encode($xmlObj), true)
                ];
            }
        } catch (\Exception $e) {
            Log::error("Get Booking Error: " . $e->getMessage());
        }

        return [
            'status' => 'error',
            'message' => 'Failed to retrieve booking. Please try again later.'
        ];

    }

        public function confirmBookings()
    {
        set_time_limit(0);
        // Obtienes TODAS las reservas sin clave y pendientes de proveedor 32.
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
            ->where('reservaciones.proveedor', 32)
            ->get();


        $confirmReservations = 0;

        foreach ($reservations as $reservation) {

            $quotation = DB::table('america_group_quotations')
                ->where('client_id', $reservation->client_id)
                ->first();

            if (!$quotation) {

                $carProviderDb = DB::table('provider_vehicles')
                ->select('acriss')
                ->where('fk_provider', 32)
                ->where('provider_vehicles.category_id', $reservation->category_id)
                ->first();

                if($carProviderDb) {
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
                        'carType' => $carProviderDb->acriss,
                    ];

                    $cars = $this->getAvailability($searchParams, 32);

                    if(count($cars) > 0) {
                        if($cars[0]->carType == $carProviderDb->acriss) {
                            $quotation = (object) [
                                'car_type' => $cars[0]->carType,
                                'vendor_rate_id' => $cars[0]->vendorRateId,
                            ]; 
                        }
                    }

                }
                
            }

            if(!$quotation) {
                continue;
            }

            $xml = $this->generateVehResXml($reservation, $quotation);
            $responseXml = $this->sendOtaXmlRequest($xml);

            if ($responseXml) {

                $confirmReservations++;

                $xmlObj = simplexml_load_string($responseXml, "SimpleXMLElement", LIBXML_NOCDATA);
                $json = json_encode($xmlObj);
                $array = json_decode($json, true);

                // Acceder al ID de confirmación
                $id = $array['VehResRSCore']['VehReservation']['VehSegmentCore']['ConfID']['@attributes']['ID'] ?? null;

                if ($id) {
                    DB::table('reservaciones')
                        ->where('id_cliente', $reservation->client_id)
                        ->update(['no_confirmacion' => $id]);
                }

                DB::table('america_group_quotations')
                    ->where('client_id', $reservation->client_id)
                    ->update([
                        'confirmation_request' => $xml,
                        'confirmation_response' => $array,
                    ]);
            }
        }

        return $confirmReservations;
    }

    public function confirmBooking($tokenId)
    {
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
            ->where('reservaciones.proveedor', 32)
            ->where('clientes.token_id', $tokenId)
            ->first();

        if (!$reservation) {
            return [
                'status' => 'error',
                'message' => 'Reservation not found.'
            ];
        }

        $quotation = DB::table('america_group_quotations')
        ->where('client_id', $reservation->client_id)
        ->first();

        if (!$quotation) {

            $carProviderDb = DB::table('provider_vehicles')
            ->select('acriss')
            ->where('fk_provider', 32)
            ->where('provider_vehicles.category_id', $reservation->category_id)
            ->first();

            if($carProviderDb) {
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
                    'carType' => $carProviderDb->acriss,
                ];

                $cars = $this->getAvailability($searchParams, 32);

                if(count($cars) > 0) {
                    if($cars[0]->carType == $carProviderDb->acriss) {
                        $quotation = (object) [
                            'car_type' => $cars[0]->carType,
                            'vendor_rate_id' => $cars[0]->vendorRateId,
                        ]; 
                    }
                }

            }
            
        }

        if(!$quotation) {
            return [
                'status' => 'error',
                'message' => 'Quotation not found for the client.'
            ];
        }

        $xml = $this->generateVehResXml($reservation, $quotation);

        $responseXml = $this->sendOtaXmlRequest($xml);

        if ($responseXml) {
            $xmlObj = simplexml_load_string($responseXml, "SimpleXMLElement", LIBXML_NOCDATA);
            $json = json_encode($xmlObj);
            $array = json_decode($json, true);

            // Acceder al ID
            $id = $array['VehResRSCore']['VehReservation']['VehSegmentCore']['ConfID']['@attributes']['ID'] ?? null;

            if ($id) {
                DB::table('reservaciones')
                    ->where('id_cliente', $reservation->client_id)
                    ->update(['no_confirmacion' => $id]);
            }

            DB::table('america_group_quotations')
            ->where('client_id', $reservation->client_id)
            ->update([
                'confirmation_request' => $xml,
                'confirmation_response' => $array,
            ]);

            return $array;
        }

        return null;
    }



    private function generateVehResXml($reservation, $quotation): string
    {
        $xml = new \SimpleXMLElement('<?xml version="1.0"?><OTA_VehResRQ Version="1.00"></OTA_VehResRQ>');

        $pos = $xml->addChild('POS');
        $source = $pos->addChild('Source');
        $source->addChild('RequestorID')->addAttribute('ID', '13');

        $bookingRef = $xml->addChild('BookingReferenceID');
        $bookingRef->addChild('UniqueID_Type')->addAttribute('ID', $reservation->token_id);

        $core = $xml->addChild('VehResRQCore');
        $vehRentalCore = $core->addChild('VehRentalCore');
        $vehRentalCore->addAttribute('PickUpDateTime', "{$reservation->pickup_date}T{$reservation->pickup_time}");
        $vehRentalCore->addAttribute('ReturnDateTime', "{$reservation->dropoff_date}T{$reservation->dropoff_time}");

        $vehRentalCore->addChild('PickUpLocation')->addAttribute('LocationCode', $reservation->pickup_location_code);
        $vehRentalCore->addChild('ReturnLocation')->addAttribute('LocationCode', $reservation->dropoff_location_code);

        $vehPref = $core->addChild('VehPref');
        $vehPref->addAttribute('VendorCarType', $quotation->car_type);
        $vehPref->addChild('VehClass', $quotation->car_type);
        $vehPref->addChild('VehType');

        $core->addChild('RateQualifier')->addAttribute('VendorRateID', $quotation->vendor_rate_id);


        // 'reservaciones.estado',
        // 'reservaciones.fechaRecoger as pickup_date',
        // 'reservaciones.fechaDejar as dropoff_date',
        // 'reservaciones.horaRecoger as pickup_time',
        // 'reservaciones.horaDejar as dropoff_time',
        // 'reservaciones.no_vuelo as flight',
        // 'reservaciones.aereolinea as airline',
        // 'clientes.id as client_id',
        // 'clientes.nombre as name',
        // 'clientes.apellido as last_name',
        // 'pickup_location.code as pickup_location_code',
        // 'dropoff_location.code as dropoff_location_code'

        $customer = $core->addChild('Customer');
        $primary = $customer->addChild('Primary');
        $personName = $primary->addChild('PersonName');
        $personName->addChild('GivenName', $reservation->name);
        $personName->addChild('Surname', $reservation->last_name);
        // $primary->addChild('Telephone')
        //     ->addAttribute('PhoneTechType', '001.PTT')
        //     ->addAttribute('PhoneNumber', $params['phone'] ?? '440610336706');
        $email = $primary->addChild('Email');
        $email->addChild('Value', 'reservaciones@mexicocarrental.com.mx');

   
        if($reservation->status == 'dpa') {
  
            $core->addChild('Fees');
            $vehicleCharges = $core->addChild('VehicleCharges');          
            $vehicleCharges->addAttribute('Purpose', '022.VCP');
        }
        // else {
        //     $vehicleCharges->addAttribute('Purpose', '023.VCP');
        // }
        // $vehicleCharge = $vehicleCharges->addChild('VehicleCharge');
        // $vehicleCharge->addAttribute('CurrencyCode', 'MXN');
        // $vehicleCharge->addAttribute('Description', '');
        // $vehicleCharge->addAttribute('Amount', $params['amount'] ?? '25.00');
        // $vehicleCharge->addChild('TaxAmounts');

        // $tpa = $core->addChild('TPA_Extensions');
        // $extrasReq = $tpa->addChild('SOE_ExtrasRequest');
        // $extras = $extrasReq->addChild('Extras');
        // $extra = $extras->addChild('Extra');
        // $extra->addAttribute('Code', $params['extra_code'] ?? '3');
        // $extra->addAttribute('Quantity', $params['extra_quantity'] ?? '1');

        // $comments = $tpa->addChild('SOE_Comments');
        // $comments->addChild('Comment')->addAttribute('Name', 'Remarks');
        // $comments->addChild('Text', $params['remarks'] ?? '');

        // $info = $xml->addChild('VehResRQInfo');
        // $arrival = $info->addChild('ArrivalDetails');
        // $arrival->addAttribute('Number', $params['arrival_number'] ?? '');
        // $arrival->addChild('OperatingCompany')->addAttribute('CompanyShortName', $params['operating_company'] ?? '');

        $dom = dom_import_simplexml($xml)->ownerDocument;
        $dom->formatOutput = true;

        return $dom->saveXML();
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
                ->where('fk_provider', 32)
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


    private function getVehicles()
    {
        Cache::forget('group_america_vehicles');
        if(Cache::has('group_america_vehicles')) {
            return Cache::get('group_america_vehicles');
        }

        $vehicles = DB::table('provider_vehicles')
        ->join('gps_categorias', 'gps_categorias.id', '=', 'provider_vehicles.category_id')
        ->join('gps_autos_copy', 'gps_autos_copy.id_gps_categorias', '=', 'provider_vehicles.category_id')
        ->select(
            'gps_categorias.categoria as category', 'gps_categorias.id as category_id', 'gps_categorias.descripccion',
            'gps_categorias.cAcriss', 'provider_vehicles.acriss', 'provider_vehicles.auto as car_name', 'gps_categorias.tipo as vehicle_type',
            'gps_autos_copy.auto as car_name_mcr', 'gps_autos_copy.camino as image', 'gps_autos_copy.id as vehicle_id'
            )
        ->where('fk_provider', '32')
        ->groupBy('provider_vehicles.category_id')
        ->orderBy('gps_categorias.categoria', 'ASC')
        ->get();

        Cache::put('group_america_vehicles', $vehicles, now()->addDays(7));

        return $vehicles;
    }

    private function sendOtaXmlRequest(string $xml): ?string
    {
        $encodedXml = urlencode($xml);
        $endpoint = $this->endpoint . "?XML={$encodedXml}";

        try {
            $response = Http::timeout(3)->get($endpoint);

            if (!$response->successful()) {
                Log::error('Error al consultar OTA ACR', [
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);
                return null;
            }

            return $response->body();
        } catch (\Exception $e) {
            Log::error('Excepción al consultar OTA ACR', [
                'message' => $e->getMessage(),
            ]);
            return null;
        }
    }

    public function insertACROffices()
    {

        $branchesXml = '<?xml version="1.0"?>
        <OTA_VehLocSearchRQ Version="1.4.5">
            <POS>
                <Source>
                    <RequestorID ID="13"></RequestorID>
                </Source>
            </POS>
        </OTA_VehLocSearchRQ>';

        $responseXml = $this->sendOtaXmlRequest($branchesXml);

        if ($responseXml) {
            $xmlObj = simplexml_load_string($responseXml);
            $allNodes = $xmlObj->VehMatchedLocs;
            $count = 0;

            foreach ($allNodes as $nodeGroup) {
                foreach ($nodeGroup as $node) {
                    // Asegurarse que sea un nodo de locación válido
                    if (!isset($node->LocationDetail)) {
                        continue;
                    }

                    $data = [
                        'code'          => (string) $node->LocationDetail['Code'],
                        'iata'          => (string) $node->LocationDetail['CodeContext'],
                        'name'          => (string) $node->LocationDetail['Name'],
                        'city'          => (string) $node->LocationDetail->Address->CityName ?? null,
                        'state'         => (string) $node->LocationDetail->Address->StateProv ?? null,
                        'country'       => (string) $node->LocationDetail->Address->CountryName ?? null,
                        'address'       => (string) $node->LocationDetail->Address->AddressLine ?? null,
                        'phone'         => (string) $node->LocationDetail->Telephone['PhoneNumber'] ?? null,
                        'hours'         => (string) $node->LocationDetail->AdditionalInfo->VehRentLocInfos->VehRentLocInfo->Paragraph ?? null,
                        'shuttle_start' => (string) $node->LocationDetail->AdditionalInfo->Shuttle->OperationSchedule['Start'] ?? null,
                        'shuttle_end'   => (string) $node->LocationDetail->AdditionalInfo->Shuttle->OperationSchedule['End'] ?? null,
                        'latitude'      => (string) $node->VehLocSearchCriterion->Position['Latitude'] ?? null,
                        'longitude'     => (string) $node->VehLocSearchCriterion->Position['Longitude'] ?? null,
                        'updated_at'    => now(),
                    ];

                    DB::table('providers_acr_locations')->updateOrInsert(
                        ['code' => $data['code']],
                        $data
                    );

                    $count++;
                }
            }

            echo "✅ Se insertaron o actualizaron {$count} locaciones correctamente.";
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
