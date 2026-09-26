# Funcionamento do projeto

Guia técnico principal, na ordem do pipeline. Para executar, consulte
[COMANDOS_TESTE.md](COMANDOS_TESTE.md). Os catálogos são referências para consulta;
o runner não carrega esses CSVs como configuração.

Consulta por assunto: [mapa](#1-mapa-e-condições-de-referência),
[demanda](#2-demanda-random), [APIs](#3-execução-e-apis-utilizadas),
[métricas](#4-métricas-seleção-e-interpretação),
[arquivos de saída](#5-resultados-e-por-que-são-separados) e
[desempenho](#6-desempenho-já-medido).

## 1. Mapa e condições de referência

O único mapa fonte é
`SistemaDeSemaforos/network/uberlandia.vehicular.families.16_2_4.net.xml`.
O nome é histórico; o responsável confirmou o cenário **Rondon Norte**.
O XML contém geometria, faixas, conexões, permissões e programas semafóricos.
Não há fontes OSM de construção versionadas neste repositório.

| Característica | Valor conferido na reauditoria de 26/09/2026 |
| --- | --- |
| Vias direcionadas | 2.142 externas e 5.706 segmentos internos |
| Faixas | 8.578, sendo 2.497 externas |
| Nós/conexões | 1.996 junctions (901 internos); 11.261 conexões; cinco rotatórias |
| Semáforos | 34 nós, 28 programas estáticos, 106 fases; ciclos de 90 s e offset 0 |
| Extensão de faixas externas | 181,77929 km-faixa; soma de faixas, não extensão geográfica das ruas |
| Limites de velocidade externos | 11,11 a 27,78 m/s; não são velocidades medidas no tráfego |
| Largura | 242 faixas explicitam 1,75 m; 8.336 omissões foram medidas em t=0 como 3,2 m |

Um controlador pode atender vários nós. Coordenadas locais estão em metros
(UTM zona 22/WGS84), não em latitude/longitude. Detalhes por elemento permanecem
no XML, sem outro inventário por edge/lane. Rede auditada: 5.201.327 bytes,
SHA-256 `46e7c4a4627cd511d419c01f15d65f66724941ac83360c4fc424b86626a5c10b`.

**Baseline** é o conjunto de condições de referência, não uma simulação vazia:
mapa e seus programas, versões, código, defaults SUMO e parâmetros da demanda.
A instalação auditada é **SUMO 1.27.1**, com passo de 1 s, seed interna 23423,
modelo veicular Krauss e `time-to-teleport=300` s. Defaults dependem do tipo/classe;
não devem ser extrapolados para modelos ausentes.

| Classe de mudança | Exemplos | Regra experimental |
| --- | --- | --- |
| Operacional | GUI, pasta de saída, quantidade de episódios, perfil de observação | Pode variar; registrar pois altera custo/volume. Perfil deve preservar a dinâmica. |
| Experimental | Seed, intensidade/janela de demanda, limite `--end` | Pode variar em comparação explicitamente identificada; afeta os resultados. |
| Condicional | Passo, car-following, teleportes, modelos/dispositivos, duração de fases | Exige hipótese, validação e compatibilidade dos agregadores; não é ajuste operacional automático. |
| Estrutural | Geometria, conexões, permissões, associação de semáforos | Preservar neste baseline; mudança define outro cenário. |
| Resultado/derivado | Métricas, hashes, contagens estruturais | Não é entrada editável; recalcular a partir de suas fontes. |

O [catálogo de configurações](configuration_catalog.csv) tem **2.005 entradas**:
462 opções SUMO/sumo-gui, 124 duarouter, 64 randomTrips, 13 argumentos do projeto,
1.185 atributos XML, 156 defaults de tipos embutidos e uma verificação agrupada
de larguras omitidas. Conhecer uma opção SUMO não a torna uma flag do nosso CLI.

Filtre `currently_used`, `category` e `scientific_relevance`. Compare
`native_default`, `current_core` e `current_full`; consulte `modifiable`,
`change_impact`, `source_reference`, versão e hash. Ausência de default não é zero.
Recursos inativos precisam de validação ao habilitar. A cobertura é versionada;
extensões e chaves genéricas de `<param>` não formam um conjunto finito.

## 2. Demanda random

Origens/destinos são sorteados; partidas são regulares. A demanda serve para
exercitar o cenário e ainda não é calibrada por contagens reais.

```text
make run-random (um episódio)
        ↓
runner sorteia a seed e chama generator.generate_random_demand
        ↓
randomTrips.py sorteia viagens na rede Rondon Norte
        ↓
viagens com origem, destino e partida
        ↓
duarouter calcula rotas e verifica conectividade
        ↓
random.trips.xml — viagens verificadas
random.rou.xml   — veículos com suas rotas
        ↓
SUMO carrega random.rou.xml
```

Nosso código chama `randomTrips.py` uma vez. Na versão instalada, a ferramenta
chama `duarouter` para produzir rotas e novamente com `--write-trips` para validar
viagens. Pode filtrar solicitações inviáveis; os XMLs finais representam os
respectivos resultados. O `.trips.xml` não é um template vazio nem uma cópia do
`.rou.xml`: descreve intenções de viagem, enquanto o segundo contém caminhos.
Os dois XMLs finais são conferidos antes de substituir uma demanda anterior.

| Arquivo | Função | Uso |
| --- | --- | --- |
| `random.trips.xml` | Viagens verificadas: origem, destino e partida. | Intermediário do roteamento e conferência do sorteio. |
| `random.rou.xml` | Veículos e sequências de vias a percorrer. | **Demanda carregada pela simulação.** |

Manter ambos permite conferir o processo. O gerador retorna apenas o caminho
de `random.rou.xml`; a simulação recebe um arquivo de rotas pronto.

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

## 3. Execução e APIs utilizadas

O pipeline usa **linha de comando e XML**, sem endpoint HTTP ou cliente
TraCI/libsumo durante os episódios. As ferramentas vêm da instalação SUMO,
separadamente do mapa. Episódios são sequenciais; sem `--end`, terminam ao
esgotar a demanda. Não há controlador Python nem mudança dos sinais pela coleta.

| Interface | Função que chama / módulo | Entrada → saída | Uso e dependência |
| --- | --- | --- | --- |
| [randomTrips.py](https://sumo.dlr.de/docs/Tools/Trip.html) | `generate_random_demand` / `demand/generator.py`; `_find_random_trips` localiza o script. | Rede, janela de partidas, período, seed, classe `passenger` → viagens e rotas XML. | Prepara demanda; script em `$SUMO_HOME/tools/randomTrips.py`. |
| [duarouter](https://sumo.dlr.de/docs/duarouter.html) | Chamada **indireta** por `randomTrips.py`, com `--route-file` e `--validate`. | Viagens e rede → rotas válidas e viagens verificadas. | Calcula caminhos e verifica conectividade; pode descartar solicitações inviáveis. |
| [sumo](https://sumo.dlr.de/docs/sumo.html) / [sumo-gui](https://sumo.dlr.de/docs/sumo-gui.html) | `run_simulation` / `simulation/runner.py`, via `subprocess.run`. | Rede, rotas, opções e arquivo adicional → processo concluído, código de saída e observações. | Binário no `PATH`; GUI exige sessão gráfica. |
| Configuração/template do SUMO | `prepare_baseline` / `simulation/baseline.py`: `--version`, `--save-template`; `run_simulation`: `--save-configuration`. | Executável e opções → versão, defaults e opções explícitas em XML. | Defaults ficam no baseline compartilhado; o episódio preserva suas diferenças. |

Geração: `--net-file`, `--output-trip-file`, `--route-file`, `--begin`, `--end`,
`--period`, `--seed`, `--vehicle-class`, `--validate`. O gerador retorna `Path`;
o argumento opcional `metadata` recebe parâmetros, contagens, seed, comando,
hash do script e tempos. `log_file` recebe stdout/stderr quando solicitado.

Execução: `--net-file`, `--route-files`, `--begin`, `--no-step-log`,
`--aggregate-warnings`; `--end` quando solicitado; `--start --quit-on-end`
para GUI. Com `recording_dir`, salva a configuração explícita e executa o SUMO.
Versão e template são consultados ao criar um baseline novo, não em cada episódio.
O manifesto referencia o snapshot e registra os argumentos utilizados.
Falhas de processo geram exceção, com contexto preservado pelo runner.

Não há configuração HTTP nem credenciais. As funções públicas recebem `Path`
ou strings de caminhos locais. O gerador retorna o caminho de rotas;
`run_simulation` retorna `None` após sucesso e preenche `metadata` quando fornecido.
As chamadas usam listas de argumentos, sem shell intermediário.

### Biblioteca padrão Python

| Interface | Onde / chamadas | Responsabilidade |
| --- | --- | --- |
| `subprocess` / `shutil.which` | Gerador e runner: `run`, localização de binários. | Passar argumentos, aguardar e conferir processos, sem shell intermediário. |
| `xml.etree.ElementTree` | Gerador: `parse`; `sumo_outputs`: `parse`, `Element`, `SubElement`, `write`; coletor: `iterparse`. | Validar XML, configurar observadores e ler registros incrementalmente. |
| `time` / `datetime` | Gerador/runner: `perf_counter`, `datetime.now(timezone.utc)`. | Duração monotônica e datas UTC. |
| `random` / `uuid` | Gerador/runner: `randint`; runner: `uuid4`. | Seed da demanda e identificação sem sobrescrita. |
| `json` / `gzip` / `hashlib` | Storage/baseline: `dump`, `open`, `sha256`; coletor: `gzip.open`. | Dados tipados, compressão, hashes e identificação do baseline. |
| `tempfile` / `pathlib` | Gerador: `TemporaryDirectory`; storage: `NamedTemporaryFile`, `Path.replace`. | Limpeza automática e publicação de arquivos completos. |

`sumolib` é dependência interna das ferramentas SUMO, sem importação direta no
projeto.

### Interfaces usadas somente na auditoria

[TraCI](https://sumo.dlr.de/docs/TraCI.html) e
[libsumo](https://sumo.dlr.de/docs/Libsumo.html) permitem consultas/controle durante
passos; não são acionados pelo runner. `netconvert`/`netedit` também não são chamados.
`scripts/audit_configuration.py --probe-defaults` usa TraCI somente em t=0:
`start`, `getConnection`, `simulation.getTime`, `vehicletype.getIDList`, os
26 getters de `PROBE_GETTERS`, `lane.getWidth` e `close`. Mede defaults dos seis
tipos embutidos e larguras omitidas, sem inserir veículos ou avançar passos.
`audit_metrics.py` apenas inspeciona métodos/docstrings, sem conectar ao SUMO.
Esses utilitários usam o TraCI que acompanha `$SUMO_HOME/tools`.

## 4. Métricas: seleção e interpretação

O [catálogo único de métricas](metrics_catalog.csv) contém **1.498 entradas**:
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

`metrics/sumo_outputs.py:prepare_outputs` recebe a pasta e o perfil de coleta,
prepara as opções e grava `observations.add.xml`. Retorna argumentos para o SUMO.
SUMO produz os arquivos durante a execução;
`metrics/collector.py:collect_episode` coordena sua leitura após o término.
Este recebe `raw/`, a rede e o perfil; retorna dicionários de métricas globais
e entidades. O catálogo distingue fontes habilitadas das apenas disponíveis.

| Interface/documentação | Opção ou elemento SUMO | Leitor em `collector.py` / dados utilizados |
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
├── baseline.json         # rede/controladores, versões, hashes e defaults
├── network.net.xml       # rede exata, preservada uma vez
├── sumo_options.xml      # catálogo nativo de defaults desta instalação
└── code/                 # código de produção utilizado

outputs/outputs-random/[subpasta/]<UTC>_seed-<seed>_<UUID>/
├── metrics.json          # métricas globais tipadas
├── entities.json.gz      # consolidado por entidade, tipado e comprimido
├── manifest.json         # contexto, comandos, referência ao baseline e hashes
├── generation.log        # diagnóstico de randomTrips/duarouter
├── sumo.log              # diagnóstico dos processos SUMO
├── inputs/
│   ├── random.trips.xml
│   ├── random.rou.xml
│   ├── observations.add.xml
│   └── sumo_config.sumocfg
└── raw/
    ├── summary.xml.gz, trips.xml.gz, statistics.xml
    ├── queues.xml.gz, tls.xml.gz, lanechanges.xml.gz
    ├── collisions.xml.gz, vehicle_routes.xml.gz
    └── edges.xml.gz, lanes.xml.gz, fcd.xml.gz, emissions.xml.gz  # apenas full
```

`raw/` conserva as observações originais, inclusive temporais. **Os consolidados
não têm linhas por timestep.** O arquivo por entidade é separado e comprimido
para tornar rápida a consulta do resumo global.

O manifesto registra parâmetros, argv reais, opções explícitas e horários.
`baseline.id` e o hash de `baseline.manifest` vinculam rede, controladores,
defaults, ambiente, ferramentas e código. Arquivos compartilhados têm integridade
verificada ao reutilizar o baseline; nunca devem ser editados no lugar.
O argv de geração registra a pasta temporária originalmente usada; os caminhos
finais também ficam disponíveis. As configurações preservam texto XML nativo;
as métricas numéricas exportadas usam números.

Opção efetiva = `baseline.json.sumo_defaults` sobreposto por
`manifest.json.simulation.configured_options`. A configuração salva contém
as opções explícitas. Os caminhos são absolutos: uma reprodução precisa
adaptar entradas movidas e usar novos destinos para todas as saídas.

Ao arquivar um episódio, preserve também seu baseline. Novos manifestos usam
schema 2; os registros de métricas permanecem no schema 1.

Resultados e logs são ignorados pelo Git, mas não são caches. Excluir testes
autorizados é diferente de apagar experimentos científicos automaticamente.

### Formato dos consolidados

```json
{"metric_name": "vehicles_completed", "data_type": "int", "value": 4800}
```

Tipos: `int`, `float`, `bool`, `string`; `NaN` e infinito são rejeitados.
`metrics.json.metrics` é a lista global. `entities.json.gz.entities` organiza
listas por escopo e ID original: `vehicles`, `lanes`, `edges`, `traffic_lights`,
`approaches`, `intersections`. A chave única é **escopo + ID + metric_name**;
nomes `snake_case` não se repetem dentro de uma lista.

Uma aproximação usa ID `controlador/via_de_entrada`. Uma interseção agrupa
faixas de entrada do controlador; ele pode controlar vários nós físicos.

`metrics/` contém código com três tarefas distintas: `sumo_outputs.py` solicita
observações, `collector.py` agrega e `storage.py` valida nomes/tipos e exporta.
O runner coordena essas tarefas. Uni-las misturaria configuração SUMO, cálculos
e gravação sem reduzir o trabalho necessário.

`simulation/baseline.py` preserva uma cópia compartilhada do cenário, evitando
copiar mapa/código/defaults em cada episódio. Ela permite recuperar as condições
antigas mesmo se o projeto mudar. `inputs/observations.add.xml` solicita
observações; não é outro mapa nem outra demanda. Pastas são criadas sob demanda.

IDs de episódio combinam UTC com microssegundos, seed e UUID; criação exclusiva
impede sobrescrita. Horários são UTC e durações usam `perf_counter`. Há tempos
separados para preparação, geração, SUMO, agregação, exportação e inventário.
Parsers são subetapas da agregação, não parcelas adicionais. O total exclui
somente a escrita final dos dois JSONs pequenos que contêm sua própria duração.
O tempo SUMO inclui startup e escrita nativa, sem isolá-los artificialmente.

Falhas interrompem o lote e preservam contexto/arquivos parciais. `Ctrl+C`
registra interrupção; encerramento forçado pode deixar `status: running`.
Saída obrigatória ausente ou período incompatível causa erro de consolidação.
Observações XML são lidas incrementalmente; memória depende das entidades/métricas.

### Pastas de teste e histórico

`outputs/benchmarks/` só aparece ao executar `scripts/benchmark_pipeline.py`.
É uma comparação de custo entre perfis com a mesma demanda, não parte do run normal.
Baselines podem ser apagados junto dos testes quando nenhum episódio preservado
precisar deles. Procedimentos de reprodução ficam no guia de comandos.

[auditoria_historica.zip](auditoria_historica.zip) reúne as 27 tabelas das
planilhas originais em CSV convencional, com índice e instruções dentro do ZIP.
Há medições/notas históricas únicas; por isso foi preservado. Não é documentação
corrente. Não há pasta `archive/` nem leitor especial para acessar seu conteúdo.

## 6. Desempenho já medido

Na validação de 26/09/2026, dez episódios padrão `core`, sem GUI nem `--end`,
concluíram 48.000 viagens em **316,98 s**. Média **31,70 s**, intervalo
**21,71–62,66 s**: dez episódios foram operacionalmente viáveis naquele ambiente.
Houve 3–1.027 teletransportes por episódio e zero colisões; conclusão integral
não comprova calibração ou suficiência estatística.

Médias por episódio: geração 3,487 s; SUMO 22,094 s; agregação 4,457 s;
exportação de entidades 1,604 s. SUMO representou aproximadamente 70% do total.
Não há consultas TraCI por timestep, DataFrames ou flush por passo neste pipeline.

Comparação controlada, mesma demanda de 400 viagens e duas repetições:
observação mínima 0,900 s; `core` 2,796 s; `full` 29,463 s. Todos os atributos de
viagem coincidiram, exceto a lista de dispositivos observadores. No `full`, séries
detalhadas elevaram sobretudo agregação e exportação. A observação mínima ainda
gravava tripinfo; não é custo zero de coleta. Tempos não incluem geração/baseline compartilhados.

Seeds, método e decomposição estão no [relatório incremental](../RELATORIO_INCREMENTAL.md).
Os outputs de teste foram apagados a pedido do responsável; estes são registros
históricos, não novas medições desta limpeza. Próxima investigação possível:
paralelismo limitado de dois episódios, conferindo resultados por seed e
contenção de recursos antes de adotá-lo.
