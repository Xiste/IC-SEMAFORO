# Métricas do experimento PPO

Atualização da interface: a [tabela completa de coleta](catalogos/metrics_catalog.csv) inclui paradas/pico na rede inteira, CO, HC, NOx, PMx, eletricidade e, para viagens concluídas, desvio populacional, mínimo, máximo e mediana além de média/p95. O [inventário TraCI](catalogos/traci_queries.csv) lista consultas disponíveis, sem presumir que todas sejam coletadas. Veja [escopo e instruções](interface_catalogos.md).

Cada episódio conserva `run_config.json`, `routes.rou.xml`, `tripinfo.xml` e,
quando habilitado, `actions.csv`. O treino grava `manifest.json` com configuração,
versões, hashes da rede, planilha e mapeamento e hiperparâmetros PPO. A avaliação
grava `runs.csv`, `signals.csv`, `aggregate.csv`, `summary.json`, `report.md` e
`comparison.png`. `aggregate.csv` contém média, desvio padrão amostral e número
de observações por controlador. O relatório compara PPO, programa da rede e
heurística reativa de filas (`queue_actuated`).

| Métrica | Fonte e cálculo | Unidade/limite |
| --- | --- | --- |
| `planned_vehicles` | Viagens geradas ou estimativa dos fluxos no XML | veículos; estimativa sinalizada |
| `departed`, `arrived`, `unfinished`, `pending_departure` | Contadores TraCI e expectativa ao fim do horizonte | veículos; `unfinished` inclui apenas os que partiram |
| `wait_vehicle_seconds` | Incrementos do tempo de espera dos veículos ativos por passo | veículo s; não equivale à espera de viagens concluídas |
| `queue_vehicle_seconds`, `peak_halted_vehicles` | Soma e pico dos parados nas faixas controladas | veículo s e veículos; sobreposição de faixas entre sinais pode duplicar contagem |
| `active_vehicle_seconds` | Veículos ativos × passo | veículo s; aproximação de tempo em trânsito no horizonte |
| `mean_lane_speed_meters_per_second`, `mean_lane_occupancy_percent` | Amostras TraCI por faixa e passo, agrupadas por sinal | m/s e %; média simples das amostras |
| `phase_N_seconds` | Contagem de passos em cada fase por sinal | s; tempo dentro do horizonte simulado |
| `mean_` e `p95_` de `travel_time_seconds`, `trip_waiting_seconds`, `time_loss_seconds`, `stops`, `route_length_meters`, `departure_delay_seconds` | Atributos do `tripinfo` das viagens concluídas | s, número ou m; nulo se não houve chegada |
| `tripinfo_completed`, `tripinfo_unfinished` | Viagens com `arrival` válido ou `-1` | veículos; não inclui partidas ainda pendentes |
| `co2_grams`, `fuel_grams` | Taxas TraCI por veículo integradas pelo passo | g; coleta opcional e dependente do modelo de emissão |
| `teleports_started`, `collision_vehicles` | Eventos TraCI por passo | eventos/veículos; coleta opcional |
| `real_seconds`, `cpu_seconds`, `peak_rss_mb` | Relógio e `psutil` do processo Python e filhos | s, s, MiB; pico amostrado, não pico absoluto |
| `reward` | Soma da função de recompensa configurada | adimensional; depende dos pesos e escalas |

As métricas por faixa, emissão, eventos, recursos e ações podem ser ligadas ou
desligadas em `metrics` ou na interface. Os contadores são amostrados por passo
SUMO; o custo real varia com o número de veículos. Viagens incompletas ficam
fora de médias e percentis de viagem. Três sementes padrão de avaliação permitem
medir dispersão, mas não garantem poder estatístico. A igualdade de demanda
planejada entre PPO e referência é verificada por semente. Não se interpreta
uma diferença curta ou sem chegadas como ganho de desempenho.
