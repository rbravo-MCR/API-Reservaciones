<?php declare(strict_types=1);

namespace App\Repositories;

use Illuminate\Support\Str;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Cache;
use Carbon\Carbon;
use Illuminate\Support\Collection;
use Utilities;
use Session;

final class AvailabilityRepositoryv2
{
    private const MODELS_CACHE_KEY  = 'mcr.models.by_category.v1';
    private const MODELS_CACHE_TTL  = 600; // 10 min
    private const TZ_DEFAULT        = 'America/Merida';

    /** Mapas a config/providers.php en prod */
    private const PROVIDER_GROUPS = [
        'europcar_group' => [1, 93, 109],
        'america_group'  => [32],
        'infinity_group' => [106],
        'mex_group'      => [28],
        'niza_cars'      => [126]
    ];

    /** Bandas de descuento por días (límite superior => descuento [0..1]) */
    private const DISCOUNT_BANDS = [
        1   => 0.60, // 1 día
        5   => 0.65, // 2-3
        // 13  => 0.70, // 4-13
        PHP_INT_MAX => 0.70, // 14+
    ];

    public function __construct(
        private EuropcarGroupRepository $europcarGroupRp,
        private MexGroupRepository $mexGroupRp,
        private AmericaGroupRepository $americaGroupRp,
        private InfinityGroupRepository $infinityGroupRp,
        private NizaCarsRepository $nizaGroupRp,
    ) {}

    /** @param array $searchParams esperado: pickup_zone_id, dropoff_zone_id, pickup_date, pickup_time, dropoff_date, dropoff_time */
    public function getQuotationv2(array $searchParams): array
    {
        $this->validateInput($searchParams);

        // 0) Destino (PAP) y TZ
        $destinations = $this->getDestinationsByZoneIds(
            (int)$searchParams['pickup_zone_id'],
            (int)$searchParams['dropoff_zone_id']
        );

        $pickupDestination  = (object) $destinations['pickup'];
        $dropoffDestination = (object) $destinations['dropoff'];

        if (!$pickupDestination || !$dropoffDestination) {
            throw new \DomainException('No se encontró destino para la zona de pickup.');
        }

        // Set Currency global
        // Utilities::setCurrency($pickupDestination->country_name);

        $tz = self::TZ_DEFAULT; // opcional: resolver por destino
        $pickupAt  = Carbon::createFromFormat('Y-m-d H:i', "{$searchParams['pickup_date']} {$searchParams['pickup_time']}", $tz);
        $dropoffAt = Carbon::createFromFormat('Y-m-d H:i', "{$searchParams['dropoff_date']} {$searchParams['dropoff_time']}", $tz);
        if ($dropoffAt->lessThanOrEqualTo($pickupAt)) {
            throw new \DomainException('La fecha/hora de dropoff debe ser posterior al pickup.');
        }

        // 1) Derivados para cotización
        $searchParams['IATA']  = $pickupDestination->destination_code;
        $searchParams['pickup_name'] =  $pickupDestination->zone . ', ' . $pickupDestination->city_name . ', ' . $pickupDestination->country_name;
        $searchParams['dropoff_name'] = $dropoffDestination->zone . ', ' . $dropoffDestination->city_name . ', ' . $dropoffDestination->country_name;
        $searchParams['destination_id']   = (int)$pickupDestination->destination_id;
        $searchParams['dropoff_destination_id'] = (int) $dropoffDestination->destination_id;
        // Si hay dropoff distinto, en buildProviderSearchParams se ajusta para cada proveedor
        $searchParams['pickup_human_date']  = $pickupAt->toFormattedDateString();
        $searchParams['dropoff_human_date'] = $dropoffAt->toFormattedDateString();

        // 2) Flota por oficinas
        $fleet = $this->getFleetByOffices($searchParams, $tz);

        $currency = 'MXN';
        $rate = 1.0;

        if($pickupDestination->country_name != 'México') {
            $currency = $pickupDestination->default_currency;
            $rate = 1.0; // las tarifas se quedan en su moneda original.
            // $rate = $pickupDestination->default_currency_exchange;
        }

        Session::put('currency', $currency);


        // 3) Adaptar (moneda/atributos extra) —> todo en arrays, sin formateo string
        $adaptedResult = $this->adaptVehiclesv2($fleet, [
            'currency' => $currency,       // cámbialo según tu lógica real
            'rate'     => $rate,         // rate=1 para MXN; si USD, pásalo aquí
            'tz'       => $tz,
            'isPlatinum' => (auth()->check() ? (bool)(auth()->user()->isPlatinum ?? false) : false),
            'zero_deductible' => $searchParams['zero_deductible'] ?? false,
        ]);

        // 4) Guardado de cotización (asumo que retorna ['fleet'=>[], ...])
        $quotation = $this->storeQuotation($searchParams, $adaptedResult);

        // 5) Filtros
        $filters = \Utilities::getFiltersFleet($quotation['fleet']);
        $quotation['fleet']   = $filters['fleet'];
        $quotation['filters'] = $filters['filters'];

        return $quotation;
    }

    /** Núcleo de disponibilidad */
    private function getFleetByOffices(array $searchParams, string $tz): array
    {
        // 1) Oficinas por zonas (usa zone_id explícito)
        $availableOffices = $this->getAvailableOffices($searchParams);

        // 2) Etiquetas pickup/dropoff
        $availableOffices = $this->labelPickupDropoff($availableOffices, $searchParams);

        // 3) Si zonas distintas, solo proveedores con ambas
        if ((int)$searchParams['pickup_zone_id'] !== (int)$searchParams['dropoff_zone_id']) {
            $availableOffices = $this->filterProvidersWithBoth(
                $availableOffices,
                (int)$searchParams['destination_id'],
                (int)$searchParams['dropoff_destination_id']
            );
        }

        // 4-5) Proveedores con API y sus códigos
        [$apiProviders, $providerLocations] = $this->loadProviderLocations($availableOffices);

        // 6) Params por proveedor (code si API; si no, mcr_office_id)
        $providerSearchParams = $this->buildProviderSearchParams($availableOffices, $providerLocations, $searchParams);

        // 7-8) Grupos a ejecutar
        [$providerGroups, $groupsToExecute] = $this->detectGroupsToExecute($apiProviders);


        $mergedFleet = [];

        if($searchParams['zero_deductible']) {
            if($searchParams['destination_id'] == $searchParams['dropoff_destination_id']){

                $mergedFleet = array_merge($mergedFleet, $this->mergeNonApiResults($searchParams));
                $mergedFleet = $this->getZeroDeductibleRates($mergedFleet);
            }
        } else {
             // 9) Ejecutar loaders (con logs/try-catch) y normalizar
            $mergedFleet = $this->executeGroupLoaders($groupsToExecute, $providerGroups, $providerSearchParams);

            // $mergedFleet = [];
            if($searchParams['destination_id'] == $searchParams['dropoff_destination_id']){
                // 10) Agregar flota de proveedores sin API (si mismo destino)
                $mergedFleet = array_merge($mergedFleet, $this->mergeNonApiResults($searchParams));
            }

            // 10.5) Filtrado por condición de tarjeta (si aplica)
            if($searchParams['car_warranty'] == 'debit_card'){
                $mergedFleet = $this->filterByDebitCard($mergedFleet);
            }
        }

        // 11) Ganador por categoría (desempate: has_api)
        $winnersByCategory = $this->pickWinnersByCategory($mergedFleet, $availableOffices);

        // 12) Clonar ganador sobre catálogo de modelos
        $finalClonedFleet = array_values($this->cloneWinnersOverModels($winnersByCategory));

        // 13-15) PAPs por fecha/destino y ajuste de tarifas
        $paps = $this->getPapByPickupDate($searchParams['pickup_date'], (int)$searchParams['destination_id']);
        $finalClonedFleet = $this->adjustFleetWithPaps($finalClonedFleet, $paps, self::DISCOUNT_BANDS, 0.70);

        $finalClonedFleet = collect($finalClonedFleet)
        ->sortBy(fn ($item) => (float)($item['publicRateAmount'] ?? INF))
        ->values()
        ->all();

        return $finalClonedFleet;
    }

    private function filterByDebitCard(array $finalClonedFleet): array
    {
        $providersWhoAcceptDebit = DB::table('debit_card_conditions')
            ->select(['id_provider as provider_id', DB::raw('ifnull(categories, "") as categories'), 'accepts_downtown', 'increment_amount'])
            ->join('proveedores', 'proveedores.id', '=', 'debit_card_conditions.id_provider')
            ->where('debit_card_conditions.status', 1)
            ->where('proveedores.estado', 'Activo')
            ->get();

            // 1) Mapa de proveedores que aceptan débito -> categorías permitidas
            $providersMap = $providersWhoAcceptDebit
                ->mapWithKeys(function ($row) {
                    $cats = collect(explode(',', $row->categories ?? ''))
                        ->map(fn ($c) => trim($c))
                        ->filter() // quita vacíos
                        ->values()
                        ->all();

                    return [
                        $row->provider_id => [
                            'increment_amount' => (float)($row->increment_amount ?? 0.0),
                            'categories' => $cats,                       // [] => todas
                            'accepts_downtown' => (int)$row->accepts_downtown === 1,
                        ],
                    ];
                })
                ->toArray();

            // 2) Filtrar la flota por proveedor y categoría
            $filteredFleet = collect($finalClonedFleet)->filter(function ($car) use ($providersMap) {
                // Ajusta las llaves según tu estructura exacta
                $providerId = data_get($car, 'providerId') ?? data_get($car, 'provider_id');
                if (!$providerId || !isset($providersMap[$providerId])) {
                    return false; // proveedor no acepta débito
                }

                $car['netRate'] = $car['netRate'] + $providersMap[$providerId]['increment_amount'] ?? 0;

                $allowedCats = $providersMap[$providerId]['categories']; // [] => todas
                if (empty($allowedCats)) {
                    return true; // todas las categorías permitidas
                }

                $carCat = data_get($car, 'vehicleCategory') ?? data_get($car, 'category');
                return $carCat && in_array($carCat, $allowedCats, true);
            })->values();

            // (opcional) Si también quieres forzar que acepte “downtown”
            /*
            $isDowntown = ($searchParams['pickup_area'] ?? null) === 'downtown';
            if ($isDowntown) {
                $filteredFleet = $filteredFleet->filter(function ($car) use ($providersMap) {
                    $providerId = data_get($car, 'providerId') ?? data_get($car, 'provider_id');
                    return $providerId && !empty($providersMap[$providerId]['accepts_downtown']);
                })->values();
            }
            */

        return $filteredFleet->toArray();
    }

    /* ========================= Helpers ========================= */

    private function validateInput(array $p): void
    {
        foreach (['pickup_zone_id','dropoff_zone_id','pickup_date','pickup_time','dropoff_date','dropoff_time', 'car_warranty', 'zero_deductible'] as $k) {
            if (!array_key_exists($k, $p)) throw new \InvalidArgumentException("Falta parámetro requerido: {$k}");
        }
    }

    /** Paso 1 */
    private function getAvailableOffices(array $p): \Illuminate\Support\Collection
    {
        return DB::table('datosDirectorio')
            ->select([
                'proveedores.id as provider_id',
                'proveedores.nombre as provider_name',
                'datosDirectorio.id as mcr_office_id',
                'datosDirectorio.idDirectorio as destination_id',
                'datosDirectorio.mexicocarrental_zone_id',
                'proveedores.has_api',
                'proveedores.one_way'
            ])
            ->join('proveedores', 'proveedores.id', '=', 'datosDirectorio.agencia')
            ->where('proveedores.estado', 'Activo')
            ->where('datosDirectorio.estado', 1)
            ->whereIn('mexicocarrental_zone_id', [(int)$p['pickup_zone_id'], (int)$p['dropoff_zone_id']])
            ->get();
    }

    /** Paso 2 */
    private function labelPickupDropoff(\Illuminate\Support\Collection $offices, array $p): \Illuminate\Support\Collection
    {
        $pickup  = (int)$p['pickup_zone_id'];
        $dropoff = (int)$p['dropoff_zone_id'];
        return $offices->transform(function ($o) use ($pickup, $dropoff) {
            $o->type = $o->mexicocarrental_zone_id == $pickup ? 'pickup'
                     : ($o->mexicocarrental_zone_id == $dropoff ? 'dropoff' : null);
            return $o;
        });
    }

    /** Paso 3 */
    // private function filterProvidersWithBoth(\Illuminate\Support\Collection $offices): \Illuminate\Support\Collection
    // {
    //     $validProviderIds = $offices->groupBy('provider_id')->filter(function ($ofs) {
    //         $types = $ofs->pluck('type')->unique();
    //         return $types->contains('pickup') && $types->contains('dropoff');
    //     })->keys();

    //     return $offices->whereIn('provider_id', $validProviderIds)->values();
    // }

    private function filterProvidersWithBoth(
        Collection $offices,
        int $pickupDestinationId,
        int $dropoffDestinationId
    ): Collection {

        // ===== Caso 1: MISMO destino → el proveedor debe tener pickup y dropoff en ese destino
        if ($pickupDestinationId === $dropoffDestinationId) {
            // Solo miramos ese destino
            $validProviders = $offices
                ->where('destination_id', $pickupDestinationId)
                ->groupBy('provider_id')
                ->filter(function ($ofs) {
                    $types = $ofs->pluck('type')->unique();
                    return $types->contains('pickup') && $types->contains('dropoff');
                })
                ->keys(); // provider_id

            // Devolvemos las oficinas de ese destino y de esos proveedores
            return $offices->filter(function ($o) use ($validProviders, $pickupDestinationId) {
                return (int)$o->destination_id === $pickupDestinationId
                    && $validProviders->contains($o->provider_id);
            })->values();
        }

        // ===== Caso 2: DESTINOS DISTINTOS → has_api = true y cobertura en cada destino correspondiente
        $providersWithPickup = $offices
            ->where('destination_id', $pickupDestinationId)
            ->where('type', 'pickup')
            ->pluck('provider_id')
            ->unique();

        $providersWithDropoff = $offices
            ->where('destination_id', $dropoffDestinationId)
            ->where('type', 'dropoff')
            ->pluck('provider_id')
            ->unique();

        $providersWithApi = $offices
            // ->filter(fn ($o) => (bool) data_get($o, 'has_api', data_get($o, 'provider.has_api', false)))
             ->filter(function ($o) {
                $hasApi  = (bool) data_get($o, 'has_api', data_get($o, 'provider.has_api', false));
                $oneWay  = (bool) data_get($o, 'one_way', data_get($o, 'provider.one_way', false));
                return $hasApi && $oneWay;
            })
            ->pluck('provider_id')
            ->unique();

        $validProviders = $providersWithPickup
            ->intersect($providersWithDropoff)
            ->intersect($providersWithApi)
            ->values();

        // Devolvemos solo las oficinas útiles al tramo:
        // - pickup en destino de pickup
        // - dropoff en destino de dropoff
        return $offices->filter(function ($o) use ($validProviders, $pickupDestinationId, $dropoffDestinationId) {
            if (!$validProviders->contains($o->provider_id)) {
                return false;
            }
            return ((int)$o->destination_id === $pickupDestinationId && $o->type === 'pickup')
                || ((int)$o->destination_id === $dropoffDestinationId && $o->type === 'dropoff');
        })->values();
    }

    /** Pasos 4 y 5 */
    private function loadProviderLocations(\Illuminate\Support\Collection $offices): array
    {
        $apiProviders = $offices->filter(fn($o) => (int)$o->has_api === 1);
        $apiOfficeIds = $apiProviders->pluck('mcr_office_id')->unique()->all();

        $providerLocations = collect();
        if ($apiOfficeIds) {
            $providerLocations = DB::table('provider_locations')
                ->whereIn('mcr_office_id', $apiOfficeIds)
                ->get();
        }
        return [$apiProviders, $providerLocations];
    }

    /** Paso 6 */
    private function buildProviderSearchParams(\Illuminate\Support\Collection $offices, \Illuminate\Support\Collection $providerLocations, array $p): array
    {
        $params = [];
        $std = $p;
        $std['pickupDate']  = $p['pickup_date'];
        $std['dropoffDate'] = $p['dropoff_date'];
        $std['pickupTime']  = $p['pickup_time'];
        $std['dropoffTime'] = $p['dropoff_time'];

        $offices->groupBy('provider_id')->each(function ($ofs, $providerId) use (&$params, $std, $providerLocations) {
            $pickup  = $ofs->firstWhere('type', 'pickup');
            $dropoff = $ofs->firstWhere('type', 'dropoff') ?? $pickup;
            if (!$pickup) return;

            $hasApi = (int)($ofs->first()->has_api ?? 0) === 1;
            if ($hasApi) {
                $pickupCode  = $providerLocations->firstWhere('mcr_office_id', $pickup->mcr_office_id)?->code;
                $dropoffCode = $providerLocations->firstWhere('mcr_office_id', $dropoff->mcr_office_id)?->code ?? $pickupCode;
                if ($pickupCode && $dropoffCode) {
                    $params[$providerId] = $std + [
                        'pickupLocation'  => $pickupCode,
                        'pickupOfficeId'  => $pickup->mcr_office_id,
                        'dropoffOfficeId' => $dropoff->mcr_office_id,
                        'dropoffLocation' => $dropoffCode,
                    ];
                } else {
                    Log::warning('provider_location_code_missing', ['provider' => $providerId, 'pickup' => $pickup->mcr_office_id, 'dropoff' => $dropoff->mcr_office_id]);
                }
            } else {
                $params[$providerId] = $std + [
                    'pickupLocation'  => $pickup->mcr_office_id,
                    'pickupOfficeId'  => $pickup->mcr_office_id,
                    'dropoffOfficeId' => $dropoff->mcr_office_id,
                    'dropoffLocation' => $dropoff->mcr_office_id,
                ];
            }
        });

        return $params;
    }

    /** Pasos 7 y 8 */
    private function detectGroupsToExecute(\Illuminate\Support\Collection $apiProviders): array
    {
        $present = $apiProviders->pluck('provider_id')->unique();
        $groups  = self::PROVIDER_GROUPS;
        $exec    = [];

        foreach ($groups as $key => $ids) {
            if ($present->intersect($ids)->isNotEmpty()) $exec[] = $key;
        }
        if (!$exec) Log::info('no_groups_to_execute');

        return [$groups, $exec];
    }

    /** Paso 10 (con logs/try-catch y normalización) */
    private function executeGroupLoaders(array $groupsToExecute, array $providerGroups, array $providerSearchParams): array
    {
        $merged = [];

        foreach ($groupsToExecute as $groupKey) {
            $providerId = collect($providerGroups[$groupKey])
                ->intersect(array_keys($providerSearchParams))
                ->first();

            if (!$providerId) continue;

            $params = $providerSearchParams[$providerId];
            $start  = microtime(true);

            try {
                $fleet = match ($groupKey) {
                    'europcar_group' => (app()->environment('production')) ? $this->europcarGroupRp->getAvailabilityForAllProviders($params): [],
                    'america_group'  => $this->americaGroupRp->getAvailability($params),
                    'infinity_group' => $this->infinityGroupRp->getAvailability($params),
                    'mex_group'      => $this->mexGroupRp->getAvailability($params),
                    'niza_cars'      => $this->nizaGroupRp->getAvailability($params),
                    default          => [],
                };

                if (!is_array($fleet)) $fleet = [];

                // Europcar puede regresar array de arrays
                if ($groupKey === 'europcar_group') {
                    foreach ($fleet as $providerFleet) {
                        $merged = array_merge($merged, $this->normalizeFleet($providerFleet));
                    }
                } else {
                    $merged = array_merge($merged, $this->normalizeFleet($fleet));
                }

                Log::info('loader_ok', [
                    'group'  => $groupKey,
                    'prov'   => $providerId,
                    'ms'     => (int)((microtime(true) - $start) * 1000),
                    'count'  => count($merged),
                ]);
            } catch (\Throwable $e) {
                Log::error('loader_fail', [
                    'group' => $groupKey,
                    'prov'  => $providerId,
                    'err'   => $e->getMessage(),
                ]);
                // Continuamos sin romper toda la cotización
            }
        }
        return $merged;
    }

    /** SP no-API => arrays (no objetos) */
    private function mergeNonApiResults(array $p): array
    {
        $rows = DB::select("
            CALL sp_get_non_api_providers_by_zones(:pickup_zone_id,:dropoff_zone_id,:pickup_datetime,:dropoff_datetime)
        ", [
            'pickup_zone_id'   => (int)$p['pickup_zone_id'],
            'dropoff_zone_id'  => (int)$p['dropoff_zone_id'],
            'pickup_datetime'  => "{$p['pickup_date']} {$p['pickup_time']}",
            'dropoff_datetime' => "{$p['dropoff_date']} {$p['dropoff_time']}",
        ]);

        // Solo activamos cero deducible si viene la llave y es true
        // Esto te cubre casos "1", "true", true, etc.
        $applyZeroDeductible = isset($p['zero_deductible'])
            && filter_var($p['zero_deductible'], FILTER_VALIDATE_BOOLEAN);

        $fleet = [];
        foreach ($rows as $car) {
            $fleet[] = [
                'providerId'        => (int)$car->provider_id,
                'providerName'      => (string)$car->provider_name,
                'vehicleCategory'   => (string)$car->category_name,
                'vehicleDescription'=> $car->vehicle_description ?? '',
                'vehicleAcriss'     => $car->vehicle_acriss ?? null,
                'vehicleName'       => (string)$car->vehicle_name,
                'vehicleType'       => $car->vehicle_type ?? null,
                'vehicleId'         => (int)$car->vehicle_id,
                'vehicleImage'      => (string)$car->vehicle_image,
                'pickupOfficeId'    => (int)$car->pickup_zone_id,
                'dropoffOfficeId'   => (int)$car->dropoff_zone_id,
                'totalDays'         => (int)$car->rent_days,
                'netRate'           => (float)$car->net_rate,
                'zeroDeductibleNetRate' => $applyZeroDeductible
                    ? (float)($car->zero_deductible_net_rate ?? 0)
                    : 0.0,
                'zeroDeductiblePublicRate' => $applyZeroDeductible
                ? (float)($car->zero_deductible_public_rate ?? 0)
                : 0.0,
                'source'            => 'non_api',
            ];
        }

        return $fleet;
    }

    private function normalizeFleet(array $fleet): array
    {
        return array_values(array_filter(array_map(function ($i) {
            $a = is_array($i) ? $i : (json_decode(json_encode($i), true) ?? []);
            if (!$a) return null;
            if (!isset($a['providerId']) && isset($a['provider_id'])) $a['providerId'] = (int)$a['provider_id'];
            if (isset($a['netRate'])) $a['netRate'] = (float)$a['netRate'];
            return $a;
        }, $fleet)));
    }

    /** Paso 11 */
    private function getComparableRate(array $item): float
    {
        $net = (float) ($item['netRate'] ?? 0);

        $zero = 0.0;
        if (isset($item['zeroDeductibleNetRate']) && (float)$item['zeroDeductibleNetRate'] > 0) {
            $zero = (float) $item['zeroDeductibleNetRate'];
        }

        return $net + $zero;
    }

    private function pickWinnersByCategory(array $mergedFleet, \Illuminate\Support\Collection $availableOffices): array
    {
        $provHasApi = $availableOffices->groupBy('provider_id')
            ->map(fn($ofs) => $ofs->contains(fn($o) => (int)$o->has_api === 1) ? 1 : 0);

        $byCat = collect($mergedFleet)->groupBy(fn($i) => $i['vehicleCategory'] ?? 'UNKNOWN');
        $winners = [];

        foreach ($byCat as $cat => $items) {
            // Solo items con netRate
            $items = $items->filter(fn($i) => isset($i['netRate']));
            if ($items->isEmpty()) continue;

            $byProv = $items->groupBy(fn($i) => $i['providerId'] ?? $i['provider_id'] ?? null)
                            ->filter(fn($_, $pid) => !is_null($pid));
            if ($byProv->isEmpty()) continue;

            $winningProviderId = null;
            $winningMinRate    = null;

            foreach ($byProv as $pid => $list) {
                // MIN por proveedor usando netRate + zeroDeductibleNetRate (>0) SOLO PARA COMPARAR
                $minRate = $list
                    ->map(fn($i) => $this->getComparableRate($i))
                    ->min();

                if (
                    $winningMinRate === null ||
                    $minRate < $winningMinRate ||
                    (
                        $minRate == $winningMinRate &&
                        ($provHasApi[$pid] ?? 0) > ($provHasApi[$winningProviderId] ?? 0)
                    )
                ) {
                    $winningMinRate    = $minRate;
                    $winningProviderId = (int) $pid;
                }
            }

            if ($winningProviderId !== null) {
                // Dentro del proveedor ganador, también usamos la tarifa "comparable" para elegir el auto,
                // pero el objeto que devolvemos sigue teniendo su netRate intacto.
                $winners[$cat] = $byProv[$winningProviderId]
                    ->sortBy(fn($i) => $this->getComparableRate($i))
                    ->first();
            }
        }

        return $winners;
    }

    /** Paso 12 */
    private function cloneWinnersOverModels(array $winnersByCategory): array
    {
        $models = $this->getModelsByCategory();
        $modelsByCat = collect($models)->groupBy('vehicleCategory');

        $out = [];
        foreach ($winnersByCategory as $cat => $winner) {
            $wArr = is_array($winner) ? $winner : (json_decode(json_encode($winner), true) ?? []);
            $list = $modelsByCat->get($cat, collect());
            if ($list->isEmpty()) { $out[] = $wArr; continue; }

            foreach ($list as $m) {
                $clone = $wArr;
                $clone['vehicleName']  = $m['vehicleName']  ?? ($wArr['vehicleName']  ?? null);
                $clone['vehicleImage'] = $m['vehicleImage'] ?? ($wArr['vehicleImage'] ?? null);
                $clone['vehicleId']    = $m['vehicleId']    ?? ($wArr['vehicleId']    ?? null);
                $out[] = $clone;
            }
        }
        return $out;
    }

    /** Cache correcto (sin forget interno) */
    private function getModelsByCategory(): array
    {
        return Cache::remember(self::MODELS_CACHE_KEY, self::MODELS_CACHE_TTL, function () {
            return DB::table('gps_autos_copy as a')
                ->join('gps_categorias as c', 'c.id', '=', 'a.id_gps_categorias')
                ->select(
                    'c.categoria as vehicleCategory',
                    'a.auto as vehicleName',
                    'a.camino as vehicleImage',
                    'a.id as vehicleId',
                )
                ->get()
                ->map(fn($r) => [
                    'vehicleCategory' => (string)$r->vehicleCategory,
                    'vehicleName'     => (string)$r->vehicleName,
                    'vehicleImage'    => (string)$r->vehicleImage,
                    'vehicleId'       => (int)$r->vehicleId,
                ])->toArray();
        });
    }

    public function getDestinationsByZoneIds(int $pickupZoneId, int $dropoffZoneId): array
    {
        $rows = DB::table('mexicocarrental_zones as z')
            ->join('directorio as d', 'd.id', '=', 'z.city_id')
            ->select(
                'z.id as zone_id',
                'd.country_name',
                'd.default_currency',
                'd.default_currency_exchange',
                'd.city_name',
                'z.city_id as destination_id',
                'd.clave as destination_code',
                'z.description as zone'
            )
            ->whereIn('z.id', [$pickupZoneId, $dropoffZoneId])
            ->get()
            ->keyBy('zone_id');

        if ($pickupZoneId === $dropoffZoneId) {
            $row = $rows->get($pickupZoneId);
            if (!$row) {
                throw new \DomainException('No se encontró destino para la zona especificada.');
            }
            // Clonar para evitar referencias compartidas si luego mutas el objeto
            $clone = (object) (array) $row;
            return ['pickup' => $row, 'dropoff' => $clone];
        }

        if (!$rows->has($pickupZoneId) || !$rows->has($dropoffZoneId)) {
            throw new \DomainException('No se encontraron ambos destinos para las zonas especificadas.');
        }

        return [
            'currency' => $rows->first()->default_currency,
            'pickup'  => $rows->get($pickupZoneId),
            'dropoff' => $rows->get($dropoffZoneId),
        ];
    }

    private function getZeroDeductibleRates($fleet)
    {
        $zeroDeductibleRates = [];
        foreach ($fleet as $vehicle) {
            if (isset($vehicle['zeroDeductibleNetRate']) && $vehicle['zeroDeductibleNetRate'] > 0) {
                // $vehicle->tarifaNeta = ;
                // $vehicle->tarifaPublica = 0;
                $zeroDeductibleRates[] = $vehicle;
            }
        }
        return $zeroDeductibleRates;
    }


    /** PAP por pickup_date/destino */
    private function getPapByPickupDate(string $pickupDate, int $destinationId): \Illuminate\Support\Collection
    {
        $paps = DB::table('gps_categorias')
            ->leftJoin('mym_pap', function($join) use ($destinationId) {
                $join->on('mym_pap.category_id', '=', 'gps_categorias.id')
                    ->where('mym_pap.destination_id', '=', $destinationId);
            })
            ->leftJoin('gps_temporadas', 'gps_temporadas.id', '=', 'mym_pap.season_id')
            ->whereRaw('? BETWEEN gps_temporadas.fhInicio AND gps_temporadas.fhFin', [$pickupDate])
            ->orderBy('gps_categorias.categoria')
            ->select('gps_categorias.categoria as category_name','gps_temporadas.id as season_id','mym_pap.pap', 'gps_categorias.pap_default')
            ->get();


        if ($paps->isEmpty()) {
            $destinationData = DB::table('directorio')
                ->select('country_name')
                ->where('id', $destinationId)
                ->first();

            // Normaliza para evitar problemas de mayúsculas/acentos
            $country = $destinationData->country_name ?? '';
            $countryNorm = Str::of($country)->lower()->replace('méxico', 'mexico');
            $factor = ($countryNorm !== 'mexico') ? 18 : 1;

            $paps = DB::table('gps_categorias')
                ->select('gps_categorias.categoria as category_name')
                ->selectRaw('COALESCE(gps_categorias.pap_default, 0) / ? as pap', [$factor])
                ->orderBy('gps_categorias.categoria')
                ->get();
        }

        return $paps;
    }

    /**
     * Ajuste de PAPs (sin formateo string; números en floats)
     * @param array $discountBands mapa de límite superior de días => descuento [0..1]
     */
    private function adjustFleetWithPaps(array $fleet, \Illuminate\Support\Collection $paps, array $discountBands, float $maxDiscount): array
    {

        // 1) Fallback global = primer pap > 0 respetando el orden de $paps
        $globalFallback = optional(
            $paps->first(fn ($row) => isset($row->pap) && (float)$row->pap > 0)
        )->pap;

        // Si no hubiera ningún > 0 en todo el dataset (caso extremo),
        // como último recurso toma el primer pap no null (puede ser 0.0).
        if ($globalFallback === null) {
            $globalFallback = (float) optional(
                $paps->first(fn ($row) => $row->pap !== null)
            )->pap ?? 0.0;
        } else {
            $globalFallback = (float) $globalFallback;
        }

        // if($globalFallback === 0.0) {
        //     $globalFallback = 200.0;
        // }

        // 2) Construir el mapa por categoría
        $papByCat = $paps
            ->groupBy('category_name')
            ->mapWithKeys(function ($group) use ($globalFallback) {
                // Primer pap > 0 dentro del grupo (respetando su orden)
                $firstPositive = $group->first(function ($row) {
                    return isset($row->pap) && (float)$row->pap > 0;
                });

                $value = $firstPositive ? (float) $firstPositive->pap : $globalFallback;

                return [$group->first()->category_name => $value];
            });

        foreach ($fleet as &$item) {
            $cat = $item['vehicleCategory'] ?? null;
            $net = isset($item['netRate']) ? (float)$item['netRate'] : null;
            if (!$cat || $net === null) continue;

            $days = max(1, (int)($item['totalDays'] ?? 1));

            // banda de descuento por días
            $disc = 0.70; // fallback
            foreach ($discountBands as $limit => $d) {
                if ($days <= $limit) { $disc = $d; break; }
            }

            // $papMax = (float)($papByCat[$cat] ?? 0.0);
            $papMax = max((float)($papByCat[$cat] ?? 0.0), 200.0);
            $denMax = max(0.0001, 1 - $maxDiscount);
            $mkt    = ($net + $papMax) / $denMax;      // ancla marketing
            $pub    = $mkt * (1 - $disc);              // tarifa pública con banda
            $papDyn = max(0.0, $pub - $net);

            $item['papAmount']        = round($papDyn, 2);
            $item['publicRateAmount'] = round($pub, 2);
            $item['mktRateAmount']    = round($mkt, 2);
            $item['discount']         = (int)round($disc * 100);
        }
        unset($item);

        return $fleet;
    }


    private function adaptVehiclesv2(array $vehicles, array $ctx): array
    {
        $currency = $ctx['currency'] ?? 'MXN';
        $rate     = (float)($ctx['rate'] ?? 1.0);
        $safeRate = $rate > 0 ? $rate : 1.0;

        // Redondeo a entero con .5 hacia arriba
        $roundInt = fn (float $v) => (int) round($v, 0, PHP_ROUND_HALF_UP);

        // Detectar cliente Platino
        $isPlatinum = (bool)($ctx['isPlatinum'] ?? (auth()->check() ? (bool)(auth()->user()->isPlatinum ?? false) : false));

        // Flag de búsqueda con cero deducible
        $applyZeroDeductible = (bool)($ctx['zero_deductible'] ?? false);

        return array_values(array_filter(array_map(function ($v) use ($currency, $rate, $safeRate, $isPlatinum, $roundInt, $applyZeroDeductible) {
            $v = is_array($v) ? $v : (json_decode(json_encode($v), true) ?? []);
            if (!$v) return null;

            // ID de paquete y flags
            $v['packageId']    = (string) \Illuminate\Support\Str::uuid();
            $v['OFF_SELL']     = 0;
            $v['ON_REQUEST']   = false;
            $v['currency']     = $currency;
            $v['exchangeRate'] = $rate;

            // Características legibles
            $desc  = (string)($v['vehicleDescription'] ?? '');
            $chars = array_values(array_filter(explode('|', str_replace(["<br>","<br/>","<br />"], '|', $desc))));
            $v['characteristics']    = $chars;
            $v['vehicleDescription'] = implode(' | ', $chars);

            // Totales base
            $days = max(1, (int)($v['totalDays'] ?? 1));
            $net  = (float)($v['netRate'] ?? 0.0);
            $pub  = (float)($v['publicRateAmount'] ?? 0.0);
            $mkt  = (float)($v['mktRateAmount'] ?? 0.0);

            // --- Zero deductible "crudo" del vehículo (por si viene en distintos formatos de key) ---
            $zeroNetRaw = (float)($v['zeroDeductibleNetRate']      // camelCase
                            ?? $v['zero_deductible_net_rate']      // snake_case
                            ?? 0.0);

            $zeroPubRaw = (float)($v['zeroDeductiblePublicRate']   // camelCase
                            ?? $v['zero_deductible_public_rate']   // snake_case
                            ?? 0.0);

            // dd($zeroNetRaw, $zeroPubRaw);

            $v['cancellationFeeCheck']  = true;
            $v['additionalDriverCheck'] = false;

            // Conversión de moneda
            if ($safeRate !== 1.0) {
                $v['netRate']          = $roundInt($net / $safeRate);
                $v['publicRateAmount'] = $roundInt($pub / $safeRate);
                $v['mktRateAmount']    = $roundInt($mkt / $safeRate);

                // Convertimos también los montos de cero deducible
                $zeroNetConv = $roundInt($zeroNetRaw / $safeRate);
                $zeroPubConv = $roundInt($zeroPubRaw / $safeRate);
            } else {
                $v['netRate']          = $roundInt($net);
                $v['publicRateAmount'] = $roundInt($pub);
                $v['mktRateAmount']    = $roundInt($mkt);

                $zeroNetConv = $roundInt($zeroNetRaw);
                $zeroPubConv = $roundInt($zeroPubRaw);
            }

            // Si el cliente NO pidió cero deducible, dejamos esos montos en 0
            if (!$applyZeroDeductible) {
                $zeroNetConv = 0;
                $zeroPubConv = 0;
            }

            // Guardamos los montos (ya en moneda final y redondeados)
            $v['zeroDeductibleNetRate']    = $zeroNetConv;
            $v['zeroDeductiblePublicRate'] = $zeroPubConv;

            // Usar SIEMPRE lo que quedó en $v tras conversión
            $pubUse = (float)$v['publicRateAmount'];
            $netUse = (float)$v['netRate'];
            $mktUse = (float)$v['mktRateAmount'];

            // --- Cliente Platino ---
            $v['isPlatinum'] = $isPlatinum;
            if ($isPlatinum) {
                $v['publicRateAmountOriginal'] = $pubUse;

                $platinumPerDay        = $this->calculatePlatinumRate($pubUse, $netUse);
                $v['publicRateAmount'] = $roundInt($platinumPerDay);

                $v['discountPlatinum'] = (int) round(
                    $this->calculateDiscountPlatinum($v['publicRateAmount'], $mktUse),
                    0,
                    PHP_ROUND_HALF_UP
                );
                $v['pricingContext']   = 'platinum';
            } else {
                $v['pricingContext']   = 'standard';
            }

            // Recalcular totales con tarifa vigente
            $pubNow = (float)$v['publicRateAmount'];
            $netNow = (float)$v['netRate'];

            $v['totalNetRate'] = $roundInt($netNow * $days);
            $v['total']        = $roundInt($pubNow * $days);

            // Prepayment = total - totalNetRate
            $v['prepayment']   = max(0, $roundInt($v['total'] - $v['totalNetRate']));

            // 1) cancellationFee = 18% del prepayment
            $v['cancellationFee'] = $roundInt($v['prepayment'] * 0.18);

            // 2) additionalDriver
            $additionalDriverDays = min($days, 5);
            $perDay = (strtoupper((string)$currency) === 'MXN') ? 100.0 : 5.5;
            $v['additionalDriver'] = $roundInt($perDay * $additionalDriverDays);

            // Coupons and additional promotions
            $v['hasAdditionalPromotion'] = false;
            $v['hasCoupon']              = false;
            $v['couponCode']             = null;

            // 🔹 Aquí calculamos los rates con/sin zero deductible
            // rate_without_zero_deductible = tarifa pública sin el extra
            // rate_with_zero_deductible    = tarifa pública actual
            $rateWithoutZero = max(0, $roundInt($pubNow));
            $rateWithZero    = $roundInt($pubNow + $zeroPubConv);

            $v['rate_without_zero_deductible'] = $rateWithoutZero;
            $v['rate_with_zero_deductible']    = $rateWithZero;

            // Totales con y sin zero deductible
            $v['total_without_zero_deductible'] = $roundInt($rateWithoutZero * $days);
            $v['total_with_zero_deductible']    = $roundInt($rateWithZero * $days);

            // Si quieres también netos con/sin zero deductible:
            $v['net_without_zero_deductible'] = max(0, $roundInt($netNow - $zeroNetConv));
            $v['net_with_zero_deductible']    = $roundInt($netNow);

            // Este override lo dejo tal cual lo tenías
            $v['netRate'] = $roundInt($net);

            // Limpieza de nulos opcionales
            foreach ([
                'sessionId','bookId','providerCarModel','availabilityResponse','availabilityRequest',
                'corporateSetup','classType','rateId','rateCode','vendorRateId','carType'
            ] as $k) {
                if (array_key_exists($k, $v) && $v[$k] === null) unset($v[$k]);
            }

            return $v;
        }, $vehicles)));
    }



    // private function adaptVehiclesv2(array $vehicles, array $ctx): array
    // {
    //     $currency = $ctx['currency'] ?? 'MXN';
    //     $rate     = (float)($ctx['rate'] ?? 1.0);
    //     $safeRate = $rate > 0 ? $rate : 1.0;

    //     // Redondeo a entero con .5 hacia arriba
    //     $roundInt = fn (float $v) => (int) round($v, 0, PHP_ROUND_HALF_UP);

    //     // Detectar cliente Platino: primero ctx, si no usar auth()
    //     $isPlatinum = (bool)($ctx['isPlatinum'] ?? (auth()->check() ? (bool)(auth()->user()->isPlatinum ?? false) : false));

    //     return array_values(array_filter(array_map(function ($v) use ($currency, $rate, $safeRate, $isPlatinum, $roundInt) {
    //         $v = is_array($v) ? $v : (json_decode(json_encode($v), true) ?? []);
    //         if (!$v) return null;

    //         // ID de paquete y flags
    //         $v['packageId']    = (string) \Illuminate\Support\Str::uuid();
    //         $v['OFF_SELL']     = 0;
    //         $v['ON_REQUEST']   = false;
    //         $v['currency']     = $currency;
    //         $v['exchangeRate'] = $rate;

    //         // Características legibles
    //         $desc  = (string)($v['vehicleDescription'] ?? '');
    //         $chars = array_values(array_filter(explode('|', str_replace(["<br>","<br/>","<br />"], '|', $desc))));
    //         $v['characteristics']    = $chars;
    //         $v['vehicleDescription'] = implode(' | ', $chars);

    //         // Totales base (no formatear; cálculos en float y luego redondeo a entero)
    //         $days = max(1, (int)($v['totalDays'] ?? 1));
    //         $net  = (float)($v['netRate'] ?? 0.0);
    //         $pub  = (float)($v['publicRateAmount'] ?? 0.0);
    //         $mkt  = (float)($v['mktRateAmount'] ?? 0.0);

    //         $v['cancellationFeeCheck'] = true;
    //         $v['additionalDriverCheck']= false;

    //         // Conversión de moneda -> luego redondeo entero
    //         if ($safeRate !== 1.0) {
    //             $v['netRate']          = $roundInt($net / $safeRate);
    //             $v['publicRateAmount'] = $roundInt($pub / $safeRate);
    //             $v['mktRateAmount']    = $roundInt($mkt / $safeRate);
    //         } else {
    //             $v['netRate']          = $roundInt($net);
    //             $v['publicRateAmount'] = $roundInt($pub);
    //             $v['mktRateAmount']    = $roundInt($mkt);
    //         }

    //         // Usar SIEMPRE lo que quedó en $v tras conversión
    //         $pubUse = (float)$v['publicRateAmount'];
    //         $netUse = (float)$v['netRate'];
    //         $mktUse = (float)$v['mktRateAmount'];

    //         // >>> Cliente Platino <<<
    //         $v['isPlatinum'] = $isPlatinum;
    //         if ($isPlatinum) {
    //             $v['publicRateAmountOriginal'] = $pubUse;

    //             // Tarifa platino por día -> redondeo entero
    //             $platinumPerDay = $this->calculatePlatinumRate($pubUse, $netUse);
    //             $v['publicRateAmount'] = $roundInt($platinumPerDay);

    //             // % de descuento (mantén entero %)
    //             $v['discountPlatinum'] = (int) round($this->calculateDiscountPlatinum($v['publicRateAmount'], $mktUse), 0, PHP_ROUND_HALF_UP);
    //             $v['pricingContext']   = 'platinum';
    //         } else {
    //             $v['pricingContext']   = 'standard';
    //         }

    //         // Recalcular totales con tarifa vigente (entero)
    //         $pubNow = (float)$v['publicRateAmount'];
    //         $netNow = (float)$v['netRate'];

    //         $v['totalNetRate'] = $roundInt($netNow * $days);
    //         $v['total']        = $roundInt($pubNow * $days);

    //         // Prepayment = total - totalNetRate (entero, mínimo 0)
    //         $v['prepayment']   = max(0, $roundInt($v['total'] - $v['totalNetRate']));

    //         // 1) cancellationFee = 18% del prepayment (entero)
    //         $v['cancellationFee'] = $roundInt($v['prepayment'] * 0.18);

    //         // 2) additionalDriver = 100 * min(días, 5) (MXN) ó 5.5 * min(días, 5) (USD aprox.) -> entero
    //         $additionalDriverDays = min($days, 5);
    //         $perDay = (strtoupper((string)$currency) === 'MXN') ? 100.0 : 5.5;
    //         $v['additionalDriver'] = $roundInt($perDay * $additionalDriverDays);

    //         // Coupons and additional promotions
    //         $v['hasAdditionalPromotion'] = false;
    //         $v['hasCoupon'] = false;
    //         $v['couponCode'] = null;

    //         $v['netRate'] = $roundInt($net);

    //         // Limpieza de nulos opcionales
    //         foreach ([
    //             'sessionId','bookId','providerCarModel','availabilityResponse','availabilityRequest',
    //             'corporateSetup','classType','rateId','rateCode','vendorRateId','carType'
    //         ] as $k) {
    //             if (array_key_exists($k, $v) && $v[$k] === null) unset($v[$k]);
    //         }

    //         return $v;
    //     }, $vehicles)));
    // }

    private function calculatePlatinumRate(float $publicRate, float $netRate): float
    {
        // Descuento del 15% sobre el markup (public - net)
        $mupPerDay = max(0.0, $publicRate - $netRate);
        // Nunca por debajo del neto
        return round(max($netRate, $netRate + ($mupPerDay * 0.85)), 2);
    }

    private function calculateDiscountPlatinum(float $publicRate, float $mktRateAmount): float
    {
        // Evitar división por cero / negativas
        $base = $mktRateAmount > 0 ? $mktRateAmount : $publicRate;
        if ($base <= 0) return 0.0;

        // Mantengo tu fórmula: 100 - (public * 100 / mkt)
        return max(0.0, min(100.0, 100.0 - round(($publicRate * 100.0) / $base)));
    }

    public function storeQuotation($searchParams, $fleet)
    {
        $quotation = [
            'quotationId' => (string) Str::uuid(),
            'searchParams' => $searchParams,
            'fleet' => $fleet,
            'filters' => [
                'categories' => []
            ]
        ];

        Cache::put($quotation['quotationId'], $quotation, 10080);

        return $quotation;
    }
}
