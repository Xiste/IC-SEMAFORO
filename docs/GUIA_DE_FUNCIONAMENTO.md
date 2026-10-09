# Funcionamento do projeto

Este é o manual operacional: [executar](#1-quero-executar),
[entender](#2-quero-entender), [experimentar](#3-quero-experimentar) e
[evoluir](#4-quero-evoluir). O projeto gera demanda aleatória, executa SUMO e
consolida observações da rede Rondon Norte, em Uberlândia.

## 1. Quero executar

### Preparação

Instale Python 3.10+, `make` e SUMO com `randomTrips.py` e `duarouter`.
`sumo` e `duarouter` precisam estar no `PATH`; `SUMO_HOME` aponta para a
instalação que contém `tools/randomTrips.py`. A instalação de referência é
SUMO **1.27.1**. O código de produção usa a biblioteca padrão Python.

```bash
export SUMO_HOME=/usr/share/sumo
sumo --version
make test
```

Para abrir a interface visual, instale também `sumo-gui` e use uma sessão gráfica.
Todos os targets Make impedem a criação de caches Python.

### Comandos do dia a dia

Execute na raiz do repositório:

```bash
make run-random
make run-random RUN_ARGS='--episodes 10'
make run-random RUN_ARGS='--episodes 10 --metrics-profile full'
make run-random RUN_ARGS='--gui'
```

O primeiro comando executa um episódio `random`/`current`/`core`. Cada época é
um episódio independente, com demanda e seed novas; dez épocas não são dez
passos de simulação nem treinamento. A execução é sequencial.

Para uma **prova curta explicitamente solicitada**, altere os parâmetros:

```bash
make run-random RUN_ARGS='--duration 30 --period 5'
```

Esse comando serve para conferir a instalação. Os experimentos padrão continuam
com janela de demanda de **7.200 s**, período de partidas de **1,5 s** e término
natural. Escolher `core` ou `full` altera somente as observações.

A interface Make tem três comandos: `run-random` executa; `test` verifica;
`demand-random` gera somente viagens/rotas quando elas forem necessárias
separadamente. As opções estão no mesmo runner:

```bash
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --help
```

### Onde ficam os resultados

A execução normal grava tudo em arquivos, sem relatório ou progresso no terminal.
Erros continuam sendo informados. Cada chamada cria uma pasta exclusiva em
`outputs/outputs-random/`; ordene as pastas pelo nome para encontrar o lote mais
recente. Seus nomes começam pela data e hora UTC.

```text
outputs/outputs-random/<lote>/
├── <episódio_1>/
│   ├── metrics.json              # métricas explicadas, seeds e execução
│   ├── generation.log, sumo.log   # mensagens das ferramentas
│   └── raw/, entities.json.gz     # somente full após sucesso
└── <episódio_2>/ ...
```

Abra `metrics.json` da época desejada: ele reúne resultados, seeds, tempos,
nomes, descrições e unidades. O bloco `execution` registra a versão SUMO,
a rede selecionada, os comandos e as opções aplicadas.

As viagens, rotas e configurações XML de entrada são temporárias nos dois perfis.
Após sucesso, o `core` também remove seus XMLs de observação; conserva os
indicadores globais calculados. O `full` conserva os XMLs de observação e
entidades para análise detalhada. Falhas preservam arquivos disponíveis para
diagnóstico. Os dados de configuração e as seeds permanecem nos resultados,
sem cópias da rede ou do código. Outputs ficam fora do Git.

### Material para o professor

A pasta `docs/` reúne o guia, os dados SETTRAN e duas planilhas CSV (UTF-8, separador vírgula):
[CONFIGURACOES.csv](CONFIGURACOES.csv), com 65 configurações nativas
relevantes ao cenário veicular, e [METRICAS.csv](METRICAS.csv), com
65 indicadores coletáveis. As configurações distinguem o padrão de fábrica do
SUMO 1.27.1, o uso em cada perfil e como alterar no projeto. As métricas indicam
fonte, unidade, população, perfil e localização nos resultados.
`valor_no_core` e `valor_no_full` descrevem as condições padrão (`current`);
argumentos explícitos podem substituí-las. Saídas brutas do `core` são temporárias.

### Defaults e tempos

Padrões confirmados: 1 episódio, demanda de **7.200 s**, partidas a cada
**1,5 s**, início em t=0, **timestep de 1 s** e término natural (`end=None`;
SUMO `-1`). Perfis padrão: `current` e `core`. Sem `--end`, a simulação pode
ultrapassar 7.200 s para concluir viagens. O perfil de observação não muda
esses parâmetros ou o critério de encerramento.

Os resultados separam janela da demanda (`demand_duration_seconds`), duração
simulada (`simulation_duration_seconds`) e processamento real
(`execution_time_seconds`). O tempo real inclui preparação, demanda, SUMO,
consolidação e gravação de entidades; exclui a gravação final de `metrics.json`
e a limpeza dos temporários. Durações usam relógio monotônico;
horários são UTC. A fronteira é a mesma nos dois perfis.

Estas são todas as opções operacionais do runner, além de `--help`:

| Opção | Padrão | Uso |
| --- | --- | --- |
| `--episodes` | `1` | Quantidade de episódios independentes. |
| `--duration` | `7200` s | Janela de partidas da demanda, a partir de t=0. |
| `--period` | `1.5` s | Intervalo programado entre partidas. |
| `--end` | Ausente | Término natural; um valor impõe horizonte finito. |
| `--metrics-profile` | `core` | Seleciona observações `core` ou `full`. |
| `--signal-profile` | `current` | Programas da rede ou `settran` validado. |
| `--settran-plan` | Ausente | ID oficial escolhido explicitamente; exige `settran`. |
| `--settran-intersection` | Todas do plano | Nome exato e repetível para selecionar interseções; exige `settran`. |
| `--gui` | Desativado | Abre e fecha `sumo-gui` por episódio. |
| `--net-file` | Rede Rondon Norte do projeto | Seleciona a rede física. |
| `--output-dir` | `outputs/outputs-random/` | Destino dos lotes dentro dessa árvore. |

## 2. Quero entender

### Arquitetura e responsabilidades

```text
rede física única + demanda random + current/settran + core/full
                              ↓
                            SUMO
                              ↓
                   coleta e consolidação
                              ↓
                  arquivos de resultados
```

| Local | Responsabilidade |
| --- | --- |
| `SistemaDeSemaforos/network/` | Rede física compartilhada e programas `current`. |
| `SistemaDeSemaforos/demand/random_demand_generator.py` | Geração de viagens e rotas. |
| `SistemaDeSemaforos/simulation/episode_runner.py` | Episódios, comandos, ciclo de vida e resultados. |
| `SistemaDeSemaforos/simulation/settran_configuration.py` | Validação e conversão de planos SETTRAN. |
| `SistemaDeSemaforos/metrics/sumo_output_configuration.py` | Fontes nativas solicitadas por perfil. |
| `SistemaDeSemaforos/metrics/episode_metrics_collector.py` | Leitura XML e cálculos das métricas. |
| `SistemaDeSemaforos/metrics/metric_presentation.py` | Significados, unidades e apresentação. |
| `SistemaDeSemaforos/metrics/metrics_storage.py` | Contrato e gravação dos resultados. |
| `docs/settran_programs.json` | Planos normalizados e contrato operacional SETTRAN. |
| `scripts/`, `tests/` | Manutenção e validação, fora do caminho normal de execução. |
| `outputs/` | Lotes de resultados gerados. |

O fluxo usa **CLI e XML**, com processos aguardados via `subprocess.run`.
Nosso código seleciona entradas, registra parâmetros, valida, agrega e grava.
O SUMO calcula movimentação, seguimento, filas, viagens e eventos. Não há
controlador Python por timestep ou consultas TraCI contínuas nos episódios.

### Caminho de execução

1. Você inicia com `make run-random`, passando as opções por `RUN_ARGS`.
2. O runner valida parâmetros, rede e seleção semafórica; SETTRAN exige plano válido.
3. Cria a pasta do lote e a do primeiro episódio em `outputs/outputs-random/`.
4. Sorteia a seed da demanda e consulta em memória a versão e os defaults SUMO.
5. `randomTrips.py` gera as viagens; `duarouter` calcula e valida as rotas.
6. Prepara programas semafóricos e observações conforme `current`/`settran` e `core`/`full`.
7. Executa `sumo` ou `sumo-gui` com a rede e a demanda; por padrão, termina naturalmente.
8. O coletor lê as saídas nativas e calcula as métricas.
9. Grava `metrics.json` e, no `full`, entidades e observações; remove temporários após sucesso.
10. Repete a partir do sorteio para os próximos episódios, reutilizando os defaults em memória.

TraCI, `sumolib` e `netconvert/netedit` são recursos da instalação SUMO usados
quando necessários por ferramentas de manutenção/validação. Não são necessários
novos mecanismos de coleta para apresentar o que já está nos XMLs.

### Rede Rondon Norte e referência `current`

A rede é
[`uberlandia.vehicular.families.16_2_4.net.xml`](../SistemaDeSemaforos/network/uberlandia.vehicular.families.16_2_4.net.xml),
carregada por `--net-file`. A região foi confirmada pelo responsável como Rondon
Norte. O XML contém geometria, faixas, conexões, permissões e programas;
coordenadas locais estão em metros (UTM zona 22/WGS84). Não há fonte OSM de
construção versionada no repositório.

São **36 TLS** (controladores semafóricos SUMO), **314 índices**, **316 conexões
controladas** e **43 travessias**. Há 34 TLS fisicamente OK e dois com evidência
insuficiente, sem erro estrutural comprovado. Um TLS pode atender vários nós.
Correções físicas são comuns a `current`/`settran` e reproduzíveis por
[`correct_signal_infrastructure.py`](../scripts/correct_signal_infrastructure.py).

`current` usa os programas de referência SUMO, inclusive prioridades `O/o`;
os tempos não são certificados como operação real. Batalhão permanece verde
no regime normal, sem acionamento emergencial. Travessias existentes ficam
na rede; índices pedestres sem programação comprovada permanecem vermelhos.
Avisos correspondentes não rebaixam a infraestrutura veicular.

A referência mantém modelo Krauss e `time-to-teleport=300` s. Defaults dependem
do tipo/classe; não devem ser extrapolados para modelos ausentes. Mudanças de
rede, demanda, seed, programação, horizonte ou modelos definem outras condições
experimentais e exigem registro. Observar mais dados aumenta custo, sem alterar
essas condições.

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

### Demanda e seeds

A demanda `random` sorteia origens/destinos e programa partidas regulares.
Serve para exercitar o cenário; ainda não é calibrada por contagens reais.
`randomTrips.py` chama `duarouter` para rotear e novamente com `--write-trips`
para validar viagens. Solicitações inviáveis podem ser filtradas. Nosso código
confere os dois XMLs finais antes de substituir uma demanda avulsa anterior.

| Arquivo | Conteúdo e uso |
| --- | --- |
| `random.trips.xml` | Origem, destino e partida das viagens verificadas; conferência do sorteio. |
| `random.rou.xml` | Veículos e sequências de vias; **demanda carregada pelo SUMO**. |

`7200 / 1.5 = 4800` solicitações, com partidas programadas de 0 a 7198,5 s.
O total válido depende da conectividade; gerados, inseridos e concluídos são
populações diferentes. A classe gerada é `passenger`.

Cada episódio sorteia a seed da demanda entre 0 e `2**31 - 1`. A seed interna
SUMO permanece no default e é registrada separadamente. O gerador aceita
`--seed`; o runner continua sorteando e não possui flag CLI de replay.

`make demand-random` gera somente o par avulso em `SistemaDeSemaforos/demandas/`;
repetir no mesmo destino substitui o par anterior. `make run-random` gera direto
em `inputs/` temporário do novo episódio, sem ler nem preencher o par avulso.
Essa pasta é removida após sucesso; as seeds permanecem nos resultados.

### Dados reais preservados

[RondonNorte.xlsx](../RondonNorte.xlsx) é a fonte original dos planos.
[Medicoes_5_6.csv](../Medicoes_5_6.csv) contém
medições locais e permanece como fonte para futura calibração/validação.
A associação dos pontos 5/6 a Niterói é textual, não comprovada por coordenadas
ou TLS. A convenção de `vehicle_total` e a unidade de `speed_pxm` não estão
confirmadas; zero não prova velocidade nula em m/s.
Essas observações não alimentam `random`, não geram uma matriz origem/destino (OD)
e não representam demanda global nem agenda dos planos.

### Configurações e métricas

Os CSVs de `docs/` são referências para consulta; editá-los não configura o
programa. `CONFIGURACOES.csv` contém 65 opções selecionadas e seus padrões da
versão de referência. Todas as opções nativas podem ser consultadas com
`sumo --save-template -`. O resultado guarda a versão SUMO, os parâmetros do
experimento e as opções explícitas em `execution.simulation.configured_options`;
rede e tipos veiculares também definem condições. Célula vazia no default de
arquivo significa que nenhum arquivo foi configurado. Opções nativas não
expostas pelo runner exigem alteração explícita no código; não são argumentos
adicionais aceitos por `RUN_ARGS`.

`core` conserva indicadores globais essenciais; `full` acrescenta detalhes
por entidade e observações brutas. Ambos usam a mesma demanda, duração e
semântica nas métricas comuns. Métricas não têm valor de fábrica: são calculadas
das observações. O CLI seleciona somente `--metrics-profile core/full`, sem
seleção individual de métricas ou alteração de fórmulas. Acrescentar uma fonte
exige suporte no código; recursos nativos como SSM/TTC/PET, detectores E2 e
bateria não estão integrados à coleta atual.

### O que SETTRAN altera no SUMO

`current` é padrão e independente dos dados SETTRAN. `settran` seleciona
programação semafórica para teste de plano fixo; a demanda continua `random`.
As nove interseções documentadas abrangem **17 TLS**, todos fisicamente OK.
Vínculos e tempos ficam em [`settran_programs.json`](settran_programs.json).

A V2 é a integração das configurações SETTRAN pedida pelo professor.
O conversor está implementado, mas **nenhum plano real 2/4/16/24 pode ser executado hoje**:
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

Um plano válido gera `inputs/settran.add.xml`, com um `<tlLogic>` por TLS
aplicado: `type="static"`, `programID="settran_<plano>"` e `offset` calculado.
Cada intervalo operacional vira `<phase duration="..." state="..." name="...">`.
O caractere de posição **i** em `state` controla as conexões cujo
`linkIndex=i` naquele TLS; esse índice também é chamado `signalIndex` nas
verificações. As posições não são números de fases nem IDs de vias.

Portanto, SETTRAN muda **programa selecionado, sequência de fases, duração,
estados dos sinais e defasagens**. Os XMLs adicionais carregados por
`--additional-files` conservam a rede física e o mecanismo de observação.
Demanda, rotas fornecidas, gerador, seeds, timestep, horizonte e critérios de
encerramento permanecem os do experimento. Os tempos de percurso e as filas
podem mudar como consequência esperada da programação semafórica.
Coordenação requer as referências comprovadas abaixo; a agenda ainda não
executa trocas automáticas.

#### Contrato para receber os dados restantes

O [settran_programs.json](settran_programs.json), schema 2, separa fonte,
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
O conversor em [settran_configuration.py](../SistemaDeSemaforos/simulation/settran_configuration.py)
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

### Consultar resultados

Abra `metrics.json` da época desejada. O schema 3 reúne `execution` e a lista `metrics`;
busque por `metric_name`, não pela posição. Cada registro tem tipo, valor,
legenda, descrição e unidade; unidade `null` não significa adimensional.
`execution` registra a versão SUMO, parâmetros, seeds, comandos, tempos e
cobertura da coleta. Os resultados não dependem de outro arquivo de configuração.

No `core`, `entity_metrics_file` é `null`. No `full`, aponta para
`entities.json.gz` (schema 1), com `vehicles`, `lanes`, `edges`, `traffic_lights`,
`approaches` e `intersections` sob `entities`; identifique cada medida por
escopo + ID + chave. Os arquivos em `raw/` guardam as observações nativas,
incluindo rotas realizadas com tempos de saída. O CSV de métricas indica onde
encontrar os 65 indicadores selecionados; o coletor também produz outros
agregados e registros de amostragem. Em falhas, consulte o erro e os logs;
entradas e observações disponíveis permanecem para diagnóstico.

## 3. Quero experimentar

### Alterar parâmetros deliberadamente

```bash
make run-random RUN_ARGS='--duration 1200 --period 3'
make run-random RUN_ARGS='--duration 1200 --period 3 --end 1500'
make run-random RUN_ARGS='--episodes 10 --metrics-profile full --output-dir outputs/outputs-random/estudo'
```

Duração maior prolonga a geração; período menor solicita mais veículos.
`--end` muda o horizonte e pode interromper viagens. São escolhas explícitas de
experimento, independentes do perfil de métricas. Não altere regras de teleporte,
modelos, rede ou semáforos para tornar os indicadores artificialmente melhores.

Use `core` para avaliação inicial e dez épocas rotineiras. Use `full` quando a
pergunta exigir localização de filas, fases, veículos, trajetórias, emissões ou
reanálise temporal. Dados não observados não podem ser recuperados a posteriori;
uma nova análise que precise deles exige outro experimento `full`.

### Interpretar e comparar épocas

Confira primeiro as condições e a população observada. Seeds diferentes
produzem experimentos independentes. Compare rede, demanda, programação, seed
SUMO, horizonte, timestep e encerramento. `status=completed` indica o término
do pipeline, não a calibração do cenário.

- Ausência de dado não significa zero. Cada média usa
  suas próprias amostras válidas (`_samples`); sem amostras não há média.
- Médias `completed_*` excluem viagens sem chegada, sem partida e remoções
  excepcionais (`vaporized`). Chegadas de Summary podem diferir dessa amostra.
  Compare também incompletas, descartes, colisões e teletransportes.
- Contadores acumulados de Summary usam o último valor. Velocidade global é
  média temporal; passos sem veículos não recebem velocidade zero artificial.
- A fila global soma comprimentos por faixa em cada passo; não é uma fila
  física única. Passos observados sem fila contribuem zero. Não some medidas
  de vias às das próprias faixas: representam o mesmo tráfego.
- No `full`, velocidade ponderada usa veículo-segundos; ruído usa média
  energética e direção usa média circular. Estados/sinais são categorias.
  Durações de fase podem incluir fragmentos nas bordas do episódio. Emissões
  e ruído são estimativas dos modelos, não medições ambientais.

### Retenção dos resultados

Conserve os lotes cujos dados ainda são úteis. As seeds, configurações e
métricas são os registros do experimento; não há arquivo de reprodução nem
cópias da rede e do código em outputs. A execução usa a rede atual do projeto.
Dados não coletados não podem ser recuperados de um resultado `core`.

Excluir uma pasta de lote descartado remove apenas seus resultados locais.
Não exclua os dados-fonte originais ou a rede para limpar resultados.
Uma nova chamada de `make run-random` sorteia novas seeds de demanda.

### Validar e medir custo

```bash
make test
python3 -B scripts/correct_signal_infrastructure.py --check
python3 -B scripts/audit_settran.py --check
python3 -B scripts/audit_results.py --episodes outputs/outputs-random/LOTE
```

Os testes cobrem demanda, runner, armazenamento, contrato SETTRAN, infraestrutura e
métricas; não abrem episódios SUMO. Os checks de manutenção usam a instalação
SUMO. A auditoria de resultados verifica contratos, tipos e completude; não substitui a interpretação científica. Para validar a execução
real, use a prova curta explicitamente parametrizada da seção 1.

O check SETTRAN verifica a fonte e o contrato; não declara planos reais prontos.
Os quatro planos 2/4/16/24 devem continuar recusados antes da demanda/simulação.
Testes com suplemento sintético verificam o conversor sem certificar plano real.
Para integridade externa, confira schema XML, TLS, controlledLinks e estados;
a suíte isolada não substitui essa validação com SUMO.

A comparação técnica entre observadores usa o benchmark existente:

```bash
python3 -B scripts/benchmark_observation_pipeline.py --duration 7200 --period 1.5 --seed 123 --repetitions 2
```

Ele usa a mesma rede, rotas, seed SUMO e término natural, invertendo a ordem na
segunda repetição. O controle interno `minimal` grava somente Tripinfo.
A comparação exige atributos das viagens e métricas comuns idênticos; terminar
sem erro não comprova equivalência. Tempos abrangem configuração, SUMO, coleta e
persistência, excluindo a geração compartilhada e a verificação. A memória é o
RSS máximo de processos novos: Python e SUMO separados, sem somar seus picos.

O destino padrão é `outputs/benchmarks/`; `--output-dir` permite reunir a
comparação numa pasta nova dentro do lote. `benchmark.json` guarda a medição;
`observation.json` guarda valores técnicos sem legendas. Os bytes medidos nesse
teste excluem entradas compartilhadas e não representam o tamanho
completo dos resultados operacionais. A janela é explícita no comando: o
benchmark não redefine os defaults do runner.

Dez épocas são viáveis quando o custo total e espaço cabem no ambiente, mantendo
as condições planejadas e registrando problemas do tráfego. A duração real varia
com máquina, carga, seed, GUI e observação; medições locais não são promessa de
tempo em outro computador. Consulte os tempos registrados em cada
`metrics.json` do experimento para avaliar o custo observado.

## 4. Quero evoluir

### Onde fazer cada alteração

| Evolução | Lugar da alteração | Preservação necessária |
| --- | --- | --- |
| Nova opção experimental | Runner; gerador quando pertencer à demanda | Default explícito, registro nos resultados, testes e explicação no guia. |
| Nova métrica suportada | Configuração de saídas, coletor, apresentação/armazenamento | Fonte, unidade, população, ausência de dado e perfil declarados. |
| Dados SETTRAN complementares | `docs/settran_programs.json`, sob `operational` e `schedule` | Fonte, evidências, hash da rede, vínculos e validações do contrato. |
| Reimportar planilha SETTRAN | `scripts/audit_settran.py` | Células originais e suplementos manuais válidos; usar `--help`. |
| Nova demanda | `SistemaDeSemaforos/demand/`, integrada pelo runner | Rede, protocolo, seed e proveniência; manter `random`. |
| Correção física comprovada | Rede e `scripts/correct_signal_infrastructure.py` | Efeito comum a `current`/`settran`, fonte e validação estrutural. |

Configuração consumida pelo programa pertence aos dados estruturados; lógica
pertence ao código; resultados ficam em outputs; explicação operacional fica
neste guia; material para o professor fica nos CSVs de `docs/`; validação fica nos
testes; histórico de desenvolvimento fica no Git. O README orienta o início.

Ao receber os dados SETTRAN, preencha o contrato já descrito, valide e selecione
explicitamente. Não converta vínculos físicos em permissões sem evidência, não
presuma amarelos/limpeza/offsets e não mude a rede para liberar um plano.

Arquivos de entrada originais (`RondonNorte.xlsx`, `Medicoes_5_6.csv`) permanecem
preservados. Outputs conservam os dados experimentais; remova apenas lotes
conscientemente descartados. Falhas de consolidação deixam as observações e
entradas disponíveis para diagnóstico.

Demandas reais/contextuais, reconstrução de fluxo, aprendizagem por reforço,
Hazarika, Acciai/TFR, novos controladores e treinamento continuam futuros,
sem integração implementada nesta etapa. A continuação atual depende sobretudo
dos dados operacionais SETTRAN e das evidências físicas ainda pendentes.
