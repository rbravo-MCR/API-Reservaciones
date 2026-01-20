<?php

declare(strict_types=1);

namespace App\Repositories;

use Carbon\Carbon;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use SimpleXMLElement;

/**
 * Repositorio para integración OTA con America Car Rental (America Group)
 * - Enfocado a producción: manejo de errores, reintentos, logging estructurado,
 *   caching, código desacoplado y válido para pruebas.
 */
class AmericaGroupRepository
{
    private const PROVIDER_ID = 32;

    private string $endpoint;
    private string $requestorId;
    private int $httpTimeout;
    private int $httpRetries;
    private int $httpRetrySleepMs;

    public function __construct()
    {
        $this->endpoint        = (string) config('americagroup.endpoint');
        $this->requestorId     = (string) (config('americagroup.requestor_id') ?? '13');
        $this->httpTimeout     = (int) (config('americagroup.timeout_seconds') ?? 5);
        $this->httpRetries     = (int) (config('americagroup.retry_times') ?? 2);
        $this->httpRetrySleepMs= (int) (config('americagroup.retry_sleep_ms') ?? 300);
    }

    /**
     * Obtiene disponibilidad y mapea a categorías internas.
     * @param array $searchParams
     * @param int|null $provider Ignorado (compatibilidad); se usa PROVIDER_ID.
     * @return array<int, object>
     */
    public function getAvailability(array $searchParams, ?int $provider = null, bool $includeRaw = false): array
    {
        $locations = $this->resolveLocations($searchParams);
        if (!$locations['pickupLocation'] || !$locations['dropoffLocation']) {
            return [];
        }

        $pickupDateTime  = sprintf('%sT%s:00', $searchParams['pickupDate'], $searchParams['pickupTime']);
        $dropoffDateTime = sprintf('%sT%s:00', $searchParams['dropoffDate'], $searchParams['dropoffTime']);

        $vehPrefsLine = '';
        if (!empty($searchParams['carType'])) {
            $code = e((string) $searchParams['carType']);
            $vehPrefsLine = '<VehPrefs><VehPref Code="' . $code . '" CodeContext="' . $code . '" /></VehPrefs>';
        }

        $availabilityXml = '<?xml version="1.0"?>
        <OTA_VehAvailRateRQ Version="1.4.5">
            <POS>
                <Source>
                    <RequestorID ID="' . e($this->requestorId) . '" Type="23"/>
                </Source>
            </POS>
            <VehAvailRQCore Status="Available">
                <VehRentalCore PickUpDateTime="' . e($pickupDateTime) . '" ReturnDateTime="' . e($dropoffDateTime) . '">
                    <PickUpLocation LocationCode="' . e($locations['pickupLocation']) . '"/>
                    <ReturnLocation LocationCode="' . e($locations['dropoffLocation']) . '"/>
                </VehRentalCore>
                ' . $vehPrefsLine . '
            </VehAvailRQCore>
        </OTA_VehAvailRateRQ>';

        $responseXml = $this->sendOtaXmlRequest($availabilityXml);
        if ($responseXml === null || stripos(ltrim($responseXml), '<') !== 0) {
            return [];
        }

        $array = $this->xmlStringToArray($responseXml);
        if (isset($array['Errors'])) {
            Log::warning('ACR OTA errors in availability', [
                'errors' => $array['Errors']
            ]);
            return [];
        }

        // Normaliza el árbol esperado
        $vehAvails = Arr::get($array, 'VehVendorAvails.VehVendorAvail.VehAvails.VehAvail');
        $vehAvails = $this->ensureArray($vehAvails);
        if (empty($vehAvails)) {
            return [];
        }

        $vehiclesDb = $this->getVehicles();
        $vehiclesByCarModel = [];
        foreach ($vehiclesDb as $vehicle) {
            $vehiclesByCarModel[$vehicle->car_name] = $vehicle;
        }

        $cars = [];
        foreach ($vehAvails as $veh) {
            $status = Arr::get($veh, '@attributes.Status');
            if ($status !== 'Available') {
                continue;
            }

            $vehicle    = Arr::get($veh, 'Vehicle', []);
            // Log::info($vehicle);
            $rentalRate = Arr::get($veh, 'RentalRate', []);
            // Log::info($rentalRate);
            $picture    = Arr::get($vehicle, 'PictureURL');

            $totalPrice = (float) Arr::get($rentalRate, 'TotalCharge.@attributes.EstimatedTotalAmount', 0);

            // Trae las fees (puede venir 1 objeto o un arreglo) y normaliza a arreglo
            $fees = Arr::wrap(Arr::get($rentalRate, 'Fees.Fee', []));

            // Suma únicamente las que tengan IncludedInEstTotalInd == "0"
            $extraFees = collect($fees)
                ->filter(fn ($fee) => (string) Arr::get($fee, '@attributes.IncludedInEstTotalInd') === '0')
                ->sum(fn ($fee) => (float) Arr::get($fee, '@attributes.Amount', 0));

            // Log::info($extraFees);

            // Agrega esas fees al total
            $totalPrice += ($extraFees * 20); // fees esta en usd

            $car = [
                'model_name'    => Arr::get($vehicle, 'VehMakeModel.@attributes.Name'),
                'display_name'  => Arr::get($vehicle, 'VehMakeModel.Value'),
                'car_type'      => Arr::get($vehicle, '@attributes.VendorCarType'),
                'transmission'  => Arr::get($vehicle, '@attributes.TransmissionType'),
                'baggage_qty'   => (int) Arr::get($vehicle, '@attributes.BaggageQuantity', 0),
                'passengers'    => (int) Arr::get($vehicle, '@attributes.PassengerQuantity', 0),
                'class'         => Arr::get($vehicle, 'VehClass.@attributes.Size'),
                'doors'         => (int) Arr::get($vehicle, 'VehType.@attributes.DoorCount', 0),
                'image_url'     => $picture,
                'total_price'   => $totalPrice,
                'extrasIncluded'=> $extraFees,
                'currency'      => Arr::get($rentalRate, 'TotalCharge.@attributes.CurrencyCode', 'USD'),
                'rate_comment'  => Arr::get($rentalRate, 'RateQualifier.RateComments.RateComment'),
                'vendor_rate_id'=> Arr::get($rentalRate, 'RateQualifier.@attributes.VendorRateID'),
            ];

            if ($includeRaw) {
                $car['availabilityRequest']  = $availabilityXml;
                $car['availabilityResponse'] = json_encode($array, JSON_UNESCAPED_UNICODE);
            }

            $cars[] = $car;
        }

        if (empty($cars)) {
            return [];
        }

        $totalDays = $this->calculateFullDays(
            $searchParams['pickupDate'] . ' ' . $searchParams['pickupTime'],
            $searchParams['dropoffDate'] . ' ' . $searchParams['dropoffTime']
        );

        $matchList = [];
        $addedCategories = [];
        foreach ($cars as $providerVehicle) {
            $carModel = (string) ($providerVehicle['model_name'] ?? '');
            if ($carModel === '' || !isset($vehiclesByCarModel[$carModel])) {
                // Inserta faltantes para mapeo manual posterior
                $this->upsertProviderVehicleIfMissing($carModel, (string) $providerVehicle['car_type']);
                continue;
            }

            $vehicle = $vehiclesByCarModel[$carModel];
            if (in_array($vehicle->category, $addedCategories, true)) {
                continue;
            }

            $addedCategories[] = $vehicle->category;
            $item = (object) [
                'vehicleName'        => $vehicle->car_name_mcr,
                'vehicleCategory'    => $vehicle->category,
                'vehicleDescription' => $vehicle->descripccion,
                'vehicleAcriss'      => $vehicle->cAcriss,
                'vehicleImage'       => $vehicle->image,
                'vehicleId'          => $vehicle->vehicle_id,
                'vehicleType'        => $vehicle->vehicle_type,
                'providerId'         => self::PROVIDER_ID,
                'providerName'       => 'AMERICA CAR RENTAL',
                'pickupOfficeId'     => $locations['pickupOfficeId'],
                'dropoffOfficeId'    => $locations['dropoffOfficeId'],
                'totalDays'          => $totalDays,
                'netRate'            => $totalDays > 0 ? ($providerVehicle['total_price'] / $totalDays) : 0.0,
                'extrasIncluded'     => $totalDays > 0 ? ($providerVehicle['extrasIncluded'] / $totalDays): 0.0,
                'vendorRateId'       => $providerVehicle['vendor_rate_id'],
                'carType'            => $providerVehicle['car_type'],
            ];

            if ($includeRaw && isset($providerVehicle['availabilityResponse'], $providerVehicle['availabilityRequest'])) {
                $item->availabilityResponse = $providerVehicle['availabilityResponse'];
                $item->availabilityRequest  = $providerVehicle['availabilityRequest'];
            }

            $matchList[] = $item;
        }

        return $matchList;
    }

    /**
     * Cancela por tokenId del cliente.
     */
    public function cancelBooking(string $tokenId): array
    {
        $reservation = $this->findReservationWithConfirmationByToken($tokenId);
        if (!$reservation) {
            return ['status' => 'error', 'message' => 'Reservation not found or already cancelled.'];
        }

        $timestamp = now()->toIso8601String();
        $requestXml = '<?xml version="1.0"?>
            <OTA_VehCancelRQ Version="1.4.5" TimeStamp="' . e($timestamp) . '"> 
                <POS><Source><RequestorID ID="' . e($this->requestorId) . '" /></Source></POS>
                <VehCancelRQCore><UniqueID ID="' . e($reservation->confirmation_code) . '" Instance="' . e($tokenId) . '" /></VehCancelRQCore>
            </OTA_VehCancelRQ>';

        try {
            $response = $this->sendOtaXmlRequest($requestXml);
            if ($response) {
                return [
                    'status'  => 'success',
                    'message' => 'Booking cancelled successfully.',
                    'data'    => $this->xmlStringToArray($response),
                ];
            }
        } catch (\Throwable $e) {
            Log::error('ACR cancelBooking exception', ['error' => $e->getMessage()]);
        }

        return ['status' => 'error', 'message' => 'Failed to cancel booking. Please try again later.'];
    }

    /**
     * Consulta una reserva por tokenId del cliente.
     */
    public function searchBooking(string $tokenId): array
    {
        $reservation = $this->findReservationWithConfirmationByToken($tokenId);
        if (!$reservation) {
            return ['status' => 'error', 'message' => 'Reservation not found or already cancelled.'];
        }

        $requestXml = '<?xml version="1.0"?>
        <OTA_VehRetResRQ Version="1.4.5"> 
            <POS><Source><RequestorID ID="' . e($this->requestorId) . '"></RequestorID></Source></POS> 
            <VehRetResRQCore><UniqueID ID="' . e($reservation->confirmation_code) . '" Instance="' . e($tokenId) . '" /></VehRetResRQCore>
        </OTA_VehRetResRQ>';

        try {
            $response = $this->sendOtaXmlRequest($requestXml);
            if ($response) {
                return [
                    'status'  => 'success',
                    'message' => 'Booking retrieved successfully.',
                    'data'    => $this->xmlStringToArray($response),
                ];
            }
        } catch (\Throwable $e) {
            Log::error('ACR searchBooking exception', ['error' => $e->getMessage()]);
        }

        return ['status' => 'error', 'message' => 'Failed to retrieve booking. Please try again later.'];
    }

    /**
     * Confirma en batch todas las reservas elegibles.
     * @return int número de confirmaciones realizadas
     */
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
                Log::error('ACR confirmBookings: reservation failed', [
                    'client_id' => $reservation->client_id,
                    'error'     => $e->getMessage(),
                ]);
            }
        }

        return $confirmed;
    }

    /**
     * Confirma una sola reserva por tokenId.
     */
    public function confirmBooking(string $tokenId): array
    {
        $reservation = $this->findSingleConfirmableReservationByToken($tokenId);
        if (!$reservation) {
            return ['status' => 'error', 'message' => 'Reservation not found.'];
        }

        try {
            $ok = $this->confirmSingleReservation($reservation);
            return $ok ? ['status' => 'success'] : ['status' => 'error', 'message' => 'Confirmation failed.'];
        } catch (\Throwable $e) {
            Log::error('ACR confirmBooking exception', ['error' => $e->getMessage()]);
            return ['status' => 'error', 'message' => 'Confirmation failed.'];
        }
    }

    /**
     * GENERA, ENVÍA y PERSISTE una confirmación para una reserva.
     * @param object $reservation
     * @return bool true si confirma y guarda el no_confirmacion
     */
    private function confirmSingleReservation(object $reservation): bool
    {
        $quotation = $this->loadOrDeriveQuotation((int) $reservation->client_id, (int) $reservation->category_id, [
            'pickup_date'  => $reservation->pickup_date,
            'pickup_time'  => $reservation->pickup_time,
            'dropoff_date' => $reservation->dropoff_date,
            'dropoff_time' => $reservation->dropoff_time,
            'IATA'         => $reservation->destination_code,
            'pickupLocation'  => $reservation->pickup_location_code,
            'dropoffLocation' => $reservation->dropoff_location_code,
            'pickupOfficeId'  => $reservation->pickup_location_mcr_office_id,
            'dropoffOfficeId' => $reservation->dropoff_location_mcr_office_id,
        ]);

        if (!$quotation) {
            return false;
        }

        $xml = $this->generateVehResXml($reservation, $quotation);
        $responseXml = $this->sendOtaXmlRequest($xml);
        if (!$responseXml) {
            return false;
        }

        $array = $this->xmlStringToArray($responseXml);
        $id = Arr::get($array, 'VehResRSCore.VehReservation.VehSegmentCore.ConfID.@attributes.ID');
        if (!$id) {
            return false;
        }

        DB::table('reservaciones')
            ->where('id_cliente', $reservation->client_id)
            ->update(['no_confirmacion' => $id]);

        DB::table('america_group_quotations')
            ->where('client_id', $reservation->client_id)
            ->update([
                'confirmation_request'  => $xml,
                'confirmation_response' => json_encode($array, JSON_UNESCAPED_UNICODE),
            ]);

        return true;
    }

    /**
     * Construye XML de confirmación.
     * @param object $reservation
     * @param object $quotation {car_type, vendor_rate_id}
     */
    private function generateVehResXml(object $reservation, object $quotation): string
    {
        $xml = new SimpleXMLElement('<?xml version="1.0"?><OTA_VehResRQ Version="1.00"></OTA_VehResRQ>');

        $pos = $xml->addChild('POS');
        $source = $pos->addChild('Source');
        $source->addChild('RequestorID')->addAttribute('ID', $this->requestorId);

        $bookingRef = $xml->addChild('BookingReferenceID');
        $bookingRef->addChild('UniqueID_Type')->addAttribute('ID', (string) $reservation->token_id);

        $core = $xml->addChild('VehResRQCore');
        $vehRentalCore = $core->addChild('VehRentalCore');
        $vehRentalCore->addAttribute('PickUpDateTime', sprintf('%sT%s', $reservation->pickup_date, $reservation->pickup_time));
        $vehRentalCore->addAttribute('ReturnDateTime', sprintf('%sT%s', $reservation->dropoff_date, $reservation->dropoff_time));
        $vehRentalCore->addChild('PickUpLocation')->addAttribute('LocationCode', (string) $reservation->pickup_location_code);
        $vehRentalCore->addChild('ReturnLocation')->addAttribute('LocationCode', (string) $reservation->dropoff_location_code);

        $vehPref = $core->addChild('VehPref');
        $vehPref->addAttribute('VendorCarType', (string) $quotation->car_type);
        $vehPref->addChild('VehClass', (string) $quotation->car_type); // Conservado del original
        $vehPref->addChild('VehType');

        $core->addChild('RateQualifier')->addAttribute('VendorRateID', (string) $quotation->vendor_rate_id);

        $customer = $core->addChild('Customer');
        $primary = $customer->addChild('Primary');
        $personName = $primary->addChild('PersonName');
        $personName->addChild('GivenName', (string) $reservation->name);
        $personName->addChild('Surname', (string) $reservation->last_name);
        $primary->addChild('Email')->addChild('Value', 'reservaciones@mexicocarrental.com.mx');

        if ($reservation->status === 'dpa') {
            $core->addChild('Fees');
            $vehicleCharges = $core->addChild('VehicleCharges');
            $vehicleCharges->addAttribute('Purpose', '022.VCP');
        }

        $dom = dom_import_simplexml($xml)->ownerDocument;
        $dom->formatOutput = true;
        return (string) $dom->saveXML();
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
        return Cache::remember('group_america_vehicles', now()->addDays(7), function () {
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

    /**
     * Envía XML por GET ?XML=... con reintentos y timeouts.
     */
    private function sendOtaXmlRequest(string $xml): ?string
    {
        if ($this->endpoint === '') {
            Log::error('ACR endpoint not configured');
            return null;
        }

        $encodedXml = urlencode($xml);
        $url = $this->endpoint . '?XML=' . $encodedXml;

        try {
            $response = Http::retry($this->httpRetries, $this->httpRetrySleepMs)
                ->timeout($this->httpTimeout)
                ->withHeaders(['Accept' => 'application/xml'])
                ->get($url);

            if (!$response->successful()) {
                Log::warning('ACR OTA non-success response', [
                    'status' => $response->status(),
                    'body'   => mb_substr($response->body(), 0, 1000),
                ]);
                return null;
            }

            return $response->body();
        } catch (\Throwable $e) {
            Log::error('ACR OTA request exception', [
                'message' => $e->getMessage(),
            ]);
            return null;
        }
    }

    /**
     * Inserta/actualiza oficinas del proveedor (OTA_VehLocSearchRQ)
     * Devuelve número de locaciones procesadas.
     */
    public function storeOffices(): int
    {
        $branchesXml = '<?xml version="1.0"?>
        <OTA_VehLocSearchRQ Version="1.4.5">
            <POS><Source><RequestorID ID="' . e($this->requestorId) . '"></RequestorID></Source></POS>
        </OTA_VehLocSearchRQ>';

        $responseXml = $this->sendOtaXmlRequest($branchesXml);
        if (!$responseXml) {
            return 0;
        }

        $xmlObj = simplexml_load_string($responseXml);
        if (!$xmlObj || !isset($xmlObj->VehMatchedLocs)) {
            return 0;
        }

        $count = 0;
        foreach ($xmlObj->VehMatchedLocs as $nodeGroup) {
            foreach ($nodeGroup as $node) {
                if (!isset($node->LocationDetail)) {
                    continue;
                }

                $data = [
                    'code'          => (string) $node->LocationDetail['Code'],
                    'iata'          => (string) $node->LocationDetail['CodeContext'],
                    'name'          => (string) $node->LocationDetail['Name'],
                    'city'          => (string) ($node->LocationDetail->Address->CityName ?? ''),
                    'state'         => (string) ($node->LocationDetail->Address->StateProv ?? ''),
                    'country'       => (string) ($node->LocationDetail->Address->CountryName ?? ''),
                    'address'       => (string) ($node->LocationDetail->Address->AddressLine ?? ''),
                    'phone'         => (string) ($node->LocationDetail->Telephone['PhoneNumber'] ?? ''),
                    'hours'         => (string) ($node->LocationDetail->AdditionalInfo->VehRentLocInfos->VehRentLocInfo->Paragraph ?? ''),
                    'shuttle_start' => (string) ($node->LocationDetail->AdditionalInfo->Shuttle->OperationSchedule['Start'] ?? ''),
                    'shuttle_end'   => (string) ($node->LocationDetail->AdditionalInfo->Shuttle->OperationSchedule['End'] ?? ''),
                    'latitude'      => (string) ($node->VehLocSearchCriterion->Position['Latitude'] ?? ''),
                    'longitude'     => (string) ($node->VehLocSearchCriterion->Position['Longitude'] ?? ''),
                    'updated_at'    => now(),
                ];

                DB::table('providers_acr_locations')->updateOrInsert(
                    ['code' => $data['code']],
                    $data
                );

                $count++;
            }
        }

        return $count;
    }

    /**
     * Días completos entre dos datetimes (ceil a día completo).
     */
    public function calculateFullDays(string $startDate, string $endDate): int
    {
        $start = Carbon::parse($startDate);
        $end   = Carbon::parse($endDate);
        $minutes = $start->diffInMinutes($end);
        return (int) ceil($minutes / 1440);
    }

    // ---------------------- Helpers de datos/DB ----------------------

    private function findReservationWithConfirmationByToken(string $tokenId): ?object
    {
        return DB::table('reservaciones')
            ->select('reservaciones.no_confirmacion as confirmation_code')
            ->join('clientes', 'clientes.id', '=', 'reservaciones.id_cliente')
            ->whereIn('reservaciones.estado', ['dpe', 'dpa', 'cld'])
            ->where('reservaciones.no_confirmacion', '<>', '')
            ->where('reservaciones.proveedor', self::PROVIDER_ID)
            ->where('clientes.token_id', $tokenId)
            ->first();
    }

    private function findConfirmableReservations(): \Illuminate\Support\Collection
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

    private function findSingleConfirmableReservationByToken(string $tokenId): ?object
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

    private function loadOrDeriveQuotation(int $clientId, int $categoryId, array $ctx): ?object
    {
        $quotation = DB::table('america_group_quotations')->where('client_id', $clientId)->first();
        if ($quotation) {
            return $quotation;
        }

        $carProviderDb = DB::table('provider_vehicles')
            ->select('acriss')
            ->where('fk_provider', self::PROVIDER_ID)
            ->where('provider_vehicles.category_id', $categoryId)
            ->first();

        if (!$carProviderDb) {
            return null;
        }

        $cars = $this->getAvailability([
            'pickupDate'     => $ctx['pickup_date'],
            'pickupTime'     => $ctx['pickup_time'],
            'dropoffDate'    => $ctx['dropoff_date'],
            'dropoffTime'    => $ctx['dropoff_time'],
            'IATA'           => $ctx['IATA'],
            'pickupLocation' => $ctx['pickupLocation'],
            'dropoffLocation'=> $ctx['dropoffLocation'],
            'pickupOfficeId' => $ctx['pickupOfficeId'],
            'dropoffOfficeId'=> $ctx['dropoffOfficeId'],
            'carType'        => $carProviderDb->acriss,
        ], self::PROVIDER_ID);

        if (!empty($cars) && isset($cars[0]->carType) && $cars[0]->carType === $carProviderDb->acriss) {
            return (object) [
                'car_type'      => $cars[0]->carType,
                'vendor_rate_id'=> $cars[0]->vendorRateId,
            ];
        }

        return null;
    }

    private function upsertProviderVehicleIfMissing(string $carModel, string $acriss): void
    {
        if ($carModel === '') {
            return;
        }

        $exists = DB::table('provider_vehicles')
            ->where('auto', $carModel)
            ->where('fk_provider', self::PROVIDER_ID)
            ->exists();

        if (!$exists) {
            DB::table('provider_vehicles')->insert([
                'auto'        => $carModel,
                'acriss'      => $acriss,
                'fk_provider' => self::PROVIDER_ID,
                'category_id' => 0,
                'transmission'=> '',
            ]);
        }
    }

    // ---------------------- Helpers XML/arrays ----------------------

    /** @param mixed $maybeList */
    private function ensureArray($maybeList): array
    {
        if ($maybeList === null) return [];
        return is_array($maybeList) && array_is_list($maybeList) ? $maybeList : [$maybeList];
    }

    private function xmlStringToArray(string $xml): array
    {
        $xmlObj = simplexml_load_string($xml, SimpleXMLElement::class, LIBXML_NOCDATA);
        if ($xmlObj === false) {
            return [];
        }
        return json_decode(json_encode($xmlObj, JSON_UNESCAPED_UNICODE), true) ?? [];
    }
}

