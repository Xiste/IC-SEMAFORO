# Funcionamento do projeto

Guia técnico principal, na ordem do pipeline. Para executar, consulte
[GUIA_DE_EXECUCAO_E_TESTES.md](GUIA_DE_EXECUCAO_E_TESTES.md). Os catálogos são referências para consulta;
o runner não carrega esses CSVs como configuração.

Consulta por assunto: [mapa](#1-mapa-e-condições-de-referência),
[demanda](#2-demanda-random), [APIs](#3-execução-e-apis-utilizadas),
[métricas](#4-métricas-seleção-e-interpretação),
[arquivos de saída](#5-resultados-e-por-que-são-separados) e
[desempenho](#6-desempenho-já-medido).
A direção estratégica e a distinção entre estado atual, consolidação em andamento
e etapas futuras ficam no [README](../../README.md#direção-estratégica).

## 1. Mapa e condições de referência

O único mapa fonte é
`SistemaDeSemaforos/network/uberlandia.vehicular.families.16_2_4.net.xml`.
O nome é histórico; o responsável confirmou o cenário **Rondon Norte**.
O XML contém geometria, faixas, conexões, permissões e programas semafóricos.
Não há fontes OSM de construção versionadas neste repositório.

| Característica | Referência histórica V1 de 26/09/2026, anterior às correções abaixo |
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
no XML, sem outro inventário por edge/lane. Fonte V1 auditada: 5.201.327 bytes,
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

O [catálogo principal de configurações](../catalogos/configuration_catalog.csv) tem
**104 entradas selecionadas** para decisões experimentais, operacionais, estruturais
e de proveniência. A [referência completa](../catalogos/configuration_reference.csv)
mantém **2.007 entradas** agrupadas por classe/interface, incluindo opções SUMO,
duarouter, randomTrips, argumentos do projeto, atributos XML e defaults auditados.
Conhecer uma opção SUMO não a torna uma flag do nosso CLI.

Filtre `currently_used`, `category` e `scientific_relevance`. Compare
`native_default`, `current_core` e `current_full`; consulte `modifiable`,
`change_impact`, `source_reference`, versão e hash. Ausência de default não é zero.
Recursos inativos precisam de validação ao habilitar. A cobertura é versionada;
extensões e chaves genéricas de `<param>` não formam um conjunto finito.

### Perfil semafórico SETTRAN

`current` usa os programas de referência presentes na rede geral corrigida
e continua sendo o comportamento padrão. `settran` é uma possibilidade de configuração separada da
demanda `random`. É possível indicar explicitamente um plano para validar sua
seleção como teste fixo; atualmente a execução ainda é bloqueada por movimentos,
transições e referência da defasagem não comprovados. A [auditoria](../settran/settran_audit.csv) conserva os campos
originais, planos, ciclos e tempos; o [artefato normalizado](../settran/settran_programs.json)
é intermediário, consultado somente ao selecionar SETTRAN. Associações físicas
confirmadas não constituem permissões de verde nem fases SUMO executáveis.

A rede-base corrigida é comum aos perfis: 36 TLS, 314 índices de controle
(316 conexões controladas) e 43 travessias físicas. Benjamim recebeu quatro faixas
contínuas e um único miolo físico; Porto Alegre, Niterói e Belém tiveram os
fragmentos artificiais de suas aproximações eliminados. Foram representadas
travessias comprovadas, corrigidas prioridades cedentes e recompostos cruzamentos
fragmentados que provocavam bloqueios. Rio de Janeiro possui controle físico,
sem plano SETTRAN no dataset. Anselmo conserva as três retas e o limite local
comprovado. Fotografias de 2020 e março de 2026, referenciadas no CSV, distinguem
os focos veiculares das retas do foco pedestre baixo na ilhota. O ramo direito
se separa antes das retas; a representação veicular `priority` foi preservada,
sem criar um TLS veicular a partir do foco pedestre. O
[corretor determinístico](../../scripts/correct_signal_infrastructure.py)
reproduz essas mudanças sobre a fonte auditada, sem uma rede exclusiva da SETTRAN.

`current` é uma referência SUMO, não uma reprodução dos tempos reais. Os controles
novos da Rondon usam `O/o` para conservar prioridades; os sinais do Batalhão ficam
verdes no regime normal, com acesso pelo canteiro reservado a `emergency`, sem
acionamento especial implementado. Cruzamentos cujo programa antigo não cobria
as aproximações recuperadas receberam programas de referência calculados pelo
SUMO. Nos demais, estados veiculares e durações foram preservados ou estendidos
às faixas equivalentes. Travessias novas possuem geometria; seus links vinculados a TLS permanecem
vermelhos em `current`: não foi inventada uma programação pedestre. Três zebras
permanecem sem vínculo TLS comprovado. O SUMO avisa
sobre essas fases verdes ausentes; a demanda atual é veicular.

Benjamim, Paraná, Cesário × Paraná, Porto Alegre, Belém, Antônio Crescêncio/Rotary,
Niterói e João Naves tiveram a cobertura veicular corrigida. O atendimento pedestre
ainda está incompleto; em Belém também falta confirmar quais focos controlam as
zebras. Isso não torna os planos executáveis: ainda faltam diagramas de grupos,
permissões, sequência, transições e referência da defasagem. Niterói conserva
os três vermelhos discrepantes, e Anselmo a identidade Nascimento/Santos.
Antônio Crescêncio é saída de sentido único; nenhuma entrada artificial foi
criada. A travessia OSM 13340894097 pertence ao acesso de serviço do shopping,
e não indica um TLS ausente na pista principal da Rondon.

Corrigir a malha pode mudar rotas e resultados: a mesma rede corrigida é usada
na geração e simulação de todos os perfis. Acessos pedonais sintéticos tiveram
seus envelopes limitados para preservar 24 contornos, incluindo Anselmo e
João Naves, e a ilha do Rotary.
A lógica de `random`, o sorteio de
seeds, as métricas e os formatos de saída permanecem inalterados. A ausência de
plano SETTRAN não impede preservar ou corrigir um semáforo físico comprovado.

A [conferência temporária dos TLS atuais](../settran/current_tls_audit.csv) tem
uma linha por TLS. `plan_capable` indica capacidade técnica de receber outro
programa; `has_settran_plan` indica dados conhecidos para a interseção, sem
certificar sua atribuição a cada controle. Os estados são independentes:
`physical_status=OK` indica ausência de defeito veicular identificado nas
evidências disponíveis; `EVIDENCIA_INSUFICIENTE` exige a confirmação de campo
descrita em `note`. `real_world_status` conserva a confiança da associação.
`pedestrian_status=DADOS_AUSENTES` registra a lacuna operacional já conhecida;
`NAO_AVALIADO` não afirma ausência de travessias ou necessidade de novo controle.
Pedestres estão fora desta etapa e não rebaixam o estado físico veicular.
`settran_status` distingue `SEM_PLANOS`, `MAPEAMENTO_INCOMPLETO` e
`DADOS_OPERACIONAIS_AUSENTES` (descrições de estágios vinculadas, mas ainda sem
permissões/fases comprovadas). As contagens se sobrepõem; nenhum desses campos
declara um plano SETTRAN executável.

A classificação cobre os TLS, sem certificar todas as cargas da malha. Nos
cruzamentos sem TLS de Suíça e Viena, colisões com ônibus também foram
reproduzidas em lotes menores, sem teleports, variando com os encontros e o passo
simulado. As conexões, prioridades e conflitos estão registrados; não foi
comprovado um erro físico que autorize alterar curvas ou permissões. Faltam
cotas de retenções/raios ou vídeo de trajetórias de veículos longos. O diagnóstico
com passo de 0,1 s altera a dinâmica do modelo e não substitui o protocolo de
1 s ([documentação SUMO](https://sumo.dlr.de/docs/Simulation/Safety.html)).

Planos e agenda permanecem separados: existem 36 definições dos IDs oficiais
2/4/16/24; `schedule`, `operational_day_start` e `initial_plan_id` continuam nulos.
`--settran-plan` valida uma escolha explícita, sem assumir ordem temporal entre
planos. Um teste fixo não precisa de agenda; precisa de programa compilado e
comprovado, ainda indisponível. Não há scheduler, troca automática ou plano
inicial presumido. A sugestão de 00:00 não foi convertida em regra operacional.
Futuramente, com a agenda real, a seleção contextual poderá usar o tempo simulado
do SUMO. Esse comportamento não está implementado. A
[auditoria existente](../settran/settran_audit.csv) distingue a infraestrutura
corrigida das lacunas operacionais. A fonte georreferenciada descartada não foi
usada.

## 2. Demanda random

Origens/destinos são sorteados; partidas são regulares. A demanda serve para
exercitar o cenário e ainda não é calibrada por contagens reais.

```text
make run-random (um episódio)
        ↓
runner sorteia a seed e chama random_demand_generator.generate_random_demand
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
| [randomTrips.py](https://sumo.dlr.de/docs/Tools/Trip.html) | `generate_random_demand` / `demand/random_demand_generator.py`; `_find_random_trips` localiza o script. | Rede, janela de partidas, período, seed, classe `passenger` → viagens e rotas XML. | Prepara demanda; script em `$SUMO_HOME/tools/randomTrips.py`. |
| [duarouter](https://sumo.dlr.de/docs/duarouter.html) | Chamada **indireta** por `randomTrips.py`, com `--route-file` e `--validate`. | Viagens e rede → rotas válidas e viagens verificadas. | Calcula caminhos e verifica conectividade; pode descartar solicitações inviáveis. |
| [sumo](https://sumo.dlr.de/docs/sumo.html) / [sumo-gui](https://sumo.dlr.de/docs/sumo-gui.html) | `run_simulation` / `simulation/episode_runner.py`, via `subprocess.run`. | Rede, rotas, opções e arquivo adicional → processo concluído, código de saída e observações. | Binário no `PATH`; GUI exige sessão gráfica. |
| Configuração/template do SUMO | `prepare_baseline` / `simulation/experiment_baseline.py`: `--version`, `--save-template`; `run_simulation`: `--save-configuration`. | Executável e opções → versão, defaults e opções explícitas em XML. | Defaults ficam no baseline compartilhado; o episódio preserva suas diferenças. |

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
| `xml.etree.ElementTree` | Gerador: `parse`; `sumo_output_configuration`: `parse`, `Element`, `SubElement`, `write`; coletor: `iterparse`. | Validar XML, configurar observadores e ler registros incrementalmente. |
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
`scripts/audit_configuration_catalog.py --probe-defaults` usa TraCI somente em t=0:
`start`, `getConnection`, `simulation.getTime`, `vehicletype.getIDList`, os
26 getters de `PROBE_GETTERS`, `lane.getWidth` e `close`. Mede defaults dos seis
tipos embutidos e larguras omitidas, sem inserir veículos ou avançar passos.
`audit_metrics_catalog.py` apenas inspeciona métodos/docstrings, sem conectar ao SUMO.
Esses utilitários usam o TraCI que acompanha `$SUMO_HOME/tools`.

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
├── baseline.json         # rede/controladores, versões, hashes e defaults
├── network.net.xml       # rede exata, preservada uma vez
├── sumo_options.xml      # catálogo nativo de defaults desta instalação
└── code/                 # código de produção utilizado

outputs/outputs-random/[subpasta/]<UTC>_seed-<seed>_<UUID>/
├── metrics.json          # resultados globais e contexto, tipados e interpretáveis
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
schema 2; novos `metrics.json` usam schema 2; `entities.json.gz` permanece no
schema 1. São contratos independentes. Episódios históricos não são regravados.

Resultados e logs são ignorados pelo Git, mas não são caches. Excluir testes
autorizados é diferente de apagar experimentos científicos automaticamente.

### Formato dos consolidados

`metrics.json` conserva a lista `metrics`, o nome técnico canônico, o tipo e o
valor de cada registro. O schema 2 acrescenta uma legenda curta em português,
unidade e classificação, e ordena os registros pela utilidade experimental.
Exemplo de estrutura, com valor apenas ilustrativo:

```json
{
  "schema_version": 2,
  "metrics": [
    {
      "metric_name": "completed_trip_time_loss_mean",
      "data_type": "float",
      "value": 12.84,
      "label_pt": "Tempo médio perdido (viagens concluídas)",
      "description_pt": "Média do tempo perdido ao circular abaixo da velocidade ideal individual, excluindo paradas programadas, entre viagens concluídas.",
      "unit": "s",
      "kind": "result",
      "category": "performance",
      "priority": 1
    }
  ],
  "entity_metrics_file": "entities.json.gz"
}
```

Tipos: `int`, `float`, `bool`, `string`; `NaN` e infinito são rejeitados.
A lista global conserva todos os nomes e valores anteriormente exportados,
inclusive contexto. Nenhuma métrica CORE foi adicionada ou removida por essa
reorganização; campos condicionais continuam ausentes quando a fonte/população
não existe. A apresentação não modifica fórmulas, amostras ou perfis de coleta.

| Campo novo | Interpretação |
| --- | --- |
| `label_pt` | Nome curto para leitura humana, ao lado do nome canônico estável. |
| `description_pt` | O que o valor representa, incluindo a população ou agregação pertinente. |
| `unit` | Unidade do valor; `null` quando não se aplica ou não foi confirmada. Contagem de amostras tem unidade própria, não a unidade da grandeza observada. |
| `kind` | `result`: resultado medido; `context`: condição/identificação; `diagnostic`: observação técnica da execução/coleta. |
| `category` | `performance`: desempenho; `operation`: comportamento operacional; `integrity`: confiabilidade; `diagnostic`: diagnóstico; `context`: contexto experimental. |
| `priority` | Inteiro de 1 a 4 para importância de apresentação, independente do CORE/OPTIONAL do catálogo. |

Ordem de apresentação:

1. **Resultado principal:** perda média de tempo e espera média das viagens
   concluídas, vazão de chegadas e veículos concluídos; depois os indicadores
   complementares de eficiência. Abrem a leitura por serem evidências diretamente
   comparáveis entre controladores, demandas e versões sob condições declaradas.
2. **Comportamento operacional:** velocidade, duração/distância das viagens,
   utilização e emissões modeladas ajudam a explicar os resultados.
3. **Integridade:** viagens incompletas/não iniciadas, remoções anormais,
   teletransportes, colisões e situação de execução delimitam sua confiabilidade.
4. **Diagnóstico e contexto:** tempos de processamento, cobertura/amostras,
   parâmetros, seeds e identificação encerram a lista. Continuam necessários
   para auditoria, reprodução e comparação, mesmo aparecendo depois dos resultados.

`kind` distingue resultado de contexto sem retirar registros dos consumidores
existentes. `status` e `error` exigem atenção mesmo quando aparecem após os
resultados: um episódio encerrado não garante que todas as viagens tenham sido
concluídas. O manifesto continua sendo a fonte completa de configuração,
controladores, proveniência e integridade dos arquivos; contexto não é ganho de
desempenho. Os nomes técnicos continuam sendo as chaves de integração.

Esperas no trânsito e atrasos de inserção são grandezas distintas. As médias
`completed_*` descrevem apenas viagens concluídas; confronte-as com viagens
incompletas e teletransportes para evitar uma comparação enviesada. A vazão de
chegadas usa toda a duração simulada, portanto compare demandas, horizonte e
critério de término compatíveis. `vehicles_halting_*` mede veículos parados,
não o comprimento de uma fila. As filas existentes continuam por entidade;
`queue_observation_steps` mede cobertura temporal da coleta, não congestionamento.

As explicações técnicas completas continuam no [catálogo de métricas](../catalogos/metrics_catalog.csv).
As legendas curtas e regras de ordem ficam em
[`metric_presentation.py`](../../SistemaDeSemaforos/metrics/metric_presentation.py),
incluído no snapshot de código do baseline, sem carregar o CSV durante a execução.
Essa separação prepara a leitura por dashboards futuros sem duplicar o catálogo
em cada episódio nem implementar a visualização.
Nomes globais sem uma definição de apresentação são rejeitados explicitamente;
ao adicionar uma fonte ou atualizar o SUMO, revise também essa cobertura.
Nenhuma tradução ou unidade é inventada para atributos desconhecidos.

Compatibilidade: leitores devem selecionar registros por `metric_name`, preservar
o tipo/valor e tolerar os campos adicionais. Não use posições da lista ou a ordem
alfabética como chave. Leitores estritos de schema 1 precisam aceitar explicitamente
o schema 2; arquivos históricos continuam legíveis pelos campos canônicos, mas não
possuem necessariamente legendas/prioridades. No repositório, a auditoria lê esses
campos por nome; testes de persistência/runner exercitam o contrato. O benchmark
compara observações/viagens e entidades diretamente, sem ler `metrics.json`.
Não há consumidores implementados de dashboard ou treinamento no repositório;
consumidores externos não disponíveis não podem ser certificados aqui.

Recomendações futuras, **não implementadas**: avaliar um resumo global de filas
somente com definição explícita de cobertura espacial, ponderação e ausência de
dupla contagem; poderia facilitar comparações sem substituir as entidades.
Uma eventual taxa de conclusão também exige declarar o denominador (solicitados,
gerados ou inseridos) e o horizonte. Os totais existentes são preservados e nenhuma
dessas propostas acrescenta uma métrica nesta etapa.

`entities.json.gz.entities` mantém os registros de três campos
`metric_name`/`data_type`/`value` do schema 1, organizados por escopo e ID original:
`vehicles`, `lanes`, `edges`, `traffic_lights`, `approaches`, `intersections`.
A chave única é **escopo + ID + metric_name**; nomes `snake_case` não se repetem
dentro de uma lista.

Uma aproximação usa ID `controlador/via_de_entrada`. Uma interseção agrupa
faixas de entrada do controlador; ele pode controlar vários nós físicos.

`metrics/` separa configuração, cálculo, apresentação e gravação:
`sumo_output_configuration.py` solicita observações, `episode_metrics_collector.py`
agrega, `metric_presentation.py` descreve/ordena os resultados globais e
`metrics_storage.py` valida nomes/tipos e exporta. O runner coordena essas tarefas.

`simulation/experiment_baseline.py` preserva uma cópia compartilhada do cenário, evitando
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

`outputs/benchmarks/` só aparece ao executar `scripts/benchmark_observation_pipeline.py`.
É uma comparação de custo entre perfis com a mesma demanda, não parte do run normal.
Baselines podem ser apagados junto dos testes quando nenhum episódio preservado
precisar deles. Procedimentos de reprodução ficam no guia de comandos.

[auditoria_historica.zip](../historico/auditoria_historica.zip) reúne as 27 tabelas das
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

Seeds, método e decomposição estão no [relatório incremental](../../RELATORIO_INCREMENTAL.md).
Os outputs de teste foram apagados a pedido do responsável; estes são registros
históricos, não novas medições desta limpeza. Próxima investigação possível:
paralelismo limitado de dois episódios, conferindo resultados por seed e
contenção de recursos antes de adotá-lo.
