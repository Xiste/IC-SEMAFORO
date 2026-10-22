# Funcionamento do projeto

Este é o manual operacional: [executar](#1-quero-executar),
[entender](#2-quero-entender), [experimentar](#3-quero-experimentar) e
[evoluir](#4-quero-evoluir). O projeto gera demanda `random` ou o protótipo
`metasettran`, executa SUMO e
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

Em `random`, viagens, rotas e configurações XML de entrada são temporárias nos dois perfis.
O protótipo MetaSettran usa `outputs/outputs-metasettran/` e conserva também
`metasettran.rou.xml`, para reutilizar exatamente as viagens entre controladores.
Após sucesso, o `core` também remove seus XMLs de observação; conserva os
indicadores globais calculados. O `full` conserva os XMLs de observação e
entidades para análise detalhada. Falhas preservam arquivos disponíveis para
diagnóstico. Os dados de configuração e as seeds permanecem nos resultados,
sem cópias da rede ou do código. Outputs ficam fora do Git.

### Material para o professor

A pasta `docs/` reúne o guia, os dados SETTRAN e duas planilhas CSV (UTF-8, separador vírgula):
[CONFIGURACOES.csv](CONFIGURACOES.csv), com 65 configurações nativas
relevantes ao cenário veicular, e [METRICAS.csv](METRICAS.csv), com
80 indicadores coletáveis. As configurações têm seis colunas: categoria,
opção SUMO, padrão de fábrica, efeito e unidade, uso no projeto e como alterar.
Os 65 padrões foram conferidos no template do SUMO 1.28.0 e coincidem com
os valores da referência 1.27.1. `uso_no_projeto` mostra um valor comum aos
perfis ou distingue `core` e `full` quando necessário; considera `current`
e os argumentos padrão. A coluna `como_alterar` distingue opções do CLI de
ajustes que exigem editar o código em `SistemaDeSemaforos/`.
As métricas indicam fonte, unidade, população, perfil e localização nos resultados.
Das 80 linhas de `METRICAS.csv`, 40 indicam `core e full` e 40 são exclusivas
do `full`. O catálogo inclui contexto temporal e contagens de amostras
válidas/excluídas para interpretar as médias. A divisão 40/40 conta indicadores
disponíveis no `core` e indicadores adicionais do `full`; o perfil `full` também
coleta os indicadores comuns. O CSV é uma seleção, não a lista de todos os
campos de `metrics.json`; custos de coleta, por exemplo, ficam fora do catálogo.
Saídas brutas do `core` são temporárias.

### Defaults e tempos

Padrões de `random`: 1 episódio, demanda de **7.200 s**, partidas a cada
**1,5 s**, início em t=0, **timestep de 1 s** e término natural (`end=None`;
SUMO `-1`). Perfis padrão: `current` e `core`. Sem `--end`, a simulação pode
ultrapassar 7.200 s para concluir viagens. O perfil de observação não muda
esses parâmetros ou o critério de encerramento.

Os resultados separam janela da demanda (`demand_duration_seconds`), duração
simulada (`simulation_duration_seconds`) e processamento real
(`execution_time_seconds`). O tempo real inclui preparação, demanda, SUMO,
consolidação e gravação de entidades; exclui a gravação final de `metrics.json`
e a limpeza dos temporários. Durações usam relógio monotônico;
horários de processamento são UTC. O horário civil de MetaSettran é Brasília;
t=0 da simulação corresponde a 15h no contexto implementado.
A fronteira de medição do processamento é a mesma em `core` e `full`.

Estas são todas as opções operacionais do runner, além de `--help`:

| Opção | Padrão | Uso |
| --- | --- | --- |
| `--episodes` | `1` | Quantidade de episódios independentes. |
| `--demand-profile` | `random` | `random` ou protótipo `metasettran`, independente dos semáforos. |
| `--duration` | `7200` s | Janela de partidas de `random`, a partir de t=0. |
| `--period` | `1.5` s | Intervalo programado entre partidas de `random`. |
| `--end` | Ausente | Em `random`, término natural; um valor impõe horizonte finito. |
| `--day`, `--start`, `--sections` | `tuesday`, `15:00`, `1` em MetaSettran | Sete dias, inícios a cada três horas e 1–56 seções consecutivas; modelo experimental. |
| `--variation` | `1` em MetaSettran | Índice 1–25; episódios seguintes usam índices consecutivos, sem ultrapassar 25. |
| `--spatial-scenario` | `regional-integrated` em MetaSettran | Modelo regional compartilhado; `regional-midpoint` é alias, sem recriar os antigos orçamentos. |
| `--drain-limit` | `2700` s em MetaSettran | Limite adicional após as partidas; inteiro não negativo, preservando timestep de 1 s. |
| `--metrics-profile` | `core` | Seleciona observações `core` ou `full`. |
| `--signal-profile` | `current` | Programas da rede ou `settran` validado. |
| `--settran-plan` | Ausente | ID oficial escolhido explicitamente; exige `settran`. |
| `--settran-intersection` | Todas do plano | Nome exato e repetível para selecionar interseções; exige `settran`. |
| `--gui` | Desativado | Abre e fecha `sumo-gui` por episódio. |
| `--net-file` | Rede Rondon Norte do projeto | Seleciona a rede física. |
| `--output-dir` | `outputs/outputs-<perfil de demanda>/` | Destino dos lotes dentro da árvore correspondente. |

## 2. Quero entender

### Arquitetura e responsabilidades

```text
rede física única + random/metasettran + current/settran + core/full
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
| `SistemaDeSemaforos/demand/metasettran_calibration.py` | Auditoria das contagens `car`, curvas temporais e separação de datas. |
| `SistemaDeSemaforos/demand/metasettran_demand_generator.py` | Partidas reproduzíveis, duarouter e verificação das rotas entre portais. |
| `SistemaDeSemaforos/demand/metasettran_spatial.json` | Cadastro geográfico de portais e corredores, pesos iniciais e hipóteses dos sensores. |
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

### Caminho de execução de random

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

Cada episódio `random` sorteia a seed da demanda entre 0 e `2**31 - 1`. A seed interna
SUMO permanece no default e é registrada separadamente. O gerador aceita
`--seed`; o runner continua sorteando e não possui flag CLI de replay.

`make demand-random` gera somente o par avulso em `SistemaDeSemaforos/demandas/`;
repetir no mesmo destino substitui o par anterior. `make run-random` gera direto
em `inputs/` temporário do novo episódio, sem ler nem preencher o par avulso.
Essa pasta é removida após sucesso; as seeds permanecem nos resultados.

### Dados reais preservados

[RondonNorte.xlsx](RondonNorte.xlsx) é a fonte original dos planos.
[Medicoes_5_6.csv](Medicoes_5_6.csv) contém 175.729 registros, em 67 datas entre
26/06 e 16/09/2026. A auditoria integral confirma `vehicle_total = car + bus + truck`;
motos e bicicletas ficam fora dessa soma. Os campos de velocidade são sempre zero
e não calibram velocidades. Não há duplicatas ou sobreposições por sensor;
existem interrupções, dias parciais e intervalos longos. Ausência não é fluxo zero.
As linhas virtuais dos sensores 5/6 não têm coordenadas comprovadas.
Essas observações alimentam somente o protótipo descrito abaixo, preservando
`random`; não identificam uma matriz OD completa nem uma agenda semafórica.

### MetaSettran: modelo regional integrado, ainda experimental

Execute pelo runner compartilhado, com demanda e semáforos independentes:

```bash
python3 -B -m SistemaDeSemaforos.simulation.episode_runner \
  --demand-profile metasettran --day tuesday --start 15:00 --sections 1 \
  --variation 7 --signal-profile current --metrics-profile core
```

`regional-integrated` é o modelo ativo. `regional-midpoint` é somente alias de
compatibilidade; não recria a distribuição antiga. Os cenários reprovados
`balanced`, `dispersed`, `local`, `regional-control` e `regional-upper` são recusados.
Os resultados históricos permanecem em outputs com suas configurações originais.

**Escopo e organização.** Um único modelo atende sete dias (`monday` a `sunday`),
oito inícios (`00:00`, `03:00`, …, `21:00`) e variações 1–25. O cadastro comum
`metasettran_spatial.json`, campo `temporal_contexts`, representa essa hierarquia;
não há 56 geradores nem 1.400 XMLs antecipados. Cada episódio gera e conserva sua
rota sob demanda. `--episodes 10 --variation 1` executa dez realizações independentes,
com índices 1–10. Isso não equivale a dez seções consecutivas.

São representados somente carros (`passenger`), com extremos periféricos.
Ônibus, caminhões, motocicletas, bicicletas, pedestres e deslocamentos com extremos
internos estão excluídos. Não se aumenta a demanda periférica para compensá-los.
O modelo não é uma reprodução integral do tráfego real nem uma matriz OD medida.

**Relógio, dados e variações.** Os timestamps permanecem no horário de Brasília,
sem deslocamento UTC especulativo, conforme declaração do responsável. Falta o
metadado de fuso do exportador. Somente `car` calibra o modelo;
`vehicle_total = car + bus + truck` exclui motocicletas e bicicletas. As velocidades
zeradas não são usadas. A classificação não tem verificação manual independente.

O módulo de calibração verifica o arquivo integral e conserva seus dados originais.
Intervalos aceitos de até 120 s são rateados por sobreposição; lacunas não viram
zero. Cada quarto de hora requer pelo menos 95% de exposição nos dois sensores.
As medianas, IQR e MAD são calculadas separadamente por dia da semana e horário,
com datas anteriores a 24/08/2026, excluindo os feriados cadastrados. A semana
iniciada em 24/08 é verificação principal; semanas posteriores são verificação
adicional. Janelas que cruzam dias são avaliadas contra datas consecutivas reais.
Intervalos incompletos de verificação ficam sem erro calculado, com exposição explícita.

Os 672 quartos de hora do CSV atual têm 5–7 datas comuns de treino; não foi
necessário recorrer ao fallback entre weekdays. Cada variação reamostra conjuntamente
um dia completo de treino para cada weekday, compartilhado pelos dois sensores,
preservando a correlação intradia e entre contadores. Há apenas 3–6 dias completos
por weekday: 25 realizações não significam 25 semanas observadas independentes.
A interpolação linear entre centros de 15 min é cíclica na semana e não aplica
outra janela de suavização. Datas vizinhas sorteadas podem não ser consecutivas;
a correlação entre dias permanece uma limitação.

As partidas seguem um processo Poisson de taxa contínua sobre a realização sorteada.
Seed, configuração e versão iguais reproduzem o mesmo XML, independentemente de
`current`/`settran` e `core`/`full`. A variação 7 continua identificada pela seed
1082464323, mas uma mudança da versão do modelo altera as rotas e deve ser registrada.

**População regional e observações.** Há uma população única de viagens.
Uma rota pode atravessar nenhum, um ou vários pontos de observação; incidências
não criam veículos. Não existem origens exclusivas por sensor nem rotas proibidas
somente por atravessarem ambos. A existência de viagens compartilhadas depende da
geografia: não se impõem desvios para produzi-las.

A escala de referência, 17.864,7156 partidas esperadas para terça 15–18, permanece
uma **hipótese experimental herdada**, preservada para comparações. Não é um total
regional medido. Nos demais contextos:

`taxa_regional(t) = escala_referência × [car5(t) + car6(t)] / integral_referência[car5 + car6]`

A soma define um índice temporal normalizado, não uma contagem de veículos únicos.
Não se divide por cobertura presumida, não se somam VMD de interseções e não se
ajusta o total à capacidade do `current`. A antiga extrapolação por 5,80% está removida.
Na comparação espacial, `generate_metasettran_demand(schedule_file=...)` preserva
IDs, atributos, tipos, horários e quantidade do XML anterior; somente OD e percursos
mudam. Essa opção Python é um suporte de experimento, não um executor paralelo.

**Portais, OD e percursos.** Os 44 acessos de entrada e 37 de saída têm nó, coordenada,
referências cartográficas e evidência do corte. A validação confere hash da rede,
conectividade, faixas e posição da extremidade; topologia sozinha não aprova um portal.
A qualificação é cartográfica, sem inspeção operacional em campo. Tipos ausentes
conservam o valor original; `prior_road_type` registra separadamente a hipótese
inferida do mesmo corredor ou, sem suporte, a classificação local conservadora.

O prior usa oportunidade por acesso físico orientado: faixas × hierarquia ordinal,
modulada por evidência externa relativa quando disponível. Ramos do mesmo
`boundary_group` repartem a maior oportunidade desse grupo, sem somar representações
do mesmo acesso. Extremos opostos da Rondon são acessos distintos; não dividem um
orçamento pelo nome da avenida. Os pesos 4/3/2/1 são hipóteses de hierarquia,
não capacidades semafóricas. O produto das oportunidades de origem e destino é
normalizado sobre os pares conectados; alternativas repartem a massa do mesmo OD
pela eficiência relativa de tempo livre. Não há requisito de ocupar todos os pares.

`duarouter` calcula os caminhos. O catálogo inclui alternativas explícitas por
Jerônimo–Brasil–Niterói, Brasil e João Pinheiro–Jataí, qualificadas pela geometria.
Pontos intermediários de templates de atravessamento não podem produzir uma segunda
visita à mesma junção. Retornos legais e trajetos curtos encontrados naturalmente
continuam permitidos. Toda viagem parte de `departPos=0` e termina em `arrivalPos=max`,
com rota contínua e permissões `passenger`, inclusive nas conexões internas.
Não se selecionam caminhos pela taxa de conclusão obtida em simulação.

Os [VMD SETTRAN de 2025](https://www.uberlandia.mg.gov.br/prefeitura/secretarias/transito-e-transportes/fiscalizacao-eletronica/)
de João Naves, Monsenhor Eduardo, Afonso Pena e Segismundo são referências relativas
de outras seções e de todas as classes. O cadastro conserva os quatro PDFs, páginas,
valores e faixas. VMD por faixa fiscalizada é normalizado antes de aplicar as faixas
locais; esses números não viram orçamentos independentes. A transferência entre
seções, sentidos e classes é estimativa. Contagens históricas de conversão de 2002
permanecem referência, mas não determinam preferência por destino no mesmo corredor.

O [estudo UFU de 2026](https://repositorio.ufu.br/handle/123456789/49701), tabela 2,
observou duas outras seções em terças, de manhã, ao meio-dia e à tarde. As razões
entre sentidos informam uma **restrição estimada** no sentido bairro da Rondon,
relativa à curva6. A interpolação entre centros desses períodos, a transferência aos
demais dias e a razão neutra noturna são hipóteses explícitas; não uma terceira medição.

**Ajuste espacial e validação física.** As probabilidades OD variam a cada 15 min,
com interpolação contínua. A forma relativa6 informa o prior arterial e a5 o local,
uma transferência experimental sem contagens semanais nas demais vias. Um ajuste
iterativo de probabilidades relaciona cada rota aos pontos atravessados e ao tempo
livre calculado até eles. Conserva a massa regional e registra resíduos, inclusive
quando uma restrição é inviável. Na geração normal os alvos acompanham a realização
sorteada; na comparação de agenda congelada usam medianas de treino.

Esse ajuste é uma projeção de planejamento: não conhece filas, atraso de inserção
ou espera nos sinais. Somente as passagens físicas SUMO podem validar o fluxo realizado.
O ajuste considera a janela inteira: uma seção isolada pode receber escolhas OD
diferentes das obtidas dentro de uma execução maior. A reprodução exige a mesma
seleção completa, além da seed e dos parâmetros.

As posições dos sensores continuam hipóteses: 5 na Niterói e 6 na Rondon rumo centro.
Antes/depois do cruzamento são candidatos alternativos, não contagens somáveis.
Uma conversão entre os pontos pode tornar suas contagens diferentes. Faltam linha
virtual, direção e faixas efetivamente observadas; não há calibração empírica regional
confirmada. MAE/WAPE contra treino e verificação são condicionais a essa correspondência.

O coletor compartilhado registra por portal e intervalo: programados, inseridos,
pendentes de inserção, atrasos e estados finais. Separa conclusões naturais, chegadas
após teleporte, incompletos e não inseridos. Passagens conservadoras excluem qualquer
veículo com teleporte e ficam separadas de `edgeData` nativo. Movimentos entre edges
são observados por `vehroute` com tempos das conexões internas. Tempos até o sensor,
filas e teleportes não são ocultados para melhorar os erros.

**Seções contínuas.** Os comandos abaixo usam um processo SUMO por seleção:

```bash
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day tuesday --start 15:00 --sections 2 --variation 7
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day friday --start 21:00 --sections 2 --variation 7
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day sunday --start 21:00 --sections 2 --variation 7
```

Cada seleção gera uma agenda única, ordenada, sem reiniciar RNG, veículos ou rede
na fronteira. Intervalos são semiabertos. Uma seção programa `[0,10800)` e simula
até 13.500 s; duas programam `[0,21600)` e simulam até 24.300 s. O padrão de
escoamento é 2.700 s, ajustável por `--drain-limit`. O horizonte é fixo mesmo se a
rede esvaziar antes. Inserções e passagens após a janela civil são identificadas e
não integram sua contagem. Não existe aquecimento oculto nem deslocamento da curva
observada para corrigir o início vazio. `--duration`, `--period` e `--end` pertencem
a `random` e são recusados com MetaSettran. Horário civil, tempo relativo, janela
de partidas, horizonte e tempo real de processamento são registrados separadamente.

**Reprodução e limites de aceitação.** `metrics.json` conserva versão, seeds, hashes,
fonte, calibração, parâmetros espaciais, rotas utilizadas e observações. O XML retido
pode ser reutilizado em `run_simulation(demand_file=...)`; gerar com as mesmas
entradas também reproduz suas viagens. Alterar os sinais não sorteia outra demanda.
Os perfis oficiais permanecem intactos. Os diagnósticos de Niterói e Europa ×
Benjamim são configurações temporárias registradas nos resultados, não planos SETTRAN.

A integridade e a continuidade do software não comprovam realismo em todos os
contextos. Volumes regionais, preferências OD, abrangência externa das contagens,
fluxos nas vias sem medição e operação real de `current` continuam incertos.
Aprovação científica exige distribuição justificável, resultados interpretáveis e
verificação independente, não ausência artificial de filas ou 100% de chegadas.

### Configurações e métricas

Os CSVs de `docs/` são referências para consulta; editá-los não configura o
programa. `CONFIGURACOES.csv` contém 65 opções selecionadas e seus padrões da
versão de referência. Todas as opções nativas podem ser consultadas com
`sumo --save-template -`. O resultado guarda a versão SUMO, os parâmetros do
experimento e as opções explícitas em `execution.simulation.configured_options`;
rede e tipos veiculares também definem condições. `Não definido` no padrão de
fábrica de arquivo significa que nenhuma entrada ou saída foi configurada;
`Não habilitado` no uso do projeto significa que o perfil não solicita a saída.
As unidades e o significado de valores especiais, como `-1`, ficam em
`efeito_e_unidade`. Opções nativas não
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
programação semafórica para teste de plano fixo; a demanda é selecionada
independentemente por `--demand-profile`, cujo padrão continua `random`.
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
encontrar os 80 indicadores selecionados; o coletor também produz outros
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

MetaSettran oferece estrutura semanal experimental e transições contínuas; isso
não confirma a calibração empírica de todos os contextos. Reconstrução integral de fluxo,
aprendizagem por reforço, Hazarika, Acciai/TFR, novos controladores e treinamento
continuam futuros. Dados operacionais ausentes bloqueiam planos reais SETTRAN,
mas não impedem MetaSettran com `current`.
