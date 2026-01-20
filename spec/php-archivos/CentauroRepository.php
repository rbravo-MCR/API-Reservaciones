<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Carbon;

class CentauroRepository
{
    private string $baseUrl;
    private string $login;
    private string $password;
    private int $agency;

    public function __construct()
    {
        $cfg = config('centauro');
        $this->baseUrl = $cfg['base_url'];
        $this->login   = $cfg['login'];
        $this->password= $cfg['password'];
        $this->agency  = (int) $cfg['agency'];
    }

    private function auth(): array
    {
        return ['login' => $this->login, 'pwd' => $this->password, 'agency' => $this->agency];
    }

    private function parseXml(string $xml)
    {
        return simplexml_load_string($xml);
    }

    /** --------- Disponibilidad y tarifa (action=13) --------- */
    public function availability(string $fa, string $fr, string $fd, string $sr, string $sd, array $extras = []): \SimpleXMLElement
    {
        $params = array_merge($this->auth(), [
            'action' => 13, 'fa' => $fa, 'fr' => $fr, 'fd' => $fd, 'sr' => $sr, 'sd' => $sd,
        ]);
        if (!empty($extras)) $params['extras'] = implode(',', $extras);

        $resp = Http::timeout(25)->get($this->baseUrl, $params);
        if (!$resp->ok()) throw new \RuntimeException('HTTP '.$resp->status());
        return $this->parseXml($resp->body());
    }

    /** --------- Consulta de extras (action=14) --------- */
    public function checkExtras(string $fa, string $fr, string $fd, string $sr, string $sd, string $group, string $lang = 'EN'): \SimpleXMLElement
    {
        $params = array_merge($this->auth(), [
            'action' => 14, 'fa' => $fa, 'fr' => $fr, 'fd' => $fd, 'sr' => $sr, 'sd' => $sd, 'g' => $group, 'lang' => $lang,
        ]);
        $resp = Http::timeout(25)->get($this->baseUrl, $params);
        if (!$resp->ok()) throw new \RuntimeException('HTTP '.$resp->status());
        return $this->parseXml($resp->body());
    }

    /** --------- Insertar reserva (action=1) --------- */
    public function insertReservation(array $payload): \SimpleXMLElement
    {
        $xml = $this->buildReservationXml($payload, includeCreationDate: true);
        $params = array_merge($this->auth(), ['action' => 1, 'xml' => $xml]);

        // Usa POST con form-data para evitar problemas de longitud de URL
        $resp = Http::asForm()->timeout(30)->post($this->baseUrl, $params);
        if (!$resp->ok()) throw new \RuntimeException('HTTP '.$resp->status());
        return $this->parseXml($resp->body());
    }

    /** --------- Modificar reserva (action=2) --------- */
    public function modifyReservation(array $payload): \SimpleXMLElement
    {
        $xml = $this->buildReservationXml($payload, includeCreationDate: false);
        $params = array_merge($this->auth(), ['action' => 2, 'xml' => $xml]);

        $resp = Http::asForm()->timeout(30)->post($this->baseUrl, $params);
        if (!$resp->ok()) throw new \RuntimeException('HTTP '.$resp->status());
        return $this->parseXml($resp->body());
    }

    /** --------- Cancelar reserva (action=3) --------- */
    public function cancelReservation(array $payload): \SimpleXMLElement
    {
        // Debe incluir oficina de recogida correcta en el XML (pickup code) para cancelar
        $xml = $this->buildReservationXml($payload, includeCreationDate: false);
        $params = array_merge($this->auth(), ['action' => 3, 'xml' => $xml]);

        $resp = Http::asForm()->timeout(30)->post($this->baseUrl, $params);
        if (!$resp->ok()) throw new \RuntimeException('HTTP '.$resp->status());
        return $this->parseXml($resp->body());
    }

    /** Helper: formatear fechas a DD/MM/YYYY HH:MM:SS en UTC */
    public static function formatUtc(Carbon $dt): string
    {
        return $dt->clone()->utc()->format('d/m/Y H:i:s');
    }

    /** Crea el XML de reserva conforme al manual de Centauro */
    private function buildReservationXml(array $d, bool $includeCreationDate = true): string
    {
        $sx = new \SimpleXMLElement('<RESERVATION/>');
        $header = $sx->addChild('HEADER');

        // Agency/Salesman y voucher
        if (!empty($d['agency_id']))   $header->addChild('AGENCY_ID', $d['agency_id']);
        if (!empty($d['salesman_id'])) $header->addChild('SALESMAN_ID', $d['salesman_id']);
        $header->addChild('CODE', $d['code']); // voucher (máx 20)

        // Passenger
        $who = $header->addChild('WHO')->addChild('CONTACT_DATA');
        $who->addChild('NAME', $d['name']);
        $who->addChild('SURNAME', $d['surname']);

        // Offices
        $where = $header->addChild('WHERE');
        $where->addChild('PICKUP')->addChild('SERVICE_POINT_PICKUP')->addChild('CODE', $d['pickup_office']);
        $where->addChild('RETURN')->addChild('SERVICE_POINT_RETURN')->addChild('CODE', $d['dropoff_office']);

        // Dates
        $when = $header->addChild('WHEN');
        if ($includeCreationDate && !empty($d['creation_date'])) {
            $when->addChild('CREATION_DATE', $d['creation_date']);
        }
        $when->addChild('START_DATE', $d['start_date']);
        $when->addChild('END_DATE', $d['end_date']);

        // Flight (obligatorio en aeropuertos)
        $header->addChild('FLIGHT')->addChild('NUMBER', $d['flight_number'] ?? '');

        if (!empty($d['remarks'])) $header->addChild('REMARKS', $d['remarks']);

        // Car group
        $sx->addChild('CAR')->addChild('PROVIDER_CATEGORY', $d['group']);

        // Extras
        if (!empty($d['extras']) && is_array($d['extras'])) {
            foreach ($d['extras'] as $ex) {
                $acc = $sx->addChild('ACCESORIES');
                $acc->addChild('PROVIDER_CATEGORY', $ex['code']);
                if (array_key_exists('invoiceable', $ex)) {
                    $acc->addChild('INVOICEABLE', $ex['invoiceable'] ? 'TRUE' : 'FALSE');
                }
            }
        }

        // Precio neto
        if (isset($d['net'])) {
            $sx->addChild('TOTAL')->addChild('NET', $d['net']);
        }

        return $sx->asXML();
    }
}
