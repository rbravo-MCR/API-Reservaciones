<?php

declare(strict_types=1);

namespace App\Repositories;

use Carbon\Carbon;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class HertzArgentinaRepository{
    private const PROVIDER_ID = 128;

    private string $auth_endpoint;
    private string $endpoint; // base URL, termina con '/'
    private string $username;
    private string $password;
    private string $grant_type;
    private string $client_id;

    public function __construct()
    {
        $this->auth_endpoint = (string) config('hertzargentina.auth_url');
        $this->endpoint = (string) config('hertzargentina.base_url');
        $this->username = (string) config('hertzargentina.username');
        $this->password = (string) config('hertzargentina.password');
        $this->grant_type = (string) config('hertzargentina.grant_type');
        $this->client_id = (string) config('hertzargentina.client_id');
    }

    // ----------------------------- Auth -----------------------------
    private function getToken()
    {
        $res = Http::asForm()
        ->post($this->auth_endpoint, [
            'username'   => $this->username,
            'password'   => $this->password,
            'grant_type' => $this->grant_type,
            'client_id'  => $this->client_id,
        ]);
        if (!$res->successful()) {
            Log::warning('HertzAR rates non-success', ['status' => $res->status(), 'body' => $res->json() ?? $res->body()]);
            return ['status' => 'error', 'message' => 'API returned error', 'status_code' => $res->status()];
        }

        $json = $res->json();
        $token = $json['access_token'];
        return $token;
    }

    public function getAvailability($params){
        try {
            $token = $this->getToken();
            $res = Http::withHeaders([
                'Authorization' => 'Bearer ' . $token,
                'Accept' => 'application/json'
            ])->get($this->endpoint . "Availability", [
                "DeliveryLocation" => $params['pickupLocation'],
                "DropoffLocation" => $params['dropoffLocation'],
                "From" =>  $params['pickupDate'],
                "To" => $params['dropoffDate'],
                "IlimitedKm" => 'true'
            ]);
            if (!$res->successful()) {
                Log::warning('HertzAR rates non-success', ['status' => $res->status(), 'body' => $res->json() ?? $res->body()]);
                return ['status' => 'error', 'message' => 'API returned error', 'status_code' => $res->status()];
            }
            $json = $res->json();
            if (isset($json)) {
                return ['status' => 'success', 'availability_request' => $params, 'data' => $json];
            }
            return ['status' => 'error', 'message' => 'Unexpected response structure', 'details' => $json];
        }catch (\Throwable $e) {
            Log::error('MEX rates exception', ['error' => $e->getMessage()]);
            return ['status' => 'error', 'message' => 'Exception occurred'];
        }
    }

    public function calculateAge($birthDate)
    {
        // Convertir la cadena a formato Carbon
        $date = Carbon::createFromFormat('Y-m-d', $birthDate);
        // Calcular la edad en años
        return $date->age;
    }

    public function cancelBooking($booking){
        try {
            $token = $this->getToken();
            $bookingId = $booking;
            $res = Http::withHeaders([
                'Authorization' => 'Bearer ' . $token,
                'Accept' => 'application/json'
            ])->delete($this->endpoint . "Booking/".$bookingId);
            if (!$res->successful()) {
                Log::warning('HertzAR cancel booking', ['status' => $res->status(), 'body' => $res->json() ?? $res->body()]);
                return ['status' => 'error', 'message' => 'API returned error', 'status_code' => $res->status()];
            }
            $json = $res->json();
            if ($res->status() == "200") {
                return ['status' => 'success', 'booking_request' => $booking, 'data' => [
                    "status" => $res->status(),
                    "booking" => $bookingId . " has been canceled"
                ]];
            }
            return ['status' => 'error', 'message' => 'Unexpected response structure', 'details' => $json];
        }catch (\Throwable $e) {
            Log::error('HertzAR cancel booking exception', ['error' => $e->getMessage()]);
            return ['status' => 'error', 'message' => $e->getMessage()];
        }
    }

    public function specificBooking($booking){
        try {
            $token = $this->getToken();
            $bookingId = $booking;
            $res = Http::withHeaders([
                'Authorization' => 'Bearer ' . $token,
                'Accept' => 'application/json'
            ])->get($this->endpoint . "Booking/".$bookingId);
            if (!$res->successful()) {
                Log::warning('HertzAR booking info', ['status' => $res->status(), 'body' => $res->json() ?? $res->body()]);
                return ['status' => 'error', 'message' => 'API returned error', 'status_code' => $res->status()];
            }
            $json = $res->json();
            if(isset($json)){
                return ['status' => 'success', 'booking_request' => $booking, 'data' => $json];
            }
            return ['status' => 'error', 'message' => 'Unexpected response structure', 'details' => $json];
        }catch (\Throwable $e) {
            Log::error('HertzAR booking info exception', ['error' => $e->getMessage()]);
            return ['status' => 'error', 'message' => $e->getMessage()];
        }
    }

    public function createBooking($params){
        try {
            $token = $this->getToken();
            $years_old = $this->calculateAge($params['dob']);
            $requestBody = [
                'customer' => [
                    'firstName' => $params['name'],
                    'lastName' => $params['lastname'],
                    'name' => $params['driver_name'],
                    'emailAddress' => $params['driver_email'],
                    'age' => $years_old,
                    'driverLicenceNumber' => $params['license_nr'],
                    'driverLicenseExpiration' => $params['license_exp'],
                    'driverLicenceCountry' => $params['license_place'], 
                ],
                "model" => $params['model'],
                "fromDate" => $params['pu_date'],
                "toDate" => $params['do_date'],
                "deliveryPlace" => $params['deliveryPlace']
            ];
            $res = Http::withHeaders([
                'Authorization' => 'Bearer ' . $token,
                'Accept' => 'application/json'
            ])->post($this->endpoint . "Booking", $requestBody);
            if (!$res->successful()) {
                Log::warning('HertzAR create Booking', ['status' => $res->status(), 'body' => $res->json() ?? $res->body()]);
                return ['status' => 'error', 'message' => 'API returned error', 'status_code' => $res->status()];
            }
            $json = $res->json();
            if (isset($json)) {
                return ['status' => 'success', 'booking_request' => $params, 'data' => $json];
            }
            return ['status' => 'error', 'message' => 'Unexpected response structure', 'details' => $json];
        }catch (\Throwable $e) {
            Log::error('HertzAR create BookingException', ['error' => $e->getMessage()]);
            return ['status' => 'error', 'message' => $e->getMessage()];
        }
    }
}