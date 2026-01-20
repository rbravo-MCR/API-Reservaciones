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
 * Repositorio para integración OTA con Infinity Car Rental.
 * Limpieza de producción, mismo patrón que AmericaGroupRepository.
 */
class InfinityGroupRepository
{
    private const PROVIDER_ID = 106;     // Infinity

    private string $endpoint;
    private string $requestorId;         // OTA RequestorID (por defecto 92)
    private int $httpTimeout;
    private int $httpRetries;
    private int $httpRetrySleepMs;

    public function __construct()
    {
        $this->endpoint         = (string) config('americagroup.infinity.endpoint');
        $this->requestorId      = (string) (config('americagroup.infinity.requestor_id') ?? '92');
        $this->httpTimeout      = (int) (config('americagroup.infinity.timeout_seconds') ?? 5);
        $this->httpRetries      = (int) (config('americagroup.infinity.retry_times') ?? 2);
        $this->httpRetrySleepMs = (int) (config('americagroup.infinity.retry_sleep_ms') ?? 300);
    }

    /**
     * Disponibilidad Infinity, con opción de incluir raw XML solo cuando se guardará la reserva.
     * @param array $searchParams
     * @param int|null $provider (compatibilidad, ignorado)
     * @param bool $includeRaw   Si true, incluye availabilityRequest/Response.
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

        $availabilityXml = '<?xml version="1.0"?>
        <OTA_VehAvailRateRQ Version="1.4.5">
            <POS>
                <Source>
                    <RequestorID ID="' . e($this->requestorId) . '" Type="341"/>
                </Source>
            </POS>
            <VehAvailRQCore Status="Available">
                <VehRentalCore PickUpDateTime="' . e($pickupDateTime) . '" ReturnDateTime="' . e($dropoffDateTime) . '">
                    <PickUpLocation LocationCode="' . e($locations['pickupLocation']) . '"/>
                    <ReturnLocation LocationCode="' . e($locations['dropoffLocation']) . '"/>
                </VehRentalCore>
            </VehAvailRQCore>
        </OTA_VehAvailRateRQ>';

        $responseXml = $this->sendOtaXmlRequest($availabilityXml);
        if ($responseXml === null || stripos(ltrim($responseXml), '<') !== 0) {
            return [];
        }

        $array = $this->xmlStringToArray($responseXml);
        if (isset($array['Errors'])) {
            Log::warning('Infinity OTA errors in availability', ['errors' => $array['Errors']]);
            return [];
        }

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

        // Construcción de coches del proveedor
        $cars = [];
        foreach ($vehAvails as $veh) {
            $status = Arr::get($veh, '@attributes.Status');
            if ($status !== 'Available') {
                continue;
            }

            $vehicle    = Arr::get($veh, 'Vehicle', []);
            $rentalRate = Arr::get($veh, 'RentalRate', []);
            $picture    = Arr::get($vehicle, 'PictureURL');

            $totalPrice = (float) Arr::get($rentalRate, 'TotalCharge.@attributes.EstimatedTotalAmount', 0);

             // Trae las fees (puede venir 1 objeto o un arreglo) y normaliza a arreglo
            $fees = Arr::wrap(Arr::get($rentalRate, 'Fees.Fee', []));

            // Suma únicamente las que tengan IncludedInEstTotalInd == "0"
            $extraFees = collect($fees)
                ->filter(fn ($fee) => (string) Arr::get($fee, '@attributes.IncludedInEstTotalInd') === '0')
                ->sum(fn ($fee) => (float) Arr::get($fee, '@attributes.Amount', 0));

            // Agrega esas fees al total
            $totalPrice += $extraFees;

            $car = [
                'model_name'     => Arr::get($vehicle, 'VehMakeModel.@attributes.Name'),
                'display_name'   => Arr::get($vehicle, 'VehMakeModel.Value'),
                'car_type'       => Arr::get($vehicle, '@attributes.VendorCarType'),
                'transmission'   => Arr::get($vehicle, '@attributes.TransmissionType'),
                'baggage_qty'    => (int) Arr::get($vehicle, '@attributes.BaggageQuantity', 0),
                'passengers'     => (int) Arr::get($vehicle, '@attributes.PassengerQuantity', 0),
                'class'          => Arr::get($vehicle, 'VehClass.@attributes.Size'),
                'doors'          => (int) Arr::get($vehicle, 'VehType.@attributes.DoorCount', 0),
                'image_url'      => $picture,
                'total_price'    => $totalPrice,
                'extrasIncluded' => $extraFees,
                'currency'       => Arr::get($rentalRate, 'TotalCharge.@attributes.CurrencyCode', 'USD'),
                'rate_comment'   => Arr::get($rentalRate, 'RateQualifier.RateComments.RateComment'),
                'vendor_rate_id' => Arr::get($rentalRate, 'RateQualifier.@attributes.VendorRateID'),
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
                // NO upsert automático en Infinity por ahora (comentado en tu código original)
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
                'providerId'         => self::PROVIDER_ID,
                'providerName'       => 'INFINITY CAR RENTAL',
                'pickupOfficeId'     => $locations['pickupOfficeId'],
                'dropoffOfficeId'    => $locations['dropoffOfficeId'],
                'totalDays'          => $totalDays,
                'netRate'            => $totalDays > 0 ? ($providerVehicle['total_price'] / $totalDays) : 0.0,
                'extrasIncluded'     => $totalDays > 0 ? ($providerVehicle['extrasIncluded'] / $totalDays): 0.0,
                'vehicleImage'       => $vehicle->image,
                'vehicleId'          => $vehicle->vehicle_id,
                'vehicleType'        => $vehicle->vehicle_type,
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

    /** Inserta/actualiza oficinas Infinity (OTA_VehLocSearchRQ). Devuelve count. */
    public function insertOffices(): int
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

                DB::table('providers_infinity_locations')->updateOrInsert(
                    ['code' => $data['code']],
                    $data
                );

                $count++;
            }
        }

        return $count;
    }

    /** Cachea vehículos Infinity mapeados a categorías MCR. */
    private function getVehicles(): \Illuminate\Support\Collection
    {
        return Cache::remember('group_infinity_vehicles', now()->addDays(7), function () {
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
     * Resuelve oficinas desde params explícitos o por IATA + tipo (Aeropuerto/City).
     * @return array{pickupLocation:?string,dropoffLocation:?string,pickupOfficeId:?int,dropoffOfficeId:?int}
     */
    private function resolveLocations(array $searchParams): array
    {
        // Caso explícito (vía reservación previa)
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

    /** Envía XML con retries/timeout. */
    private function sendOtaXmlRequest(string $xml): ?string
    {
        if ($this->endpoint === '') {
            Log::error('Infinity endpoint not configured');
            return null;
        }

        $encodedXml = urlencode($xml);
        $endpoint = $this->endpoint . '?XML=' . $encodedXml;

        try {
            $response = Http::retry($this->httpRetries, $this->httpRetrySleepMs)
                ->timeout($this->httpTimeout)
                ->withHeaders(['Accept' => 'application/xml'])
                ->get($endpoint);

            if (!$response->successful()) {
                Log::warning('Infinity OTA non-success response', [
                    'status' => $response->status(),
                    'body'   => mb_substr($response->body(), 0, 1000),
                ]);
                return null;
            }

            return $response->body();
        } catch (\Throwable $e) {
            Log::error('Infinity OTA request exception', ['message' => $e->getMessage()]);
            return null;
        }
    }

    /** Días completos (ceil) entre dos datetimes. */
    public function calculateFullDays(string $startDate, string $endDate): int
    {
        $start = Carbon::parse($startDate);
        $end   = Carbon::parse($endDate);
        $minutes = $start->diffInMinutes($end);
        return (int) ceil($minutes / 1440);
    }

    /**
     * Confirma todas las reservas pendientes del proveedor Infinity.
     * Nota: mantiene la tabla america_group_quotations (como tu código original).
     */
    public function confirmBookings(): int
    {
        set_time_limit(0);

        $reservations = DB::table('reservaciones')
            ->select([
                'reservaciones.estado AS status',
                'reservaciones.fechaRecoger as pickup_date',
                'reservaciones.fechaDejar as dropoff_date',
                'reservaciones.horaRecoger as pickup_time',
                'reservaciones.horaDejar as dropoff_time',
                'reservaciones.no_vuelo as flight',
                'reservaciones.aereolinea as airline',
                'clientes.id as client_id',
                'clientes.nombre as name',
                'clientes.token_id as token_id',
                'clientes.apellido as last_name',
                'pickup_location.code as pickup_location_code',
                'dropoff_location.code as dropoff_location_code',
            ])
            ->join('clientes', 'clientes.id', 'reservaciones.id_cliente')
            ->join('provider_locations as pickup_location', 'pickup_location.mcr_office_id', 'reservaciones.id_direccion')
            ->join('provider_locations as dropoff_location', 'dropoff_location.mcr_office_id', 'reservaciones.id_direccion_dropoff')
            ->whereIn('reservaciones.estado', ['dpe', 'dpa'])
            ->where('reservaciones.no_confirmacion', '')
            ->where('reservaciones.proveedor', self::PROVIDER_ID)
            ->get();

        $confirmReservations = 0;

        foreach ($reservations as $reservation) {
            $quotation = DB::table('america_group_quotations')
                ->where('client_id', $reservation->client_id)
                ->first();

            if (!$quotation) {
                continue;
            }

            $xml = $this->generateVehResXml($reservation, $quotation);
            $responseXml = $this->sendOtaXmlRequest($xml);

            if ($responseXml) {
                $confirmReservations++;
                $array = $this->xmlStringToArray($responseXml);
                $id = Arr::get($array, 'VehResRSCore.VehReservation.VehSegmentCore.ConfID.@attributes.ID');

                if ($id) {
                    DB::table('reservaciones')
                        ->where('id_cliente', $reservation->client_id)
                        ->update(['no_confirmacion' => $id]);
                }

                DB::table('america_group_quotations')
                    ->where('client_id', $reservation->client_id)
                    ->update([
                        'confirmation_request'  => $xml,
                        'confirmation_response' => json_encode($array, JSON_UNESCAPED_UNICODE),
                    ]);
            }
        }

        return $confirmReservations;
    }

    /** Construye XML de confirmación. */
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
        $vehPref->addChild('VehClass', (string) $quotation->car_type);
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

    // ---------------- Helpers XML/array ----------------

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
