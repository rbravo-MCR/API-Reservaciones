<?php

namespace App\Repositories;

use GuzzleHttp\Client;
use GuzzleHttp\Exception\RequestException;
use DB;
use Cache;
use Carbon\Carbon;

class AvisRepository
{
    private Client $http;
    private string $endpoint;
    private string $user;
    private string $password;
    private string $target;
    private const PROVIDER_ID = 16;

    public function __construct(?Client $http = null)
    {
        $this->http = $http ?? new Client([
            'timeout' => 30,
            'connect_timeout' => 15,
        ]);

        $this->endpoint = config('avis.endpoint');
        $this->user     = config('avis.user');
        $this->password = config('avis.password');
        $this->target   = config('avis.target', 'Test'); // Test|Production
    }

    public function getAvailability(array $searchParams, ?int $provider = null, bool $includeRaw = false): array
{
    // 1) Resolver locaciones
    $locations  = $this->resolveLocations($searchParams);
    $pickupLoc  = $locations['pickupLocation']  ?? null;
    $dropoffLoc = $locations['dropoffLocation'] ?? null;
    if (empty($pickupLoc)) return [];
    if (empty($dropoffLoc)) $dropoffLoc = $pickupLoc;

    // 2) Fechas/horas ISO (yyyy-mm-ddTHH:MM:SS)
    $pickupDateTime  = sprintf('%sT%s:00', $searchParams['pickupDate'],  $searchParams['pickupTime']);
    $dropoffDateTime = sprintf('%sT%s:00', $searchParams['dropoffDate'], $searchParams['dropoffTime']);
    $pickupDT        = htmlspecialchars($pickupDateTime, ENT_XML1);
    $returnDT        = htmlspecialchars($dropoffDateTime, ENT_XML1);

    // 3) Codes
    $pickupCode = htmlspecialchars($pickupLoc, ENT_XML1);
    $returnCode = htmlspecialchars($dropoffLoc, ENT_XML1);

    // 4) Parámetros negocio (opcionales)
    $rateCategory = (string)($searchParams['rateCategory'] ?? '6'); // 6=All (como sample)
    $corp         = $searchParams['corpDiscount'] ?? null;          // AWD/BCD
    $coupon       = $searchParams['couponCode']   ?? null;
    $citizenCode  = htmlspecialchars($searchParams['citizenCountry'] ?? 'MX', ENT_XML1);
    $maxResponses = (int)($searchParams['maxResponses'] ?? 50);
    $inclusive    = (bool)($searchParams['inclusiveRates'] ?? false);
    $includeVehPrefs = (bool)($searchParams['includeVehPrefs'] ?? false);

    // 5) Bloques del RQ (al estilo que ya te funcionó)
    $pos = '<POS><Source><RequestorID ID="MexicoCarRental" Type="1"/></Source></POS>';

    $vendorPrefs = '<VendorPrefs><VendorPref CompanyShortName="Avis"/></VendorPrefs>';

    $vehPrefs = '';
    if ($includeVehPrefs) {
        $vehPrefs = '<VehPrefs><VehPref AirConditionPref="Preferred" ClassPref="Preferred" TransmissionPref="Preferred" TransmissionType="Automatic" TypePref="Preferred"><VehType VehicleCategory="1"/><VehClass Size="4"/></VehPref></VehPrefs>';
    }

    // RateQualifier
    $rqAttrs = ['RateCategory' => $rateCategory];
    if (!empty($corp))   $rqAttrs['CorpDiscountNmbr'] = $corp;
    if (!empty($coupon)) $rqAttrs['PromotionCode']    = $coupon;
    $rateQualifier = '<RateQualifier '.implode(' ', array_map(fn($k,$v)=>$this->xmlAttr($k,$v), array_keys($rqAttrs), $rqAttrs)).'/>';

    // TPA (InclusiveRates)
    $tpaExt = $inclusive ? '<TPA_Extensions><InclusiveRates>true</InclusiveRates></TPA_Extensions>' : '';

    $core = sprintf(
        '<VehAvailRQCore Status="Available">
           <VehRentalCore PickUpDateTime="%s" ReturnDateTime="%s">
             <PickUpLocation LocationCode="%s"/>
             <ReturnLocation LocationCode="%s"/>
           </VehRentalCore>
           %s
           %s
           %s
           %s
         </VehAvailRQCore>',
        $pickupDT, $returnDT, $pickupCode, $returnCode, $vendorPrefs, $vehPrefs, $rateQualifier, $tpaExt
    );

    $info = '<VehAvailRQInfo><Customer><Primary><CitizenCountryName Code="'.$citizenCode.'"/></Primary></Customer></VehAvailRQInfo>';

    // RQ SIN namespace OTA por omisión (tal cual el que ya aceptó el gateway)
    $rq = sprintf(
        '<OTA_VehAvailRateRQ MaxResponses="%d" ReqRespVersion="small" Version="1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">%s%s%s</OTA_VehAvailRateRQ>',
        $maxResponses, $pos, $core, $info
    );

    // 6) Enviar (send() pone el sobre SOAP + credenciales)
    $rsXml = $this->send($rq);

    dd($rsXml);

    // 7) Parsear RS (ignorando namespaces)
    try {
        $env = $this->parseSimpleXml($rsXml);
    } catch (\Throwable $e) {
        logger()->error('Avis AvailRate parse error: '.$e->getMessage());
        return [];
    }

    // VehAvail nodos
    $vehAvailNodes = $env->xpath("//*[local-name()='VehAvail']");
    if (!$vehAvailNodes) {
        // log de muestra del RS para depurar si hace falta
        logger()->warning('Avis AvailRate: 0 VehAvail en RS', ['first_kb' => substr($rsXml, 0, 2048)]);
        return [];
    }

    // 8) Índice de catálogo (nombre + ACRISS)
    $vehiclesDb = $this->getVehicles();
    $normalize = function (?string $s) {
        $s = $s ?? '';
        $s = preg_replace('/\s+/', ' ', trim($s));
        return mb_strtolower($s);
    };
    $makeKey = function ($name, $acriss) use ($normalize) {
        if (!$name || !$acriss) return null;
        return $normalize($name) . '|' . $normalize($acriss);
    };

    $vehiclesByNameAcriss = [];
    foreach ($vehiclesDb as $v) {
        $name   = $v->car_name ?? null;
        $acriss = $v->acriss ?? ($v->cAcriss ?? null);
        $key    = $makeKey($name, $acriss);
        if ($key) $vehiclesByNameAcriss[$key] = $v;
    }

    // 9) Días totales
    $totalDays = $this->calculateFullDays(
        $searchParams['pickupDate'].' '.$searchParams['pickupTime'],
        $searchParams['dropoffDate'].' '.$searchParams['dropoffTime']
    );
    $totalDays = max(1, (int)$totalDays);

    // 10) Mapear RS → catálogo
    $matchList = [];
    $addedCategories = [];

    foreach ($vehAvailNodes as $node) {
        // VehAvailCore
        $coreArr = $node->xpath("./*[local-name()='VehAvailCore']");
        if (!$coreArr || !isset($coreArr[0])) continue;
        $coreNode = $coreArr[0];

        // Vehicle
        $vehArr = $coreNode->xpath("./*[local-name()='Vehicle']");
        if (!$vehArr || !isset($vehArr[0])) continue;
        $vehNode = $vehArr[0];

        // ACRISS: normalmente en Vehicle/@Code
        $vehAttrs = $vehNode->attributes();
        $acriss   = isset($vehAttrs['Code']) ? trim((string)$vehAttrs['Code']) : null;

        // Nombre de modelo: VehMakeModel/@Name
        $mmArr = $vehNode->xpath("./*[local-name()='VehMakeModel']");
        $modelName = null;
        if ($mmArr && isset($mmArr[0])) {
            $mmAttrs   = $mmArr[0]->attributes();
            $modelName = isset($mmAttrs['Name']) ? trim((string)$mmAttrs['Name']) : null;
        }

        // Total: VehAvailCore/TotalCharge/@EstimatedTotalAmount || @RateTotalAmount
        $tcArr = $coreNode->xpath("./*[local-name()='TotalCharge']");
        $grandTotal = 0.0;
        if ($tcArr && isset($tcArr[0])) {
            $tcAttrs = $tcArr[0]->attributes();
            if (isset($tcAttrs['EstimatedTotalAmount'])) {
                $grandTotal = (float)$tcAttrs['EstimatedTotalAmount'];
            } elseif (isset($tcAttrs['RateTotalAmount'])) {
                $grandTotal = (float)$tcAttrs['RateTotalAmount'];
            }
        }

        // RateCode: en RateQualifier/@RateQualifier (si viene)
        $rqArr = $coreNode->xpath("./*[local-name()='RateQualifier']");
        $rateCode = null;
        if ($rqArr && isset($rqArr[0])) {
            $rqAttrs = $rqArr[0]->attributes();
            if (isset($rqAttrs['RateQualifier'])) {
                $rateCode = (string)$rqAttrs['RateQualifier'];
            }
        }

        // Match por (nombre + acriss)
        $key = $makeKey($modelName, $acriss);
        if (!$key || !isset($vehiclesByNameAcriss[$key])) {
            // si no hay match exacto, intenta sólo por ACRISS
            $fallback = null;
            foreach ($vehiclesDb as $v) {
                $va = $v->acriss ?? ($v->cAcriss ?? null);
                if ($va && $normalize($va) === $normalize($acriss)) { $fallback = $v; break; }
            }
            if (!$fallback) continue;
            $vehicle = $fallback;
        } else {
            $vehicle = $vehiclesByNameAcriss[$key];
        }

        // Restringir a 1 por categoría (como en tu ejemplo)
        if (in_array($vehicle->category, $addedCategories, true)) continue;
        $addedCategories[] = $vehicle->category;

        $extrasTotalEstim = 0.0; // si luego quieres sumar Fees/Extras del RS, aquí

        $netPerDay = $totalDays > 0 ? ($grandTotal / $totalDays) : 0.0;

        $item = (object) [
            'vehicleName'        => $vehicle->car_name_mcr,
            'vehicleCategory'    => $vehicle->category,
            'vehicleDescription' => $vehicle->descripccion,
            'vehicleAcriss'      => $vehicle->cAcriss ?? ($vehicle->acriss ?? null),
            'providerId'         => self::PROVIDER_ID,
            'providerName'       => 'AVIS',
            'pickupOfficeId'     => $locations['pickupOfficeId'],
            'dropoffOfficeId'    => $locations['dropoffOfficeId'],
            'totalDays'          => $totalDays,
            'netRate'            => $netPerDay,                          // por día
            'extrasIncluded'     => ($extrasTotalEstim / $totalDays),    // placeholder
            'vehicleImage'       => $vehicle->image,
            'vehicleId'          => $vehicle->vehicle_id ?? null,
            'vehicleType'        => $vehicle->vehicle_type ?? null,
            'rateCode'           => (string)($rateCode ?? ''),
            'rateId'             => '',                                  // si el RS lo trae en otro nodo, mapéalo aquí
            'classType'          => $acriss,
            'corporateSetup'     => null,
        ];

        if ($includeRaw) {
            $item->availabilityRequest  = $rq;
            $item->availabilityResponse = substr($this->cleanSoapXml($rsXml), 0, 50000); // recorte para no inflar
        }

        $matchList[] = $item;
    }

    return $matchList;
}

    // public function getAvailability(array $searchParams, ?int $provider = null, bool $includeRaw = false)
    // {
    //     // 1) Resolver locaciones
    //     $locations  = $this->resolveLocations($searchParams);
    //     $pickupLoc  = $locations['pickupLocation']  ?? null;
    //     $dropoffLoc = $locations['dropoffLocation'] ?? null;
    //     if (empty($pickupLoc)) return [];            // sin pickup no podemos cotizar
    //     if (empty($dropoffLoc)) $dropoffLoc = $pickupLoc; // fallback

    //     // 2) Fechas/horas ISO (yyyy-mm-ddTHH:MM:SS)
    //     $pickupDateTime  = sprintf('%sT%s:00', $searchParams['pickupDate'],  $searchParams['pickupTime']);
    //     $dropoffDateTime = sprintf('%sT%s:00', $searchParams['dropoffDate'], $searchParams['dropoffTime']);

    //     // 3) Sanitizar
    //     $pickupCode = htmlspecialchars($pickupLoc, ENT_XML1);
    //     $returnCode = htmlspecialchars($dropoffLoc, ENT_XML1);
    //     $pickupDT   = htmlspecialchars($pickupDateTime, ENT_XML1);
    //     $returnDT   = htmlspecialchars($dropoffDateTime, ENT_XML1);

    //     // 4) Opcionales negocio
    //     $rateCategory = $searchParams['rateCategory']   ?? '6';   // 6 = All (como sample)
    //     $corp         = $searchParams['corpDiscount']   ?? null;  // AWD/BCD
    //     $coupon       = $searchParams['couponCode']     ?? null;
    //     $citizenCode  = htmlspecialchars($searchParams['citizenCountry'] ?? 'MX', ENT_XML1);
    //     $maxResponses = (int)($searchParams['maxResponses'] ?? 1);
    //     $inclusive    = (bool)($searchParams['inclusiveRates'] ?? false);
    //     $includeVehPrefs = (bool)($searchParams['includeVehPrefs'] ?? false);

    //     // VendorPrefs
    //     $vendorPrefs = <<<XML
    // <VendorPrefs>
    // <VendorPref CompanyShortName="Avis"/>
    // </VendorPrefs>
    // XML;

    //     // RateQualifier (opcional)
    //     $rateQualifierAttrs = ['RateCategory' => (string)$rateCategory];
    //     if (!empty($corp))   $rateQualifierAttrs['CorpDiscountNmbr'] = $corp;
    //     if (!empty($coupon)) $rateQualifierAttrs['PromotionCode']    = $coupon;

    //     $rateQualifier = '<RateQualifier '.
    //         implode(' ', array_map(fn($k,$v)=>$this->xmlAttr($k,$v), array_keys($rateQualifierAttrs), $rateQualifierAttrs)).
    //         '/>';

    //     // VehPrefs (opcional, como el sample del PDF)
    //     $vehPrefs = '';
    //     if ($includeVehPrefs) {
    //         $vehPrefs = <<<XML
    // <VehPrefs>
    // <VehPref AirConditionPref="Preferred" ClassPref="Preferred" TransmissionPref="Preferred" TransmissionType="Automatic" TypePref="Preferred">
    //     <VehType VehicleCategory="1"/>
    //     <VehClass Size="4"/>
    // </VehPref>
    // </VehPrefs>
    // XML;
    //     }

    //     // TPA_Extensions (InclusiveRates) - opcional
    //     $tpaExt = $inclusive ? '<TPA_Extensions><InclusiveRates>true</InclusiveRates></TPA_Extensions>' : '';

    //     // POS (1 Source como el que te funcionó)
    //     $pos = '<POS><Source><RequestorID ID="MexicoCarRental" Type="1"/></Source></POS>';

    //     // Core (Status="Available" + ReturnLocation)
    //     $core = sprintf(
    //         '<VehAvailRQCore Status="Available">
    //         <VehRentalCore PickUpDateTime="%s" ReturnDateTime="%s">
    //             <PickUpLocation LocationCode="%s"/>
    //             <ReturnLocation LocationCode="%s"/>
    //         </VehRentalCore>
    //         %s
    //         %s
    //         %s
    //         %s
    //         </VehAvailRQCore>',
    //         $pickupDT, $returnDT, $pickupCode, $returnCode,
    //         $vendorPrefs, $vehPrefs, $rateQualifier, $tpaExt
    //     );

    //     // Info (ciudadanía, como el sample)
    //     $info = '<VehAvailRQInfo><Customer><Primary><CitizenCountryName Code="'.$citizenCode.'"/></Primary></Customer></VehAvailRQInfo>';

    //     // 5) Construcción del RQ siguiendo el XML que te funciona
    //     // IMPORTANTE: sin Target y sin xmlns OTA por omisión (solo xmlns:xsi)
    //     $xml = sprintf(
    //         '<OTA_VehAvailRateRQ MaxResponses="%d" ReqRespVersion="small" Version="1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    //         %s
    //         %s
    //         %s
    //         </OTA_VehAvailRateRQ>',
    //         $maxResponses, $pos, $core, $info
    //     );

    //     // 6) Enviar (send() envuelve con el SOAP + credenciales)
    //     $rs = $this->send($xml);

    //     if ($includeRaw) {
    //         return ['raw' => $rs];
    //     }
    //     return ['raw' => $rs]; // deja así por ahora; luego mapeamos a DTO si quieres
    // }





        /**
     * Cachea y retorna vehículos del proveedor mapeados a categorías MCR.
     */
    private function getVehicles(): \Illuminate\Support\Collection
    {
        return Cache::remember('group_avis_vehicles', now()->addDays(7), function () {
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

    /**
     * Envía un sobre SOAP 1.1 al WSG, con header de credenciales, envolviendo el payload OTA.
     */
    public function send(string $otaPayloadXml): string
    {
        $envelope = $this->buildSoapEnvelope($otaPayloadXml);


        try {
            $headers = [
                'Content-Type' => 'text/xml; charset=utf-8', // SOAP 1.1
            ];
            // Algunos gateways esperan SOAPAction (aunque ABG no siempre lo exige).
            $soapAction = config('avis.soap_action');
            if ($soapAction !== null) {
                $headers['SOAPAction'] = $soapAction; // puede ser "" (cadena vacía)
            }

            // dd($headers, $envelope);

            $resp = $this->http->post($this->endpoint, [
                'headers' => $headers,
                'body'    => $envelope,
            ]);
            return (string) $resp->getBody();
        } catch (RequestException $e) {
            $body = $e->getResponse() ? (string) $e->getResponse()->getBody() : $e->getMessage();
            throw new \RuntimeException("Avis DC request failed: {$body}", 0, $e);
        }
    }

    private function buildSoapEnvelope(string $payloadBodyXml): string
    {
        // Header con credenciales según especificación:
        // <ns:credentials xmlns:ns="http://wsg.avis.com/wsbang/authInAny">
        //   <ns:userID>...</ns:userID>
        //   <ns:password>...</ns:password>
        // </ns:credentials>
        // y payload dentro de <ns:Request xmlns:ns="http://wsg.avis.com/wsbang">...</ns:Request>

        $user = htmlspecialchars($this->user, ENT_XML1);
        $pass = htmlspecialchars($this->password, ENT_XML1);
        return <<<XML
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope
  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <SOAP-ENV:Header>
    <ns:credentials xmlns:ns="http://wsg.avis.com/wsbang/authInAny">
      <ns:userID ns:encodingType="xsd:string">{$user}</ns:userID>
      <ns:password ns:encodingType="xsd:string">{$pass}</ns:password>
    </ns:credentials>
    <ns:WSBang-Roadmap xmlns:ns="http://wsg.avis.com/wsbang"/>
  </SOAP-ENV:Header>
  <SOAP-ENV:Body>
    <ns:Request xmlns:ns="http://wsg.avis.com/wsbang">
      {$payloadBodyXml}
    </ns:Request>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
XML;
    }

    /* ========= Helpers para construir RQ OTA estándar ========= */

    private function isoNow(): string
    {
        return gmdate('Y-m-d\TH:i:s');
    }

    private function xmlAttr(string $name, string $value): string
    {
        return sprintf('%s="%s"', $name, htmlspecialchars($value, ENT_XML1));
    }

    private function targetAttr(): string
    {
        return $this->xmlAttr('Target', $this->target);
    }

    private function versionAttr(string $version = '1.0'): string
    {
        return $this->xmlAttr('Version', $version);
    }

    /* ========= Operaciones públicas (mensajes OTA soportados) ========= */

    // 0) Ping
    public function ping(string $echo = 'Hello World'): string
    {
        $xml = sprintf(
            '<OTA_PingRQ xmlns="http://www.opentravel.org/OTA/2003/05" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" %s %s TimeStamp="%s"><EchoData>%s</EchoData></OTA_PingRQ>',
            $this->targetAttr(),
            $this->versionAttr('1.0'),
            $this->isoNow(),
            htmlspecialchars($echo, ENT_XML1)
        );
        // dd($xml);
        return $this->send($xml);
    }


    private function cleanSoapXml(string $xml): string
    {
        $xml = mb_convert_encoding($xml, 'UTF-8', 'UTF-8, ISO-8859-1, Windows-1252');
        $xml = preg_replace('/^\xEF\xBB\xBF/', '', $xml);              // BOM
        $xml = preg_replace('/[^\x09\x0A\x0D\x20-\xFF]/', '', $xml);   // control chars
        return ltrim($xml);
    }

    private function parseSimpleXml(string $xml): \SimpleXMLElement
    {
        libxml_use_internal_errors(true);
        $clean = $this->cleanSoapXml($xml);

        $sx = simplexml_load_string($clean, 'SimpleXMLElement', LIBXML_NOCDATA);
        if ($sx !== false) return $sx;

        $errs = array_map(function($e){ return trim(sprintf('[%d:%d] %s',$e->line,$e->column,$e->message));}, libxml_get_errors());
        libxml_clear_errors();
        logger()->warning('Avis SOAP: simplexml falló; intentar DOM', ['errors'=>$errs,'first_kb'=>substr($clean,0,2048)]);

        $dom = new \DOMDocument();
        $dom->recover = true;
        $dom->strictErrorChecking = false;
        $dom->validateOnParse = false;

        if (@$dom->loadXML($clean, LIBXML_NOERROR | LIBXML_NOWARNING)) {
            $import = simplexml_import_dom($dom);
            if ($import !== false) return $import;
        }
        throw new \RuntimeException('No se pudo parsear XML de respuesta (limpiado + DOM).');
    }

    public function locationSearch(array $f): string
    {
        $maxResponses = (int)($f['maxResponses'] ?? 25);

        // ----- Address opcional
        $addressParts = [];
        if (!empty($f['addressLine'])) $addressParts[] = '<AddressLine>'.htmlspecialchars($f['addressLine'], ENT_XML1).'</AddressLine>';
        if (!empty($f['city']))        $addressParts[] = '<CityName>'.htmlspecialchars($f['city'], ENT_XML1).'</CityName>';
        if (!empty($f['postalCode']))  $addressParts[] = '<PostalCode>'.htmlspecialchars($f['postalCode'], ENT_XML1).'</PostalCode>';
        if (!empty($f['state']))       $addressParts[] = '<StateProv StateCode="'.htmlspecialchars($f['state'], ENT_XML1).'"/>';
        if (!empty($f['country']))     $addressParts[] = '<CountryName Code="'.htmlspecialchars($f['country'], ENT_XML1).'"/>';
        $addressXml = $addressParts ? ('<Address>'.implode('', $addressParts).'</Address>') : '';

        // ----- Position + Radius opcionales
        $positionXml = '';
        if (!empty($f['lat']) && !empty($f['lng'])) {
            $positionXml = '<Position Latitude="'.htmlspecialchars((string)$f['lat'], ENT_XML1).'" Longitude="'.htmlspecialchars((string)$f['lng'], ENT_XML1).'"/>';
        }
        $radiusXml = '';
        if (!empty($f['radiusMax'])) {
            $measure = htmlspecialchars($f['radiusMeasure'] ?? 'Miles', ENT_XML1);
            $radiusXml = '<Radius DistanceMax="'.htmlspecialchars((string)$f['radiusMax'], ENT_XML1).'" DistanceMeasure="'.$measure.'"/>';
        }

        // ----- CodeRef opcional
        $codeRefXml = '';
        if (!empty($f['codeRef'])) {
            $ctx = htmlspecialchars($f['codeContext'] ?? 'apo', ENT_XML1); // apo|ldbmnem|ldbnum
            $codeRefXml = '<RefPoint><CodeRef><LocationCode>'.htmlspecialchars($f['codeRef'], ENT_XML1).'</LocationCode><CodeContext>'.$ctx.'</CodeContext></CodeRef></RefPoint>';
        }

        if (!$addressXml && !$positionXml && !$radiusXml && !$codeRefXml) {
            $addressXml = '<Address/>';
        }

        $criterion  = "<VehLocSearchCriterion>{$addressXml}{$positionXml}{$radiusXml}{$codeRefXml}</VehLocSearchCriterion>";
        $vendorCode = htmlspecialchars($f['vendor'] ?? 'Avis', ENT_XML1);
        $vendorXml  = '<Vendor Code="'.$vendorCode.'"/>';

        // ----- TPA filters
        $tpa = [];
        if (isset($f['sortOrderType']))      $tpa[] = '<SortOrderType>'.htmlspecialchars($f['sortOrderType'], ENT_XML1).'</SortOrderType>';
        if (isset($f['testLocationType']))   $tpa[] = '<TestLocationType>'.htmlspecialchars($f['testLocationType'], ENT_XML1).'</TestLocationType>';
        if (isset($f['locationStatusType'])) $tpa[] = '<LocationStatusType>'.htmlspecialchars($f['locationStatusType'], ENT_XML1).'</LocationStatusType>';
        if (isset($f['locationType']))       $tpa[] = '<LocationType>'.htmlspecialchars($f['locationType'], ENT_XML1).'</LocationType>';
        $tpaXml = $tpa ? ('<TPA_Extensions>'.implode('', $tpa).'</TPA_Extensions>') : '';

        // ----- RQ
        $xml = sprintf(
            '<OTA_VehLocSearchRQ xmlns="http://www.opentravel.org/OTA/2003/05" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" %s %s MaxResponses="%d" TimeStamp="%s">
                <POS><Source/></POS>
                %s
                %s
                %s
            </OTA_VehLocSearchRQ>',
            $this->targetAttr(),
            $this->versionAttr('1.0'),
            $maxResponses,
            $this->isoNow(),
            $criterion,
            $vendorXml,
            $tpaXml
        );

        // ----- Enviar
        $respXml = $this->send($xml);

        // ----- Parsear + Insertar
        try {
            $env = $this->parseSimpleXml($respXml);

            // Tomamos todos los VehMatchedLoc sin importar namespace:
            $locNodes = $env->xpath("//*[local-name()='VehMatchedLoc']");
            $count = is_array($locNodes) ? count($locNodes) : 0;

            // Log diagnóstico siempre:
            logger()->info('Avis SOAP: VehMatchedLoc encontrados', ['count' => $count]);

            if (!$count) {
                // dumpear primeras líneas para depurar si no llegó nada
                logger()->warning('Avis SOAP: 0 VehMatchedLoc. Muestra:', ['first_kb' => substr($this->cleanSoapXml($respXml), 0, 2048)]);
                return $respXml;
            }

            $now = now();

            foreach ($locNodes as $i => $node) {
                // LocationDetail (mismo truco local-name)
                $locArr = $node->xpath("./*[local-name()='LocationDetail']");
                if (!$locArr || !isset($locArr[0])) { continue; }
                $locDetail = $locArr[0];

                // Atributos (sin namespaces) -> attributes() funciona igual
                $attrs     = $locDetail->attributes();
                $name      = isset($attrs['Name']) ? trim((string)$attrs['Name']) : null;
                $atAirport = isset($attrs['AtAirport']) && ((string)$attrs['AtAirport'] === 'true') ? 1 : 0;

                // Para verificar que sí los tenemos, loguea el primero:
                if ($i === 0) {
                    logger()->info('Avis SOAP: primer LocationDetail', ['name' => $name, 'at_airport' => $atAirport]);
                }

                // Dirección
                $addrArr  = $locDetail->xpath("./*[local-name()='Address']");
                $address1 = $address2 = $city = $postal = $country = null;
                if ($addrArr && isset($addrArr[0])) {
                    $addr     = $addrArr[0];
                    $a1       = $addr->xpath("./*[local-name()='AddressLine'][1]");
                    $a2       = $addr->xpath("./*[local-name()='AddressLine'][2]");
                    $address1 = $a1 && isset($a1[0]) ? trim((string)$a1[0]) : null;
                    $address2 = $a2 && isset($a2[0]) ? trim((string)$a2[0]) : null;

                    $c1       = $addr->xpath("./*[local-name()='CityName']");
                    $p1       = $addr->xpath("./*[local-name()='PostalCode']");
                    $cn1      = $addr->xpath("./*[local-name()='CountryName']");

                    $city     = $c1  && isset($c1[0])  ? trim((string)$c1[0])  : null;
                    $postal   = $p1  && isset($p1[0])  ? trim((string)$p1[0])  : null;
                    $country  = $cn1 && isset($cn1[0]) ? (string)$cn1[0]->attributes()->Code : null;
                }

                // Teléfono
                $telArr   = $locDetail->xpath("./*[local-name()='Telephone']");
                $phone = $phoneTechType = $phoneLocType = null;
                if ($telArr && isset($telArr[0])) {
                    $tattrs        = $telArr[0]->attributes();
                    $phone         = isset($tattrs['PhoneNumber'])       ? (string)$tattrs['PhoneNumber']       : null;
                    $phoneTechType = isset($tattrs['PhoneTechType'])     ? (string)$tattrs['PhoneTechType']     : null;
                    $phoneLocType  = isset($tattrs['PhoneLocationType']) ? (string)$tattrs['PhoneLocationType'] : null;
                }

                // Criterion (lat/lng)
                $posArr = $node->xpath("./*[local-name()='VehLocSearchCriterion']/*[local-name()='Position']");
                $lat = $lng = null;
                if ($posArr && isset($posArr[0])) {
                    $pattrs = $posArr[0]->attributes();
                    $lat = isset($pattrs['Latitude'])  ? (float)$pattrs['Latitude']  : null;
                    $lng = isset($pattrs['Longitude']) ? (float)$pattrs['Longitude'] : null;
                }

                // TPA_Extensions
                $tpaArr = $locDetail->xpath("./*[local-name()='AdditionalInfo']/*[local-name()='TPA_Extensions']");
                $ldbMnemonic=$gdsLocationCode=$dbrLocationCode=$locationType=$licenseeType=$status=$testLocationType=$intlDivision=$regionalCode=$wireLocationType=$autonationInd=$selfServiceInd=$secureLotInd=$truckIndicator=null;
                $distanceFromOrigin = null;

                if ($tpaArr && isset($tpaArr[0])) {
                    $tpa = $tpaArr[0];
                    $get = function($tag) use ($tpa){
                        $n = $tpa->xpath("./*[local-name()='{$tag}']");
                        return ($n && isset($n[0])) ? trim((string)$n[0]) : null;
                    };
                    $ldbMnemonic         = $get('LDBMnemonic');
                    $gdsLocationCode     = $get('GDSLocationCode');
                    $dbrLocationCode     = $get('DbrLocationCode');
                    $locationType        = $get('LocationType');
                    $licenseeType        = $get('LicenseeType');
                    $status              = $get('LocationStatusType');
                    $testLocationType    = $get('TestLocationType');
                    $intlDivision        = $get('InternationalDivisionCodeType');
                    $regionalCode        = $get('RegionalCode');
                    $wireLocationType    = $get('WireLocationType');
                    $autonationInd       = $get('AutonationIndType');
                    $selfServiceInd      = $get('SelfServiceInd');
                    $secureLotInd        = $get('SecureLotInd');
                    $truckIndicator      = $get('TruckIndicator');
                    $distanceFromOrigin  = $get('DistanceFromMapOrigin');
                    $distanceFromOrigin  = is_numeric($distanceFromOrigin) ? (float)$distanceFromOrigin : null;
                }

                // Horarios
                $hours = [];
                $schArr = $locDetail->xpath("./*[local-name()='AdditionalInfo']/*[local-name()='OperationSchedules']/*[local-name()='OperationSchedule']");
                foreach ($schArr ?: [] as $sch) {
                    $sattrs = $sch->attributes();
                    $schStart = isset($sattrs['Start']) ? (string)$sattrs['Start'] : '';
                    $schEnd   = isset($sattrs['End'])   ? (string)$sattrs['End']   : '';
                    $times = [];
                    $tArr = $sch->xpath("./*[local-name()='OperationTimes']/*[local-name()='OperationTime']");
                    foreach ($tArr ?: [] as $t) {
                        $ta = $t->attributes();
                        $times[] = [
                            'sun'   => ((string)($ta['Sun']  ?? 'false')) === 'true',
                            'mon'   => ((string)($ta['Mon']  ?? 'false')) === 'true',
                            'tue'   => ((string)($ta['Tue']  ?? 'false')) === 'true',
                            'weds'  => ((string)($ta['Weds'] ?? 'false')) === 'true',
                            'thur'  => ((string)($ta['Thur'] ?? 'false')) === 'true',
                            'fri'   => ((string)($ta['Fri']  ?? 'false')) === 'true',
                            'sat'   => ((string)($ta['Sat']  ?? 'false')) === 'true',
                            'start' => (string)($ta['Start'] ?? ''),
                            'end'   => (string)($ta['End']   ?? ''),
                        ];
                    }
                    $hours[] = ['valid_from'=>$schStart,'valid_to'=>$schEnd,'times'=>$times];
                }

                // Payload a BD
                $payload = [
                    'vendor'               => 'Avis',
                    'at_airport'           => (int)$atAirport,
                    'name'                 => $name,

                    'ldb_mnemonic'         => $ldbMnemonic ?: null,
                    'gds_location_code'    => $gdsLocationCode ?: null,
                    'dbr_location_code'    => $dbrLocationCode ?: null,

                    'location_type'        => $locationType ?: null,
                    'licensee_type'        => $licenseeType ?: null,
                    'status'               => $status ?: null,
                    'test_location_type'   => $testLocationType ?: null,
                    'intl_division'        => $intlDivision ?: null,
                    'regional_code'        => $regionalCode ?: null,
                    'wire_location_type'   => $wireLocationType ?: null,
                    'autonation_ind'       => $autonationInd ?: null,
                    'self_service_ind'     => $selfServiceInd ?: null,
                    'secure_lot_ind'       => $secureLotInd ?: null,
                    'truck_indicator'      => $truckIndicator ?: null,
                    'distance_from_origin' => $distanceFromOrigin,

                    'country_code'         => $country ?: null,
                    'city'                 => $city ?: null,
                    'address1'             => $address1 ?: null,
                    'address2'             => $address2 ?: null,
                    'postal_code'          => $postal ?: null,

                    'phone'                => $phone ?: null,
                    'phone_tech_type'      => $phoneTechType ?: null,
                    'phone_loc_type'       => $phoneLocType ?: null,

                    'latitude'             => $lat,
                    'longitude'            => $lng,

                    'hours_json'           => json_encode($hours, JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE),
                    'raw_xml'              => $locDetail->asXML(),

                    'updated_at'           => $now,
                    'created_at'           => $now,
                ];

                // Clave única
                $unique = [];
                if (!empty($gdsLocationCode)) {
                    $unique = ['gds_location_code' => $gdsLocationCode];
                } elseif (!empty($dbrLocationCode)) {
                    $unique = ['dbr_location_code' => $dbrLocationCode];
                } else {
                    $unique = ['name' => $name, 'city' => $city ?: null];
                }

                // DB::table('api_avis_stations')->updateOrInsert($unique, $payload);
            }

        } catch (\Throwable $e) {
            logger()->error('Avis LocationSearch parse/insert error: '.$e->getMessage(), ['trace'=>$e->getTraceAsString()]);
        }

        return $respXml;
    }


    // 2) Availability & Rate: OTA_VehAvailRateRQ
    public function availRate(array $args): string
    {
        // Requeridos: pickupCode, pickupDateTime, returnDateTime
        $pickupCode = htmlspecialchars($args['pickupCode'], ENT_XML1);
        $pickupDT   = htmlspecialchars($args['pickupDateTime'], ENT_XML1);
        $returnDT   = htmlspecialchars($args['returnDateTime'], ENT_XML1);
        $vendor     = htmlspecialchars($args['vendor'] ?? config('services.avis_dc.vendor_default','Avis'), ENT_XML1);

        // Opcionales
        $rateCategory = $args['rateCategory'] ?? null; // 2=Business, 3=Leisure, 6=All
        $corp         = $args['corpDiscount'] ?? null; // AWD/BCD
        $coupon       = $args['couponCode'] ?? null;
        $inclusive    = $args['inclusiveRates'] ?? false;

        $vendorPrefs = <<<XML
<VendorPrefs>
  <VendorPref CompanyShortName="{$vendor}" />
</VendorPrefs>
XML;

        $rateQualifier = '';
        if ($rateCategory || $corp || $coupon) {
            $attrs = [];
            if ($rateCategory) $attrs[] = $this->xmlAttr('RateCategory', (string)$rateCategory);
            if ($corp)         $attrs[] = $this->xmlAttr('CorpDiscountNmbr', $corp);
            if ($coupon)       $attrs[] = $this->xmlAttr('PromotionCode', $coupon);
            $rateQualifier = '<RateQualifier '.implode(' ', $attrs).'/>';
        }

        $tpaExt = $inclusive ? '<TPA_Extensions><InclusiveRates>true</InclusiveRates></TPA_Extensions>' : '';

        $xml = sprintf(
            '<OTA_VehAvailRateRQ xmlns="http://www.opentravel.org/OTA/2003/05" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" %s %s TimeStamp="%s" ReqRespVersion="small">
               <POS>
                 <Source>
                   <RequestorID Type="1" ID="PARTNER_COMPANY"/>
                 </Source>
               </POS>
               <VehAvailRQCore>
                 <VehRentalCore PickUpDateTime="%s" ReturnDateTime="%s">
                   <PickUpLocation LocationCode="%s"/>
                 </VehRentalCore>
                 %s
                 %s
                 %s
               </VehAvailRQCore>
             </OTA_VehAvailRateRQ>',
            $this->targetAttr(),
            $this->versionAttr('1.0'),
            $this->isoNow(),
            $pickupDT,
            $returnDT,
            $pickupCode,
            $vendorPrefs,
            $rateQualifier,
            $tpaExt
        );

        return $this->send($xml);
    }

    // 3) Rate Rule: OTA_VehRateRuleRQ
    public function rateRule(array $args): string
    {
        // Suele incluir los mismos datos de renta y el RateQualifier/RateCode que devolvió el AvailRate
        $pickupCode = htmlspecialchars($args['pickupCode'], ENT_XML1);
        $pickupDT   = htmlspecialchars($args['pickupDateTime'], ENT_XML1);
        $returnDT   = htmlspecialchars($args['returnDateTime'], ENT_XML1);
        $rateCode   = htmlspecialchars($args['rateCode'] ?? '', ENT_XML1);

        $rateQual = $rateCode ? '<RateQualifier RateQualifier="'.$rateCode.'"/>' : '';

        $xml = sprintf(
            '<OTA_VehRateRuleRQ xmlns="http://www.opentravel.org/OTA/2003/05" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" %s %s TimeStamp="%s">
               <VehRentalCore PickUpDateTime="%s" ReturnDateTime="%s">
                 <PickUpLocation LocationCode="%s"/>
               </VehRentalCore>
               %s
             </OTA_VehRateRuleRQ>',
            $this->targetAttr(),
            $this->versionAttr('1.0'),
            $this->isoNow(),
            $pickupDT,
            $returnDT,
            $pickupCode,
            $rateQual
        );

        return $this->send($xml);
    }

    // 4) Create Reservation: OTA_VehResRQ
    public function createReservation(array $args): string
    {
        $pickupCode = htmlspecialchars($args['pickupCode'], ENT_XML1);
        $pickupDT   = htmlspecialchars($args['pickupDateTime'], ENT_XML1);
        $returnDT   = htmlspecialchars($args['returnDateTime'], ENT_XML1);
        $email      = htmlspecialchars($args['email'], ENT_XML1);

        $givenName  = htmlspecialchars($args['firstName'], ENT_XML1);
        $surname    = htmlspecialchars($args['lastName'], ENT_XML1);
        $vendor     = htmlspecialchars($args['vendor'] ?? config('services.avis_dc.vendor_default','Avis'), ENT_XML1);

        // Opcionales
        $rateCode   = !empty($args['rateCode']) ? ' RateQualifier="'.$this->escape($args['rateCode']).'"' : '';
        $corp       = !empty($args['corpDiscount']) ? ' CorpDiscountNmbr="'.$this->escape($args['corpDiscount']).'"' : '';
        $coupon     = !empty($args['couponCode']) ? ' PromotionCode="'.$this->escape($args['couponCode']).'"' : '';

        $rateQualifier = ($rateCode || $corp || $coupon)
            ? "<RateQualifier{$rateCode}{$corp}{$coupon}/>"
            : '';

        $xml = sprintf(
            '<OTA_VehResRQ xmlns="http://www.opentravel.org/OTA/2003/05" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" %s %s TimeStamp="%s">
               <POS>
                 <Source>
                   <RequestorID Type="1" ID="PARTNER_COMPANY"/>
                 </Source>
               </POS>
               <VehResRQCore>
                 <VehRentalCore PickUpDateTime="%s" ReturnDateTime="%s">
                   <PickUpLocation LocationCode="%s"/>
                 </VehRentalCore>
                 <Customer>
                   <Primary>
                     <PersonName>
                       <GivenName>%s</GivenName>
                       <Surname>%s</Surname>
                     </PersonName>
                     <Email>%s</Email>
                   </Primary>
                 </Customer>
                 <VendorPref CompanyShortName="%s"/>
                 %s
               </VehResRQCore>
             </OTA_VehResRQ>',
            $this->targetAttr(),
            $this->versionAttr('1.0'),
            $this->isoNow(),
            $pickupDT,
            $returnDT,
            $pickupCode,
            $givenName,
            $surname,
            $email,
            $vendor,
            $rateQualifier
        );

        return $this->send($xml);
    }

    // 5) Retrieve Reservation: OTA_VehRetResRQ
    public function retrieveReservation(string $confirmationId): string
    {
        $id = htmlspecialchars($confirmationId, ENT_XML1);
        $xml = sprintf(
            '<OTA_VehRetResRQ xmlns="http://www.opentravel.org/OTA/2003/05" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" %s %s TimeStamp="%s">
               <UniqueID Type="14" ID="%s"/>
             </OTA_VehRetResRQ>',
            $this->targetAttr(),
            $this->versionAttr('1.0'),
            $this->isoNow(),
            $id
        );
        return $this->send($xml);
    }

    // 6) Modify Reservation: OTA_VehModifyRQ
    public function modifyReservation(string $confirmationId, array $changes): string
    {
        $id = htmlspecialchars($confirmationId, ENT_XML1);

        $core = '';
        if (!empty($changes['pickupDateTime']) || !empty($changes['returnDateTime']) || !empty($changes['pickupCode'])) {
            $attrs = [];
            if (!empty($changes['pickupDateTime']))  $attrs[] = $this->xmlAttr('PickUpDateTime', $changes['pickupDateTime']);
            if (!empty($changes['returnDateTime']))  $attrs[] = $this->xmlAttr('ReturnDateTime', $changes['returnDateTime']);
            $core .= '<VehRentalCore '.implode(' ', $attrs).'>';
            if (!empty($changes['pickupCode'])) {
                $core .= '<PickUpLocation '.$this->xmlAttr('LocationCode', $changes['pickupCode']).'/>';
            }
            $core .= '</VehRentalCore>';
        }

        $xml = sprintf(
            '<OTA_VehModifyRQ xmlns="http://www.opentravel.org/OTA/2003/05" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" %s %s TimeStamp="%s">
               <VehModifyRQCore>
                 <UniqueID Type="14" ID="%s"/>
                 %s
               </VehModifyRQCore>
             </OTA_VehModifyRQ>',
            $this->targetAttr(),
            $this->versionAttr('1.0'),
            $this->isoNow(),
            $id,
            $core
        );
        return $this->send($xml);
    }

    // 7) Cancel Reservation: OTA_VehCancelRQ
    public function cancelReservation(string $confirmationId): string
    {
        $id = htmlspecialchars($confirmationId, ENT_XML1);
        $xml = sprintf(
            '<OTA_VehCancelRQ xmlns="http://www.opentravel.org/OTA/2003/05" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" %s %s TimeStamp="%s">
               <UniqueID Type="14" ID="%s"/>
             </OTA_VehCancelRQ>',
            $this->targetAttr(),
            $this->versionAttr('1.0'),
            $this->isoNow(),
            $id
        );
        return $this->send($xml);
    }

    private function escape(string $v): string
    {
        return htmlspecialchars($v, ENT_XML1);
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
