<?php

namespace App\Repositories;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Cache;
use Illuminate\Database\QueryException;
use Carbon\Carbon;
use Log;
use DB;



class NationalGroupRepository
{
    private $user;
    private $password;
    private $endpoint;
    
    protected string $nationalUrl = 'http://45.33.33.253/api/v1';
    protected string $nationalToken = '9|JrqRPJXDy3OwutkjyMwIcIRizRoJxDPuz1bv7vK1c630999b';

    public function __construct()
    {
        $this->user = config('nationalgroup.national.user');
        $this->password = config('nationalgroup.national.password');       
    }


    public function setNationalGroupBookings($tokenId = "")
    {
        // 1) Trae las reservas candidatas a confirmar con National (ids de ejemplo 2 y 82)
        $reservations = DB::table('reservaciones')
            ->select([
                'reservaciones.id as reservation_id',
                'reservaciones.estado as status',                 // dpe/dpa -> para mapear a "N" (New)
                'reservaciones.fechaRecoger as pickup_date',      // YYYY-MM-DD
                'reservaciones.fechaDejar as dropoff_date',       // YYYY-MM-DD
                'reservaciones.horaRecoger as pickup_time',       // HH:MM:SS
                'reservaciones.horaDejar as dropoff_time',        // HH:MM:SS
                'reservaciones.no_vuelo as flight',
                'reservaciones.aereolinea as airline',
                'reservaciones.pagina as destination_code',
                'reservaciones.tarifaNeta as net_rate',

                'reservaciones.id_direccion as pickup_location_mcr_office_id',
                'reservaciones.id_direccion_dropoff as dropoff_location_mcr_office_id',

                'clientes.id as client_id',
                'clientes.nombre as name',
                'clientes.apellido as last_name',
                'clientes.correo as email',            // <-- verifica nombre exacto de columna
                'clientes.celular as phone',          // <-- o 'clientes.telefono' según tu esquema

                'pickup_location.code as pickup_location_code',     // código de locación del proveedor
                'dropoff_location.code as dropoff_location_code',

                'auto_clientes.categoria as category_name',
                'gps_categorias.id as category_id',
                'gps_categorias.cAcriss as acriss'
            ])
            ->join('clientes', 'clientes.id', 'reservaciones.id_cliente')
            ->join('provider_locations as pickup_location', 'pickup_location.mcr_office_id', 'reservaciones.id_direccion')
            ->join('provider_locations as dropoff_location', 'dropoff_location.mcr_office_id', 'reservaciones.id_direccion_dropoff')
            ->join('auto_clientes', 'auto_clientes.id_cliente', 'reservaciones.id_cliente')
            ->join('gps_categorias', 'gps_categorias.categoria', 'auto_clientes.categoria')
            ->whereIn('reservaciones.estado', ['dpe', 'dpa'])            // listas para confirmar
            ->where('reservaciones.no_confirmacion', '')                 // aún sin confirmación
            ->whereIn('reservaciones.proveedor', [2, 82])                // ¡ojo! whereIn (antes estaba where([...]))
            ->get();

        if ($reservations->isEmpty()) {
            Log::info('No hay reservaciones pendientes para enviar a National.');
            return;
        }

        foreach ($reservations as $r) {
            // 2) Combina fecha + hora y conviértelo a ISO 8601 en UTC (terminado en "Z")
            //    Ajusta el timezone si tu BD está en otra zona. MX por defecto:

            // $tz = 'America/Mexico_City';
            // $pickupAt = Carbon::parse("{$r->pickup_date} {$r->pickup_time}", $tz)->utc()->toIso8601String();
            // $dropoffAt = Carbon::parse("{$r->dropoff_date} {$r->dropoff_time}", $tz)->utc()->toIso8601String();

            // 3) Mapea a lo que pide el API.
            //    - season_id: si no lo tienes, mando "1" como placeholder.
            //    - office_*: uso los códigos del proveedor (provider_locations.code).
            //    - net_rate/sipp_code/group/age: placeholders si no hay dato.
            //    - status: API espera "N" (New). Si necesitas otro mapping, cámbialo aquí.

            $current_season = DB::table('gps_temporadas')
            ->select('gps_temporadas.id')
            ->whereRaw('? BETWEEN gps_temporadas.fhInicio AND gps_temporadas.fhFin', [$r->pickup_date])
            ->first();

            $payload = [
                'season_id'        => $current_season->id ?? 1,
                'destination_code' => $r->destination_code,
                'office_pickup'    => $r->pickup_location_code,
                'office_dropoff'   => $r->dropoff_location_code,
                'pickup_date'      => $r->pickup_date . 'T' . $r->pickup_time . ':00',
                'dropoff_date'     => $r->dropoff_date . 'T' . $r->dropoff_time . ':00',
                'net_rate'         => $r->net_rate,                          // TODO: reemplazar con tu tarifa neta real si la tienes
                'sipp_code'        => $r->acriss,                       // TODO: si la tienes; puedes derivarla de la categoría
                'group'            => $r->category_name,  // o el grupo/familia de auto requerido por el proveedor
                'name'             => $r->name,
                'last_name'        => $r->last_name,
                'email'            => 'reservaciones@mexicocarrental.com.mx',  // fallback
                'phone'            => '5541637157' ,
                'age'              => 0,                          // TODO: si la edad es requerida por National, coloca el valor real
                'status'           => 'N',
            ];

            // Elimina nulls/strings vacíos para no mandar basura
            $payload = array_filter($payload, fn($v) => !is_null($v) && $v !== '');

            $confirmation = "";
            try {
                $resp = Http::acceptJson()
                    ->withToken($this->nationalToken)
                    ->asJson()
                    ->retry(3, 500)   // 3 intentos, 500ms entre intentos
                    ->timeout(15)
                    ->post($this->nationalUrl . '/otas/reservaciones', $payload);

                if ($resp->successful()) {
                    $json = $resp->json();

                    // Si el API regresa un código de confirmación, guárdalo.
                    // Ajusta la clave según la respuesta real (p.ej. 'confirmation_code' o 'no_confirmacion')
                     $confirmation = data_get($json, 'data.id');


                    //  dd($confirmation);

                    $shouldUpdateDb = true;
                    if ($confirmation) {

                     if($shouldUpdateDb) {
                        try {
                                DB::connection()->getPdo(); // valida conexión
                                DB::table('reservaciones')
                                ->where('id', $r->reservation_id)
                                ->update(['no_confirmacion' => $confirmation]);
                            } catch (\Throwable $e) {
                                // log suave, pero no rompas la prueba de API
                                Log::warning('No se pudo actualizar DB: ' . $e->getMessage());
                            }
                        }
                    }

                    Log::info('Reserva enviada/confirmada con National', [
                        'reservation_id' => $r->reservation_id,
                        'payload'        => $payload,
                        'response'       => $json,
                    ]);
                } else {
                    Log::error('Fallo al enviar reserva a National', [
                        'reservation_id' => $r->reservation_id,
                        'status'         => $resp->status(),
                        'body'           => $resp->body(),
                        'payload'        => $payload,
                    ]);
                }
            } catch (\Throwable $e) {
                Log::error('Excepción al enviar reserva a National', [
                    'reservation_id' => $r->reservation_id,
                    'error'          => $e->getMessage(),
                ]);
            }
        }

        return $confirmation;
    }

        /**
     * Llama al endpoint y devuelve el array de oficinas SIN cache.
     */
    public function getOffices(): array
    {
        $officeUrl = $this->nationalUrl . '/ubicaciones/oficinas/web';
        
        $query = [
            'marca' => 'National'
        ];

        try {
            $response = Http::acceptJson()
                ->withToken($this->nationalToken)
                ->retry(3, 500)   // 3 intentos, 500ms entre intentos
                ->timeout(15)
                ->get($officeUrl, $query);

            if (!$response->successful()) {
                Log::error('Error al consultar oficinas', [
                    'status' => $response->status(),
                    'body'   => $response->body(),
                ]);
                throw new \RuntimeException('No se pudo obtener la lista de oficinas (HTTP ' . $response->status() . ').');
            }

            $json = $response->json();

            // Muchas APIs devuelven { data: [...] }
            $offices = data_get($json, 'data', $json);

            return is_array($offices) ? $offices : (array) $offices;
        } catch (\Throwable $e) {
            Log::error('Excepción al consultar oficinas', ['error' => $e->getMessage()]);
            throw new \RuntimeException('Falló la consulta de oficinas: ' . $e->getMessage());
        }
    }

    /**
     * Inserta una sola vez las oficinas en provider_locations (SIN cache).
     * - Inserta en bloques de 1000.
     * - Si lo corres 2 veces, duplicará registros (usa insertOrIgnore si quieres blindaje).
     *
     * @return int Total de filas insertadas
     */
    public function syncOfficesToDb(): int
    {
        $offices = $this->getOffices(); // ya trae el array que mostraste

        $now  = now();
        $rows = [];

        foreach ($offices as $o) {
            // Normalizaciones y fallbacks
            $code    = data_get($o, 'id'); // clave principal del proveedor
            $name    = data_get($o, 'nombre');

            // Si no hay code, no podemos insertarlo
            if (empty($code)) {
                continue;
            }

            $rows[] = [
                'fk_provider'   => 2,         // National
                'code'          => $code,
                'name'          => $name,
                'mcr_code'      => null,
                'mcr_office_id' => null,       // no viene en el payload actual
                'station_name'   => $name, 
                'location' => null
            ];
        }

        if (empty($rows)) {
            return 0;
        }

        // Evita duplicados por (code, provider_id) y actualiza campos si ya existen
        DB::beginTransaction();
        try {
            // Disponible en Laravel 8+: upsert
            DB::table('provider_locations')->upsert(
                $rows,
                ['fk_provider', 'code'],                 // índices únicos para detectar duplicado
                ['name', 'mcr_code', 'mcr_office_id', 'station_name', 'location'] // columnas a actualizar si ya existe
            );
            DB::commit();
        } catch (\Throwable $e) {
            DB::rollBack();
            Log::error('Error insertando/actualizando oficinas', ['error' => $e->getMessage()]);
            throw new \RuntimeException('No se pudo escribir la lista de oficinas: ' . $e->getMessage());
        }

        return count($rows);
    }

}