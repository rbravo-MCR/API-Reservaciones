<?php

namespace App\Repositories;

use Carbon\Carbon;
use GuzzleHttp\Client;
use GuzzleHttp\Exception\GuzzleException;
use Illuminate\Support\Facades\Log;

class LocalizaRepository
{
    protected string $endpoint;
    protected string $authEndpoint;
    protected string $echoToken;
    protected string $username;
    protected string $password;
    protected array $requestorIds;
    protected Client $client;

    public function __construct()
    {
        $config    = config('localiza');
        $env       = $config['env'] ?? 'qa';
        $envConfig = $config[$env] ?? [];

        // Endpoint OTA (VehAvailRate, etc.)
        $this->endpoint     = $envConfig['endpoint']      ?? '';
        // Endpoint de autorización (AutenticarAcessoExterno / VerificarStatusSessaoAcessoExterno)
        $this->authEndpoint = $envConfig['auth_endpoint'] ?? '';

        $this->echoToken    = $envConfig['echo_token']    ?? '';
        $this->username     = $envConfig['username']      ?? '';
        $this->password     = $envConfig['password']      ?? '';
        $this->requestorIds = $envConfig['requestor_ids'] ?? [];

        $this->client = new Client([
            'timeout' => 30,
        ]);
    }

    /**
     * Consulta disponibilidad y tarifas en Localiza (OTA_VehAvailRate).
     *
     * @param array $params
     *  - source_market: inbound_eu_latam|domestic|inbound_us_canada (default inbound_eu_latam)
     *  - pickup_location_code (string)
     *  - return_location_code (string|null)
     *  - pickup_datetime (string|Carbon)
     *  - return_datetime (string|Carbon)
     *  - veh_size (string|null)     // SIZ
     *  - veh_category (string|null) // VEC
     */
    public function getAvailability(array $params): array
    {
        $xmlRequest   = $this->buildVehAvailRateRequest($params);
        $soapEnvelope = $this->wrapSoapEnvelope($xmlRequest);

        try {
            $response = $this->client->post($this->endpoint, [
                'headers' => [
                    'Content-Type' => 'text/xml; charset=utf-8',
                    // SOAPAction según el WSDL de VehAvailRate, si lo tienes. Aquí lo dejamos genérico.
                    'SOAPAction'   => 'OTA_VehAvailRateRQ',
                ],
                // Si el endpoint OTA también exige HTTP auth, esto se mantiene.
                // Si no, puedes quitar 'auth'.
                'auth' => [$this->username, $this->password],
                'body' => $soapEnvelope,
            ]);

            $body = (string) $response->getBody();

            // Útil para depurar con Localiza si algo falla
            Log::info('LOCALIZA AVAIL REQUEST', ['xml' => $soapEnvelope]);
            Log::info('LOCALIZA AVAIL RESPONSE', ['xml' => $body]);

            return $this->parseVehAvailRateResponse($body);
        } catch (GuzzleException $e) {
            Log::error('LOCALIZA AVAIL ERROR', ['message' => $e->getMessage()]);

            return [
                'success' => false,
                'error'   => 'localiza_request_failed',
                'message' => $e->getMessage(),
            ];
        }
    }

    /**
     * Construye OTA_VehAvailRateRQ con EchoToken y POS/RequestorID.
     */
    protected function buildVehAvailRateRequest(array $params): string
    {
        $pickupLocationCode = $params['pickup_location_code'];
        $returnLocationCode = $params['return_location_code'] ?? $pickupLocationCode;

        $pickupDateTime = $this->formatOtaDateTime($params['pickup_datetime']);
        $returnDateTime = $this->formatOtaDateTime($params['return_datetime']);

        $vehPrefsXml = $this->buildVehPrefsXml($params);

        // Source market para elegir el RequestorID correcto
        $sourceMarket = $params['source_market'] ?? 'inbound_eu_latam';
        $requestorId  = $this->requestorIds[$sourceMarket] ?? reset($this->requestorIds) ?: '';

        $echoToken = htmlspecialchars($this->echoToken, ENT_QUOTES, 'UTF-8');

        return <<<XML
<OTA_VehAvailRateRQ EchoToken="{$echoToken}" Version="2.001" xmlns="http://www.opentravel.org/OTA/2003/05">
    <POS>
        <Source>
            <!-- Type=5 => Travel agency ID (RequestorID que te dio Localiza) -->
            <RequestorID Type="5" ID="{$requestorId}" />
        </Source>
    </POS>
    <VehAvailRQCore>
        <VehRentalCore PickUpDateTime="{$pickupDateTime}" ReturnDateTime="{$returnDateTime}">
            <PickUpLocation LocationCode="{$pickupLocationCode}" />
            <ReturnLocation LocationCode="{$returnLocationCode}" />
        </VehRentalCore>
        {$vehPrefsXml}
    </VehAvailRQCore>
</OTA_VehAvailRateRQ>
XML;
    }

    /**
     * VehPrefs opcionales (filtro por SIZ/VEC).
     */
    protected function buildVehPrefsXml(array $params): string
    {
        $size     = $params['veh_size'] ?? null;
        $category = $params['veh_category'] ?? null;

        if (!$size && !$category) {
            return '';
        }

        $sizeAttr = $size ? ' Size="' . htmlspecialchars($size, ENT_QUOTES, 'UTF-8') . '"' : '';
        $catAttr  = $category ? ' VehicleCategory="' . htmlspecialchars($category, ENT_QUOTES, 'UTF-8') . '"' : '';

        return <<<XML
<VehPrefs>
    <VehPref>
        <VehClass{$sizeAttr} />
        <VehType{$catAttr} />
    </VehPref>
</VehPrefs>
XML;
    }

    /**
     * SOAP 1.1 Envelope genérico para OTA.
     */
    protected function wrapSoapEnvelope(string $bodyXml): string
    {
        return <<<XML
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ota="http://www.opentravel.org/OTA/2003/05">
    <soapenv:Header/>
    <soapenv:Body>
        {$bodyXml}
    </soapenv:Body>
</soapenv:Envelope>
XML;
    }

    protected function formatOtaDateTime($value): string
    {
        if (!$value instanceof Carbon) {
            $value = Carbon::parse($value);
        }

        return $value->format('Y-m-d\TH:i:s');
    }

    /**
     * Parser sencillo del VehAvailRateRS → lo puedes adaptar a tu modelo de “CarOption”.
     */
    protected function parseVehAvailRateResponse(string $xml): array
    {
        $dom = new \DOMDocument();
        if (!@$dom->loadXML($xml)) {
            return [
                'success' => false,
                'error'   => 'invalid_xml',
                'raw_xml' => $xml,
            ];
        }

        $xpath = new \DOMXPath($dom);
        $xpath->registerNamespace('soap', 'http://schemas.xmlsoap.org/soap/envelope/');
        $xpath->registerNamespace('ota',  'http://www.opentravel.org/OTA/2003/05');

        $nodes = $xpath->query('//soap:Body/ota:OTA_VehAvailRateRS');

        if ($nodes->length === 0) {
            return [
                'success' => false,
                'error'   => 'invalid_response',
                'raw_xml' => $xml,
            ];
        }

        $responseNode  = $nodes->item(0);
        $vehAvailNodes = $xpath->query('.//ota:VehAvailRSCore/ota:VehVendorAvails/ota:VehAvails/ota:VehAvail', $responseNode);

        $result = [
            'success' => true,
            'quotes'  => [],
            'raw_xml' => $xml,
        ];

        /** @var \DOMElement $vehAvail */
        foreach ($vehAvailNodes as $vehAvail) {
            $status      = $vehAvail->getAttribute('Status');
            $vehicleNode = $xpath->query('.//ota:Vehicle', $vehAvail)->item(0);
            $vehicle     = null;

            if ($vehicleNode) {
                $vehicle = [
                    'code'             => $vehicleNode->getAttribute('Code'),
                    'description'      => $vehicleNode->getAttribute('Description'),
                    'air_conditioned'  => $vehicleNode->getAttribute('AirConditionInd') === 'true',
                    'baggage_quantity' => $vehicleNode->getAttribute('BaggageQuantity'),
                    'passenger_qty'    => $vehicleNode->getAttribute('PassengerQuantity'),
                ];
            }

            $totalChargeNode = $xpath->query('.//ota:TotalCharge', $vehAvail)->item(0);
            $totalCharge     = null;

            if ($totalChargeNode) {
                $totalCharge = [
                    'rate_total_amount'      => $totalChargeNode->getAttribute('RateTotalAmount'),
                    'estimated_total_amount' => $totalChargeNode->getAttribute('EstimatedTotalAmount'),
                    'currency_code'          => $totalChargeNode->getAttribute('CurrencyCode'),
                ];
            }

            $result['quotes'][] = [
                'status'      => $status,
                'vehicle'     => $vehicle,
                'totalCharge' => $totalCharge,
            ];
        }

        return $result;
    }

    /**
     * Llama a Autorizacao.svc → AutenticarAcessoExterno
     * para verificar el tokenAplicacao (echoToken) y obtener IdSessao/TokenAplicacao.
     *
     * OJO: Esto NO genera un token nuevo; solo valida el que ya tienes.
     */
    public function requestAuthInfo(): array
    {
        if (empty($this->authEndpoint)) {
            return [
                'success' => false,
                'error'   => 'auth_endpoint_not_configured',
                'message' => 'No se ha configurado auth_endpoint en config/localiza.php',
            ];
        }

        $soapEnvelope = $this->buildAuthRequestEnvelope();

        try {
            $response = $this->client->post($this->authEndpoint, [
                'headers' => [
                    'Content-Type' => 'text/xml; charset=utf-8',
                    'SOAPAction'   => 'http://tempuri.org/IAutorizacao/AutenticarAcessoExterno',
                ],
                'auth' => [$this->username, $this->password],
                'body' => $soapEnvelope,
            ]);

            $body = (string) $response->getBody();

            Log::info('LOCALIZA AUTH REQUEST', ['xml' => $soapEnvelope]);
            Log::info('LOCALIZA AUTH RESPONSE', ['xml' => $body]);

            $parsed = $this->parseAuthResponse($body);

            return [
                'success' => $parsed !== null,
                'data'    => $parsed,
                'raw_xml' => $body,
            ];
        } catch (GuzzleException $e) {
            Log::error('LOCALIZA AUTH ERROR', ['message' => $e->getMessage()]);

            return [
                'success' => false,
                'error'   => 'localiza_auth_failed',
                'message' => $e->getMessage(),
            ];
        }
    }

    /**
     * SOAP para AutenticarAcessoExterno usando el echoToken como tokenAplicacao.
     */
    protected function buildAuthRequestEnvelope(): string
    {
        $tokenAplicacao = htmlspecialchars($this->echoToken, ENT_QUOTES, 'UTF-8');

        return <<<XML
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:tem="http://tempuri.org/">
    <soapenv:Header/>
    <soapenv:Body>
        <tem:AutenticarAcessoExterno>
            <tem:tokenAplicacao>{$tokenAplicacao}</tem:tokenAplicacao>
        </tem:AutenticarAcessoExterno>
    </soapenv:Body>
</soapenv:Envelope>
XML;
    }

    /**
     * Parsea la respuesta de AutenticarAcessoExterno para extraer IdSessao y TokenAplicacao.
     */
    protected function parseAuthResponse(string $xml): ?array
    {
        $dom = new \DOMDocument();
        if (!@$dom->loadXML($xml)) {
            return null;
        }

        $xpath = new \DOMXPath($dom);

        $xpath->registerNamespace('s',   'http://schemas.xmlsoap.org/soap/envelope/');
        $xpath->registerNamespace('t',   'http://tempuri.org/');
        $xpath->registerNamespace('ent', 'http://schemas.datacontract.org/2004/07/Autenticacao.Business.Entities');

        $resultNode = $xpath->query('//t:AutenticarAcessoExternoResult')->item(0);
        if (!$resultNode) {
            return null;
        }

        $idSessaoNode  = $xpath->query('ent:IdSessao', $resultNode)->item(0);
        $tokenNode     = $xpath->query('ent:TokenAplicacao', $resultNode)->item(0);

        return [
            'id_sessao'       => $idSessaoNode?->nodeValue,
            'token_aplicacao' => $tokenNode?->nodeValue,
        ];
    }
}
