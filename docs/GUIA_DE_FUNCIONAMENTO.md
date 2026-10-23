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
t=0 da simulação corresponde ao dia e horário inicial selecionados.
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
| `--variation` | `1` numa faixa individual sem sorteio | Índice 1–25; exclusivo de uma faixa. Épocas seguintes usam índices consecutivos, sem ultrapassar 25. |
| `--master-seed` | Sorteada e registrada para seleções combinadas | Inteiro 0–2⁶³−1; sorteia independentemente uma variação 1–25 por faixa. Também funciona numa faixa individual. |
| `--variations` | Ausente | Lista explícita com exatamente uma variação 1–25 por faixa; reproduz a demanda sem precisar da seed mestra. |
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

**Relógio, dados e variações.** A versão `metasettran-regional-integrated-v4.3.2-utc`
interpreta os timestamps originais como UTC e os converte explicitamente com
`ZoneInfo("America/Sao_Paulo")` antes de construir datas, weekdays e quartos de hora.
UTC é uma decisão metodológica do projeto, **não uma confirmação do equipamento**:
falta o metadado de fuso do exportador. O CSV não é alterado. Por exemplo, terça
00:30 UTC pertence a segunda 21:30 civil. A conversão ocorre uma vez na leitura
para agregação; timestamps de entrada com fuso explícito exigem revisão e são
recusados. Metadados registram convenção, conversão e datas civis. Somente `car` calibra o modelo;
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

Após a conversão, continuam 67 datas civis observadas, 48 elegíveis para treino e
17 para verificação. A composição e os cortes de datas são recalculados no horário
local; a igualdade das quantidades não significa igualdade dos registros.
Os 672 quartos de hora do CSV atual têm 5–7 datas comuns de treino; não foi
necessário recorrer ao fallback entre weekdays. Cada variação reamostra conjuntamente
um dia completo de treino para cada weekday, compartilhado pelos dois sensores,
preservando a correlação intradia e entre contadores. Há apenas 3–6 dias completos
por weekday: 25 realizações não significam 25 semanas observadas independentes.
A interpolação linear entre centros de 15 min é cíclica na semana e não aplica
outra janela de suavização. Datas vizinhas sorteadas podem não ser consecutivas;
a correlação entre dias permanece uma limitação.

A agenda de referência segue um processo Poisson de taxa contínua sobre a realização
sorteada. A agenda moderada retém `floor(0,85 × N)` posições sistematicamente espaçadas
nessa agenda, com deslocamento pseudoaleatório determinístico. Não é um novo Poisson
independente: é uma amostra de tamanho fixo que preserva a forma temporal e reduz
a variância adicional de remoção. Cada viagem mantida conserva ID, partida, atributos
e percurso. A escolha OD também é consumida para posições removidas, evitando
redistribuição acidental. Não há ajuste por filas durante a execução.
Seed, configuração e versão iguais reproduzem o mesmo XML, independentemente de
`current`/`settran` e `core`/`full`. A variação 7 continua identificada pela seed
1082464323, mas uma mudança da versão do modelo altera as rotas e deve ser registrada.

**População regional e observações.** Há uma população única de viagens.
Uma rota pode atravessar nenhum, um ou vários pontos de observação; incidências
não criam veículos. Não existem origens exclusivas por sensor nem rotas proibidas
somente por atravessarem ambos. A existência de viagens compartilhadas depende da
geografia: não se impõem desvios para produzi-las.

O coeficiente regional histórico permanece `17864,7155948 / (1614,7760417 +
6151,8447917) = 2,30019155`. O denominador é congelado na v4.3.1 **antes** da
conversão. Recalculá-lo na nova terça 15–18 renormalizaria silenciosamente os volumes,
confundindo correção de relógio e mudança de escala. O número 17.864,7 passa a ser
somente a referência histórica do coeficiente, não o novo volume dessa seção.

`taxa_B(t) = 2,30019155 × [car5_UTC→civil(t) + car6_UTC→civil(t)]`

`taxa_C(t) = 0,85 × taxa_B(t); N_C = floor(0,85 × N_B)`

A redução de 15% é uma **hipótese experimental**, fixada antes das simulações para
atender à decisão do projeto de reduzir mais de 10% em cada realização. É uma
moderação limitada da escala não identificável com dois sensores; nenhuma medição
comprova especificamente esse percentual. Mantê-lo comum preserva diferenças
relativas entre contextos e evita inventar reduções por horário ou portal sem dados.
A distribuição espacial já desigual continua sendo a da v4.3.1. Não houve busca
iterativa de um percentual que eliminasse congestionamentos.

A soma de curvas define um índice temporal, não veículos únicos medidos. Não se
divide por cobertura de 5,80%, não se somam VMD como novas viagens nem se aumenta
a demanda periférica para compensar viagens internas ausentes. As datas observadas
representam variabilidade temporal, não um intervalo de confiança do total regional.

O Python permite `source_time_convention="legacy_civil", volume_retention=1` para a
referência A, `source_time_convention="utc", volume_retention=1` para B e os defaults
UTC/0,85 para C. São suportes da comparação controlada, sem novos comandos de CLI.
`generate_metasettran_demand(schedule_file=...)` continua preservando a quantidade,
IDs, atributos e horários da agenda fornecida, alterando somente OD/percursos;
**não reaplica redução** a uma agenda pareada. A geração normal sempre reconstrói B
antes de selecionar C, sem reduções cumulativas.

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
não capacidades semafóricas. Na v4.3.1, cada entrada reparte sua oportunidade pelos ramos dos caminhos nativos.
Em cada divergência, o peso é `faixas de origem permitidas / (1 + ângulo / (π/2))`,
normalizado entre as continuações disponíveis. Uma faixa com várias conexões de
chegada conta uma vez no movimento. O custo angular unitário é hipótese geométrica,
não proporção medida de conversão. Adicionar destinos depois de uma conversão não
multiplica sua oportunidade a montante. Retornos mantêm peso positivo; não há
quota de percursos ou preferência calculada por congestionamento. O algoritmo
apenas distribui probabilidade entre caminhos já calculados pelo `duarouter`.

`duarouter` calcula os caminhos. O catálogo inclui alternativas explícitas por
Jerônimo–Brasil–Niterói, Brasil e João Pinheiro–Jataí, qualificadas pela geometria.
A continuidade Niterói→lado do shopping também admite origens periféricas
geograficamente compatíveis, além da Jerônimo: origem atrás do início e destino
adiante do fim, projetados no eixo orientado da Niterói. Isso remove uma assimetria
do catálogo que oferecia a outras origens principalmente a conversão para a Rondon.
Não há mínimo de veículos nesse caminho nem desvio integral obrigatório pela Brasil.
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
relativa à curva do sensor 6. A interpolação entre centros desses períodos, a transferência aos
demais dias e a razão neutra noturna são hipóteses explícitas; não uma terceira medição.

**Ajuste espacial e validação física.** As probabilidades OD variam a cada 15 min,
com interpolação contínua. A forma relativa do sensor 6 informa o prior arterial
e a do sensor 5 o local,
uma transferência experimental sem contagens semanais nas demais vias. Um ajuste
iterativo de probabilidades relaciona cada rota aos pontos atravessados e ao tempo
livre calculado até eles. Conserva a massa regional e registra resíduos, inclusive
quando uma restrição é inviável. Na geração normal os alvos acompanham a realização
sorteada; na comparação de agenda congelada usam medianas de treino.

Na versão moderada o ajuste OD é feito sobre B, e somente depois se retêm viagens.
Os alvos medidos permanecem intactos; `experimental_target_passages` e projeções
reduzidas ficam separados. Não se reajustam pesos para recuperar artificialmente
a contagem completa com menos veículos.

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

**Seções contínuas e sorteio contextual.** A composição `metasettran-chronological-v1`
preserva a calibração `v4.3.2-utc`. Um único mecanismo atende de uma a 56 faixas
cronológicas. `--sections` conta faixas de três horas, sem interromper a seleção
à meia-noite ou na passagem de domingo para segunda. Não aceita horários arbitrários
nem seleção descontínua. Exemplos no executor compartilhado:

```bash
# Uma faixa específica, preservando a realização individual aprovada
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day tuesday --start 15:00 --sections 1 --variation 7
# Duas faixas, sorteadas independentemente e reproduzíveis
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day tuesday --start 15:00 --sections 2 --master-seed 20261022
# 21 horas: terça 00h–21h
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day tuesday --start 00:00 --sections 7 --master-seed 20261022
# Dia inteiro: segunda 00h–terça 00h
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day monday --start 00:00 --sections 8 --master-seed 20261022
# Dois dias; para uma semana, usar --sections 56
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day monday --start 00:00 --sections 16 --master-seed 20261022
# Meia-noite e virada semanal
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day friday --start 21:00 --sections 2 --master-seed 20261022
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day sunday --start 21:00 --sections 2 --master-seed 20261022
# Reprodução explícita do exemplo de terça 15h–21h acima
python3 -B -m SistemaDeSemaforos.simulation.episode_runner --demand-profile metasettran --day tuesday --start 15:00 --sections 2 --variations 6 8
```

A seed mestra controla sorteios uniformes independentes, com reposição: repetir um
índice em faixas vizinhas é permitido. As 25 variações continuam próprias de cada
contexto. Não se materializam as `25^n` combinações. Sem seed informada numa seleção
combinada, o sistema cria e registra uma seed de 63 bits. A lista explícita não sorteia
novos índices e prevalece sobre uma seed mestra eventualmente informada. `--variation`
não pode ser combinada com lista, seed mestra ou várias faixas. Uma faixa sem opções
continua V1, por compatibilidade; use `--master-seed` para sorteá-la.

`execution.context_selection` registra a seed mestra, a lista, os dias/horários,
as seeds efetivas e o deslocamento semanal antes da geração. A geração conserva
a seleção enriquecida com os orçamentos de cada faixa. Seeds/rotas não dependem de
`current`, `settran`, `core` ou `full`. A mesma lista explícita reproduz o XML da
seleção sorteada, inclusive seus IDs. `--episodes 10` mantém dez episódios independentes:
com `--variation 1`, V1–V10; com seed mestra, seeds de episódio derivadas e registradas;
com lista explícita, repete a mesma realização para comparação.

Cada seleção gera uma única agenda ordenada, com IDs prefixados pelo índice da faixa.
Mantêm-se exatamente as partidas de cada realização individual; perto das fronteiras,
o transporte por quantis apenas reposiciona seus horários dentro da própria faixa.
As marcas aleatórias OD de cada viagem também são preservadas: fora da transição,
mudar uma variação seguinte não altera seus percursos. Não há geração em resposta
às filas, população remanescente ou troca de controlador.

A harmonização altera no máximo **15 minutos de cada lado** de uma fronteira,
compatível com a resolução dos dados. Uma ponte linear positiva une as taxas e
conserva separadamente a integral de cada meia-janela e de cada faixa. Assim, tanto
a expectativa quanto a quantidade programada são as somas individuais, sem inflação.
O valor comum parte da média harmônica das taxas vizinhas. Quando a ponte exigiria
um novo pico ou vale, ajustam-se a junção e a duração das rampas, conservando a área
e respeitando os extremos já presentes na janela. A maior rampa viável espalha a
mudança no tempo; os extremos, eventuais limites de viabilidade e as janelas de
5/15 minutos ficam registrados. Isso é harmonização numérica, não uma nova
estimativa de volume ou evidência de pico real. Uma fronteira matematicamente
incompatível com continuidade, conservação e limite de pico é rejeitada explicitamente,
sem criar viagens ou elevar silenciosamente a taxa.

As probabilidades OD aprovadas nos centros de 15 minutos continuam interpoladas,
inclusive entre as duas faixas: sua junção ocupa 7,5 minutos de cada lado. Não há
novo ajuste espacial, novo roteamento ou desvio obrigatório. Horários transportados
podem mudar a rota sorteada dentro da janela de transição. O manifesto separa as
projeções individuais de passagem, anteriores à harmonização, das passagens efetivas
medidas no SUMO. As curvas medidas de referência não são deslocadas nem suavizadas.

Um único processo SUMO conserva veículos, filas e semáforos durante toda a seleção.
Intervalos são semiabertos. O horizonte é `10800 × sections + 2700` segundos:
6h45, 21h45, 24h45, 48h45 e 168h45 para as seleções correspondentes. O escoamento
ocorre somente ao final, nunca entre faixas, e é ajustável por `--drain-limit`.
O horizonte é fixo mesmo se a rede esvaziar antes. Veículos aguardando inserção e
veículos em circulação continuam no episódio; só o horizonte final define incompletos.
`execution.demand_validation.boundary_continuity` registra essas populações e IDs
com inserção antes e término após cada fronteira, separando ocorrências de teleporte.

Inserções e passagens após a janela civil são identificadas e não integram sua
contagem. Não existe aquecimento oculto nem deslocamento da curva observada para
corrigir o início vazio. `--duration`, `--period` e `--end` pertencem a `random` e
são recusados com MetaSettran. Horário civil, tempo relativo, janela de partidas,
horizonte e tempo real de processamento são registrados separadamente.

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

**Validação vigente — UTC e redução experimental de 15% (22/10/2026).**
A referência A conserva relógio e escala da v4.3.1; B converte UTC sem mudar o
coeficiente regional; C acrescenta a redução de 15%. Não foram alterados rede,
sinais oficiais, parâmetros físicos ou regras de teleporte. A reprodução de A
foi conferida byte a byte contra o XML anterior. Nas comparações B/C, cada viagem
retida tem exatamente os mesmos ID, horário e percurso. Os programas diagnósticos
são os mesmos de Niterói e Europa com quatro atendimentos, usados apenas onde indicado.

**Os 56 contextos.** Cada célula mostra **B → C**, em partidas esperadas, arredondadas,
obtidas pela integração da curva mediana de treino. A redução exata dessa expectativa
é **15,00% em todas as células**. Status comum: cálculo **verificado**, volume regional
**estimado sob hipótese experimental**, não medido. Justificativa comum: curvas
car específicas do dia/horário após UTC, coeficiente regional histórico congelado e
moderação experimental única; não existem percentuais extras por madrugada ou portal.

| Horário civil | Segunda | Terça | Quarta | Quinta | Sexta | Sábado | Domingo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 00–03 | 747 → 635 | 554 → 471 | 644 → 547 | 810 → 688 | 1005 → 854 | 1844 → 1567 | 2181 → 1853 |
| 03–06 | 673 → 572 | 615 → 522 | 626 → 532 | 651 → 554 | 704 → 598 | 783 → 666 | 793 → 674 |
| 06–09 | 12083 → 10270 | 12394 → 10535 | 12592 → 10703 | 12473 → 10602 | 12072 → 10261 | 5486 → 4663 | 2491 → 2117 |
| 09–12 | 13223 → 11239 | 13624 → 11581 | 13789 → 11721 | 13818 → 11745 | 14360 → 12206 | 12610 → 10719 | 6659 → 5661 |
| 12–15 | 16479 → 14007 | 17865 → 15185 | 17636 → 14991 | 17852 → 15174 | 18129 → 15410 | 14791 → 12572 | 10651 → 9054 |
| 15–18 | 16379 → 13922 | 17517 → 14890 | 17736 → 15076 | 17703 → 15047 | 18454 → 15686 | 12374 → 10518 | 10346 → 8794 |
| 18–21 | 13583 → 11546 | 14277 → 12135 | 14977 → 12731 | 15372 → 13067 | 16310 → 13863 | 13159 → 11185 | 10305 → 8760 |
| 21–24 | 4677 → 3976 | 5464 → 4645 | 6295 → 5351 | 6855 → 5826 | 8225 → 6991 | 8895 → 7561 | 4675 → 3973 |

As 1.400 agendas foram verificadas programaticamente, sem gerar 1.400 XMLs.
A redução das quantidades inteiras variou de **15,0000% a 15,1874%**: o arredondamento
para baixo explica a diferença. A ordem de intensidade das variações foi preservada
(admite-se empate por arredondamento); a seleção repetida reproduziu os mesmos IDs.
A→B pode mudar a data doadora da mesma V porque a conversão recompõe os dias
civis completos elegíveis; seed e regra de reamostragem permanecem iguais. B→C
preserva a mesma data doadora e a ordem de intensidade contextual.
O erro máximo por quarto de hora entre a contagem retida e 85% da agenda B foi
1,10 veículo. Isso testa preservação temporal, não acurácia empírica regional.

A conversão mantém mínimos horários de treino do sensor 6 na madrugada (medianas
por weekday entre 03h e 05h), com máximo às 17h nos cinco dias úteis e às 12h no
sábado/domingo. O crescimento matinal e a alta vespertina ficam qualitativamente
mais coerentes com os períodos investigados pelo [estudo UFU](https://repositorio.ufu.br/handle/123456789/49701).
O estudo cobre outras seções e horários delimitados; essa coerência **não comprova UTC**
nem valida a escala regional. Não houve correção artificial de picos. Na terça,
03–06 equivale a 3,51% de 15–18 tanto em B quanto em C. O domingo diurno tem menor
intensidade que os dias úteis, enquanto 00–03 de sábado/domingo permanece acima da
madrugada útil. Há somente 3–6 dias integrais elegíveis por weekday para reamostragem.

**Frequência dinâmica.** Na terça 15–18, os doze intervalos de 15 min têm as seguintes
expectativas; o pico tardio continua presente após a redução:

| Civil | B | C | Intervalo médio B → C (s/veículo) |
| --- | ---: | ---: | ---: |
| 15:00 | 1191 | 1012 | 0.76 → 0.89 |
| 15:15 | 1197 | 1017 | 0.75 → 0.88 |
| 15:30 | 1282 | 1090 | 0.70 → 0.83 |
| 15:45 | 1342 | 1141 | 0.67 → 0.79 |
| 16:00 | 1369 | 1164 | 0.66 → 0.77 |
| 16:15 | 1382 | 1175 | 0.65 → 0.77 |
| 16:30 | 1414 | 1202 | 0.64 → 0.75 |
| 16:45 | 1498 | 1273 | 0.60 → 0.71 |
| 17:00 | 1597 | 1357 | 0.56 → 0.66 |
| 17:15 | 1681 | 1429 | 0.54 → 0.63 |
| 17:30 | 1783 | 1515 | 0.50 → 0.59 |
| 17:45 | 1781 | 1514 | 0.51 → 0.59 |

O intervalo médio descreve a intensidade, não um espaçamento fixo das partidas.
A interpolação permanece linear e contínua; a agenda realizada tem intervalos
variáveis. Em terça 06–09, A previa 615 partidas, B 12.394 e C 10.535; em 21–24,
A previa 14.277, B 5.464 e C 4.645. Portanto o grande deslocamento entre madrugada,
manhã e noite decorre do relógio, não do fator 0,85. A curva temporal local de terça
15–18, antes de qualquer escala/redução, teve WAPE de verificação principal de
12,20%/3,26% para sensores 5/6 e adicional de 7,97%/6,23% (12 e 24 janelas completas).
São erros de previsão local entre datas, separados dos erros das passagens SUMO.

**Operação A/B/C.** Todos os episódios têm 10.800 s de partidas e 2.700 s adicionais.
`N.I.` é quantidade não inserida e seu percentual sobre programados; `Após TP`
são chegadas após teleporte, `Inc.` são inseridos incompletos e `TP` são eventos,
podendo haver vários por veículo. S5/S6 são passagens conservadoras durante as três
horas nos candidatos **anteriores** ao cruzamento, excluindo veículos com qualquer
teleporte. Passagens no escoamento não entram nessa coluna. As referências são links
para os resultados completos; contagens de candidatos anteriores/posteriores não se somam.

| Contexto / sinais / variação | Ref. | Prog. | Inser. | N.I. (%) | Naturais | Após TP | Inc. | TP | S5/S6 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Sáb 00–03 / current / V7 | [A](../outputs/outputs-metasettran/20261022T155705608813Z_8c927e4f/20261022T155705609024Z_seed-1082464323_bf536404/metrics.json) | 8949 | 8949 | 0 (0.00%) | 8865 | 84 | 0 | 87 | 320/3285 |
| Sáb 00–03 / current / V7 | [B](../outputs/outputs-metasettran/20261022T172202641873Z_364fe02b/20261022T172202642108Z_seed-1082464323_f250e315/metrics.json) | 2335 | 2335 | 0 (0.00%) | 2335 | 0 | 0 | 0 | 127/859 |
| Sáb 00–03 / current / V7 | [C](../outputs/outputs-metasettran/20261022T172210316226Z_42a75b68/20261022T172210316406Z_seed-1082464323_61b453fc/metrics.json) | 1984 | 1984 | 0 (0.00%) | 1984 | 0 | 0 | 0 | 104/742 |
| Sáb 12–15 / current / V7 | [A](../outputs/outputs-metasettran/20261022T155816780602Z_af267fb1/20261022T155816780816Z_seed-1082464323_7f8cbac4/metrics.json) | 13730 | 13499 | 231 (1.68%) | 11897 | 517 | 1085 | 1147 | 141/4445 |
| Sáb 12–15 / current / V7 | [B](../outputs/outputs-metasettran/20261022T172230000152Z_efaec85b/20261022T172230000334Z_seed-1082464323_f905f6d6/metrics.json) | 15822 | 14717 | 1105 (6.98%) | 11848 | 1072 | 1797 | 2456 | 15/4831 |
| Sáb 12–15 / current / V7 | [C](../outputs/outputs-metasettran/20261022T172231220014Z_82b31b0e/20261022T172231220182Z_seed-1082464323_89f08ff3/metrics.json) | 13448 | 13172 | 276 (2.05%) | 11634 | 587 | 951 | 1166 | 51/4439 |
| Dom 12–15 / current / V7 | [A](../outputs/outputs-metasettran/20261022T172655313898Z_408e80a3/20261022T172655314100Z_seed-1082464323_22ae2ef5/metrics.json) | 6461 | 6461 | 0 (0.00%) | 6461 | 0 | 0 | 0 | 393/2342 |
| Dom 12–15 / current / V7 | [B](../outputs/outputs-metasettran/20261022T172236061224Z_f38a6c14/20261022T172236061387Z_seed-1082464323_f00aa8c3/metrics.json) | 10361 | 10361 | 0 (0.00%) | 10080 | 281 | 0 | 310 | 275/3549 |
| Dom 12–15 / current / V7 | [C](../outputs/outputs-metasettran/20261022T172409359831Z_2831da7e/20261022T172409360017Z_seed-1082464323_93ad042c/metrics.json) | 8806 | 8806 | 0 (0.00%) | 8740 | 66 | 0 | 66 | 439/3094 |
| Ter 03–06 / current / V7 | [A](../outputs/outputs-metasettran/20261022T155527670181Z_1d4e38c6/20261022T155527670407Z_seed-1082464323_a4be8d7c/metrics.json) | 567 | 567 | 0 (0.00%) | 567 | 0 | 0 | 0 | 41/181 |
| Ter 03–06 / current / V7 | [B](../outputs/outputs-metasettran/20261022T172028527414Z_cb5da8e4/20261022T172028527570Z_seed-1082464323_079dc670/metrics.json) | 602 | 602 | 0 (0.00%) | 602 | 0 | 0 | 0 | 24/222 |
| Ter 03–06 / current / V7 | [C](../outputs/outputs-metasettran/20261022T172036644244Z_eb9d8a21/20261022T172036644411Z_seed-1082464323_eb14cb32/metrics.json) | 511 | 511 | 0 (0.00%) | 511 | 0 | 0 | 0 | 21/186 |
| Ter 06–09 / current / V7 | [A](../outputs/outputs-metasettran/20261022T155527668089Z_6fe1aebc/20261022T155527668310Z_seed-1082464323_1a1d6fc1/metrics.json) | 602 | 602 | 0 (0.00%) | 602 | 0 | 0 | 0 | 25/219 |
| Ter 06–09 / current / V7 | [B](../outputs/outputs-metasettran/20261022T172036947453Z_5ae6ee6b/20261022T172036947622Z_seed-1082464323_2490d56d/metrics.json) | 10596 | 10596 | 0 (0.00%) | 10232 | 362 | 2 | 392 | 127/3482 |
| Ter 06–09 / current / V7 | [C](../outputs/outputs-metasettran/20261022T172047034722Z_8f70ff40/20261022T172047034895Z_seed-1082464323_e039d27a/metrics.json) | 9006 | 9006 | 0 (0.00%) | 8796 | 210 | 0 | 224 | 147/3046 |
| Ter 15–18 / current / V7 | [A](../outputs/outputs-metasettran/20261022T172741444382Z_39ad1a61/20261022T172741444551Z_seed-1082464323_e47ef657/metrics.json) | 16501 | 15339 | 1162 (7.04%) | 12475 | 975 | 1889 | 2312 | 29/5252 |
| Ter 15–18 / current / V7 | [B](../outputs/outputs-metasettran/20261022T172502936486Z_268100c1/20261022T172502936677Z_seed-1082464323_86ae4cce/metrics.json) | 17132 | 16133 | 999 (5.83%) | 12558 | 1074 | 2501 | 2372 | 43/4201 |
| Ter 15–18 / current / V7 | [C](../outputs/outputs-metasettran/20261022T172512613381Z_ecef7574/20261022T172512613593Z_seed-1082464323_408656c6/metrics.json) | 14562 | 14306 | 256 (1.76%) | 12048 | 684 | 1574 | 1642 | 100/4512 |
| Ter 21–24 / current / V7 | [A](../outputs/outputs-metasettran/20261022T155551552048Z_acde19be/20261022T155551552286Z_seed-1082464323_e74a0498/metrics.json) | 14551 | 13792 | 759 (5.22%) | 10986 | 1120 | 1686 | 2406 | 12/4689 |
| Ter 21–24 / current / V7 | [B](../outputs/outputs-metasettran/20261022T172057689784Z_80fab562/20261022T172057689986Z_seed-1082464323_4b065029/metrics.json) | 5272 | 5272 | 0 (0.00%) | 5272 | 0 | 0 | 0 | 370/1910 |
| Ter 21–24 / current / V7 | [C](../outputs/outputs-metasettran/20261022T172134527341Z_bed67ff4/20261022T172134527513Z_seed-1082464323_7a2b5e71/metrics.json) | 4481 | 4481 | 0 (0.00%) | 4481 | 0 | 0 | 0 | 314/1628 |
| Ter 15–18 / diag / V7 | [A](../outputs/outputs-metasettran/20261022T160314612039Z_230291ec/20261022T160314612215Z_seed-1082464323_4929630c/metrics.json) | 16501 | 16334 | 167 (1.01%) | 14936 | 377 | 1021 | 902 | 825/4965 |
| Ter 15–18 / diag / V7 | [B](../outputs/outputs-metasettran/20261022T171645391439Z_c5727ad2/20261022T171645391651Z_seed-1082464323_2a6ad3ac/metrics.json) | 17132 | 16738 | 394 (2.30%) | 15063 | 339 | 1336 | 798 | 784/5035 |
| Ter 15–18 / diag / V7 | [C](../outputs/outputs-metasettran/20261022T171645398519Z_adbd36fc/20261022T171645398659Z_seed-1082464323_09f8dff4/metrics.json) | 14562 | 14562 | 0 (0.00%) | 14470 | 92 | 0 | 97 | 1067/4608 |
| Ter 15–18 / diag / V8 | [A](../outputs/outputs-metasettran/20261022T160314610233Z_0a052027/20261022T160314610432Z_seed-1817779227_70f66330/metrics.json) | 18351 | 17380 | 971 (5.29%) | 14644 | 842 | 1894 | 2084 | 627/5028 |
| Ter 15–18 / diag / V8 | [B](../outputs/outputs-metasettran/20261022T171645397942Z_3ee3b42a/20261022T171645398171Z_seed-1817779227_74b7d4ac/metrics.json) | 18025 | 17878 | 147 (0.82%) | 15897 | 413 | 1568 | 884 | 1077/4704 |
| Ter 15–18 / diag / V8 | [C](../outputs/outputs-metasettran/20261022T171826847311Z_253af1a2/20261022T171826847535Z_seed-1817779227_11ff67b4/metrics.json) | 15321 | 15321 | 0 (0.00%) | 15151 | 170 | 0 | 181 | 1136/4277 |

Na tarde diagnóstica, B→C reduz o atraso médio de inserção de **76,0→22,1 s** (V7)
e **199,4→44,7 s** (V8). Os não inseridos caem de 394 (2,30%) e 147 (0,82%) para
zero; os incompletos de 1.336/1.568 para zero. A média de veículos parados cai de
920→200 e 938→365. A quantidade absoluta de conclusões naturais diminui porque há
menos partidas; sua proporção aumenta. Não se exige conclusão integral nem se
apresenta esse resultado como prova de realismo.

Com a mesma demanda C V7, mudar somente dos sinais diagnósticos para `current`
reduz naturais de 14.470 para 12.048, aumenta teleportes de 97 para 1.642 e deixa
256 não inseridos e 1.574 incompletos. S5 cai de 1.067 para 100 passagens. Isso
isola um efeito relevante da configuração semafórica, sem comprovar qual representa
a infraestrutura real. Dentro de `current`, B→C reduz não inseridos de 999 (5,83%)
para 256 (1,76%) e atraso médio de 223,9 para 32,7 s. Dos 256 não inseridos,
209 pertencem ao acesso `261533408` e 47 à Benjamim Constant; as retenções da Niterói
continuam visíveis nos logs e nas curvas de passagem. As limitações não desaparecem.

**Sensores e espacialidade.** Na tarde V7, planejadas/efetivas durante a janela são
1.303/784→1.111/1.067 no candidato 5 e 6.183/5.035→5.283/4.608 no 6. Em V8,
1.571/1.077→1.354/1.136 e 6.495/4.704→5.512/4.277. Planejadas contam rotas contendo
o edge, independentemente do instante de passagem; efetivas são passagens físicas
sem teleporte dentro das três horas. Na redução V7 ainda ocorrem 28/615 passagens
nos candidatos 5/6 durante o escoamento, separadas da janela civil.

O sensor 5 melhora operacionalmente, enquanto o 6 recebe menos passagens. O WAPE
contra a curva central nos candidatos anteriores muda de 45,1%→25,5% (5) e
18,6%→25,5% (6) em V7; de 34,1%→24,0% e 24,0%→30,9% em V8. Os candidatos
posteriores resultam em 754/4.566 e 789/4.236 passagens em C. A redução não foi
escolhida para fazer esses erros parecerem melhores. Sensores sem linha/faixas
confirmadas continuam impedindo uma declaração de calibração empírica regional.

Os 44 portais de entrada e 37 de saída continuaram utilizados na tarde, sem quotas
obrigatórias; C usou 897 percursos em V7 e 914 em V8, de 1.908 disponíveis. Na V7,
entrada sudoeste da Rondon: 4.753→3.990; nordeste: 5.511→4.726; laterais: 6.868→5.846.
As participações permanecem próximas de 27%/32%/40%. Mediana de percurso 3,052 km,
mínimo 143 m e máximo 6,766 km em V7; rotas curtas válidas permanecem. A conversão
Rondon→João Naves programa 907→768 e realiza 676→593 passagens sem teleporte na
janela. Jerônimo–Afonso programa 126→104, Jerônimo–Brasil 95→82 e o movimento
conflitante reto da Brasil 19→18. Não se promoveu o desvio integral pela Brasil;
a pequena amostra de conflitos permanece uma limitação, não prova de baixa demanda real.

Persistem retenções na região da Benjamim (edges `666324302#1`, `300971367#3`) e em
acessos secundários. Na tarde diagnóstica C, o portal `30621472#0` (Praça Senador
Camilo Chaves) apresenta atrasos médios de 853/967 s em V7/V8, mesmo após todos
entrarem. No sábado C com `current`, `261533408` e Benjamim Constant concentram
170 e 106 não inseridos; há 951 incompletos. B→C melhora esse caso, mas frente a A
os não inseridos passam de 231 para 276 e os teleportes de 1.147 para 1.166.
Relógio, distribuição contextual e operação dos sinais não podem ser confundidos
com o efeito isolado da redução. Não houve uma nova redução para eliminar esses resíduos.

**Verificação e encaminhamento.** Passaram **282 testes**: 80 de demanda, 130 de
simulação e 72 de métricas. Incluem conversão com virada de data, corte temporal,
conservação da fonte, ausência de conversão/redução cumulativa, reprodução, subset
exato B/C, contagens compartilhadas, portais, permissões, `random`, `current`,
validação `settran`, `core`, `full`, dez épocas e continuidade existente.
Foram executados 20 episódios nativos novos; sete resultados anteriores idênticos
foram reaproveitados. Os 27 passaram no validador compartilhado e na contabilidade
programados→inseridos→estados finais. 276.171 definições de viagem desses episódios
foram verificadas contra os portais e conexões passenger. Nove pares B/C preservam
exatamente as viagens retidas. A mesma demanda C V7 foi reutilizada entre os sinais
oficiais e diagnósticos, sem novo sorteio.

A regeneração nativa C V7 reproduziu SHA-256
`3a2ec055425ed86a4481c4276fa0f51064f007af6ebe620b338a859d403e82ce`.
Foram geradas e validadas também as seleções de seis horas: terça 15–21 (26.552),
sexta 21–sábado 03 (9.195) e domingo 21–segunda 03 (4.771), mantendo agenda única
ordenada e extremos válidos. O horizonte de 24.300 s segue coberto pelos testes do
runner; estas três seleções não foram novamente simuladas naquela rodada de recalibração.
O sorteio contextual e a harmonização foram implementados posteriormente, conforme
a seção operacional acima e a validação de integração abaixo.

CSV, rede, sinais oficiais e resultados anteriores permanecem intactos. Os scripts,
cópias e XMLs usados somente nas verificações temporárias foram removidos; episódios
retêm suas rotas, parâmetros, seeds, logs e métricas no local habitual. O checkpoint
`refs/codex/metasettran-before-utc-reduction-20261022` preserva a base anterior,
sem alterar HEAD nem o índice de trabalho do colaborador.

**Decisão:** apto para uso **experimental** e avanço às transições temporais, sem
falha estrutural identificada nesta rodada. Isso não significa demanda regional
empiricamente calibrada nem aprovação irrestrita de `current`: permanecem a hipótese
UTC, a escala absoluta, sensores não confirmados, fluxos laterais estimados,
classificação veicular limitada a carros e viagens internas excluídas. Congestionamento
residual exige interpretação por cenário. Esta rodada encerra a recalibração; novos
ajustes substanciais de intensidade ou distribuição dependem de autorização.

**Validação da integração cronológica (2026-10-23).** A composição
`metasettran-chronological-v1` foi concluída sobre a calibração aprovada, sem
alterar seus volumes ou pesos. A seed mestra `20261022` selecionou `[6, 8]`
para duas faixas, `[6, 8, 22, 23, 4, 1, 12]` para sete e acrescentou `23`
para oito. Para 16 faixas, acrescentou `[16, 1, 13, 7, 5, 15, 4, 24]`.
Repetições são sorteios válidos; não há exigência de índices distintos.

| Seleção | Expectativa individual somada | Expectativa combinada | Partidas individuais somadas = combinadas |
|---|---:|---:|---:|
| Terça 15h–21h | 26.323,12 | 26.323,12 | 26.363 |
| Sexta 21h–sábado 03h | 7.730,29 | 7.730,29 | 7.753 |
| Domingo 21h–segunda 03h | 5.225,14 | 5.225,14 | 5.214 |
| Terça 00h–21h | 62.627,05 | 62.627,05 | 62.734 |
| Segunda 00h–terça 00h | 53.750,17 | 53.750,17 | 53.968 |
| Segunda 00h–quarta 00h | 123.694,57 | 123.694,57 | 124.506 |
| Segunda 00h–segunda seguinte 00h | 446.789,04 | 446.789,04 | 449.170 |

A diferença entre expectativa e realização é estocástica; a integração acrescentou
**zero viagens**. Na semana gerada, os 449.170 IDs são únicos, as partidas estão
ordenadas e as 1.662 rotas distintas usadas respeitam portais, permissões e conexões.
Todos os **672 intervalos de 15 minutos** conservaram exatamente a quantidade
programada de suas realizações individuais. O maior resíduo de conservação por
faixa foi inferior a `8e-12` veículo esperado; o resíduo semanal foi `6e-11`.

Foram verificadas as **35.000 combinações de fronteira**: 56 mudanças cronológicas
× 25 variações anteriores × 25 seguintes. Nenhuma falhou ou exigiu relaxar o mínimo
local; nenhuma criou pico superior ao máximo da janela original, além de erro de
ponto flutuante (`4,5e-16` relativo). As taxas coincidem na junção, e as probabilidades
OD interpoladas não têm salto de valor. Isso verifica continuidade e conservação;
não exige contagens iguais em janelas sucessivas, que podem refletir tendências reais.

Exemplo terça às 18h, V6→V8: nas janelas de cinco minutos anterior/posterior,
as expectativas passam de 483,77/514,05 para 487,21/499,86; foram programadas
474/506 partidas. Nas janelas de 15 minutos, as expectativas 1.468,13/1.516,02
e as contagens 1.427/1.508 permanecem iguais às individuais. A taxa comum é
1,63190 veículo/s, dentro do intervalo original 1,61006–1,72706. Não se apagou
o aumento sustentado pela curva nem se acrescentaram veículos para compensar filas.

As execuções abaixo usaram um único SUMO por seleção, perfil `core` e escoamento
final de 2.700 s. **D** indica os programas diagnósticos já existentes de Niterói e
Europa com quatro atendimentos, fixos entre esses testes; **C** é `current` oficial,
sem substituições. Os diagnósticos permanecem temporários, identificados com suas
fases em `generation.operational_experiment`; não são planos reais SETTRAN.
Links apontam para os lotes finais preservados em `outputs/outputs-metasettran/`.

| Seleção / sinais | Programados | Inseridos | Não inseridos | Naturais | Chegadas após TP | Incompletos | Eventos TP |
|---|---:|---:|---:|---:|---:|---:|---:|
| [Terça 15–21 / D](../outputs/outputs-metasettran/20261022T232851003625Z_e823819c/) | 26.363 | 25.540 | 823 | 22.944 | 1.182 | 1.414 | 2.534 |
| [Terça 15–21 / C](../outputs/outputs-metasettran/20261022T230410652340Z_1354023f/) | 26.363 | 22.967 | 3.396 | 18.738 | 2.323 | 1.906 | 5.257 |
| [Sexta 21–sábado 03 / D](../outputs/outputs-metasettran/20261022T233439887509Z_7c25b129/) | 7.753 | 7.753 | 0 | 7.753 | 0 | 0 | 0 |
| [Domingo 21–segunda 03 / D](../outputs/outputs-metasettran/20261022T233533040432Z_236d518e/) | 5.214 | 5.214 | 0 | 5.214 | 0 | 0 | 0 |
| [Terça 00–21 / D](../outputs/outputs-metasettran/20261022T230401429548Z_d9d9a1fe/) | 62.734 | 52.794 | 9.940 | 45.853 | 5.075 | 1.866 | 10.285 |
| [Segunda 00–terça 00 / D](../outputs/outputs-metasettran/20261022T230401404718Z_3436b712/) | 53.968 | 49.144 | 4.824 | 43.475 | 4.406 | 1.263 | 8.856 |
| [Segunda 00–quarta 00 / D](../outputs/outputs-metasettran/20261022T230401422667Z_a4f85aef/) | 124.506 | 115.041 | 9.465 | 102.759 | 10.535 | 1.747 | 20.841 |

Eventos de teleporte não são veículos distintos nem chegadas após teleporte.
Nos sete episódios, `programados = inseridos + não inseridos` e
`inseridos = naturais + chegadas após TP + incompletos`; não houve remoções
de término desconhecido. Os sete passaram no validador compartilhado, com 72
registros tipados por episódio. Horizontes efetivos: 24.300, 78.300, 89.100 e
175.500 s para 6, 21, 24 e 48 horas de partidas.

Houve continuidade comprovada por IDs: no teste de seis horas D, 1.281 viagens
sem qualquer teleporte atravessaram as 18h em circulação; nas viradas de sexta
e domingo, foram 74 e 38. Nas 48 horas, todas as 15 fronteiras mantiveram veículos,
incluindo 649 sem teleporte na meia-noite entre os dois dias. O veículo
`ms_s000_000879`, por exemplo, entrou em 10.475 s e chegou naturalmente em 10.805 s,
atravessando a primeira fronteira de 10.800 s. Essas contagens são conservadoras:
excluem qualquer viagem que tenha sofrido teleporte em outro momento e não devem
ser somadas entre fronteiras como veículos distintos. Pendências de inserção também
persistem; não há liberação instantânea ou descarte na troca de faixa.

O teste de 48 horas levou 46,3 minutos de processamento nesta máquina. A semana
completa foi **gerada e validada, mas não simulada no SUMO**, limitando o custo desta
etapa. Seu XML reproduzível tem SHA-256
`8feba24e7146859f180d8ccef6077d83235ba00ebc8fadae145c12ed6418e583`.
O teste de uma faixa terça V7 conservou as 14.562 viagens e o SHA aprovado acima.
Na seleção terça 15–21, seed mestra e lista explícita `[6, 8]` reproduziram o mesmo
XML, inclusive nas execuções D/C: SHA-256
`0159684ea9e1bb164ec0e2b5c446d1e05362bf17050138c571a3343427ef3a83`.

Passaram **321 testes**: 104 de demanda, 140 de simulação e 77 de métricas,
incluindo reprodução, sorteios, conservação, continuidade, `random`, `current`,
validação de `settran`, `core`, `full` e dez épocas. CSV, calibração, parâmetros
espaciais e rede oficial mantiveram seus hashes. O checkpoint
`refs/codex/metasettran-before-chronology-20261022` preserva o estado anterior.
Os artefatos temporários de geração e os scripts desta verificação foram removidos;
resultados, rotas e configurações dos episódios permanecem no mecanismo habitual.

**Decisão da integração:** apta para uso experimental, sem falha estrutural
identificada na composição. Permanecem filas, teleportes e inserções pendentes,
inclusive sob sinais diagnósticos; a troca de faixa conserva esses problemas em vez
de reiniciar a rede. A igualdade do XML D/C permite separar a demanda da configuração
semafórica, mas não comprova realismo dos programas diagnósticos. A execução semanal
completa ainda carece de validação operacional. Não houve nova calibração nem
aprovação científica adicional da escala regional ou dos sensores.

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
