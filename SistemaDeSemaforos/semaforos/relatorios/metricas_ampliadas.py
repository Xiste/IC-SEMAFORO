"""Catálogo e legendas das métricas da janela, faixas, movimentos e dinâmica."""
EXTENDED = {}


def add(name, label, description, unit, flag=None):
    EXTENDED[name] = (label, description, unit, flag)


for name, label in (('warmup_seconds', 'Aquecimento'), ('measurement_start_seconds', 'Início da medição'),
                    ('measurement_end_seconds', 'Fim da medição'), ('measured_seconds', 'Duração medida')):
    add(name, label, 'Tempo no relógio do episódio; a duração medida exclui aquecimento.', 's')
add('measurement_complete', 'Janela completa', 'O fim da janela configurada foi alcançado.', 'sim/não')
for name, label in (('vehicles_at_window_start', 'Veículos no início da janela'), ('vehicles_at_window_end', 'Veículos no fim da janela'),
                    ('total_departed', 'Inseridos no episódio inteiro'), ('total_arrived', 'Chegadas no episódio inteiro'),
                    ('mean_active_vehicles', 'Veículos ativos médios'), ('mean_global_queue_vehicles', 'Fila média global')):
    add(name, label, 'Totais inteiros incluem períodos fora da janela; médias usam apenas o tempo medido.', 'veículos')
for name, label in (('arrivals_per_hour', 'Taxa de chegadas'), ('departures_per_hour', 'Taxa de inserções')):
    add(name, label, 'Eventos da janela divididos pelo tempo efetivamente medido.', 'veículos/h')
add('arrival_service_ratio_percent', 'Atendimento na janela', 'Chegadas / (veículos inicialmente presentes + inserções na janela).', '%')
add('aggregate_wait_seconds_per_arrival', 'Espera agregada por chegada', 'Inclui espera de viagens incompletas; não é a média individual do tripinfo.', 's/chegada')

for name, label, description, unit in (
    ('vehicle_distance_meters', 'Distância acumulada', 'Integral da velocidade no tempo, aproximando a distância percorrida na janela.', 'm'),
    ('moving_vehicle_seconds', 'Tempo de veículos em movimento', 'Integral de veículos acima do limiar de parada.', 'veículo·s'),
    ('long_wait_vehicle_seconds', 'Exposição a espera longa', 'Integral dos veículos cuja espera consecutiva supera o limiar.', 'veículo·s'),
    ('maximum_vehicle_wait_seconds', 'Maior espera consecutiva', 'Espera de um veículo presente na janela; pode ter começado no aquecimento.', 's'),
    ('all_vehicles_stopped_seconds', 'Todos os veículos parados', 'Tempo com veículos ativos e todos parados; não comprova gridlock.', 's'),
    ('lane_id', 'Faixa SUMO', 'Identificador da faixa de entrada.', 'ID'),
    ('movement_id', 'Movimento SUMO', 'Controlador e índice do link; aproximações identificadas pelo próximo semáforo.', 'ID'),
    ('direction', 'Conversão SUMO', 'Código SUMO da conversão; não representa direção geográfica.', 'código'),
    ('movement_flow_available', 'Fluxo por movimento disponível', 'Os detectores internos são exclusivos do movimento; caso contrário fluxo é nulo.', 'sim/não'),
    ('maximum_jam_length_meters', 'Maior fila em metros', 'Maior congestionamento contíguo amostrado pelo E2 ao longo da faixa.', 'm'),
    ('maximum_jam_vehicles', 'Maior fila contígua em veículos', 'Maior congestionamento amostrado pelo E2.', 'veículos'),
    ('spillback_seconds', 'Indicador de transbordamento', 'Ocupação acima do limiar ou fila E2 cobrindo ao menos 90% da faixa.', 's'),
    ('mean_density_vehicles_per_kilometer', 'Densidade média da faixa', 'Média de veículos presentes / comprimento da faixa.', 'veículos/km'),
    ('mean_speed_meters_per_second', 'Velocidade média dos veículos', 'Distância integrada / tempo de veículos ativos.', 'm/s'),
    ('mean_occupancy_percent', 'Ocupação média', 'Ocupação da faixa ponderada pelo tempo medido.', '%'),
    ('green_seconds', 'Tempo de verde', 'Tempo em estado G/g do movimento na janela.', 's'),
    ('red_seconds', 'Tempo de vermelho', 'Tempo em estado r/R do movimento na janela.', 's'),
    ('yellow_seconds', 'Tempo de amarelo', 'Tempo em estado y/Y do movimento na janela.', 's'),
    ('unused_green_seconds', 'Verde sem demanda observada', 'Verde sem veículo associado; não prova desperdício por si só.', 's'),
    ('green_utilization_percent', 'Verde com demanda observada', 'Fração do verde com ao menos um veículo associado ao movimento.', '%'),
    ('maximum_continuous_red_seconds', 'Maior vermelho contínuo', 'Sequência contínua de vermelho, limitada pela janela.', 's'),
    ('green_with_blocked_downstream_seconds', 'Verde com saída congestionada', 'Verde com fila no movimento e ocupação alta na saída; indicador de bloqueio.', 's'),
    ('maximum_downstream_occupancy_percent', 'Maior ocupação a jusante', 'Máximo da ocupação nas saídas do movimento.', '%'),
    ('queue_pressure_vehicle_seconds', 'Pressão de filas', 'Integral da fila associada ao movimento menos veículos parados nas saídas.', 'veículo·s'),
    ('throughput_vehicles_per_hour', 'Fluxo atendido do movimento', 'Veículos distintos nos E1 internos / tempo medido.', 'veículos/h'),
    ('discharge_vehicles_per_green_hour', 'Passagens por hora de verde', 'Passagens / verde observado; não equivale a fluxo de saturação.', 'veículos/h de verde')):
    add(name, label, description, unit, 'collect_extended')
for name, label, description, unit in (
    ('stop_events', 'Novas paradas observadas', 'Transições movimento-parada amostradas; eventos entre passos podem ser perdidos.', 'paradas'),
    ('hard_braking_vehicle_seconds', 'Exposição a frenagem forte', 'Integral dos veículos abaixo do limiar negativo de aceleração.', 'veículo·s'),
    ('speeding_vehicle_seconds', 'Exposição acima da velocidade permitida', 'Integral dos veículos acima de 105% da velocidade permitida TraCI.', 'veículo·s'),
    ('ttc_proxy_below_threshold_vehicle_seconds', 'TTC longitudinal baixo', 'Gap / velocidade de aproximação ao líder dentro de 100 m. Não inclui conflitos laterais nem certifica risco.', 'veículo·s'),
    ('mean_absolute_jerk_meters_per_second_cubed', 'Variação média absoluta da aceleração', 'Diferença de acelerações consecutivas / passo.', 'm/s³')):
    add(name, label, description, unit, 'collect_vehicle_dynamics')
for name, label, unit in (('vehicle_class', 'Classe de veículo', 'classe'), ('observed_unique_vehicles', 'Veículos distintos observados', 'veículos'),
                          ('halted_vehicle_seconds', 'Tempo parado por classe', 'veículo·s')):
    add(name, label, 'Medição por classe SUMO durante a janela.', unit, 'collect_vehicle_classes')
add('active_person_seconds', 'Tempo de pessoas ativas', 'Integral das pessoas presentes na janela.', 'pessoa·s')
add('walking_person_seconds', 'Tempo de pessoas caminhando', 'Integral das pessoas com velocidade acima de 0,1 m/s.', 'pessoa·s')
for suffix, label, unit in (('jam_length_meters', 'comprimento da fila E2', 'm'), ('queue_vehicles', 'fila da faixa', 'veículos'),
                            ('global_queue_vehicles', 'fila global', 'veículos'), ('pedestrian_travel_time_seconds', 'duração das caminhadas', 's')):
    for stat, title in (('mean', 'Média'), ('max', 'Máximo'), ('p50', 'Percentil 50'), ('p90', 'Percentil 90'), ('p95', 'Percentil 95'), ('p99', 'Percentil 99')):
        add(f'{stat}_{suffix}', f'{title} de {label}', 'Estatística de amostras da janela; caminhadas consideram chegadas na janela.', unit,
            'collect_extended' if suffix != 'pedestrian_travel_time_seconds' else None)
for name in ('co2_grams', 'fuel_grams', 'co_grams', 'hc_grams', 'nox_grams', 'pmx_grams', 'electricity_wh'):
    add(f'{name}_per_kilometer', f'{name} por distância', 'Total na janela / distância integrada; vazio sem distância ou coleta.',
        'Wh/km' if name == 'electricity_wh' else 'g/km', 'collect_emissions')
