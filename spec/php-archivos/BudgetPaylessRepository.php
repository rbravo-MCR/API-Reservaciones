<?php

namespace App\Repositories;

use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Http\Client\RequestException;

class BudgetPaylessRepository
{
    protected string $base;
    protected string $username;
    protected string $password;
    protected string $clientId;
    protected string $clientSecret;
    protected int $ttl;

    public function __construct()
    {
        $cfg = config('guepardo');
        $this->base         = rtrim($cfg['base_url'], '/');
        $this->username     = $cfg['username'];
        $this->password     = $cfg['password'];
        $this->clientId     = $cfg['client_id'];
        $this->clientSecret = $cfg['client_secret'];
        $this->ttl          = $cfg['token_ttl_seconds'];
    }

    protected function token(): string
    {
        return Cache::remember('guepardo.token', $this->ttl, function () {
            $res = Http::acceptJson()
                ->withHeaders(['Content-Type' => 'application/json-patch+json'])
                ->post("{$this->base}/api/Authenticate/login", [
                    'username' => $this->username,
                    'password' => $this->password,
                ])
                ->throw()
                ->json();

            // Ajusta si el campo exacto del token difiere (ej. $res['token'] / $res['accessToken'])
            return $res['token'] ?? $res['accessToken'] ?? $res['jwt'] ?? throw new \RuntimeException('No token in response');
        });
    }

    protected function withAuth()
    {
        return Http::withToken($this->token());
    }

    protected function withCreds(array $params = []): array
    {
        return array_merge([
            'client_id'     => $this->clientId,
            'client_secret' => $this->clientSecret,
        ], $params);
    }

    protected function get(string $path, array $query = [])
    {
        try {
            return $this->withAuth()
                ->accept('text/plain')
                ->get("{$this->base}{$path}", $this->withCreds($query))
                ->throw()
                ->json();
        } catch (RequestException $e) {
            if ($e->response && $e->response->status() === 401) {
                Cache::forget('guepardo.token');
                return $this->withAuth()
                    ->accept('text/plain')
                    ->get("{$this->base}{$path}", $this->withCreds($query))
                    ->throw()
                    ->json();
            }
            throw $e;
        }
    }

    protected function post(string $path, array $query = [], $body = null)
    {
        try {
            $req = $this->withAuth()->accept('text/plain');

            if (!is_null($body)) {
                $req = $req->withHeaders(['Content-Type' => 'application/json-patch+json']);
                $res = $req->post("{$this->base}{$path}", $body);
            } else {
                $res = $req->post("{$this->base}{$path}", $this->withCreds($query));
            }

            // Cuando los params van en query:
            if (is_null($body)) {
                $res = $this->withAuth()
                    ->accept('text/plain')
                    ->post("{$this->base}{$path}?" . http_build_query($this->withCreds($query)));
            }

            $res->throw();
            return $res->json();
        } catch (RequestException $e) {
            if ($e->response && $e->response->status() === 401) {
                Cache::forget('guepardo.token');
                return $this->post($path, $query, $body);
            }
            throw $e;
        }
    }

    /*** ENDPOINTS ***/

    // 1) Locations (GET /v4/locations/carLocations)
    public function locations(string $locationsCode = '*', int $salesSource = -1)
    {
        return $this->get('/v4/locations/carLocations', [
            'locations_code' => $locationsCode,
            'sales_source'   => $salesSource,
        ]);
    }

    // 2) Rates (GET /v4/vehicles/rates)
    // Formato de fechas: "YYYY-MM-DD HH:mm" (ejemplo en doc)
    public function rates(array $params)
    {
        // $params: pickup_date, dropoff_date, pickup_location, dropoff_location, languaje (en|es), sales_source, currency (MXN|USD)
        return $this->get('/v4/vehicles/rates', $params);
    }

    // 3) Select Vehicle (POST /v4/vehicles/selectVehicle)
    public function selectVehicle(int $transactionId, string $vehicleClassCode)
    {
        return $this->post('/v4/vehicles/selectVehicle', [
            'transaction_id'    => $transactionId,
            'vehicle_class_code'=> $vehicleClassCode,
        ]);
    }

    // 4) Select Coverages (POST /v4/vehicles/selectCoverages)
    public function selectCoverages(int $transactionId, array $ratesSelected)
    {
        // $ratesSelected = [['code'=>'CDW','selected'=>true], ['code'=>'SLI','selected'=>true], ...]
        return $this->post('/v4/vehicles/selectCoverages', [
            'transaction_id' => $transactionId,
        ], [
            'ratesSelected' => $ratesSelected,
        ]);
    }

    // 5) Create Reservation (POST /v4/reservation/create)
    public function createReservation(array $payload)
    {
        // El body DEBE incluir transaction_id y datos del pasajero; vehicle_class_code, etc.
        return $this->post('/v4/reservation/create', [], $payload);
    }

    // 6) Cancel Reservation (GET /v4/reservation/cancel)
    public function cancelReservation(string $confirmationNumber)
    {
        return $this->get('/v4/reservation/cancel', [
            'reservation_number' => $confirmationNumber,
        ]);
    }

    // 7) View Reservation (GET /v4/reservation/view)
    public function viewReservation(string $confirmationNumber, string $lastName)
    {
        return $this->get('/v4/reservation/view', [
            'reservation_number' => $confirmationNumber,
            'last_name'          => $lastName,
        ]);
    }
}
