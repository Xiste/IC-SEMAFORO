# Referência detalhada dos parâmetros da simulação

Este é o anexo técnico do [item 3: parâmetros usados](parametros_simulacao.md). Comece pelo item 3 para acompanhar a execução em ordem.

Este documento registra **todos os parâmetros definidos pelo projeto** na configuração atual, incluindo geração de veículos, chamada ao `sumo`, controle por TraCI, avaliação e treinamento. Foi conferido com `config/cenario.json` e os módulos de `semaforos/` em 25/09/2026. O executável instalado é `sumo` 1.27.1.

O [catálogo das 462 opções possíveis de `sumo`](catalogo_completo_sumo.md) é o anexo do item 2 da documentação. Nesta execução, **11 opções de `sumo` recebem valor explícito**: dez pelo pipeline e uma porta escolhida pelo TraCI. As outras **451 opções não são sobrescritas pelo projeto** e seguem os padrões da instalação. Esse número não inclui parâmetros de `randomTrips.py`, dados dentro da rede XML ou decisões feitas por TraCI.

## 3.1. Arquivos e seleção do cenário

O arquivo [`config/cenario.json`](../config/cenario.json) é lido por [`configuracao.py`](../semaforos/configuracao.py). Caminhos `network` e `plans` são resolvidos em relação à pasta `config/`.

| Parâmetro | Valor atual | Como é usado |
| --- | --- | --- |
| `network` | `../dados/rede/uberlandia.vehicular.families.16_2_4.net.xml` | Rede viária e programas semafóricos carregados pelo SUMO e pela `sumolib`. |
| `plans` | `../dados/planos/RondonNorte.xlsx` | Planilha de referência lida antes da execução. |
| `plan_id` | `4` | Seleciona o plano da planilha registrado em `inputs.json`. **Não aplica** automaticamente suas fases ao SUMO. |
| `duration_seconds` | `600` s | Fim da geração de viagens e fim da simulação. |
| `step_seconds` | `1` s | Passo do SUMO e fator de integração dos veículos parados. |
| `seeds` | `[11]` | Cada semente gera uma execução; o mesmo valor alimenta `randomTrips.py`, `sumo` e a busca de candidatos. |
| `targets[0].name` | `Av. Rondon Pacheco x Rua Paraná` | Nome usado para localizar o plano de referência na planilha. |
| `targets[0].tls_id` | `FAM_RONDON_PARANA` | ID do semáforo que recebe o programa candidato via TraCI. |
| `targets[0].phase_indices` | `[0, 1, 2, 3, 4, 5]` | Fases cujas durações podem variar no treino. |

`targets` pode conter outros semáforos após conferir os IDs e as fases no [inventário](../dados/inventario.json). Os demais semáforos da rede não recebem `setProgramLogic` e mantêm seus programas originais.

### Programa-base do alvo no arquivo de rede

`FAM_RONDON_PARANA` usa o programa estático `1624`, defasagem `0` s e ciclo inicial de `90` s. A sequência e os estados das fases permanecem iguais nos candidatos; o treino altera somente suas durações.

| Índice | Estado SUMO | Tipo | Duração inicial |
| ---: | --- | --- | ---: |
| 0 | `GGGGrrr` | verde | 41 s |
| 1 | `yyyyrrr` | amarelo | 3 s |
| 2 | `rrrrrrr` | totalmente vermelho | 1 s |
| 3 | `rrrrGGG` | verde | 41 s |
| 4 | `rrrryyy` | amarelo | 3 s |
| 5 | `rrrrrrr` | totalmente vermelho | 1 s |

O vermelho de um movimento também dura enquanto outro movimento recebe verde ou amarelo. Os índices 2 e 5 são intervalos **totalmente vermelhos** de limpeza, não tempos vermelhos independentes por via. O ciclo total muda quando as durações mudam.

## 3.2. Demanda de veículos

[`demanda.py`](../semaforos/demanda.py) usa `demand.mode` para escolher um dos modos abaixo.

| Parâmetro | Valor atual | Uso |
| --- | --- | --- |
| `demand.mode` | `random` | Executa `randomTrips.py` e roteia as viagens. |
| `demand.vehicles_per_hour` | `360` | Convertido para intervalo de partidas: `3600 / 360 = 10` s. É uma taxa total de teste, não contagem observada. |
| `demand.flows` | `[]` | Ignorado no modo `random`. |

### Argumentos efetivamente enviados a `randomTrips.py`

| Argumento | Valor nesta execução | Origem |
| --- | --- | --- |
| `-n` | Caminho resolvido de `network` | Cenário |
| `-o` | `trips.trips.xml` na pasta da execução | Pipeline |
| `--route-file` | `routes.rou.xml` na pasta da execução | Pipeline; pede rotas válidas ao gerador |
| `-b` | `0` s | Fixo no código |
| `-e` | `600` s | `duration_seconds` |
| `-p` | `10` s | `3600 / vehicles_per_hour` |
| `--seed` | `11` | `seeds` |

`randomTrips.py` usa seu próprio conjunto de opções padrão para tudo que não foi passado acima. Como viagens desconectadas podem ser descartadas pelo roteador, a quantidade efetivamente inserida deve ser conferida em `metrics.json`. A [documentação de `randomTrips.py`](https://sumo.dlr.de/docs/Tools/Trip.html) detalha esses parâmetros.

### Modo alternativo `flows`

Se `demand.mode` passar a `flows`, `vehicles_per_hour` do modo aleatório deixa de ser usado. Cada item de `demand.flows` deve fornecer `from_edge`, `to_edge` e `vehicles_per_hour`. O pipeline valida IDs de vias e taxa positiva e escreve `<flow>` em `routes.rou.xml` com `id=flow_N`, `begin=0`, `end=duration_seconds` e `vehsPerHour` igual à taxa informada. O modo atual **não** contém fluxos por via; eles serão preenchidos quando houver demanda medida.

## 3.3. Opções passadas ao `sumo`

[`simulacao.py`](../semaforos/simulacao.py) monta a chamada sem abrir `sumo-gui`. `traci.start()` acrescenta `--remote-port` com uma porta livre. Os caminhos das saídas mudam a cada execução.

| Opção do `sumo` | Valor efetivo atual | Origem |
| --- | --- | --- |
| `--net-file` (`-n`) | Rede de `network` | Cenário |
| `--route-files` (`-r`) | `routes.rou.xml` gerado | Demanda |
| `--begin` | `0` s | Fixo no código |
| `--end` | `600` s | `duration_seconds` |
| `--step-length` | `1` s | `step_seconds` |
| `--seed` | `11` | `seeds` |
| `--tripinfo-output` | `tripinfo.xml` na pasta da execução | Pipeline |
| `--summary-output` | `summary.xml` na pasta da execução | Pipeline |
| `--statistic-output` | `statistics.xml` na pasta da execução | Pipeline |
| `--no-step-log` | `true` | Fixo no código |
| `--remote-port` | Porta TCP livre, escolhida em tempo de execução | Adicionada por `traci.start()` |

Essas são as **11 opções explícitas** entre as 462 do template local. Nenhum `.sumocfg` fixo é passado ao `sumo`. As outras opções, como comportamento de veículos, roteamento, emissões e dispositivos, seguem os valores padrão da instalação e estão listadas com tipo e valor no template em [configuracoes_sumo.md](catalogo_completo_sumo.md). A [documentação oficial de configuração](https://sumo.dlr.de/docs/Basics/Using_the_Command_Line_Applications.html) explica a precedência entre arquivo e linha de comando.

## 3.4. Controle e medições por TraCI

Após abrir a conexão, a simulação usa as seguintes chamadas e regras. Elas **não são opções de linha de comando**.

| Chamada ou regra | Valor/uso atual |
| --- | --- |
| `trafficlight.getAllProgramLogics(tls_id)[0]` | Lê o primeiro programa do semáforo selecionado. |
| `trafficlight.setProgramLogic(tls_id, logic)` | Aplica as durações do candidato às fases 0–5; estado e ordem são mantidos. |
| `trafficlight.getControlledLanes(tls_id)` | Define as faixas usadas na pontuação, removendo IDs repetidos. |
| `simulationStep()` | Avança um passo por chamada até `simulation.getTime() >= 600` s. |
| `simulation.getDepartedNumber()` | Conta veículos que entraram no passo. |
| `simulation.getArrivedNumber()` | Conta veículos que concluíram no passo. |
| `lane.getLastStepHaltingNumber(lane)` | Conta veículos parados em cada faixa controlada no passo. |
| `vehicle.getSpeed(vehicle) < 0.1` | Medida global alternativa somente se `targets` não selecionar faixas. |
| `traci.close()` | Encerra conexão e processo ao final. |

As métricas de cada execução são:

```text
unfinished = max(0, departed - arrived)
target_halted_vehicle_seconds = soma_em_cada_passo(
    step_seconds × veículos_parados_nas_faixas_controladas
)
score = target_halted_vehicle_seconds
      + unfinished × unfinished_penalty_seconds
```

Na configuração atual, `unfinished_penalty_seconds = 120`. Se não houver faixas controladas selecionadas, o código usa `global_halted_vehicle_seconds` no lugar do termo local de parada. O objetivo do treino é **minimizar** `score`. Para várias sementes, usa a média aritmética das pontuações. Os números `departed`, `arrived`, `unfinished` e os termos da pontuação são gravados em `metrics.json`.

## 3.5. Parâmetros do treinamento que afetam as simulações

[`treinamento.py`](../semaforos/treinamento.py) usa os campos abaixo de `training` em `config/cenario.json`.

| Parâmetro | Valor atual | Efeito |
| --- | ---: | --- |
| `iterations` | 20 | Número de candidatos medidos no SUMO. |
| `warmup_random` | 10 | Tentativa 0 usa a rede base; tentativas 1–9 são escolhidas aleatoriamente; da 10 em diante a rede neural escolhe. |
| `candidate_pool` | 100 | Combinações propostas a cada escolha neural, antes da medição da melhor no SUMO. |
| `minimum_green_seconds` | 8 s | Piso de verde, também limitado por 60% do tempo original. |
| `minimum_yellow_seconds` | 3 s | Piso de amarelo; a duração original também é piso. |
| `minimum_all_red_seconds` | 1 s | Piso do intervalo totalmente vermelho; a duração original também é piso. |
| `unfinished_penalty_seconds` | 120 s | Penalidade da pontuação por veículo que entrou e não chegou até o fim. |

Limites calculados para o semáforo atual:

| Fases | Tipo | Original | Intervalo de candidatos |
| --- | --- | ---: | ---: |
| 0 e 3 | Verde | 41 s | 24–58 s |
| 1 e 4 | Amarelo | 3 s | 3–5 s |
| 2 e 5 | Totalmente vermelho | 1 s | 1–3 s |

Detalhes fixos no código, sem campo próprio no JSON: gerador de candidatos `random.Random(seeds[0])`, inicialização do PyTorch com `torch.manual_seed(seeds[0])`, rede MLP com camadas `6 → 32 → 16 → 1` e ativações ReLU, otimizador Adam com taxa de aprendizado `0,01`, 150 épocas por ajuste e perda quadrática média. A entrada da MLP é cada duração dividida pelo limite superior de sua fase; o alvo é a pontuação dividida pelo desvio padrão das pontuações já observadas, com piso de `1`. O modelo é ajustado novamente a partir das amostras acumuladas quando precisa escolher outro candidato e após a última tentativa.

A MLP **prevê a pontuação para orientar a busca**. Cada pontuação registrada vem do SUMO; o modelo não faz controle adaptativo durante os passos da simulação. A primeira tentativa com os tempos originais funciona como referência.

## 3.6. Parâmetros de execução e arquivos produzidos

[`pipeline.py`](../pipeline.py) aceita `inspect`, `options`, `run` ou `train`. `--config` seleciona outro cenário; `--candidate` fornece durações para `run`; `--output` escolhe uma pasta nova. Sem `--output`, a pasta fica em `resultados/AAAAMMDD_HHMMSS`. A pasta escolhida não pode existir antes da execução.

```powershell
cd C:\Projetos\IC-SEMAFORO\SistemaDeSemaforos
python pipeline.py run --config config/cenario.json
python pipeline.py train --config config/cenario.json
```

Cada simulação grava `inputs.json`, `trips.trips.xml` e `routes.rou.xml` no modo aleatório, `tripinfo.xml`, `summary.xml`, `statistics.xml` e `metrics.json`. `run` agrega as sementes em `summary.json`. `train` grava ainda `dataset.jsonl`, `best_candidate.json` e `surrogate_model.pt`; cada tentativa e semente têm subpastas próprias. `inputs.json` guarda demanda, semente, candidato, alvo e plano de referência para rastrear a execução.

## Limites da interpretação

As opções não sobrescritas do SUMO são **padrões da versão instalada**, não escolhas medidas para Uberlândia. A rede SUMO e a planilha diferem no cruzamento selecionado: o programa da rede tem dois verdes e ciclo de 90 s; o plano 4 da planilha tem quatro estágios e ciclo de 110 s. O tráfego atual é gerado para teste, sem contagens reais por via. Assim, o inventário acima descreve exatamente o experimento de software atual; ainda não valida os tempos encontrados como operação real.
