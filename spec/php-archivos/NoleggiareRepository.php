<?php

namespace App\Repositories;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;
use SimpleXMLElement;

class NoleggiareRepository
{
    private string $wsdl;
    private string $soapEndpoint;
    private string $user;
    private string $pass;
    private string $company;
    private string $target;
    private string $version;

    private string $restAuthUrl;
    private string $restBase;
    private string $restCompany;

    private int $timeout = 30;

    public function __construct()
    {
        $cfg                = config('noleggiare');
        $this->wsdl         = $cfg['wsdl'];
        $this->soapEndpoint = rtrim($this->wsdl, '?wsdl');
        $this->user         = $cfg['username'];
        $this->pass         = $cfg['password'];
        $this->company      = $cfg['company'];
        $this->target       = $cfg['target']  ?? 'Test';
        $this->version      = $cfg['version'] ?? '1.0';

        $this->restAuthUrl  = $cfg['rest']['auth_url'];
        $this->restBase     = rtrim($cfg['rest']['base'], '/');
        $this->restCompany  = $cfg['rest']['company'] ?? $this->company;

        $this->timeout      = $cfg['timeout'] ?? 30;
    }

    /* ===================== Helpers ===================== */

    public static function iso8601WithZone(string $dt): string
    {
        if (preg_match('/Z$/i', $dt) || preg_match('/[\+\-]\d{2}:?\d{2}$/', $dt)) {
            return $dt;
        }
        return $dt.'Z';
    }

    private function echoToken(): string
    {
        return (string) Str::uuid();
    }

    private function wrapEnvelope(string $innerXml): string
    {
        return <<<XML
        <?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:ns="http://www.opentravel.org/OTA/2003/05">
          <soapenv:Header/>
          <soapenv:Body>
            {$innerXml}
          </soapenv:Body>
        </soapenv:Envelope>
        XML;
    }

    private function posBlock(): string
    {
        $u = htmlspecialchars($this->user, ENT_XML1);
        $p = htmlspecialchars($this->pass, ENT_XML1);
        $c = htmlspecialchars($this->company, ENT_XML1);

        // Permite configurar atributos extra del RequestorID si el supplier los exige
        $cfgReq = config('noleggiare.requestor', []);
        $attrs = '';
        foreach (['Type','ID_Context'] as $k) {
            if (!empty($cfgReq[$k])) {
                $attrs .= ' '.$k.'="'.htmlspecialchars((string)$cfgReq[$k], ENT_XML1).'"';
            }
        }
              // 

        return <<<XML
        <ns:POS>
          <ns:Source>
            <ns:RequestorID ID="{$u}" MessagePassword="{$p}"{$attrs}>
                <ns:CompanyName>{$c}</ns:CompanyName>
            </ns:RequestorID>
          </ns:Source>
        </ns:POS>
        XML;
    }

    private function rootRqOpen(string $rqName, ?string $echoToken = null, ?string $timeStamp = null): string
    {
        $echoToken = $echoToken ?: $this->echoToken();
        $timeStamp = $timeStamp ?: gmdate('c');
        $ver = htmlspecialchars($this->version, ENT_XML1);
        $tgt = htmlspecialchars($this->target, ENT_XML1);

        return sprintf('<ns:%s Version="%s" Target="%s" TimeStamp="%s" EchoToken="%s">',
            $rqName, $ver, $tgt, $timeStamp, $echoToken
        );
    }

    private function rootRqClose(string $rqName): string
    {
        return sprintf('</ns:%s>', $rqName);
    }

    /** Pre-extrae Error OTA aún con XML truncado (antes de parsear) */
    private function preParseOtaError(string $raw): ?array
    {
        // Busca <Error ... ShortText="..." ...> y atributos Type/Code
        if (preg_match('/<Error\b([^>]*)>/i', $raw, $m)) {
            $attrs = $m[1];
            $out = [];
            foreach (['Type','Code','ShortText'] as $k) {
                if (preg_match('/\b'.preg_quote($k,'/').'\s*=\s*"([^"]*)"/i', $attrs, $mm)) {
                    $out[strtolower($k)] = html_entity_decode($mm[1]);
                }
            }
            return $out ?: null;
        }
        return null;
    }

    /** Sanitiza respuestas SOAP: BOM, basura antes del '<', control chars */
    private function sanitizeXml(string $xml): string
    {
        $xml = $xml ?? '';
        $xml = preg_replace('/^\xEF\xBB\xBF/', '', $xml) ?? '';
        $pos = strpos($xml, '<');
        if ($pos !== false && $pos > 0) {
            $xml = substr($xml, $pos);
        }
        $xml = preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/', '', $xml) ?? $xml;
        return trim($xml);
    }

    private function postSoap(string $xml, ?string $soapAction = null): SimpleXMLElement
{
    $soap12 = (bool) (config('noleggiare.soap12') ?? false);
    $headers = [
        'Accept' => 'application/soap+xml, text/xml, application/xml;q=0.9, */*;q=0.8',
        'Content-Type' => $soap12
            ? 'application/soap+xml; charset=utf-8' . ($soapAction ? '; action="'.$soapAction.'"' : '')
            : 'text/xml; charset=utf-8',
        // Fuerza respuesta sin compresión para evitar corrupción/truncamiento
        'Accept-Encoding' => 'identity',
    ];
    if (!$soap12 && $soapAction) {
        $headers['SOAPAction'] = $soapAction;
    }

    $attempts = 0;
    $maxAttempts = 3;
    $lastErrMsg = null;

    do {
        $attempts++;

        $resp = Http::withHeaders($headers)
            ->retry(3, 250, function ($e) {
                if (method_exists($e, 'getCode')) {
                    $code = (int) $e->getCode();
                    return $code === 429 || ($code >= 500 && $code < 600);
                }
                return false;
            }, throw: false)
            // Sube un poco el timeout por respuestas grandes
            ->timeout($this->timeout)
            ->withBody($xml, $headers['Content-Type'])
            ->post($this->soapEndpoint);

        if (!$resp->successful()) {
            throw new \RuntimeException("SOAP HTTP error {$resp->status()}: ".$resp->body());
        }

        $contentType = $resp->header('Content-Type') ?? '';
        $raw = $resp->body();

        // HTML o JSON inesperado
        $body = $this->sanitizeXml($raw);
        if (stripos($contentType, 'html') !== false || stripos($body, '<!DOCTYPE') !== false || stripos($body, '<html') !== false) {
            $snippet = substr($raw, 0, 800);
            throw new \RuntimeException("SOAP parse error: respuesta HTML (posible WAF/redirect). Content-Type={$contentType}. Snippet=\n".$snippet);
        }
        if (stripos($contentType, 'json') !== false || (strlen($body) && $body[0] === '{')) {
            $snippet = substr($raw, 0, 800);
            throw new \RuntimeException("SOAP parse error: respuesta JSON no esperada. Content-Type={$contentType}. Snippet=\n".$snippet);
        }

        // (Opcional) Normaliza a UTF-8 válido y filtra chars ilegales en XML 1.0
        $body = @iconv('UTF-8', 'UTF-8//IGNORE', $body) ?: $body;
        $body = preg_replace('/[^\x09\x0A\x0D\x20-\x{D7FF}\x{E000}-\x{FFFD}]/u', '', $body) ?? $body;

        // Heurística: debe tener Envelope completo
        $hasOpen  = (bool) preg_match('~<(/)?(?:[a-zA-Z]+:)?Envelope\b~', $body);
        $hasClose = (bool) preg_match('~</(?:[a-zA-Z]+:)?Envelope>~', $body);

        if (!$hasOpen || !$hasClose) {
            // Truncado o cortado por proxy. Si aún tenemos reintentos, continua.
            $len = strlen($body);
            $snippetStart = substr($body, 0, 600);
            $snippetEnd   = substr($body, max(0, $len - 600), 600);
            $lastErrMsg = "SOAP malformed (Envelope incompleto). len={$len}. start:\n{$snippetStart}\n...\nend:\n{$snippetEnd}";
            // Pequeña espera antes de reintentar
            usleep(200 * 1000);
            continue;
        }

        libxml_use_internal_errors(true);
        $sx = simplexml_load_string($body);
        if ($sx === false) {
            $errs = libxml_get_errors();
            $first = $errs ? (trim($errs[0]->message).' at line '.$errs[0]->line.' col '.$errs[0]->column) : 'unknown libxml error';

            // Si el Envelope está completo pero sigue fallando, no vale reintentar en loop infinito.
            $len = strlen($body);
            $snippet = substr($body, 0, 800);
            $lastErrMsg = "libxml: {$first}. len={$len}. Snippet=\n".$snippet;

            // Reintenta una vez más por si fue corrupción transitoria
            if ($attempts < $maxAttempts) {
                usleep(200 * 1000);
                continue;
            }

            throw new \RuntimeException("SOAP parse error: {$first}. Content-Type={$contentType}. Snippet=\n".$snippet);
        }

        $sx->registerXPathNamespace('soapenv', 'http://schemas.xmlsoap.org/soap/envelope/');
        $sx->registerXPathNamespace('ns', 'http://www.opentravel.org/OTA/2003/05');

        $this->assertNoFault($sx);
        return $sx;

    } while ($attempts < $maxAttempts);

    // Si salimos del loop, arroja el último error acumulado
    throw new \RuntimeException($lastErrMsg ?: 'SOAP parse error: documento truncado');
}

    // private function postSoap(string $xml, ?string $soapAction = null): SimpleXMLElement
    // {
    //     $soap12 = (bool) (config('noleggiare.soap12') ?? false);
    //     $headers = [ 'Accept' => 'application/soap+xml, text/xml, application/xml;q=0.9, */*;q=0.8' ];
    //     if ($soap12) {
    //         $ct = 'application/soap+xml; charset=utf-8';
    //         if ($soapAction) { $ct .= '; action="'.$soapAction.'"'; }
    //         $headers['Content-Type'] = $ct;
    //     } else {
    //         $headers['Content-Type'] = 'text/xml; charset=utf-8';
    //         if ($soapAction) { $headers['SOAPAction'] = $soapAction; }
    //     }

    //     $resp = Http::withHeaders($headers)
    //         ->retry(3, 250, function ($e) {
    //             if (method_exists($e, 'getCode')) {
    //                 $code = (int) $e->getCode();
    //                 return $code === 429 || ($code >= 500 && $code < 600);
    //             }
    //             return false;
    //         }, throw: false)
    //         ->timeout($this->timeout)
    //         ->withBody($xml, $headers['Content-Type'])
    //         ->post($this->soapEndpoint);

    //     if (!$resp->successful()) {
    //         throw new \RuntimeException("SOAP HTTP error {$resp->status()}: ".$resp->body());
    //     }

    //     $contentType = $resp->header('Content-Type') ?? '';
    //     $raw = $resp->body();

    //     // Si trae un Error OTA pero el XML está truncado, reporta igual
    //     if ($err = $this->preParseOtaError($raw)) {
    //         // Sigue intentando parsear; si falla, al menos tendrás este detalle
    //         $short = $err['shorttext'] ?? '';
    //         $type  = $err['type'] ?? '';
    //         $code  = $err['code'] ?? '';
    //         // Si ShortText parece de credenciales, lanza inmediatamente para ahorrar tiempo
    //         if ($short) {
    //             // No lanzamos todavía; lo dejamos como contexto si el parse funciona.
    //         }
    //     }

    //     $body = $this->sanitizeXml($raw);
    //     if (stripos($contentType, 'html') !== false || stripos($body, '<!DOCTYPE') !== false || stripos($body, '<html') !== false) {
    //         $snippet = substr($raw, 0, 600);
    //         throw new \RuntimeException("SOAP parse error: respuesta HTML (posible WAF/redirect). Content-Type={$contentType}. Snippet=\n".$snippet);
    //     }
    //     if (stripos($contentType, 'json') !== false || (strlen($body) && $body[0] === '{')) {
    //         $snippet = substr($raw, 0, 600);
    //         throw new \RuntimeException("SOAP parse error: respuesta JSON no esperada. Content-Type={$contentType}. Snippet=\n".$snippet);
    //     }

    //     libxml_use_internal_errors(true);
    //     $sx = simplexml_load_string($body);
    //     if (!$sx) {
    //         $errs = libxml_get_errors();
    //         $first = $errs ? (trim($errs[0]->message).' at line '.$errs[0]->line.' col '.$errs[0]->column) : 'unknown libxml error';
    //         $snippet = substr($raw, 0, 600);

    //         // Intenta dar más contexto si preParseOtaError encontró algo
    //         if ($err ?? null) {
    //             $short = $err['shorttext'] ?? '';
    //             $type  = $err['type'] ?? '';
    //             $code  = $err['code'] ?? '';
    //             throw new \RuntimeException("SOAP parse error: {$first}. OTA Error (pre-parse) Type={$type} Code={$code} ShortText='{$short}'. Content-Type={$contentType}. Snippet=\n".$snippet);
    //         }

    //         throw new \RuntimeException("SOAP parse error: {$first}. Content-Type={$contentType}. Snippet=\n".$snippet);
    //     }

    //     $sx->registerXPathNamespace('soapenv', 'http://schemas.xmlsoap.org/soap/envelope/');
    //     $sx->registerXPathNamespace('ns', 'http://www.opentravel.org/OTA/2003/05');

    //     $this->assertNoFault($sx);
    //     return $sx;
    // }

    private function assertNoFault(SimpleXMLElement $xml): void
    {
        $xml->registerXPathNamespace('soapenv', 'http://schemas.xmlsoap.org/soap/envelope/');
        $xml->registerXPathNamespace('ns', 'http://www.opentravel.org/OTA/2003/05');

        $faults = $xml->xpath('/soapenv:Envelope/soapenv:Body/soapenv:Fault');
        if ($faults && count($faults) > 0) {
            $fault = $faults[0];
            $code = (string) ($fault->faultcode ?? 'SOAP-FAULT');
            $msg  = (string) ($fault->faultstring ?? 'Unknown SOAP fault');
            throw new \RuntimeException("$code: $msg");
        }
        $errors = $xml->xpath('//ns:Errors/ns:Error');
        if ($errors && count($errors) > 0) {
            $first = $errors[0];
            $code = (string) ($first['Code'] ?? 'OTA-ERROR');
            $text = (string) ($first['ShortText'] ?? (string) $first);
            throw new \RuntimeException("OTA error $code: $text");
        }
    }

    /* ===================== Operaciones SOAP (mismo código que antes) ===================== */

    public function locations(): array
    {
        $inner = $this->rootRqOpen('OTA_VehLocSearchRQ')
               . $this->posBlock()
               . $this->rootRqClose('OTA_VehLocSearchRQ');

        $envelope = $this->wrapEnvelope($inner);
        $xml = $this->postSoap($envelope, 'OTA_VehLocSearchRQ');

        $locations = [];
        $nodes = $xml->xpath('//ns:OTA_VehLocSearchRS//ns:VehMatchedLocs/ns:VehMatchedLoc/ns:LocationDetails');
        foreach ($nodes ?? [] as $loc) {
            $locations[] = [
                'code' => (string) ($loc['Code'] ?? ''),
                'name' => (string) ($loc['Name'] ?? ''),
            ];
        }
        if (empty($locations)) {
            $nodes = $xml->xpath('//ns:OTA_VehLocSearchRS//ns:LocationDetails');
            foreach ($nodes ?? [] as $loc) {
                $locations[] = [
                    'code' => (string) ($loc['Code'] ?? ''),
                    'name' => (string) ($loc['Name'] ?? ''),
                ];
            }
        }
        return $locations;
    }

    public function availability(string $pickupCode, string $returnCode, string $pickupAt, string $returnAt, array $sippCodes = []): SimpleXMLElement
    {
        $pickupAt = self::iso8601WithZone($pickupAt);
        $returnAt = self::iso8601WithZone($returnAt);

        $vehPrefs = '';
        if (!empty($sippCodes)) {
            $prefs = '';
            foreach ($sippCodes as $code) {
                $prefs .= '<ns:VehPref Code="'.htmlspecialchars($code, ENT_XML1).'" />';
            }
            $vehPrefs = "<ns:VehPrefs>{$prefs}</ns:VehPrefs>";
        }

        $inner = $this->rootRqOpen('OTA_VehAvailRateRQ')
               . $this->posBlock()
               . <<<XML
          <ns:VehAvailRQCore>
            {$vehPrefs}
            <ns:VehRentalCore PickUpDateTime="{$pickupAt}" ReturnDateTime="{$returnAt}">
              <ns:PickUpLocation LocationCode="{$pickupCode}"/>
              <ns:ReturnLocation LocationCode="{$returnCode}"/>
            </ns:VehRentalCore>
          </ns:VehAvailRQCore>
        XML
               . $this->rootRqClose('OTA_VehAvailRateRQ');

        $envelope = $this->wrapEnvelope($inner);
        // dd($envelope);
        return $this->postSoap($envelope, 'OTA_VehAvailRateRQ');
    }

    public function reserve(array $data): SimpleXMLElement
    {
        $pickupAt = self::iso8601WithZone($data['pickupAt']);
        $returnAt = self::iso8601WithZone($data['returnAt']);

        $optArrival = '';
        if (!empty($data['flightNumber'])) {
            $dt = htmlspecialchars(self::iso8601WithZone($data['arrivalDateTime'] ?? $data['pickupAt']), ENT_XML1);
            $fn = htmlspecialchars($data['flightNumber'], ENT_XML1);
            $optArrival = '<ns:ArrivalDetails Number="'.$fn.'" ArrivalDateTime="'.$dt.'"/>';
        }
        $voucher = '';
        if (!empty($data['voucher'])) {
            $voucher = '<ns:Voucher SeriesCode="'.htmlspecialchars($data['voucher'], ENT_XML1).'"/>';
        }
        $telephone = '';
        if (!empty($data['telephone'])) {
            $tel = htmlspecialchars($data['telephone'], ENT_XML1);
            $telephone = '<ns:Telephone PhoneTechType="1" PhoneNumber="'.$tel.'"/>';
        }
        $email = '';
        if (!empty($data['email'])) {
            $em = htmlspecialchars($data['email'], ENT_XML1);
            $email = '<ns:Email>'.$em.'</ns:Email>';
        }

        $amount   = htmlspecialchars((string)($data['amount'] ?? ''), ENT_XML1);
        $currency = htmlspecialchars((string)($data['currency'] ?? ''), ENT_XML1);
        $paymentBlock = '';
        if ($amount !== '' && $currency !== '') {
            $paymentBlock = <<<XML
            <ns:RentalPaymentPref PaymentTransactionTypeCode="charge" PaymentType="---3BONIFICO---3" Type="payment">
              {$voucher}
              <ns:PaymentAmount Amount="{$amount}" CurrencyCode="{$currency}" />
            </ns:RentalPaymentPref>
            XML;
        }

        $inner = $this->rootRqOpen('OTA_VehResRQ')
               . $this->posBlock()
               . <<<XML
          <ns:VehResRQCore>
            <ns:VehRentalCore PickUpDateTime="{$pickupAt}" ReturnDateTime="{$returnAt}">
              <ns:PickUpLocation LocationCode="{$data['pickupCode']}"/>
              <ns:ReturnLocation LocationCode="{$data['returnCode']}"/>
            </ns:VehRentalCore>
            <ns:Customer>
              <ns:Primary>
                <ns:PersonName>
                  <ns:GivenName>{$data['givenName']}</ns:GivenName>
                  <ns:Surname>{$data['surname']}</ns:Surname>
                </ns:PersonName>
                {$telephone}
                {$email}
              </ns:Primary>
            </ns:Customer>
            <ns:VehPref Code="{$data['sippCode']}" />
          </ns:VehResRQCore>
          <ns:VehResRQInfo>
            {$optArrival}
            {$paymentBlock}
          </ns:VehResRQInfo>
        XML
               . $this->rootRqClose('OTA_VehResRQ');

        $envelope = $this->wrapEnvelope($inner);
        return $this->postSoap($envelope, 'OTA_VehResRQ');
    }

    public function retrieveReservation(string $instanceId, string $surname): SimpleXMLElement
    {
        $inner = $this->rootRqOpen('OTA_VehRetResRQ')
               . $this->posBlock()
               . <<<XML
          <ns:VehRetResRQCore>
            <ns:UniqueID Instance="{$instanceId}"><ns:CompanyName></ns:CompanyName></ns:UniqueID>
            <ns:PersonName><ns:Surname>{$surname}</ns:Surname></ns:PersonName>
          </ns:VehRetResRQCore>
        XML
               . $this->rootRqClose('OTA_VehRetResRQ');

        $envelope = $this->wrapEnvelope($inner);
        return $this->postSoap($envelope, 'OTA_VehRetResRQ');
    }

    public function cancel(array $args): SimpleXMLElement
    {
        $unique = !empty($args['instance'])
            ? '<ns:UniqueID Instance="'.htmlspecialchars($args['instance'], ENT_XML1).'" />'
            : '<ns:UniqueID ID="'.htmlspecialchars($args['id'] ?? '', ENT_XML1).'" />';

        $inner = $this->rootRqOpen('OTA_VehCancelRQ')
               . $this->posBlock()
               . <<<XML
          <ns:VehCancelRQCore CancelType="Book">
            {$unique}
          </ns:VehCancelRQCore>
        XML
               . $this->rootRqClose('OTA_VehCancelRQ');

        $envelope = $this->wrapEnvelope($inner);
        return $this->postSoap($envelope, 'OTA_VehCancelRQ');
    }

    /* ===================== REST ===================== */

    public function restAuthenticate(): string
    {
        $payload = [
            'username'    => $this->user,
            'password'    => $this->pass,
            'companyCode' => $this->restCompany,
        ];

        $resp = Http::asJson()
            ->retry(3, 250)
            ->timeout($this->timeout)
            ->post($this->restAuthUrl, $payload);

        if (!$resp->successful()) {
            throw new \RuntimeException("REST auth error {$resp->status()}: ".$resp->body());
        }

        $json = $resp->json();
        foreach (['token','access_token','jwt','bearerToken'] as $k) {
            if (!empty($json[$k])) {
                return (string) $json[$k];
            }
        }
        throw new \RuntimeException('REST auth: no se encontró token en la respuesta');
    }

    public function getLocationTimetable(string $locationCode, string $dateYmd): array
    {
        $token = $this->restAuthenticate();

        $resp = Http::withToken($token)
            ->retry(3, 250)
            ->timeout($this->timeout)
            ->get($this->restBase.'/locations/'.$locationCode.'/timetable', [ 'date' => $dateYmd ]);

        if ($resp->status() === 401 || $resp->status() === 403) {
            $token = $this->restAuthenticate();
            $resp = Http::withToken($token)
                ->retry(2, 300)
                ->timeout($this->timeout)
                ->get($this->restBase.'/locations/'.$locationCode.'/timetable', [ 'date' => $dateYmd ]);
        }

        if (!$resp->successful()) {
            throw new \RuntimeException("REST timetable error {$resp->status()}: ".$resp->body());
        }

        $data = $resp->json();
        return is_array($data) ? $data : [];
    }
}
