# Funcionamento do projeto

Documentação canônica para executar, compreender, validar e continuar o sistema.
O pipeline gera viagens aleatórias, calcula rotas, executa SUMO e consolida
observações. A rede física é única; demanda e perfil semafórico são independentes.

```text
rede Rondon Norte → demanda random → current ou settran → SUMO → métricas
```

| Local | Responsabilidade |
| --- | --- |
| `SistemaDeSemaforos/network/` | Rede física compartilhada e programas de referência. |
| `SistemaDeSemaforos/demand/` | Geração de viagens e roteamento. |
| `SistemaDeSemaforos/simulation/` | Episódios, baseline e validação/conversão SETTRAN. |
| `SistemaDeSemaforos/metrics/` | Configuração de observações, agregação, apresentação e gravação. |
| `docs/settran/settran_programs.json` | Fonte normalizada, vínculos físicos e suplementos operacionais. |
| `docs/catalogos/` | Referências detalhadas de configuração e métricas; não são configuração de execução. |
| `scripts/`, `tests/` | Manutenção/reprodução e testes automatizados. |
| `outputs/` | Episódios e baselines gerados; não versionados. |

## Preparação e comandos

Requisitos: Python 3.10+, `make`, SUMO com `randomTrips.py` e `duarouter`.
O código de produção usa a biblioteca padrão Python. `sumo` e `duarouter`
devem estar no `PATH`; GUI exige `sumo-gui` e sessão gráfica.
A instalação de referência é **SUMO 1.27.1**.

```bash
export SUMO_HOME=/usr/share/sumo
sumo --version
make test
make run-random
make run-random RUN_ARGS='--episodes 3'
make run-random RUN_ARGS='--gui'
make run-random RUN_ARGS='--duration 30 --period 5'
make run-random RUN_ARGS='--duration 30 --period 5 --end 60'
make demand-random DEMAND_ARGS='--duration 60 --period 5'
```

Os episódios são sequenciais; cada um sorteia uma seed e possui pasta exclusiva.
Sem `--end`, SUMO termina ao esgotar a demanda. Com horizonte explícito, podem
restar viagens incompletas. `make demand-random` gera somente viagens/rotas,
sem simular. `make test` não abre SUMO e impede caches Python.

| Opção do runner | Padrão | Efeito |
| --- | --- | --- |
| `--episodes` | `1` | Quantidade de episódios. |
| `--gui` | Desativado | Abre/fecha GUI em cada episódio. |
| `--duration` | `7200` | Janela de partidas da demanda, em segundos. |
| `--period` | `1.5` | Intervalo entre partidas, em segundos. |
| `--end` | Sem limite explícito | Limite de tempo simulado. |
| `--net-file` | Rede Rondon Norte | Rede de entrada; identifica o baseline. |
| `--output-dir` | `outputs/outputs-random/` | Subpasta desse diretório para organizar resultados. |
| `--metrics-profile` | `core` | `core` ou `full`; seleciona observações. |
| `--signal-profile` | `current` | `current` ou `settran`; seleciona programação semafórica. |
| `--settran-plan` | Sem plano presumido | ID oficial para teste fixo SETTRAN; inválido com `current`. |
| `--settran-intersection` | Todas as interseções do plano | Nome exato na fonte; opção repetível para recorte explícito. Inválida com `current`. |

Consulte `python3 -m SistemaDeSemaforos.simulation.episode_runner --help`.
O gerador independente também aceita `--seed`, `--net-file` e `--output-dir`;
o runner sorteia seeds e não possui opção CLI de replay.
As opções do projeto não equivalem a todas as opções SUMO.

## 1. Mapa e condições de referência

A rede é
[`uberlandia.vehicular.families.16_2_4.net.xml`](../../SistemaDeSemaforos/network/uberlandia.vehicular.families.16_2_4.net.xml):
Rondon Norte, confirmada pelo responsável. O XML define geometria, faixas,
conexões, permissões e programas. Coordenadas locais estão em metros
(UTM zona 22/WGS84). Não há fonte OSM de construção versionada no repositório.

A malha tem **36 TLS**, **314 índices**, **316 conexões controladas** e
**43 travessias**: 34 TLS fisicamente OK e dois com evidência insuficiente,
sem erro estrutural comprovado. TLS pode atender vários nós. Correções físicas
valem para todos os perfis e são reproduzíveis pelo
[`corretor determinístico`](../../scripts/correct_signal_infrastructure.py).

`current` usa programas de referência SUMO, inclusive prioridades `O/o`;
os tempos não são certificados como operação real. Batalhão permanece verde
no regime normal, sem acionamento emergencial. Travessias existentes ficam na
rede; índices pedestres sem programação comprovada permanecem vermelhos.
Os avisos correspondentes não rebaixam a infraestrutura veicular.

**Baseline** reúne rede/programas, versões, código, defaults SUMO e parâmetros.
A referência usa passo de 1 s, seed interna SUMO 23423, Krauss e
`time-to-teleport=300` s. Defaults dependem do tipo/classe; não devem ser
extrapolados para modelos ausentes. Correções físicas podem alterar rotas e
resultados; isso não altera o gerador de demanda.

Mudanças de demanda, seed, horizonte, rede ou programação definem condições
experimentais diferentes; registre-as. Opções de observação/GUI alteram custo e
volume, preservando a dinâmica. Passo, modelos e teleporte exigem validação.

O [catálogo de configurações](../catalogos/configuration_catalog.csv) seleciona
campos úteis à decisão; a [referência completa](../catalogos/configuration_reference.csv)
cobre opções SUMO/ferramentas, CLI, XML e defaults. Ambos vêm do mesmo gerador.
Para leitura profunda, consulte uso atual, defaults, impacto de alterações e
fontes/hashes. Default ausente não é zero; opção catalogada não é flag do nosso CLI.

### Pendências físicas e limites conhecidos

- **Europa × Benjamim:** a representação legada da Europa conserva uma faixa e
  27,78 m/s, ainda sem comprovação. Faltam fotos/croqui das duas pistas e placas
  R-19; não transferir o limite da Benjamim.
  [Imagens consultadas](https://www.mapillary.com/app/?pKey=27886827067676861).
- **Maria das Dores Dias × Segismundo:** faltam placas/setas vistas desde Maria.
  Esquerdas 3/11 chegam à faixa comum; 4/12 à faixa bus. As restrições OSM
  8531027/8531030 partem da Segismundo e não comprovam proibição desde Maria.
  [Imagem consultada](https://www.mapillary.com/app/?pKey=1252092370200250).
- **Suíça/Viena:** diagnósticos com veículos longos apresentaram colisões em
  condições específicas; a causa física não foi comprovada. Esses resultados
  independentes não justificam alterar geometria para liberar SETTRAN nem
  certificam a rede para qualquer carga/modelo.

Rio de Janeiro e Batalhão possuem controles físicos, mesmo sem plano no XLSX.
A existência foi documentada pela Prefeitura:
[Rondon × Rio de Janeiro, 2020](https://www.uberlandia.mg.gov.br/2020/06/10/mais-de-350-semaforos-ja-contam-com-botoeiras-para-travessia-de-pedestres/)
e [5º Batalhão, 2025](https://www.uberlandia.mg.gov.br/2025/06/11/bombeiros-terao-controle-de-sistema-de-fechamento-semaforico-nas-imediacoes-do-5o-batalhao-para-garantir-agilidade-e-seguranca-na-saida-de-viaturas/).
Não existe programação SETTRAN inventada para esses sinais.

### Perfil semafórico SETTRAN

`current` é padrão e independente dos dados SETTRAN. `settran` seleciona
programação semafórica para teste de plano fixo; a demanda continua `random`.
As nove interseções documentadas abrangem **17 TLS**, todos fisicamente OK.
Vínculos e tempos ficam em [`settran_programs.json`](../settran/settran_programs.json).

A V2 está consolidada no limite dos dados disponíveis. O conversor está
implementado, mas **nenhum plano real 2/4/16/24 pode ser executado hoje**:
faltam permissões, intervalos/transições e referência da defasagem.
A agenda ausente não bloqueia, por si só, um teste fixo.

```bash
make run-random RUN_ARGS='--signal-profile current --duration 30 --period 5 --end 60'
make run-random RUN_ARGS='--signal-profile settran --settran-plan 2 --duration 30 --period 5 --end 60'
make run-random RUN_ARGS='--signal-profile settran --settran-plan 2 --settran-intersection "Av. Rondon Pacheco x Rua Belém" --duration 30 --period 5 --end 60'
```

Os dois comandos SETTRAN são recusados com os dados atuais, antes de sortear
seed, gerar demanda ou iniciar SUMO. Selecionar um plano significa executá-lo
deliberadamente, sem afirmar em qual horário real estaria ativo. O recorte por
interseção é explícito e repetível; não existe subconjunto automático ou
fallback. Os demais TLS continuam `current` e são registrados.

Das 29 descrições veiculares, 28 possuem cobertura física vinculada:
12 `CONFIRMADO` e 16 `INFERIVEL_COM_SEGURANCA`. Falta identificar o estágio D
Antônio Crescêncio/Rotary: o nome da fonte corresponde à saída, enquanto a
entrada controlada é Rotary Club. Os cinco controles auxiliares de
Porto Alegre/Niterói e os controles João Naves ainda precisam de escopo/coordenação.
Cobertura física não demonstra permissão simultânea: Benjamim e Niterói incluem
conversões conflitantes com retas. Não converter todos os vínculos em `G`.
SUMO distingue verde protegido `G` de permissivo `g`:
[estados e fases](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html#signal-state-definitions).

#### Contrato para receber os dados restantes

O [settran_programs.json](../settran/settran_programs.json), schema 2, separa fonte,
suplemento operacional e agenda. Os 36 programas preservam os IDs 2/4/16/24,
ciclos, defasagens, 128 descrições e todos os 512 tempos/células do XLSX. A ordem
das descrições é apresentação da fonte; não demonstra sequência operacional.
As três discrepâncias de vermelho pedestre e Nascimento/Santos ficam registradas,
sem correção automática. As três descrições pedestres são conservadas fora do
escopo veicular, sem inventar atendimento ou rebaixar a infraestrutura.

Cada `programs[]` identifica `intersection`, `plan_id` e todos os `sumo_tls_ids`
geográficos. `stages[]` registra `scope`, `mapping_status`, `mapping_note` e
`sumo_links` físicos. O campo **`operational` permanece `null` até receber
dados comprovados**, com o seguinte contrato:

| Campo de `operational` | Dados necessários |
| --- | --- |
| `network_sha256` | Hash da rede à qual os índices foram associados. |
| `tls_ids`, `current_tls_ids` | Partição explícita dos TLS geográficos: quais recebem SETTRAN e quais conservam `current`, comprovada por `evidence.control_scope`. |
| `stage_links` | Mapa de `stage_id` para listas de `{tls_id, link_indices}` operacionais, com grupos e movimentos demonstrados. |
| `phases` | Intervalos na ordem comprovada: `stage_id`, `transition` (`green`, `yellow`, `clearance_red`), `duration_seconds`, `states` por TLS aplicado e `source_reference`. Estados `r/G/g/y` completos, incluindo continuidade entre intervalos. |
| `offset_reference` | Referência comum ou `by_tls`: `reference_type` (`clock`/`tls_event`), `reference_id`, `reference_time_seconds`, `direction` (`delay`/`advance`), `target_phase_index` e `source_reference`; `reference_event` identifica o evento quando o tipo é `tls_event`. |
| `evidence` | `movement_mapping`, `control_scope`, `permissions`, `sequence`, `transitions`, `offset_reference`, cada um com `status` (`CONFIRMADO`/`INFERIVEL_COM_SEGURANCA`) e `source_reference`. |

A defasagem numérica da planilha permanece em `offset_seconds`; o suplemento
deve demonstrar seu marco e sentido. `reference_time_seconds` é o instante
comprovado do evento no relógio do teste, fornecido explicitamente; o código não
calcula esse alinhamento a partir do nome do TLS. Não há default de referência. A conversão
usa `SUMO offset = (referência + defasagem com sinal - posição do evento alvo) mod ciclo`;
atraso soma a defasagem, adiantamento a subtrai.
em [settran_configuration.py](../../SistemaDeSemaforos/simulation/settran_configuration.py)
confere hash, escopo, grupos, durações, ciclo, estados, conflitos/prioridades e
transições; somente então emite programas adicionais para o mesmo SUMO e a mesma
rede. A validação é por plano/interseção/TLS, antes de seed, demanda ou simulação.
O erro identifica o requisito ausente. Sem `--settran-intersection`, todas as
nove interseções precisam estar prontas; seleção menor exige nomes explícitos.
Nenhum TLS desconhecido fica silenciosamente com `current`.

`schedule=null` significa **agenda não fornecida**; `schedule=[]` significa
**agenda fornecida vazia**, sem fallback para o primeiro plano. O contrato recebe
linhas com `intersection`, `start_time`, `end_time`, `plan_id`, `weekdays` ISO 1–7,
`exceptions` (`date`, `plan_id` ou `null`), `valid_from`, `valid_until` e
`source_reference`. Horários usam `HH:MM:SS` e faixas [início, fim); faixas que
cruzam meia-noite são divididas. A vigência usa datas ISO inclusivas; uma exceção
troca/ativa a faixa naquela data ou, com `null`, cancela sua ocorrência.
`operational_day_start` e `initial_plan_id` também continuam
nulos. A validação dessa estrutura não ativa relógio, scheduler ou troca automática.
Esses comportamentos dependerão da agenda real e da política comprovada de troca segura.

Ao receber a fonte complementar, preencha `operational` na chave
`intersection + plan_id` e, separadamente, a agenda. O importador conserva esses
suplementos ao regenerar e recusa deriva dos valores/células originais. O fluxo
é **preencher contrato → validar → selecionar explicitamente**; a emissão de
programas fixos já está implementada. Agenda futura usará tempo simulado SUMO,
sem contextualizar artificialmente a demanda.

#### Dados externos necessários

- Diagrama/exportação veicular por plano: grupos/movimentos/focos, permissões
  protegidas ou cedentes, ordem, amarelos, limpeza e continuidade.
- Identidade Rotary D e escopo/coordenação dos controles auxiliares e João Naves.
- Defasagem: evento alvo, relógio/TLS/evento de referência, alinhamento e
  sentido atraso/adiantamento.
- Agenda: interseção, plano, início/fim, dias, vigência, exceções e política de
  troca segura. Marco do dia/plano inicial precisam de fonte; não são presumidos.

O [Manual Brasileiro de Sinalização Semafórica, Volume V](https://www.gov.br/transportes/pt-br/assuntos/transito/arquivos-senatran/docs/copy_of___05___MBST_Vol._V___Sinalizacao_Semaforica.pdf)
e SUMO fundamentam os conceitos, sem comprovar a referência particular da SETTRAN.
Dados pedestres originais permanecem conservados, fora desta V2 veicular.

## 2. Demanda random

Origens/destinos são sorteados; partidas são regulares. A demanda serve para
exercitar o cenário e ainda não é calibrada por contagens reais.

O runner sorteia a seed e chama `generate_random_demand`; `randomTrips.py`
sorteia as viagens e `duarouter` calcula/valida rotas. SUMO carrega o
`random.rou.xml` resultante.

Nosso código chama `randomTrips.py` uma vez. A ferramenta chama `duarouter`
para rotear e novamente com `--write-trips` para validar viagens; pode filtrar
solicitações inviáveis. Os dois XMLs finais são conferidos antes de substituir
uma demanda anterior.

| Arquivo | Função | Uso |
| --- | --- | --- |
| `random.trips.xml` | Viagens verificadas: origem, destino e partida. | Intermediário do roteamento e conferência do sorteio. |
| `random.rou.xml` | Veículos e sequências de vias a percorrer. | **Demanda carregada pela simulação.** |

### De onde vêm as 4.800 viagens

Padrões: janela de partidas de **7.200 segundos** e intervalo de **1,5 segundo**.
Assim, `7200 / 1.5 = 4800` solicitações, com partidas de `0` a `7198.5` segundos.
O total válido depende da conectividade da rede. Viagens geradas, veículos
inseridos e viagens concluídas são quantidades diferentes.

`make demand-random` prepara apenas o par avulso em `SistemaDeSemaforos/demandas/`.
Uma nova geração no mesmo destino substitui o par anterior. `make run-random`
gera diretamente em `outputs/outputs-random/<episódio>/inputs/`, com uma seed
nova por episódio. O runner não lê nem preenche os arquivos avulsos.

A classe gerada é `passenger`. A seed da demanda é sorteada entre 0 e `2**31 - 1`;
a seed interna SUMO é registrada separadamente e permanece no default.
O gerador aceita `--seed`; o runner não possui CLI de replay. Os destinos de
dados são ignorados pelo Git por serem gerados, não por serem templates ou caches.

### Dados reais preservados

`RondonNorte.xlsx` é a fonte original dos planos. `Medicoes_5_6.csv` contém
medições locais e permanece como fonte para futura calibração/validação.
A associação dos pontos 5/6 a Niterói é textual, não comprovada por coordenadas
ou TLS. A convenção de `vehicle_total` e a unidade de `speed_pxm` não estão
confirmadas; zero não prova velocidade nula em m/s.
Essas observações não alimentam `random`, não geram OD e não representam
demanda global nem agenda dos planos.

## 3. Execução e APIs utilizadas

O pipeline usa **CLI e XML**, sem HTTP ou TraCI/libsumo nos episódios.
Ferramentas SUMO são instaladas separadamente; chamadas usam listas de argumentos
via `subprocess.run`, sem shell intermediário ou controlador Python.

| Interface | Chamada no projeto | Responsabilidade |
| --- | --- | --- |
| [randomTrips.py](https://sumo.dlr.de/docs/Tools/Trip.html) | `generate_random_demand` em `demand/random_demand_generator.py` | Rede/janela/período/seed/classe → viagens e rotas XML. |
| [duarouter](https://sumo.dlr.de/docs/duarouter.html) | Indiretamente por randomTrips, inclusive `--write-trips` | Roteia e valida viagens; pode descartar solicitações inviáveis. |
| [sumo](https://sumo.dlr.de/docs/sumo.html)/[sumo-gui](https://sumo.dlr.de/docs/sumo-gui.html) | `run_simulation` em `simulation/episode_runner.py` | Executa rede, rotas e observações; aguarda término e confere retorno. |
| Template/configuração SUMO | `prepare_baseline` e `run_simulation` | Registra versão/defaults uma vez por baseline e opções explícitas por episódio. |
| Conversão SETTRAN | `prepare_selection`/`compile_selection` em `simulation/settran_configuration.py` | Valida e emite XML adicional; programa e observações compartilham `--additional-files`. |

O gerador recebe caminhos, retorna `Path` das rotas e pode preencher `metadata`
(parâmetros, seed, contagens, comando, hash e duração) e `log_file`.
`run_simulation` retorna `None` após sucesso; com `recording_dir`, preserva
configuração/observações e preenche `metadata`.
A biblioteca padrão oferece leitura XML incremental, JSON/gzip, hashes, relógio
monotônico, criação exclusiva de episódios e publicação atômica de arquivos.

TraCI, libsumo, netconvert/netedit são ferramentas de manutenção/validação,
não controles por timestep no runner. O probe opcional
`audit_configuration_catalog.py --probe-defaults` usa TraCI em t=0 para medir
defaults e larguras omitidas, sem avançar simulação. O auditor de métricas
inspeciona schemas/métodos/docstrings, sem conectar ao SUMO.
Esses utilitários usam bibliotecas de `$SUMO_HOME/tools`; `sumolib` também é
dependência interna das ferramentas SUMO.

## 4. Métricas: seleção e interpretação

O [catálogo único de métricas](../catalogos/metrics_catalog.csv) contém **1.498 entradas**:
atributos de 25 schemas de saída, outras fontes, derivados, 596 getters TraCI e
consultas adicionais. Famílias e fontes alternativas não são grandezas independentes.
Filtre `priority`, `enabled_profiles` e `entity`; `result_name_regex` relaciona
famílias aos nomes exportados. Fonte, chamada, unidade, natureza, custo e
agregação de cada métrica ficam no CSV. Unidades não confirmadas são marcadas.

- **Disponível:** consta no catálogo, inclusive getters TraCI e modelos ausentes.
- **Habilitado:** o perfil solicita sua fonte; não significa que haverá eventos.
- **Coletado:** aparece nos arquivos efetivamente produzidos. O manifesto lista
  `collection.profile`, `native_outputs` e `entity_counts`; os JSONs contêm os valores.
- **Derivado:** calculado pelo coletor a partir dessas observações, com fórmula
  e população indicadas no catálogo.

`CORE` prioriza observações úteis em toda execução. `OPTIONAL` depende da pergunta
científica; `DIAGNOSTIC` serve à validação; `CATALOG_ONLY` mantém conhecimento sem
coleta repetida. Prioridade é uma recomendação, não um mecanismo automático.
Essa classificação de **coleta** do catálogo permanece igual; é diferente da
prioridade numérica de **apresentação** de 1 a 4 em `metrics.json`.

`metrics/sumo_output_configuration.py:prepare_outputs` recebe a pasta e o perfil de coleta,
prepara as opções e grava `observations.add.xml`. Retorna argumentos para o SUMO.
SUMO produz os arquivos durante a execução;
`metrics/episode_metrics_collector.py:collect_episode` coordena sua leitura após o término.
Este recebe `raw/`, a rede e o perfil; retorna dicionários de métricas globais
e entidades. O catálogo distingue fontes habilitadas das apenas disponíveis.

| Interface/documentação | Opção ou elemento SUMO | Leitor em `episode_metrics_collector.py` / dados utilizados |
| --- | --- | --- |
| [Summary](https://sumo.dlr.de/docs/Simulation/Output/Summary.html) | `--summary-output` | `_summary`: contagens, velocidade da rede, tempos e custo por passo. |
| [Tripinfo](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html) | `--tripinfo-output`, `.write-unfinished`, `.write-undeparted`; `--device.emissions.probability 1` | `_trips`: viagens, espera, atraso, distância e emissões acumuladas. |
| [Statistic](https://sumo.dlr.de/docs/Simulation/Output/StatisticOutput.html) | `--statistic-output` | `_statistics`: segurança, motivos de teletransporte e desempenho. |
| [Vias/faixas](https://sumo.dlr.de/docs/Simulation/Output/Lane-_or_Edge-based_Traffic_Measures.html) | Perfil `full`: `<edgeData>` / `<laneData>`, `period="1"`, `excludeEmpty="true"`, `withInternal="true"` | `_traffic`: medidas de tráfego por intervalo. |
| [Filas](https://sumo.dlr.de/docs/Simulation/Output/QueueOutput.html) | `--queue-output` | `_queues`: extensão e espera por faixa, aproximação e controlador. Saída nativa experimental. |
| [Semáforos](https://sumo.dlr.de/docs/Simulation/Output/Traffic_Lights.html) | `<timedEvent type="SaveTLSStates">` | `_tls`: programas, fases, estados, mudanças e durações; registra inclusive transições entre fases com luzes iguais. |
| [FCD](https://sumo.dlr.de/docs/Simulation/Output/FCDOutput.html) | Perfil `full`: `--fcd-output`; `.acceleration`, `.signals`, `.distance`, `.speed-relative` | `_trajectories`: observações por veículo/passo. |
| [Emissões](https://sumo.dlr.de/docs/Simulation/Output/EmissionOutput.html) | Perfil `full`: `--emission-output` | `_emissions`: taxas instantâneas; totais de viagem já existem em Tripinfo no perfil `core`. |
| [Mudanças de faixa](https://sumo.dlr.de/docs/Simulation/Output/Lanechange.html) | `--lanechange-output` | `_events`: quantidade, motivos, velocidade e distâncias nos eventos. |
| [Colisões](https://sumo.dlr.de/docs/Simulation/Output/Collisions.html) | `--collision-output` | `_events`: eventos e distribuições numéricas; envolvidos permanecem no XML. |
| [Rotas efetivas](https://sumo.dlr.de/docs/Simulation/Output/VehRoutes.html) | `--vehroute-output`; `.exit-times`, `.write-unfinished`, `.route-length` | Preservadas em `raw/vehicle_routes.xml.gz`, sem segunda consolidação das rotas. |

### Regras de agregação

- Observações regulares: `_min`, `_mean`, `_max`, `_samples`. Média aritmética
  das amostras válidas a cada **1 segundo**, passo atual.
- Contadores cumulativos de Summary: **último valor**, nunca soma. Contagens
  de eventos por intervalo: soma. Espera/perda de tempo e exposição de
  meanData também têm `_sum`.
- Fluxo: `total * 3600 / duração_simulada`, em veículos/h.
  `completed_throughput_vehicles_per_hour` usa chegadas ao destino; saídas de
  vias incluem passagens intermediárias e têm significado diferente.
- Intervalos vazios omitidos pelo SUMO contribuem zero para contagens,
  densidade, ocupação, exposição, espera e perda de tempo. Nunca recebem
  velocidade zero artificial. `traffic_speed_mean` é média temporal das médias;
  `traffic_speed_vehicle_seconds_weighted_mean` pondera por `sampledSeconds`.
- Densidade: veículos/km; `laneDensity`: veículos/km/faixa; ocupação: %;
  exposição, espera e perda de tempo: veículo-segundos por intervalo.
  Não some vias com suas próprias faixas: representam o mesmo tráfego.
- Sem amostra válida: `_samples: 0`, sem extremos/média. Sentinelas negativas
  de ausência são excluídas; desaceleração, coordenadas negativas e recuperação
  de energia continuam válidas.
- Viagens `completed`, `unfinished`, `undeparted` e `vaporized` são separadas.
  `vaporized="end"` indica término da execução. Partidas futuras podem não
  aparecer em tripinfo; a demanda registra o planejado. `arrived`, não `ended`,
  conta chegadas ao destino.
- `meanWaitingTime` de Summary significa atraso para **inserção**; espera no
  trânsito vem de tripinfo. Médias acumuladas de inserção/viagens removidas
  usam somente o último valor.
- Estados são categorias: integram-se tempos e contam-se mudanças reais.
  A observação é por passo: a alternativa que grava só mudanças de luzes
  perderia transições entre fases com estados iguais.
  Durações de fase incluem trechos iniciais/finais parciais, marcados por
  `phase_duration_includes_boundary_fragments`. IDs de programa/estado viram
  hex nos nomes para preservar distinções como `G`/`g`; o valor legível acompanha.
- Ruído: `10 * log10(média(10 ** (dBA/10)))`. Direção usa média circular;
  sinais usam histogramas. Não se faz média aritmética de dBA nem de categorias.

O perfil padrão é `core`; `full` acrescenta séries detalhadas de vias, faixas e
veículos. As fontes comuns mantêm sua frequência. Um perfil não recupera dados
não observados. Filas nativas são experimentais; contagem de fila contínua por
E2 e SSM (TTC/PET/DRAC) exigem configuração/validação próprias. Bateria, recarga,
transporte público e pedestres não foram acrescentados só para gerar métricas.
Emissões e ruído são estimativas de modelos, não medições ambientais.

## 5. Resultados e por que são separados

```text
outputs/baselines/<hash>/
├── baseline.json         # versões, hashes, rede/controladores e defaults
├── network.net.xml       # rede exata compartilhada
├── sumo_options.xml      # defaults desta instalação
└── code/                 # código de produção utilizado

outputs/outputs-random/[subpasta/]<UTC>_seed-<seed>_<UUID>/
├── metrics.json          # resultados globais e contexto
├── entities.json.gz      # consolidado por entidade
├── manifest.json         # comandos, hashes e referência ao baseline
├── generation.log, sumo.log
├── inputs/
│   ├── random.trips.xml, random.rou.xml
│   ├── observations.add.xml, sumo_config.sumocfg
│   └── settran.add.xml, settran_programs.json  # somente SETTRAN validado
└── raw/
    ├── summary.xml.gz, trips.xml.gz, statistics.xml
    ├── queues.xml.gz, tls.xml.gz, lanechanges.xml.gz
    ├── collisions.xml.gz, vehicle_routes.xml.gz
    └── edges.xml.gz, lanes.xml.gz, fcd.xml.gz, emissions.xml.gz  # apenas full
```

`raw/` conserva observações, inclusive temporais. Os consolidados não têm linhas
por timestep; entidades ficam separadas/comprimidas para permitir leitura rápida
do resumo global. Baselines guardam cenário e código uma vez, sem duplicar a
rede em cada episódio; sua integridade é conferida na reutilização.

O manifesto registra parâmetros, argv, horários, versões, hashes e arquivos.
`baseline.id` e o hash de `baseline.manifest` vinculam o episódio ao cenário.
O argv da geração registra a pasta temporária utilizada; os destinos finais
também estão disponíveis. Opção efetiva = `baseline.json.sumo_defaults`
sobreposto por `manifest.json.simulation.configured_options`. A configuração
XML salva guarda opções explícitas; caminhos podem ser absolutos.

### Formato dos consolidados

`metrics.json` schema 2 conserva `metrics`: nomes técnicos, tipos e valores.
Cada registro recebe legenda/unidade/classificação e ordem de apresentação:

```json
{
  "schema_version": 2,
  "metrics": [{
    "metric_name": "completed_trip_time_loss_mean",
    "data_type": "float",
    "value": 12.84,
    "label_pt": "Tempo médio perdido (viagens concluídas)",
    "description_pt": "Média do tempo perdido entre viagens concluídas.",
    "unit": "s",
    "kind": "result",
    "category": "performance",
    "priority": 1
  }],
  "entity_metrics_file": "entities.json.gz"
}
```

O valor acima é ilustrativo. Tipos: `int`, `float`, `bool`, `string`;
NaN/infinito são recusados. Campos condicionais permanecem ausentes quando não
há fonte/população; apresentação não muda fórmulas, valores ou coleta.

| Campo | Interpretação |
| --- | --- |
| `metric_name` | Chave técnica estável; não selecionar pela posição na lista. |
| `label_pt`, `description_pt` | Nome legível e significado/população/agregação. |
| `unit` | Unidade; `null` se não aplicável/não confirmada. Amostras têm unidade própria. |
| `kind` | `result`, `context` ou `diagnostic`. |
| `category` | `performance`, `operation`, `integrity`, `diagnostic` ou `context`. |
| `priority` | Importância de apresentação, 1–4; independente de CORE/OPTIONAL. |

A ordem inicia por perda/espera médias de viagens concluídas, vazão e chegadas;
depois traz comportamento operacional, integridade e diagnóstico/contexto.
Leia também `status`, `error`, incompletas/não iniciadas, colisões e
teletransportes. `completed` não garante que todas as viagens chegaram.
`seed`, `simulation_seed`, `vehicles_generated` e tempos continuam na lista.

Médias `completed_*` descrevem apenas viagens concluídas; confrontar com
incompletas/teletransportes evita viés. Vazão de chegadas usa toda a duração
simulada: comparar demanda, horizonte e critério de término compatíveis.
`vehicles_halting_*` mede veículos parados, não comprimento de fila.
`queue_observation_steps` indica cobertura da coleta, não congestionamento.

O catálogo mantém definições técnicas completas. As legendas e ordem de leitura
ficam em [`metric_presentation.py`](../../SistemaDeSemaforos/metrics/metric_presentation.py),
incluído no baseline; o runner não carrega CSVs. Nomes globais sem definição de
apresentação são recusados. Consumidores devem indexar por `metric_name`,
respeitar `data_type`/`value` e tolerar campos adicionais.
Leitores estritos do schema 1 precisam aceitar o schema 2; outputs históricos
não são regravados. Não há dashboard/treinamento implementado nem certificação
de consumidores externos não disponíveis.

`entities.json.gz` permanece schema 1: `entities` organiza registros
`metric_name/data_type/value` por `vehicles`, `lanes`, `edges`,
`traffic_lights`, `approaches`, `intersections`.
Chave única: escopo + ID + nome da métrica. Aproximações usam
`controlador/via_de_entrada`; interseções agrupam suas faixas de entrada.

`metrics/` separa solicitação (`sumo_output_configuration.py`), agregação
(`episode_metrics_collector.py`), apresentação (`metric_presentation.py`)
e validação/gravação (`metrics_storage.py`).
Manifestos são schema 2, independente dos schemas dos dois consolidados.

### Tempos, falhas e preservação

IDs de episódio combinam UTC/microssegundos, seed e UUID; criação exclusiva
impede sobrescrita. Horários são UTC; duração usa `perf_counter`.
Tempos distinguem preparação, geração, SUMO, agregação, exportação e inventário.
Parsers são subetapas da agregação, não parcelas adicionais.
O total exclui apenas a escrita final dos dois JSONs pequenos que guardam sua
própria duração. Tempo SUMO inclui startup e escrita nativa.

Falhas interrompem o lote e preservam arquivos/contexto; leia `error` e logs.
`Ctrl+C` registra interrupção; encerramento forçado pode deixar `running`.
Saída obrigatória ausente ou período incompatível impede consolidação.
XMLs são lidos incrementalmente; memória depende das entidades/métricas.
Limitar avisos repetidos no log não altera regras SUMO de teletransporte.

Outputs são ignorados pelo Git, mas experimentos não são caches.
Preserve episódio e baseline referenciado; não edite baseline existente.
`outputs/benchmarks/` só aparece no benchmark, não na execução cotidiana.
O [ZIP de fontes históricas](../historico/auditoria_historica.zip) conserva
tabelas originais, índice/hashes e instruções próprias; há medições/notas únicas.
Sua nomenclatura é histórica e não descreve o estado atual.

## Validação e manutenção

```bash
make test
PYTHONDONTWRITEBYTECODE=1 python3 scripts/correct_signal_infrastructure.py --check
PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit_settran.py --check
PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit_configuration_catalog.py --check
PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit_metrics_catalog.py
make run-random RUN_ARGS='--duration 30 --period 5'
```

A suíte cobre demanda, runner, baseline, contrato SETTRAN, infraestrutura e
métricas, sem abrir SUMO. A prova curta executa SUMO real. Para validar estrutura
com schema e API SUMO/TraCI, confira XML, TLS, controlledLinks e estados; a suíte
não substitui essa conferência externa.

O check SETTRAN confere fonte, mapeamentos e contrato de agenda; não declara
plano pronto. A seleção explícita valida cada plano/interseção/TLS, estados,
transições, ciclo, conflitos e referência de offset. Com os dados reais,
os quatro IDs devem continuar recusados antes da demanda/simulação.
Uma prova com suplemento sintético valida o conversor, sem certificar plano real.

Para conferir outputs e custo de observação:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/audit_metrics_catalog.py --episodes outputs/outputs-random
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmark_observation_pipeline.py --repetitions 2
```

O benchmark preserva evidências em `outputs/benchmarks/`: mesma demanda de
400 viagens, observação mínima/core/full e duas repetições em ordem invertida.
`--seed` pertence ao benchmark/gerador, não ao runner. `full` acrescenta séries
densas e aumenta custos de coleta, agregação e exportação; escolher pela pergunta
experimental. Observações não devem alterar a dinâmica.

Após trocar a instalação, revise fontes/defaults e revalide observadores.
`audit_configuration_catalog.py --probe-defaults` atualiza medições em t=0;
`--refresh-descriptions` consulta documentação oficial versionada e exige rede.
São tarefas de manutenção, não etapas por episódio.

## Reproduzir uma execução

1. Preserve a pasta do episódio e o baseline indicado em `manifest.json.baseline`,
   com ferramentas externas na versão registrada.
2. Reutilize `inputs/random.rou.xml` e `network.net.xml` do baseline.
   `manifest.json.simulation.command` guarda os argumentos; a configuração SUMO
   guarda opções explícitas. SETTRAN validado também exige o suplemento congelado
   `inputs/settran_programs.json` e os programas `inputs/settran.add.xml`.
3. Troque todos os destinos de saída, inclusive no adicional de observação.
   Caminhos podem ser absolutos; executar configuração antiga sem adaptá-los
   pode sobrescrever a evidência.
4. Para refazer a geração, use seed/parâmetros registrados e mesmas rede/ferramentas:

```bash
make demand-random DEMAND_ARGS='--seed 123 --duration 7200 --period 1.5 --net-file outputs/baselines/ID/network.net.xml --output-dir SistemaDeSemaforos/demandas/reproducao'
```

O exemplo exige substituir seed e ID. Executar novamente `make run-random`
não reproduz a demanda anterior, pois sorteia nova seed.
Apague somente temporários próprios comprovados; não remova baseline necessário
a um episódio preservado.

## Continuidade

Agora: rede comum, demanda aleatória, observações/métricas, seleção explícita
e contrato SETTRAN com bloqueios corretos. Dados futuros entram em
`operational` e `schedule`, são validados e usam o pipeline existente.

Demandas reais/contextuais, reconstrução/estimação de fluxo, Hazarika, RL,
Acciai/TFR, outros controladores e treinamento permanecem futuros.
Nenhuma dessas funcionalidades está implementada.
