# Catálogo completo de opções do SUMO

Este é o anexo técnico do [item 2: configurações-base](configuracoes_sumo.md). Comece pelo item 2 para entender o que o projeto configura hoje.

Catálogo completo das **462 opções principais** do executável `sumo` 1.27.1 instalado neste projeto. A lista foi gerada do template de configuração produzido pelo próprio SUMO. Ela inclui opções que não são usadas pelo pipeline atual; algumas só fazem sentido com dispositivos, arquivos adicionais ou interface gráfica.

Os nomes das opções e seus valores padrão são os da instalação, não recomendações de uso. `—` na coluna Padrão significa valor vazio. Aliases levam à mesma opção principal. O arquivo [opcoes_sumo_1.27.1.txt](opcoes_sumo_1.27.1.txt) traz a ajuda integral do executável, e [modelo_todas_opcoes.sumocfg](modelo_todas_opcoes.sumocfg) guarda o template original. A [documentação oficial de opções e arquivos de configuração](https://sumo.dlr.de/docs/Basics/Using_the_Command_Line_Applications.html) explica como o SUMO lê esses valores.

## Configuração-base carregada pelo projeto

O pipeline lê `config/cenario.json`. Ele não usa um arquivo `.sumocfg` fixo: monta os argumentos da execução e inicia `sumo` por TraCI. A planilha é referência; `plan_id` não aplica automaticamente os tempos dela ao programa do SUMO.

| Item | Valor atual |
| --- | --- |
| Rede | `../dados/rede/uberlandia.vehicular.families.16_2_4.net.xml` |
| Planilha de referência | `../dados/planos/RondonNorte.xlsx`; plano `4` |
| Duração | `600` s |
| Passo | `1` s |
| Sementes | `11` |
| Demanda de teste | `random`; `360` veículos/h |
| Semáforo selecionado | `FAM_RONDON_PARANA`; fases `[0, 1, 2, 3, 4, 5]` |
| Saídas | `tripinfo.xml`, `summary.xml`, `statistics.xml`, `metrics.json` |

### Programa-base de `FAM_RONDON_PARANA` na rede

Programa `1624`, tipo `static`, defasagem `0` s. Ciclo atual `90` s.

| Fase | Estado SUMO | Categoria | Duração atual (s) | Treinada? |
| ---: | --- | --- | ---: | --- |
| 0 | `GGGGrrr` | verde | 41 | sim |
| 1 | `yyyyrrr` | amarelo | 3 | sim |
| 2 | `rrrrrrr` | totalmente vermelho | 1 | sim |
| 3 | `rrrrGGG` | verde | 41 | sim |
| 4 | `rrrryyy` | amarelo | 3 | sim |
| 5 | `rrrrrrr` | totalmente vermelho | 1 | sim |

O vermelho de um movimento também depende do tempo concedido aos demais movimentos. As fases totalmente vermelhas acima são intervalos de limpeza; o pipeline não define um tempo vermelho independente para cada via.

### Opções passadas diretamente em cada execução

| Opção SUMO | Origem do valor |
| --- | --- |
| `--net-file` | `network` em `config/cenario.json` |
| `--route-files` | Rotas geradas pela etapa de demanda |
| `--begin` | `0` s |
| `--end` | `duration_seconds` |
| `--step-length` | `step_seconds` |
| `--seed` | Cada valor de `seeds` |
| `--tripinfo-output` | `tripinfo.xml` da execução |
| `--summary-output` | `summary.xml` da execução |
| `--statistic-output` | `statistics.xml` da execução |
| `--no-step-log` | `true` |

TraCI estabelece a conexão com o SUMO. Durações candidatas são aplicadas ao programa semafórico durante a execução via `setProgramLogic`.

### Comandos para carregar e consultar

Execute na pasta `SistemaDeSemaforos`:

```powershell
python pipeline.py inspect
python pipeline.py run --config config/cenario.json
python pipeline.py train --config config/cenario.json
python pipeline.py options
```

Para obter novamente o template completo do executável instalado:

```powershell
sumo --save-template docs/modelo_todas_opcoes.sumocfg --save-commented
python scripts/gerar_catalogo_sumo.py
```

As opções de `randomTrips.py`, `netconvert` e outros executáveis têm catálogos próprios. Esta lista cobre **todas as opções principais de `sumo` desta versão**. Atributos internos dos arquivos de rede/rotas e métodos TraCI não são opções de linha de comando e não fazem parte deste catálogo.

## Todas as opções de `sumo`

Tipo e padrão vêm do template oficial gerado localmente. Os detalhes de cada opção estão na ajuda integral ligada no início deste documento. As 27 categorias abaixo preservam a divisão do próprio executável.

| Tipo | Valor esperado |
| --- | --- |
| `BOOL` | verdadeiro ou falso |
| `INT` | número inteiro |
| `FLOAT` | número decimal |
| `TIME` | duração ou instante de simulação |
| `STR` | texto |
| `STR[]` | lista de textos |
| `FILE` | caminho de arquivo |

| Categoria | Opções |
| --- | ---: |
| Configuração (`configuration`) | 6 |
| Entradas (`input`) | 9 |
| Saídas (`output`) | 97 |
| Tempo (`time`) | 3 |
| Processamento (`processing`) | 87 |
| Roteamento (`routing`) | 42 |
| Relatórios (`report`) | 19 |
| Emissões (`emissions`) | 9 |
| Comunicação (`communication`) | 15 |
| Bateria (`battery`) | 25 |
| Dispositivo de exemplo (`example_device`) | 4 |
| Segurança substituta (SSM) (`ssm_device`) | 15 |
| Transferência de controle (ToC) (`toc_device`) | 22 |
| Estado do motorista (`driver_state_device`) | 13 |
| Veículos de emergência (`bluelight_device`) | 5 |
| Dados de veículos flutuantes (FCD) (`fcd_device`) | 10 |
| Veículos híbridos elétricos (`elechybrid_device`) | 3 |
| Táxis (`taxi_device`) | 11 |
| GLOSA (`glosa_device`) | 10 |
| Informações de viagem (`tripinfo_device`) | 3 |
| Rotas dos veículos (`vehroutes_device`) | 3 |
| Atrito (`friction_device`) | 5 |
| Reprodução FCD (`fcd_replay_device`) | 4 |
| Servidor TraCI (`traci_server`) | 2 |
| Simulação mesoscópica (`mesoscopic`) | 18 |
| Aleatoriedade (`random_number`) | 3 |
| Interface gráfica (`gui_only`) | 19 |

### Configuração (`configuration`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--configuration-file` | `-c`, `--configuration` | `FILE` | — |
| `--save-configuration` | `-C`, `--save-config` | `FILE` | — |
| `--save-configuration.relative` | `--save-config.relative` | `BOOL` | `false` |
| `--save-template` | — | `FILE` | — |
| `--save-schema` | — | `FILE` | — |
| `--save-commented` | `--save-template.commented` | `BOOL` | — |

### Entradas (`input`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--net-file` | `-n`, `--net` | `FILE` | — |
| `--route-files` | `-r`, `--routes` | `FILE` | — |
| `--additional-files` | `-a`, `--additional` | `FILE` | — |
| `--weight-files` | `-w`, `--weights` | `FILE` | — |
| `--weight-attribute` (possui alias obsoleto) | `--measure`, `-x` | `STR` | `traveltime` |
| `--load-state` | — | `FILE` | — |
| `--load-state.offset` | — | `TIME` | `0` |
| `--load-state.remove-vehicles` | — | `STR[]` | — |
| `--junction-taz` | — | `BOOL` | `false` |

### Saídas (`output`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--write-license` | — | `BOOL` | `false` |
| `--write-metadata` | — | `BOOL` | `false` |
| `--output-prefix` | — | `STR` | — |
| `--output-suffix` | — | `STR` | — |
| `--precision` | — | `INT` | `2` |
| `--precision.geo` | — | `INT` | `6` |
| `--output.compression` | — | `STR` | — |
| `--output.format` | — | `STR` | `xml` |
| `--output.column-header` | — | `STR` | `tag` |
| `--output.column-separator` | — | `STR` | `;` |
| `--human-readable-time` | `-H` | `BOOL` | `false` |
| `--netstate-dump` | `--ndump`, `--netstate`, `--netstate-output` | `FILE` | — |
| `--netstate-dump.empty-edges` (possui alias obsoleto) | `--dump-empty-edges`, `--netstate-output.empty-edges`, `--netstate.empty-edges` | `BOOL` | `false` |
| `--netstate-dump.precision` (possui alias obsoleto) | `--dump-precision`, `--netstate-output.precision`, `--netstate.precision` | `INT` | `2` |
| `--emission-output` | — | `FILE` | — |
| `--emission-output.precision` | — | `INT` | `2` |
| `--emission-output.geo` | — | `BOOL` | `false` |
| `--emission-output.step-scaled` | — | `BOOL` | `false` |
| `--emission-output.attributes` | — | `STR[]` | — |
| `--battery-output` | — | `FILE` | — |
| `--battery-output.precision` | — | `INT` | `2` |
| `--elechybrid-output` | — | `FILE` | — |
| `--elechybrid-output.precision` | — | `INT` | `2` |
| `--elechybrid-output.aggregated` | — | `BOOL` | `false` |
| `--chargingstations-output` | — | `FILE` | — |
| `--chargingstations-output.aggregated` | — | `BOOL` | `false` |
| `--chargingstations-output.aggregated.write-unfinished` | — | `BOOL` | `false` |
| `--overheadwiresegments-output` | — | `FILE` | — |
| `--substations-output` | — | `FILE` | — |
| `--substations-output.precision` | — | `INT` | `2` |
| `--fcd-output` | — | `FILE` | — |
| `--fcd-output.geo` | — | `BOOL` | `false` |
| `--fcd-output.utm` | — | `BOOL` | `false` |
| `--fcd-output.signals` | — | `BOOL` | `false` |
| `--fcd-output.distance` | — | `BOOL` | `false` |
| `--fcd-output.acceleration` | — | `BOOL` | `false` |
| `--fcd-output.speed-relative` | — | `BOOL` | `false` |
| `--fcd-output.max-leader-distance` | — | `FLOAT` | `-1` |
| `--fcd-output.params` | — | `STR[]` | — |
| `--fcd-output.filter-edges.input-file` | — | `FILE` | — |
| `--fcd-output.attributes` | — | `STR[]` | — |
| `--fcd-output.filter-shapes` | — | `STR[]` | — |
| `--fcd-output.skip-empty` | — | `BOOL` | `false` |
| `--person-fcd-output` | `--person-fcd` | `FILE` | — |
| `--device.ssm.filter-edges.input-file` | — | `FILE` | — |
| `--full-output` | — | `FILE` | — |
| `--queue-output` | — | `FILE` | — |
| `--queue-output.period` | — | `TIME` | `-1` |
| `--vtk-output` | — | `FILE` | — |
| `--amitran-output` | — | `FILE` | — |
| `--summary-output` | `--summary` | `FILE` | — |
| `--summary-output.period` | — | `TIME` | `-1` |
| `--person-summary-output` | — | `FILE` | — |
| `--tripinfo-output` | `--tripinfo` | `FILE` | — |
| `--tripinfo-output.write-unfinished` | — | `BOOL` | `false` |
| `--tripinfo-output.write-undeparted` | — | `BOOL` | `false` |
| `--personinfo-output` | `--personinfo` | `FILE` | — |
| `--vehroute-output` | `--vehroutes` | `FILE` | — |
| `--vehroute-output.exit-times` | `--vehroutes.exit-times` | `BOOL` | `false` |
| `--vehroute-output.last-route` | `--vehroutes.last-route` | `BOOL` | `false` |
| `--vehroute-output.sorted` | `--vehroutes.sorted` | `BOOL` | `false` |
| `--vehroute-output.dua` | `--vehroutes.dua` | `BOOL` | `false` |
| `--vehroute-output.cost` | — | `BOOL` | `false` |
| `--vehroute-output.intended-depart` | `--vehroutes.intended-depart` | `BOOL` | `false` |
| `--vehroute-output.route-length` | `--vehroutes.route-length` | `BOOL` | `false` |
| `--vehroute-output.write-unfinished` | — | `BOOL` | `false` |
| `--vehroute-output.skip-ptlines` | — | `BOOL` | `false` |
| `--vehroute-output.incomplete` | — | `BOOL` | `false` |
| `--vehroute-output.stop-edges` | — | `BOOL` | `false` |
| `--vehroute-output.speedfactor` | — | `BOOL` | `false` |
| `--vehroute-output.internal` | — | `BOOL` | `false` |
| `--personroute-output` | `--personroutes` | `FILE` | — |
| `--link-output` | — | `FILE` | — |
| `--railsignal-block-output` | — | `FILE` | — |
| `--railsignal-vehicle-output` | — | `FILE` | — |
| `--bt-output` | — | `FILE` | — |
| `--lanechange-output` | — | `FILE` | — |
| `--lanechange-output.started` | — | `BOOL` | `false` |
| `--lanechange-output.ended` | — | `BOOL` | `false` |
| `--lanechange-output.xy` | — | `BOOL` | `false` |
| `--stop-output` | — | `FILE` | — |
| `--stop-output.write-unfinished` | — | `BOOL` | `false` |
| `--collision-output` | — | `FILE` | — |
| `--edgedata-output` | — | `FILE` | — |
| `--lanedata-output` | — | `FILE` | — |
| `--statistic-output` | `--statistics-output` | `FILE` | — |
| `--deadlock-output` | — | `FILE` | — |
| `--save-state.times` | — | `STR[]` | — |
| `--save-state.period` | — | `TIME` | `-1` |
| `--save-state.period.keep` | — | `INT` | `0` |
| `--save-state.prefix` | — | `FILE` | `state` |
| `--save-state.suffix` | — | `STR` | `.xml.gz` |
| `--save-state.files` | — | `FILE` | — |
| `--save-state.rng` | — | `BOOL` | `false` |
| `--save-state.transportables` | — | `BOOL` | `false` |
| `--save-state.constraints` | — | `BOOL` | `false` |
| `--save-state.precision` | — | `INT` | `2` |

### Tempo (`time`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--begin` | `-b` | `TIME` | `0` |
| `--end` | `-e` | `TIME` | `-1` |
| `--step-length` | — | `TIME` | `1` |

### Processamento (`processing`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--step-method.ballistic` | — | `BOOL` | `false` |
| `--extrapolate-departpos` | — | `BOOL` | `false` |
| `--threads` | — | `INT` | `1` |
| `--lateral-resolution` | — | `FLOAT` | `-1` |
| `--route-steps` | `-s` | `TIME` | `200` |
| `--no-internal-links` | — | `BOOL` | `false` |
| `--ignore-junction-blocker` | — | `TIME` | `-1` |
| `--ignore-route-errors` | — | `BOOL` | `false` |
| `--ignore-accidents` | — | `BOOL` | `false` |
| `--collision.action` | — | `STR` | `teleport` |
| `--intermodal-collision.action` | — | `STR` | `warn` |
| `--collision.stoptime` | — | `TIME` | `0` |
| `--intermodal-collision.stoptime` | — | `TIME` | `0` |
| `--collision.check-junctions` | — | `BOOL` | `false` |
| `--collision.check-junctions.mingap` | — | `FLOAT` | `0` |
| `--collision.mingap-factor` | — | `FLOAT` | `-1` |
| `--keep-after-arrival` | — | `TIME` | `0` |
| `--max-num-vehicles` | — | `INT` | `-1` |
| `--max-num-persons` | — | `INT` | `-1` |
| `--max-num-teleports` | — | `INT` | `-1` |
| `--scale` | — | `FLOAT` | `1` |
| `--scale-suffix` | — | `STR` | `.` |
| `--time-to-teleport` | — | `TIME` | `300` |
| `--time-to-teleport.highways` | — | `TIME` | `0` |
| `--time-to-teleport.highways.min-speed` | — | `FLOAT` | `19.1667` |
| `--time-to-teleport.disconnected` | — | `TIME` | `-1` |
| `--time-to-teleport.remove` | — | `BOOL` | `false` |
| `--time-to-teleport.remove-constraint` | — | `BOOL` | `false` |
| `--time-to-teleport.ride` | — | `TIME` | `-1` |
| `--time-to-teleport.bidi` | — | `TIME` | `-1` |
| `--time-to-teleport.railsignal-deadlock` | — | `TIME` | `-1` |
| `--waiting-time-memory` | — | `TIME` | `100` |
| `--startup-wait-threshold` | — | `TIME` | `2` |
| `--max-depart-delay` | — | `TIME` | `-1` |
| `--sloppy-insert` | — | `BOOL` | `false` |
| `--eager-insert` | — | `BOOL` | `false` |
| `--emergency-insert` | — | `BOOL` | `false` |
| `--insertion-checks` | — | `STR` | `all` |
| `--random-depart-offset` | — | `TIME` | `0` |
| `--lanechange.duration` | — | `TIME` | `0` |
| `--lanechange.overtake-right` | — | `BOOL` | `false` |
| `--tls.all-off` | — | `BOOL` | `false` |
| `--tls.actuated.show-detectors` | — | `BOOL` | `false` |
| `--tls.actuated.jam-threshold` | — | `FLOAT` | `-1` |
| `--tls.actuated.detector-length` | — | `FLOAT` | `0` |
| `--tls.delay_based.detector-range` | — | `FLOAT` | `100` |
| `--tls.yellow.min-decel` | — | `FLOAT` | `3` |
| `--railsignal-moving-block` | `--railsignal.moving-block` | `BOOL` | `false` |
| `--railsignal.moving-block.default-classes` | — | `STR[]` | `tram,cable_car` |
| `--railsignal.moving-block.max-dist` | — | `FLOAT` | `200` |
| `--railsignal.max-block-length` | — | `FLOAT` | `20000` |
| `--railsignal.default-classes` | — | `STR[]` | `rail,rail_fast,rail_electric,rail_urban,subway` |
| `--time-to-impatience` | — | `TIME` | `180` |
| `--default.departspeed` | — | `STR` | `avg` |
| `--default.departlane` | — | `STR` | `best_prob` |
| `--default.action-step-length` | — | `FLOAT` | `0` |
| `--default.carfollowmodel` | `--carfollow.model` | `STR` | `Krauss` |
| `--default.speeddev` | — | `FLOAT` | `-1` |
| `--default.emergencydecel` | — | `STR` | `default` |
| `--overhead-wire.solver` | — | `BOOL` | `true` |
| `--overhead-wire.recuperation` | — | `BOOL` | `true` |
| `--overhead-wire.substation-current-limits` | — | `BOOL` | `true` |
| `--emergencydecel.warning-threshold` | — | `FLOAT` | `1` |
| `--parking.maneuver` | — | `BOOL` | `false` |
| `--use-stop-ended` | — | `BOOL` | `false` |
| `--use-stop-started` | — | `BOOL` | `false` |
| `--pedestrian.model` | — | `STR` | `striping` |
| `--pedestrian.timegap-crossing` | — | `FLOAT` | `2` |
| `--pedestrian.striping.stripe-width` | — | `FLOAT` | `0.64` |
| `--pedestrian.striping.dawdling` | — | `FLOAT` | `0.2` |
| `--pedestrian.striping.mingap-to-vehicle` | — | `FLOAT` | `0.25` |
| `--pedestrian.striping.jamtime` | — | `TIME` | `300` |
| `--pedestrian.striping.jamtime.crossing` | — | `TIME` | `10` |
| `--pedestrian.striping.jamtime.narrow` | — | `TIME` | `1` |
| `--pedestrian.striping.jamfactor` | — | `FLOAT` | `0.25` |
| `--pedestrian.striping.reserve-oncoming` | — | `FLOAT` | `0` |
| `--pedestrian.striping.reserve-oncoming.junctions` | — | `FLOAT` | `0.34` |
| `--pedestrian.striping.reserve-oncoming.max` | — | `FLOAT` | `1.28` |
| `--pedestrian.striping.legacy-departposlat` | — | `BOOL` | `false` |
| `--pedestrian.striping.walkingarea-detail` | — | `INT` | `4` |
| `--ride.stop-tolerance` | — | `FLOAT` | `10` |
| `--mapmatch.distance` | — | `FLOAT` | `100` |
| `--mapmatch.junctions` | — | `BOOL` | `false` |
| `--mapmatch.taz` | — | `BOOL` | `false` |
| `--weights.turnaround-penalty` | — | `FLOAT` | `5` |
| `--weights.reversal-penalty` | — | `FLOAT` | `60` |
| `--persontrip.walk-opposite-factor` | — | `FLOAT` | `1` |

### Roteamento (`routing`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--routing-algorithm` | — | `STR` | `dijkstra` |
| `--weights.random-factor` | — | `FLOAT` | `1` |
| `--weights.random-factor.dynamic` | — | `BOOL` | `false` |
| `--weights.minor-penalty` | — | `FLOAT` | `1.5` |
| `--weights.tls-penalty` | — | `FLOAT` | `0` |
| `--weights.priority-factor` | — | `FLOAT` | `0` |
| `--weights.separate-turns` | — | `FLOAT` | `0` |
| `--astar.all-distances` | — | `FILE` | — |
| `--astar.landmark-distances` | — | `FILE` | — |
| `--persontrip.walkfactor` | — | `FLOAT` | `0.75` |
| `--persontrip.transfer.car-walk` | — | `STR[]` | `parkingAreas` |
| `--persontrip.transfer.taxi-walk` | — | `STR[]` | — |
| `--persontrip.transfer.walk-taxi` | — | `STR[]` | — |
| `--persontrip.default.group` | — | `STR` | — |
| `--persontrip.taxi.waiting-time` | — | `TIME` | `300` |
| `--persontrip.ride-public-line` | — | `BOOL` | `false` |
| `--railway.max-train-length` | — | `FLOAT` | `1000` |
| `--replay-rerouting` | — | `BOOL` | `false` |
| `--device.rerouting.probability` | — | `FLOAT` | `-1` |
| `--device.rerouting.explicit` (possui alias obsoleto) | `--device.rerouting.knownveh` | `STR[]` | — |
| `--device.rerouting.deterministic` | — | `BOOL` | `false` |
| `--device.rerouting.period` (possui alias obsoleto) | `--device.routing.period` | `TIME` | `0` |
| `--device.rerouting.pre-period` (possui alias obsoleto) | `--device.routing.pre-period` | `TIME` | `60` |
| `--device.rerouting.adaptation-weight` (possui alias obsoleto) | `--device.routing.adaptation-weight` | `FLOAT` | `0` |
| `--device.rerouting.adaptation-steps` (possui alias obsoleto) | `--device.routing.adaptation-steps` | `INT` | `180` |
| `--device.rerouting.adaptation-interval` (possui alias obsoleto) | `--device.routing.adaptation-interval` | `TIME` | `1` |
| `--device.rerouting.threshold.factor` | — | `FLOAT` | `1` |
| `--device.rerouting.threshold.constant` | — | `TIME` | `0` |
| `--device.rerouting.with-taz` (possui alias obsoleto) | `--device.routing.with-taz`, `--with-taz` | `BOOL` | `false` |
| `--device.rerouting.mode` | — | `STR` | `0` |
| `--device.rerouting.init-with-loaded-weights` | — | `BOOL` | `false` |
| `--device.rerouting.threads` | `--routing-threads` | `INT` | `0` |
| `--device.rerouting.synchronize` | — | `BOOL` | `false` |
| `--device.rerouting.railsignal` | — | `BOOL` | `false` |
| `--device.rerouting.bike-speeds` | — | `BOOL` | `false` |
| `--device.rerouting.output` | — | `FILE` | — |
| `--person-device.rerouting.probability` | — | `FLOAT` | `-1` |
| `--person-device.rerouting.explicit` (possui alias obsoleto) | `--person-device.rerouting.knownveh` | `STR[]` | — |
| `--person-device.rerouting.deterministic` | — | `BOOL` | `false` |
| `--person-device.rerouting.period` (possui alias obsoleto) | `--person-device.routing.period` | `TIME` | `0` |
| `--person-device.rerouting.mode` | — | `STR` | `0` |
| `--person-device.rerouting.scope` | — | `STR` | `stage` |

### Relatórios (`report`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--verbose` | `-v` | `BOOL` | `false` |
| `--print-options` | — | `BOOL` | `false` |
| `--help` | `-?` | `BOOL` | `false` |
| `--version` | `-V` | `BOOL` | `false` |
| `--xml-validation` | `-X` | `STR` | `local` |
| `--xml-validation.net` | — | `STR` | `never` |
| `--xml-validation.routes` | — | `STR` | `local` |
| `--no-warnings` (possui alias obsoleto) | `-W`, `--suppress-warnings` | `BOOL` | `false` |
| `--aggregate-warnings` | — | `INT` | `-1` |
| `--log` | `-l`, `--log-file` | `FILE` | — |
| `--message-log` | — | `FILE` | — |
| `--error-log` | — | `FILE` | — |
| `--log.timestamps` | — | `BOOL` | `false` |
| `--log.processid` | — | `BOOL` | `false` |
| `--language` | — | `STR` | `C` |
| `--duration-log.disable` | `--no-duration-log` | `BOOL` | `false` |
| `--duration-log.statistics` | `-t` | `BOOL` | `false` |
| `--no-step-log` | — | `BOOL` | `false` |
| `--step-log.period` | — | `INT` | `100` |

### Emissões (`emissions`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--emissions.volumetric-fuel` | — | `BOOL` | `false` |
| `--phemlight-path` | — | `FILE` | `./PHEMlight/` |
| `--phemlight-year` | — | `INT` | `0` |
| `--phemlight-temperature` | — | `FLOAT` | `1.79769e+308` |
| `--device.emissions.probability` | — | `FLOAT` | `-1` |
| `--device.emissions.explicit` (possui alias obsoleto) | `--device.emissions.knownveh` | `STR[]` | — |
| `--device.emissions.deterministic` | — | `BOOL` | `false` |
| `--device.emissions.begin` | — | `STR` | `-1` |
| `--device.emissions.period` | — | `STR` | `0` |

### Comunicação (`communication`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.btreceiver.probability` | — | `FLOAT` | `-1` |
| `--device.btreceiver.explicit` (possui alias obsoleto) | `--device.btreceiver.knownveh` | `STR[]` | — |
| `--device.btreceiver.deterministic` | — | `BOOL` | `false` |
| `--device.btreceiver.range` | — | `FLOAT` | `300` |
| `--device.btreceiver.all-recognitions` | — | `BOOL` | `false` |
| `--device.btreceiver.offtime` | — | `FLOAT` | `0.64` |
| `--device.btsender.probability` | — | `FLOAT` | `-1` |
| `--device.btsender.explicit` (possui alias obsoleto) | `--device.btsender.knownveh` | `STR[]` | — |
| `--device.btsender.deterministic` | — | `BOOL` | `false` |
| `--person-device.btsender.probability` | — | `FLOAT` | `-1` |
| `--person-device.btsender.explicit` (possui alias obsoleto) | `--person-device.btsender.knownveh` | `STR[]` | — |
| `--person-device.btsender.deterministic` | — | `BOOL` | `false` |
| `--person-device.btreceiver.probability` | — | `FLOAT` | `-1` |
| `--person-device.btreceiver.explicit` (possui alias obsoleto) | `--person-device.btreceiver.knownveh` | `STR[]` | — |
| `--person-device.btreceiver.deterministic` | — | `BOOL` | `false` |

### Bateria (`battery`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.stationfinder.probability` | — | `FLOAT` | `-1` |
| `--device.stationfinder.explicit` (possui alias obsoleto) | `--device.stationfinder.knownveh` | `STR[]` | — |
| `--device.stationfinder.deterministic` | — | `BOOL` | `false` |
| `--device.stationfinder.rescueTime` | — | `TIME` | `1800` |
| `--device.stationfinder.rescueAction` | — | `STR` | `remove` |
| `--device.stationfinder.reserveFactor` | — | `FLOAT` | `1.1` |
| `--device.stationfinder.emptyThreshold` | — | `FLOAT` | `0.05` |
| `--device.stationfinder.radius` | — | `TIME` | `180` |
| `--device.stationfinder.maxEuclideanDistance` | — | `FLOAT` | `-1` |
| `--device.stationfinder.repeat` | — | `TIME` | `60` |
| `--device.stationfinder.maxChargePower` | — | `FLOAT` | `100000` |
| `--device.stationfinder.chargeType` | — | `STR` | `charging` |
| `--device.stationfinder.waitForCharge` | — | `TIME` | `600` |
| `--device.stationfinder.minOpportunityDuration` | — | `TIME` | `3600` |
| `--device.stationfinder.saturatedChargeLevel` | — | `FLOAT` | `0.8` |
| `--device.stationfinder.needToChargeLevel` | — | `FLOAT` | `0.4` |
| `--device.stationfinder.opportunisticChargeLevel` | — | `FLOAT` | `0` |
| `--device.stationfinder.replacePlannedStop` | — | `FLOAT` | `0` |
| `--device.stationfinder.maxDistanceToReplacedStop` | — | `FLOAT` | `300` |
| `--device.stationfinder.chargingStrategy` | — | `STR` | `none` |
| `--device.stationfinder.checkEnergyForRoute` | — | `BOOL` | `true` |
| `--device.battery.probability` | — | `FLOAT` | `-1` |
| `--device.battery.explicit` (possui alias obsoleto) | `--device.battery.knownveh` | `STR[]` | — |
| `--device.battery.deterministic` | — | `BOOL` | `false` |
| `--device.battery.track-fuel` | — | `BOOL` | `false` |

### Dispositivo de exemplo (`example_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.example.probability` | — | `FLOAT` | `-1` |
| `--device.example.explicit` (possui alias obsoleto) | `--device.example.knownveh` | `STR[]` | — |
| `--device.example.deterministic` | — | `BOOL` | `false` |
| `--device.example.parameter` | — | `FLOAT` | `0` |

### Segurança substituta (SSM) (`ssm_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.ssm.probability` | — | `FLOAT` | `-1` |
| `--device.ssm.explicit` (possui alias obsoleto) | `--device.ssm.knownveh` | `STR[]` | — |
| `--device.ssm.deterministic` | — | `BOOL` | `false` |
| `--device.ssm.measures` | — | `STR` | — |
| `--device.ssm.thresholds` | — | `STR` | — |
| `--device.ssm.trajectories` | — | `BOOL` | `false` |
| `--device.ssm.range` | — | `FLOAT` | `50` |
| `--device.ssm.extratime` | — | `FLOAT` | `5` |
| `--device.ssm.mdrac.prt` | — | `FLOAT` | `1` |
| `--device.ssm.file` | — | `STR` | — |
| `--device.ssm.geo` | — | `BOOL` | `false` |
| `--device.ssm.write-positions` | — | `BOOL` | `false` |
| `--device.ssm.write-lane-positions` | — | `BOOL` | `false` |
| `--device.ssm.write-na` | — | `BOOL` | `true` |
| `--device.ssm.exclude-conflict-types` | — | `STR` | — |

### Transferência de controle (ToC) (`toc_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.toc.probability` | — | `FLOAT` | `-1` |
| `--device.toc.explicit` (possui alias obsoleto) | `--device.toc.knownveh` | `STR[]` | — |
| `--device.toc.deterministic` | — | `BOOL` | `false` |
| `--device.toc.manualType` | — | `STR` | — |
| `--device.toc.automatedType` | — | `STR` | — |
| `--device.toc.responseTime` | — | `FLOAT` | `-1` |
| `--device.toc.recoveryRate` | — | `FLOAT` | `0.1` |
| `--device.toc.lcAbstinence` | — | `FLOAT` | `0` |
| `--device.toc.initialAwareness` | — | `FLOAT` | `0.5` |
| `--device.toc.mrmDecel` | — | `FLOAT` | `1.5` |
| `--device.toc.dynamicToCThreshold` | — | `FLOAT` | `0` |
| `--device.toc.dynamicMRMProbability` | — | `FLOAT` | `0.05` |
| `--device.toc.mrmKeepRight` | — | `BOOL` | `false` |
| `--device.toc.mrmSafeSpot` | — | `STR` | — |
| `--device.toc.mrmSafeSpotDuration` | — | `FLOAT` | `60` |
| `--device.toc.maxPreparationAccel` | — | `FLOAT` | `0` |
| `--device.toc.ogNewTimeHeadway` | — | `FLOAT` | `-1` |
| `--device.toc.ogNewSpaceHeadway` | — | `FLOAT` | `-1` |
| `--device.toc.ogMaxDecel` | — | `FLOAT` | `-1` |
| `--device.toc.ogChangeRate` | — | `FLOAT` | `-1` |
| `--device.toc.useColorScheme` | — | `BOOL` | `true` |
| `--device.toc.file` | — | `STR` | — |

### Estado do motorista (`driver_state_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.driverstate.probability` | — | `FLOAT` | `-1` |
| `--device.driverstate.explicit` (possui alias obsoleto) | `--device.driverstate.knownveh` | `STR[]` | — |
| `--device.driverstate.deterministic` | — | `BOOL` | `false` |
| `--device.driverstate.initialAwareness` | — | `FLOAT` | `1` |
| `--device.driverstate.errorTimeScaleCoefficient` | — | `FLOAT` | `100` |
| `--device.driverstate.errorNoiseIntensityCoefficient` | — | `FLOAT` | `0.2` |
| `--device.driverstate.speedDifferenceErrorCoefficient` | — | `FLOAT` | `0.15` |
| `--device.driverstate.headwayErrorCoefficient` | — | `FLOAT` | `0.75` |
| `--device.driverstate.freeSpeedErrorCoefficient` | — | `FLOAT` | `0` |
| `--device.driverstate.speedDifferenceChangePerceptionThreshold` | — | `FLOAT` | `0.1` |
| `--device.driverstate.headwayChangePerceptionThreshold` | — | `FLOAT` | `0.1` |
| `--device.driverstate.minAwareness` | — | `FLOAT` | `0.1` |
| `--device.driverstate.maximalReactionTime` | — | `FLOAT` | `-1` |

### Veículos de emergência (`bluelight_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.bluelight.probability` | — | `FLOAT` | `-1` |
| `--device.bluelight.explicit` (possui alias obsoleto) | `--device.bluelight.knownveh` | `STR[]` | — |
| `--device.bluelight.deterministic` | — | `BOOL` | `false` |
| `--device.bluelight.reactiondist` | — | `FLOAT` | `25` |
| `--device.bluelight.mingapfactor` | — | `FLOAT` | `1` |

### Dados de veículos flutuantes (FCD) (`fcd_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.fcd.probability` | — | `FLOAT` | `-1` |
| `--device.fcd.explicit` (possui alias obsoleto) | `--device.fcd.knownveh` | `STR[]` | — |
| `--device.fcd.deterministic` | — | `BOOL` | `false` |
| `--device.fcd.begin` | — | `STR` | `-1` |
| `--device.fcd.period` | — | `STR` | `0` |
| `--device.fcd.radius` | — | `FLOAT` | `0` |
| `--person-device.fcd.probability` | — | `FLOAT` | `-1` |
| `--person-device.fcd.explicit` (possui alias obsoleto) | `--person-device.fcd.knownveh` | `STR[]` | — |
| `--person-device.fcd.deterministic` | — | `BOOL` | `false` |
| `--person-device.fcd.period` | — | `STR` | `0` |

### Veículos híbridos elétricos (`elechybrid_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.elechybrid.probability` | — | `FLOAT` | `-1` |
| `--device.elechybrid.explicit` (possui alias obsoleto) | `--device.elechybrid.knownveh` | `STR[]` | — |
| `--device.elechybrid.deterministic` | — | `BOOL` | `false` |

### Táxis (`taxi_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.taxi.probability` | — | `FLOAT` | `-1` |
| `--device.taxi.explicit` (possui alias obsoleto) | `--device.taxi.knownveh` | `STR[]` | — |
| `--device.taxi.deterministic` | — | `BOOL` | `false` |
| `--device.taxi.dispatch-algorithm` | — | `STR` | `greedy` |
| `--device.taxi.dispatch-algorithm.output` | — | `FILE` | — |
| `--device.taxi.dispatch-algorithm.params` | — | `STR` | — |
| `--device.taxi.dispatch-period` | — | `TIME` | `60` |
| `--device.taxi.dispatch-keep-unreachable` | — | `TIME` | `3600` |
| `--device.taxi.idle-algorithm` | — | `STR` | `stop` |
| `--device.taxi.idle-algorithm.output` | — | `FILE` | — |
| `--device.taxi.vclasses` | `--taxi.vclasses` | `STR[]` | `taxi` |

### GLOSA (`glosa_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.glosa.probability` | — | `FLOAT` | `-1` |
| `--device.glosa.explicit` (possui alias obsoleto) | `--device.glosa.knownveh` | `STR[]` | — |
| `--device.glosa.deterministic` | — | `BOOL` | `false` |
| `--device.glosa.range` | — | `FLOAT` | `100` |
| `--device.glosa.max-speedfactor` | — | `FLOAT` | `1.1` |
| `--device.glosa.min-speed` | — | `FLOAT` | `5` |
| `--device.glosa.add-switchtime` | — | `FLOAT` | `0` |
| `--device.glosa.use-queue` | — | `BOOL` | `false` |
| `--device.glosa.override-safety` | — | `BOOL` | `false` |
| `--device.glosa.ignore-cfmodel` | — | `BOOL` | `false` |

### Informações de viagem (`tripinfo_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.tripinfo.probability` | — | `FLOAT` | `-1` |
| `--device.tripinfo.explicit` (possui alias obsoleto) | `--device.tripinfo.knownveh` | `STR[]` | — |
| `--device.tripinfo.deterministic` | — | `BOOL` | `false` |

### Rotas dos veículos (`vehroutes_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.vehroute.probability` | — | `FLOAT` | `-1` |
| `--device.vehroute.explicit` (possui alias obsoleto) | `--device.vehroute.knownveh` | `STR[]` | — |
| `--device.vehroute.deterministic` | — | `BOOL` | `false` |

### Atrito (`friction_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.friction.probability` | — | `FLOAT` | `-1` |
| `--device.friction.explicit` (possui alias obsoleto) | `--device.friction.knownveh` | `STR[]` | — |
| `--device.friction.deterministic` | — | `BOOL` | `false` |
| `--device.friction.stdDev` | — | `FLOAT` | `0.1` |
| `--device.friction.offset` | — | `FLOAT` | `0` |

### Reprodução FCD (`fcd_replay_device`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--device.fcd-replay.probability` | — | `FLOAT` | `-1` |
| `--device.fcd-replay.explicit` (possui alias obsoleto) | `--device.fcd-replay.knownveh` | `STR[]` | — |
| `--device.fcd-replay.deterministic` | — | `BOOL` | `false` |
| `--device.fcd-replay.file` | — | `FILE` | — |

### Servidor TraCI (`traci_server`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--remote-port` | — | `INT` | `0` |
| `--num-clients` | — | `INT` | `1` |

### Simulação mesoscópica (`mesoscopic`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--mesosim` | — | `BOOL` | `false` |
| `--meso-edgelength` | — | `FLOAT` | `98` |
| `--meso-tauff` | — | `TIME` | `1.13` |
| `--meso-taufj` | — | `TIME` | `1.13` |
| `--meso-taujf` | — | `TIME` | `1.73` |
| `--meso-taujj` | — | `TIME` | `1.4` |
| `--meso-jam-threshold` | — | `FLOAT` | `-1` |
| `--meso-multi-queue` | — | `BOOL` | `true` |
| `--meso-lane-queue` | — | `BOOL` | `false` |
| `--meso-ignore-lanes-by-vclass` | `--meso.ignore-lanes.by-vclass` | `STR[]` | `pedestrian,bicycle` |
| `--meso-junction-control` | — | `BOOL` | `false` |
| `--meso-junction-control.limited` | — | `BOOL` | `false` |
| `--meso-tls-penalty` | — | `FLOAT` | `0` |
| `--meso-tls-flow-penalty` | — | `FLOAT` | `0` |
| `--meso-minor-penalty` | — | `TIME` | `0` |
| `--meso-overtaking` | — | `BOOL` | `false` |
| `--meso-recheck` | — | `TIME` | `0` |
| `--meso-interpolate-pos` | — | `BOOL` | `false` |

### Aleatoriedade (`random_number`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--random` (possui alias obsoleto) | `--abs-rand` | `BOOL` | `false` |
| `--seed` (possui alias obsoleto) | `--srand` | `INT` | `23423` |
| `--thread-rngs` | — | `INT` | `64` |

### Interface gráfica (`gui_only`)

| Opção | Alias | Tipo | Padrão |
| --- | --- | --- | --- |
| `--gui-settings-file` | `-g` | `FILE` | — |
| `--quit-on-end` | `-Q` | `BOOL` | `false` |
| `--game` | `-G` | `BOOL` | `false` |
| `--game.mode` | — | `STR` | `tls` |
| `--start` | `-S` | `BOOL` | `false` |
| `--delay` | `-d` | `FLOAT` | `0` |
| `--breakpoints` | `-B` | `STR[]` | — |
| `--edgedata-files` | `--data-files`, `-m` | `FILE` | — |
| `--alternative-net-file` | `-N` | `FILE` | — |
| `--selection-file` | — | `FILE` | — |
| `--demo` | `-D` | `BOOL` | `false` |
| `--disable-textures` | `-T` | `BOOL` | `false` |
| `--registry-viewport` | — | `BOOL` | `false` |
| `--window-size` | — | `STR[]` | — |
| `--window-pos` | — | `STR[]` | — |
| `--tracker-interval` | — | `TIME` | `1` |
| `--gui-testing` | — | `BOOL` | `false` |
| `--gui-testing-debug` | — | `BOOL` | `false` |
| `--gui-testing.setting-output` | — | `FILE` | — |
