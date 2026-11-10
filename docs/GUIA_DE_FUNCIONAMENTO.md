# Guia de funcionamento do EDI

Referência técnica do funcionamento atual, das hipóteses de demanda e da reprodução
de experimentos. A instalação e o uso cotidiano estão no [README](../README.md).

- [Fluxo e responsabilidades](#fluxo-e-responsabilidades)
- [Execuções e reprodutibilidade](#execuções-e-reprodutibilidade)
- [Modelo MetaSettran](#modelo-metasettran)
- [Resultados e interpretação](#resultados-e-interpretação)
- [Programação semafórica](#programação-semafórica)
- [Validar e medir custo](#validar-e-medir-custo)
- [Manutenção e histórico](#manutenção-e-histórico)

## Fluxo e responsabilidades

```text
Interface web ou CLI → seleção e planejamento dos episódios
                    → geração Random ou MetaSettran
                    → execução SUMO com a programação selecionada
                    → coleta core/full/diagnostic → publicação dos resultados
```

O EDI usa processos nativos aguardados por `subprocess.run`, arquivos XML e coleta
posterior à simulação. O servidor web executa o lote em uma thread e oferece consulta
de estado e navegação pelos resultados.
Trocar de página ou cancelar um download pode fechar a conexão HTTP antes do fim
da resposta. A interface encerra essa requisição sem tentar enviar outra resposta;
o lote continua na thread de execução.

`make interface` mantém o servidor no terminal. `make kill-interface` solicita
que somente a instância desta cópia do projeto pare de atender e aguarde o lote
terminar, como `Ctrl+C`. Não há encerramento por PID, nome ou porta. Um lock
nativo (`fcntl` no Linux, `msvcrt` no Windows) impede instâncias duplicadas e é
liberado pelo sistema se o processo falhar. Em `.runtime/`, `interface.lock`
permanece entre execuções; `interface.json` identifica a instância e sua porta,
e `interface.stop` leva o pedido de parada. Identificadores antigos são ignorados.
O lock permanece ocupado durante a conclusão do lote. Não remova essa pasta
enquanto a interface estiver ativa. As ferramentas SUMO chamadas pelo worker
ficam em uma sessão/grupo separado para que o `Ctrl+C` do servidor não as interrompa;
as chamadas CLI na thread principal mantêm o comportamento anterior.

No Windows, `tzdata` fornece `America/Sao_Paulo`; não há mudança na conversão
temporal nem nas seeds. Configuração, execução e consulta usam os mesmos módulos.
Na exclusão, o Git protege arquivos do índice e de HEAD. A mesma rotina Python
percorre apenas os dois perfis autorizados e preserva links, incluindo junctions.
Ela usa operações por nome dentro de diretórios cuja identidade foi conferida,
em um processo curto com CWD próprio; assim não depende de `fwalk`/`dir_fd` nem
altera o diretório do servidor. Pastas sem leitura não são percorridas, como no
mecanismo anterior. Trocas de diretório e falhas ao remover arquivos interrompem
a exclusão, sem forçar permissões ou reverter arquivos já removidos.
O lock do lote permanece adquirido até a operação terminar.
A instalação está no README. A validação nativa de Make, lock, sinais, exclusão,
SUMO/SUMO-GUI e caminhos Windows permanece pendente; mocks não substituem esse ensaio.

| Componente | Responsabilidade |
| --- | --- |
| `simulation/episode_runner.py` | Planejar faixas e grupos, executar episódios e registrar condições. |
| `simulation/web_interface.py` e `.html` | Formulário, validação das entradas, estado do lote e consulta dos outputs. |
| `demand/random_demand_generator.py` | Preparar viagens Random com as ferramentas nativas SUMO. |
| `demand/metasettran_calibration.py` | Ler contagens, tratar exposição e construir curvas e realizações temporais. |
| `demand/metasettran_network.py` | Ler a rede passenger, distribuir acessos e propor alternativas de cobertura. |
| `demand/metasettran_demand_generator.py` | Combinar taxas, oportunidades OD, caminhos e retenções. |
| `demand/metasettran_transitions.py` | Compor curvas e transportar partidas nas fronteiras temporais. |
| `simulation/settran_configuration.py` | Validar e converter suplementos operacionais semafóricos. |
| `metrics/` | Configurar observações, calcular métricas e publicar JSONs tipados. |

Os caminhos da tabela são relativos a `SistemaDeSemaforos/`. A preparação espacial
compartilha uma leitura da rede entre expansão dos acessos e validação das rotas.
O cadastro espacial e a rede física têm hashes próprios registrados nos resultados.
Na validação da versão da rede pelo cadastro MetaSettran, uma conversão de LF para
CRLF no checkout Windows é aceita sem alterar o XML. Qualquer outra diferença
continua sujeita à verificação do hash; `source_network_sha256` registra os bytes
do arquivo efetivamente utilizado, inclusive seus finais de linha.

## Execuções e reprodutibilidade

### Seleção de faixas e episódios

Cada faixa MetaSettran dura 10.800 segundos. O modo consecutivo aceita 1–56 faixas,
com inícios a cada três horas e passagem por meia-noite e pela fronteira semanal.
A seleção livre da interface executa as faixas separadamente ou agrupa as adjacentes.
O agrupador e a API Python `run_episodes(selected_sections=..., consecutive_grouping_enabled=...)`
representam a grade por índices de 0 a 55, de segunda 00h a domingo 21h.

O executor percorre episódio → grupo. Um grupo mantém a mesma simulação e seus
veículos nas fronteiras. Grupos separados iniciam redes vazias. O escoamento padrão
é de 2.700 segundos ao final de cada execução. Três grupos e dois episódios produzem
seis execuções, cada uma com diretório próprio.

### Seeds e variações

- `--variation N` escolhe uma faixa individual. Episódios seguintes usam N+1, N+2,
  até o limite 25. A chamada direta de uma faixa sem seleção explícita usa V1.
- `--master-seed` sorteia uma variação de 1 a 25 por faixa. As seeds de episódios
  e grupos adicionais são derivadas e registradas.
- `--variations` fornece exatamente um índice por faixa. A sequência explícita
  permite repetir a realização entre episódios.
- A interface sorteia uma seed mestra quando o campo de variações está vazio,
  inclusive para uma única faixa.

A composição usa `metasettran-chronological-v1`. Curvas adjacentes são harmonizadas
nas fronteiras, com transporte dos horários e conservação dos orçamentos por faixa.
A seleção completa participa da reprodução. Uma faixa isolada pode ter escolhas OD
diferentes da mesma faixa dentro de um grupo maior.

Para comparar controladores ou perfis de coleta, mantenha rede, demanda, versão,
seeds, timestep, horizonte e seleção completa equivalentes. Reutilizar o mesmo XML
MetaSettran permite fixar a demanda planejada. A configuração efetiva e as opções
nativas ficam em `execution.simulation.configured_options`.

### Parâmetros do executor

As opções estão disponíveis em `python3 -B -m SistemaDeSemaforos.simulation.episode_runner --help`.
Random usa duração de geração de 7.200 segundos, período de 1,5 segundo e término
natural. MetaSettran define sua duração pela seleção de faixas e usa `--drain-limit`
para o escoamento. Ambos usam timestep nativo de 1 segundo nos ensaios de referência.

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
| `--metrics-profile` | `core` | `core`, `full` ou `diagnostic`; o último é exclusivo do terminal/API Python. |
| `--signal-profile` | `current` | Programas da rede ou `settran` validado. |
| `--settran-plan` | Ausente | ID oficial escolhido explicitamente; exige `settran`. |
| `--settran-intersection` | Todas do plano | Nome exato e repetível para selecionar interseções; exige `settran`. |
| `--gui` | Desativado | Abre e fecha `sumo-gui` por episódio. |
| `--net-file` | Rede Rondon Norte do projeto | Seleciona a rede física. |
| `--output-dir` | `outputs/outputs-<perfil de demanda>/` | Destino dos lotes dentro da árvore correspondente. |

## Modelo MetaSettran

### Fontes e interpretação temporal

O modelo ativo é `metasettran-regional-integrated-v4.8-directional-local-access`,
cenário `regional-integrated`. `regional-midpoint` é um alias de compatibilidade.

| Fonte | Uso |
| --- | --- |
| [Medicoes_5_6.csv](Medicoes_5_6.csv) | Contagens `car` dos sensores 5 e 6. |
| [metasettran_spatial.json](../SistemaDeSemaforos/demand/metasettran_spatial.json) | Portais, zonas, hipóteses, referências cartográficas e políticas de distribuição. |
| [Rede SUMO](../SistemaDeSemaforos/network/uberlandia.vehicular.families.16_2_4.net.xml) | Geometria, permissões, conexões e programas `current`. |

Os timestamps da fonte são interpretados como UTC e convertidos para
`America/Sao_Paulo` antes da agregação. Essa convenção é uma decisão metodológica
pendente de confirmação do exportador. A posição dos sensores também permanece
hipotética, com 5 na Niterói e 6 na Rondon rumo centro.

Intervalos aceitos de até 120 segundos são rateados por sobreposição. Cada quarto
de hora exige pelo menos 95% de exposição nos dois sensores. As curvas de treino
usam datas anteriores a 24/08/2026, com exclusão dos feriados cadastrados. A semana
iniciada nessa data é a verificação principal e as posteriores são adicionais.
Lacunas conservam sua condição de dado ausente.

Cada uma das 25 variações reamostra conjuntamente um dia completo de treino por
dia da semana, compartilhado pelos dois sensores. A correlação intradia é preservada.
A interpolação linear entre centros de 15 minutos é cíclica na semana. O suporte
atual tem 3–6 dias completos por weekday, o que limita a independência das realizações.

### Taxa regional e retenções

O coeficiente regional é congelado em
`17864,7155948 / (1614,7760417 + 6151,8447917) = 2,30019155`.
Ele multiplica a soma das curvas dos dois sensores como índice temporal.
A escala regional é uma hipótese, pois essas contagens admitem incidências sobrepostas.

A agenda inicial segue um processo Poisson de taxa contínua sobre a realização.
Os seletores sistemáticos definem as seguintes retenções sobre essa agenda.
O sorteio OD cobre toda a agenda antes da remoção por origem e do corte final.

| Etapa | Política |
| --- | --- |
| Regional | Reter `floor(0,85 × N)` da agenda de referência. |
| Por origem | Reter 90% das partidas fora dos grupos protegidos `rondon_sudoeste` e `rondon_nordeste`, por contexto. |
| Final | Reter `floor(0,95 × N)` da população restante de cada faixa. |

Os fatores nominais compostos são 0,8075 para origens protegidas e 0,72675 para
as demais. A dependência da origem e os arredondamentos podem mudar a contagem
final ao mudar os pesos. A escolha OD consome também os sorteios das posições
posteriormente removidas. IDs, atributos e percursos retidos são conservados.
`volume_recalibration`, `lateral_origin_reduction` e `final_adjustment` registram
as contagens e as hipóteses aplicadas.

A API permite controlar `volume_retention` e `final_volume_retention`. Uma agenda
explícita `schedule_file` conserva IDs, tipos, horários e quantidade, usando curvas
medianas e dispensando as retenções. Esse contrato tem condições diferentes da
geração normal com curvas realizadas. Comparações devem identificar qual contrato usam.

### Distribuição espacial e escolha de caminhos

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
não capacidades semafóricas. A classificação funcional foi conferida no
[mapa municipal de setembro de 2026](https://docs.uberlandia.mg.gov.br/wp-content/uploads/2026/09/Mapa_Sistema_Viario_2026_LC_No_14.850_SETEMBRO_2026_pdf.pdf):
301 segmentos de corredores estruturais e 144 de coletoras recebem um
`road_hierarchy_overrides` para o cálculo da demanda. Brasil, Cesário Alvim e
João Pinheiro, por exemplo, tinham trechos OSM residenciais apesar da função
estrutural municipal. O proxy usa `primary` para estrutural e `tertiary` para
coletora, sem alterar limites de velocidade, faixas, conexões ou a rede física.

O modelo `metasettran-regional-integrated-v4.8-directional-local-access`, método
`urban_activity_od`, separa escolha do destino e escolha do caminho:

1. A oportunidade de cada zona é repartida entre seus acessos, uma única vez.
   Áreas externas herdam as oportunidades físicas/VMD dos portais; os três polos
   mantêm proxies ordinais 4/2/1. Zonas locais compartilham oportunidades
   proporcionais à extensão viária, sem contar cada gate como uma nova população.
2. Perfis de produção e atração por hora civil distinguem dias úteis, sábado e
   domingo. Comércio, serviços, ensino e residência têm formas diferentes, com
   interpolação contínua das probabilidades de 15 min. Os [horários oficiais do
   shopping](https://centershopping.com.br/horarios/) e as funções urbanas
   sustentam a distinção; os multiplicadores não são taxas de viagens medidas.
   As células locais herdam o perfil residencial/misto antes usado na amostra
   do Tibery, sem interpretar domicílios do bairro inteiro como população do recorte.
3. Viagens entre bordas consideram progresso geográfico em relação ao comprimento
   do trajeto, evitando privilegiar a primeira saída próxima. Viagens de atividade
   usam impedância `exp(-distância/2000 m)`. Retorno ao mesmo acesso recebe fator
   0,05; retornos legais continuam possíveis. Esses coeficientes são hipóteses.
4. Dentro de cada OD, alternativas são repartidas pelo custo relativo do percurso
   completo e pelo compartilhamento de trechos (`path size` ponderado em metros).
   A utilidade inclui `exp(-4 × (custo/custo_mínimo - 1))` e fator 0,5 por rota
   com retorno. Mais alternativas não multiplicam a atração daquele destino.
5. Além do roteamento em tempo livre, o `duarouter` busca uma alternativa para
   cada par com custos funcionais: tempo em vias locais/desconhecidas ×1,25,
   coletoras ×1,10 e estruturais/arteriais ×1, mais as conexões internas. Isso
   representa aversão moderada a atalhos locais, não velocidade observada ou
   capacidade. Rotas duplicadas e inválidas são removidas.
6. Duas buscas adicionais usam `duarouter --weights.random-factor 1.3` e seeds
   fixas 17/53, comuns a todas as realizações. Representam alternativas de
   percepção de custo; não usam filas observadas. Todas as alternativas,
   inclusive templates de corredor, ficam limitadas a 1,35 vezes o melhor custo
   funcional não perturbado do OD e a 1,5 vezes o menor comprimento. A rota
   nativa básica continua disponível. A divisão por custo e sobreposição não
   multiplica a atração de um destino quando aparecem mais alternativas.
7. A complementação de cobertura revisa trechos ausentes depois dessas buscas.
   Limites inferiores dirigidos selecionam até três ODs existentes por trecho;
   um caminho simples fornece a sequência de passagem para o `duarouter`.
   O resultado nativo precisa manter conexões `passenger`, não repetir trechos
   ou junções e respeitar os mesmos limites de custo e comprimento. A política
   acrescenta opções de caminho, sem reserva de veículos por rua.
   Se os prefixos e sufixos mais curtos não formam um caminho simples, a v4.8
   tenta manter uma metade e buscar a outra sem repetir suas junções. O cadastro
   limita essa etapa a 32 buscas por trecho. Cada testemunho passa pelos mesmos
   tetos de custo e comprimento e pela validação nativa.
   `catalog.coverage_completion` registra candidatos, rejeições e lacunas.
   Uma busca limitada sem sucesso não demonstra impossibilidade física.

**Atividades locais distribuídas.** `regional_demand.local_activity_distribution`
define células de 600 m, até quatro acessos representativos por célula, comprimento mínimo de
40 m para um acesso e oportunidade relativa de 1 por km de via local. Os parâmetros
são hipóteses de resolução e oportunidade, escolhidas antes da comparação SUMO;
não foram ajustados para eliminar congestionamento. A formação usa a rede
`passenger` e a hierarquia funcional municipal já cadastrada: exclui arteriais,
coletoras, rampas, portais e gates dos polos identificados. Cada trecho é associado
à célula do ponto situado na metade de sua geometria; não se trata de polígono
legal de bairro, área edificada medida ou cadastro de lotes.

Somam-se comprimentos, sem multiplicação por número de faixas ou de segmentos.
Sentidos opostos reconhecidos do mesmo trecho repartem sua extensão física.
Cada célula com acesso recebe `comprimento_local_km × oportunidade_por_km`;
até quatro gates espalhados, preferindo ruas OSM distintas, compartilham esse
valor. O gate precisa de entrada, saída e geometria válida; células sem gate
admissível são diagnosticadas, sem inserções forçadas. Ramais e circuitos ligados
à malha por uma única junção recebem acessos adicionais quando existe frente
local elegível: origem orientada para sair e destino orientado para entrar.
Esses acessos compartilham a oportunidade já existente da célula, sem acrescentar
extensão, atratividade ou uma população por ramal. Pontas curtas e vias que a
hierarquia funcional classifica como coletoras não viram gates residenciais
automaticamente. `directional_terminal_edges` cadastra casos auditados em que
a junção tem outras ruas, mas um sentido só admite retorno em um de seus lados.
O gerador confirma a frente residencial elegível e o papel compatível com as
conexões, usando a oportunidade da célula existente. Isso fornece acessos
agregados às atividades locais e amplia os caminhos possíveis, sem exigir que
cada rua tenha veículos em toda realização. A abordagem de zonas e acessos
ponderados é compatível com as [TAZ do SUMO](https://sumo.dlr.de/docs/Demand/Importing_O/D_Matrices.html);
o EDI mantém seu sorteio explícito e o roteador nativo calcula os percursos.

`generation.spatial_model.local_activity_expansion` registra as células,
comprimentos, oportunidades, acessos e áreas sem gate. O hash espacial identifica
o cadastro-fonte, incluindo a política, enquanto o hash da rede identifica a
geometria usada na expansão. As duas amostras antigas Brasil/Tibery permanecem
na fonte como contexto e perfil; são removidas da população ativa durante a
expansão, evitando dupla contagem. O Censo 2022 não calibra a intensidade das
novas células. A unidade 1/km e os perfis continuam experimentais até haver
contagens locais e OD, e não equivalem a capacidade, veículos/km ou densidade
real de domicílios.

Os acessos internos são trechos `passenger` reais, georreferenciados nas ruas
adjacentes. Rampas, estacionamentos e garagens ausentes da rede são abstraídos;
as posições não são apresentadas como portões veiculares comprovados. Santa Mônica e Umuarama ficam
representados nas áreas de captação externas, sem duplicar seus campi no miolo.
Viagens entre ruas distintas da mesma célula residencial/mista são permitidas;
uma célula computacional não equivale a um único portão. Origem e destino no
mesmo trecho continuam excluídos. Shopping, prefeitura e campus não recebem
viagens internas ao próprio polo por essa regra. A penalização de retorno ao
mesmo acesso periférico continua restrita aos grupos de borda.

Uma única configuração atende sete dias, oito faixas diárias e 25 variações,
inclusive na composição cronológica. A agenda regional e as retenções continuam
comuns; mudar escolhas de origem pode mudar a contagem final da redução lateral.
Agendas pareadas explícitas conservam sua população. Na política ativa,
`regional_demand.observation_projection_scope="external_od_internal_prior"`,
todas as viagens que tocam atividades internas formam um componente: entrada
de borda → atividade, atividade → saída de borda e atividade → atividade.
Nos centros de quinze minutos, a distribuição **condicional** de OD e percursos
desse componente permanece a do prior urbano. Os sensores podem ajustar sua
participação conjunta e as viagens entre bordas; não podem favorecer uma célula,
polo ou desvio interno apenas porque seu percurso atravessa um sensor.
`observation_projection.protected_internal_prior` registra massas antes/depois
e erro de conservação condicional. A interpolação temporal existente continua;
isso não cria cotas inteiras por rua ou por OD em um sorteio finito.

O escopo histórico `global_od_and_routes` e o controle `within_fixed_od`
permanecem reproduzíveis para comparação. O segundo congela toda a matriz,
mas foi rejeitado como default: no teste V7 sua projeção sem retenções ficou
cerca de 73% abaixo do sensor 6. O primeiro podia deslocar arbitrariamente
viagens internas para tentar cumprir contagens. A política ativa permite que as
medições informem a mistura regional, preservando a estrutura interna definida
pelas atividades. Densidades absolutas,
oportunidades e perfis permanecem hipóteses até haver OD e contagens de acesso.
Os métodos anteriores continuam disponíveis no cadastro para comparação, e
resultados históricos conservam a versão que os produziu.

### Decisão dos pesos padrão e comparação controlada

**O padrão escolhido é v4.8, com oportunidade local por extensão viária.**
Os pesos de hierarquia 4/3/2/1, faixas, VMD relativo, polos 4/2/1 e perfis
temporais formam a referência operacional. A avaliação de 07/11/2026 concluiu
pela manutenção dessa configuração. O CNEFE 50/50 e a sensibilidade de 100%
ficam preservados como referências comparativas. A decisão privilegia o suporte
geográfico e funcional dos acessos na rede representada.

O CNEFE contém 18.866 endereços particulares nas 28 células recortadas pelo
fecho convexo do viário. A mistura melhora a correspondência com esse conjunto,
mas transfere peso para células com pouca frente local representada. Na célula
4/8, os 500 endereços passam a informar 0,975 de oportunidade, ante 0,081 no
padrão (12 vezes). Apenas 16 ficam a até 50 m das ruas elegíveis da célula,
e 27 a até 100 m. Esses raios são verificações geométricas de sensibilidade.
A associação efetiva aos acessos dependeria do caminho entre imóvel e via.

| Distribuição das oportunidades contra endereços, variação total | v4.8 | 50/50 | 100% CNEFE |
| --- | ---: | ---: | ---: |
| Todos os endereços particulares no fecho convexo | 0,242 | 0,121 | 0,000 |
| Estabelecimentos CNEFE, espécies 3–6 | 0,302 | 0,232 | 0,220 |
| Endereços a até 25 m das ruas elegíveis da mesma célula | 0,063 | 0,138 | 0,236 |
| Até 50 m | 0,077 | 0,122 | 0,218 |
| Até 100 m | 0,132 | 0,085 | 0,173 |

A posição relativa muda com o raio de captação. A escolha de extensão viária
mantém vínculo direto com os acessos representados. Já a aplicação de todos os
endereços do fecho convexo exige uma hipótese adicional de distribuição entre
esses acessos. O mesmo multiplicador também afeta origens e destinos de células
residenciais/mistas, cuja atração inclui comércio e serviços. O CNEFE auxilia a
qualificação espacial, com incertezas sobre captação, motorização e viagens de
automóvel. [IBGE/CNEFE](https://www.ibge.gov.br/estatisticas/sociais/populacao/38734-cadastro-nacional-de-enderecos-para-fins-estatisticos.html).

**Controle das condições.** O [resultado consolidado](../outputs/outputs-metasettran/weight-review-20261107/comparison.json)
usa as curvas realizadas V7 e a sequência de uniformes OD da geração normal.
Antes das retenções por origem/final, registra o percurso sorteado para cada ID.
Depois seleciona os mesmos IDs e atributos retidos pelo v4.8 nas três hipóteses.
Assim, horários e volumes finais são idênticos. O campo `normal_N` registra
separadamente o efeito da geração normal, cujo arredondamento e retenção por
origem podem variar com os pesos. A comparação anterior via `schedule_file`
usava curvas medianas e dispensava retenções. Seus números e hashes estão
preservados no mesmo resultado, separados da comparação atual.

Terça 15–18, V7, seed de demanda 1082464323. Percentuais sobre 12.882 viagens.

| Rotas planejadas | v4.8 | 50/50 | 100% CNEFE |
| --- | ---: | ---: | ---: |
| Interno → Interno | 794 (6,16%) | 772 (5,99%) | 744 (5,78%) |
| Interno → Externo | 945 (7,34%) | 932 (7,23%) | 946 (7,34%) |
| Externo → Interno | 1.216 (9,44%) | 1.132 (8,79%) | 1.121 (8,70%) |
| Externo → Externo | 9.927 (77,06%) | 10.046 (77,98%) | 10.071 (78,18%) |
| Incluem Rondon | 9.882 (76,71%) | 9.830 (76,31%) | 9.791 (76,01%) |
| Entre pontas da Rondon | 1.659 (12,88%) | 1.679 (13,03%) | 1.692 (13,13%) |

Entre as células locais, a distância dos sorteios aos endereços cai de 0,258
para 0,130 nas origens e de 0,252 para 0,158 nos destinos com a mistura.
A participação entre bordas aumenta e o uso global da Rondon varia menos de
um ponto percentual. Em domingo 00–03, V7, as três hipóteses têm 1.662 viagens.
Borda→borda soma 1.465/1.488/1.487 (88,15%/89,53%/89,47%) e Rondon
1.512/1.519/1.511 (90,97%/91,40%/90,91%), na mesma ordem.
As seis rotas completas estão em `weight-review-20261107/planned/`.

A identificação da Rondon usa os 84 edges das duas pistas principais, conferidos
por IDs, junções, conexões passenger e 28 vias OSM versionadas. A referência
v4.8 tem 8.574 viagens (66,56%) com pelo menos 500 m contínuos no eixo,
1.308 (10,15%) com trechos menores e 3.000 (23,29%) sem usar o eixo.
Destas, 767 (5,95% do total) cruzam uma junção compartilhada em nível pelo
critério geométrico registrado no resultado. São incidências planejadas.

**Verificação SUMO curta.** Foram preservadas as 1.836 partidas dos primeiros
30 minutos da terça, com rede inicialmente vazia e 45 minutos finais de
escoamento. SUMO 1.28.0, seed 23423, passo de 1 s, sinais `current` e opções
físicas iguais. As opções configuradas diferem apenas nos caminhos dos arquivos.

| Operação até 4.500 s | v4.8 | 50/50 | 100% CNEFE |
| --- | ---: | ---: | ---: |
| Inseridos | 1.836 | 1.836 | 1.836 |
| Chegadas sem teleporte | 1.777 | 1.767 | 1.778 |
| Chegadas após teleporte | 11 | 2 | 5 |
| Incompletos | 48 | 67 | 53 |
| Eventos de teleporte | 13 | 3 | 5 |
| Colisões | 0 | 0 | 0 |
| Entradas no probe Rondon sentido bairro | 640 | 645 | 644 |
| Entradas no probe Rondon sentido centro | 653 | 685 | 678 |

Menos eventos de teleporte e mais incompletos coexistem no caso 50/50.
Esses resultados descrevem operação sob uma demanda hipotética. A decisão
sobre o padrão usa a análise geográfica acima. Os diretórios `street/`,
`half/` e `cnefe/` do lote guardam as rotas curtas, métricas e logs.
O contrato de resultados foi conferido para os três episódios.

A refatoração reproduziu byte a byte a referência v4.8 terça V7
(`b472bd92c8d1930053c00079b6aeeff46d725225f659492b41711511a2d875ef`) e
a comparação 50/50 pelo contrato anterior `schedule_file`
(`3294b0e9ea869e15aee478f75b60565f7722bd0d13485ac384df75abff7ac2d9`).
O cadastro padrão conserva o hash
`f16df47ed054b08020e5c8776f29cab58c35f9ddb80562aa8f6715907a7df8bf`.
A variante anterior pode ser refeita pela API com `schedule_file` e
`local_activity_weights_file=DEFAULT_SPATIAL_FILE.with_name("metasettran_cnefe_weights.json")`.
Cada geração deve usar uma pasta própria.

## Resultados e interpretação

### Arquivos e perfis

Cada chamada cria um lote exclusivo em `outputs/outputs-random/` ou
`outputs/outputs-metasettran/`. Os nomes operacionais incluem data/hora UTC e
identificadores exclusivos. Na seleção livre, cada execução também identifica
seu episódio e grupo. A interface permite navegar pelas pastas e baixar arquivos.

`metrics.json.gz` nos novos episódios, ou `metrics.json` nos antigos, contém o
mesmo JSON formatado, schema 3, com `execution` e uma lista `metrics`. Identifique
cada indicador por `metric_name`. Os registros incluem tipo, valor, descrição,
unidade, natureza e prioridade. `execution` registra fontes, hashes, comandos,
seeds, variações, seleção e tempos. Os tempos de processamento usam relógio
monotônico e diferem do tempo simulado.
Para investigar uma execução demorada, consulte `execution.timings_seconds`:
`generation_time_seconds` mede a preparação da demanda, `simulation_execution_time_seconds`
mede o processo SUMO e `aggregation_time_seconds` inclui coleta e validação.
Os tempos `collection_*`, publicados em `diagnostic`, já fazem parte da agregação;
não devem ser somados outra vez. `core` e `full` guardam os tempos das etapas principais.
MetaSettran prepara seu catálogo de percursos e simula três horas por faixa,
mais o escoamento solicitado. Uma execução pode levar minutos mesmo em `core`;
o número de linhas do JSON não mede o custo dessas etapas.

| Perfil | Retenção após sucesso |
| --- | --- |
| `core` | Agregados e contexto. `entity_metrics_file` é `null`. Entradas temporárias e observações intermediárias são removidas. |
| `full` | Agregados, `entities.json.gz` e observações nativas em `raw/`. |
| `diagnostic` | Mesmas observações e entidades de `full`, mais contexto técnico completo e instrumentação. Somente terminal/API Python. |

O número de registros de `core` depende das medições disponíveis e inclui contexto:
as execuções de referência Random e MetaSettran têm 65 e 72, respectivamente.
Não há preenchimento artificial nem corte por quantidade. As métricas científicas
comuns usam os mesmos cálculos nos três perfis. `full` acrescenta medições de análise;
`diagnostic` acrescenta informações para desenvolvimento, sem alterar a dinâmica.

Nos novos episódios concluídos, detalhes MetaSettran por zona, acesso, movimento
e corredor, catálogo de percursos, calibração completa e diagnósticos de sensores
ficam em `diagnostic`. `core` e `full` preservam métricas, referências das fontes,
seeds, variações, configuração, populações globais e verificações de integridade.
Neles, a referência de calibração conserva somente os totais consolidados por
sensor; curvas de 15 minutos e estatísticas de treinamento ficam em `diagnostic`.
Random segue a mesma regra para instrumentação: os tempos individuais dos coletores
e de persistência, relógios e desempenho computacional interno do SUMO ficam em
`diagnostic`. Não há arquivo complementar nem mudança
nos resultados históricos. Falhas continuam preservando os dados disponíveis
para investigação, mesmo quando o perfil solicitado foi `core` ou `full`.

As entidades full são organizadas por `vehicles`, `lanes`, `edges`, `traffic_lights`,
`approaches` e `intersections`, com escopo, ID e chave. MetaSettran conserva a demanda
planejada como `metasettran.rou.xml.gz` quando há ganho, ou `metasettran.rou.xml`.
Após uma execução bem-sucedida, a rota e os logs `generation.log` e `sumo.log`
de pelo menos 64 KiB são comprimidos individualmente quando o resultado é menor.
As observações nativas e as entidades full/diagnostic já usam GZIP; não recebem uma segunda
compressão. Falhas preservam as entradas, observações e logs disponíveis.

GZIP não altera campos, precisão ou bytes do conteúdo recuperado. Os JSONs são
gravados em arquivo temporário e sua descompressão é conferida por SHA-256 antes da
publicação atômica. A rota e os logs só perdem a cópia original depois da validação
da cópia comprimida e da publicação das métricas; uma falha de compressão preserva
os originais e é informada. O tempo `execution_time_seconds` não inclui essa
compressão final, a última escrita de métricas nem a limpeza de temporários.
Uma interrupção abrupta pode deixar temporários `.json-` ou `.gzip-` no episódio;
verifique que a execução terminou e que os resultados íntegros existem antes de
remover somente esses temporários. Nenhuma limpeza automática altera episódios antigos.

Em **Outputs**, JSON, XML e logs compactados abrem automaticamente; JSON aparece
formatado em `<pre>`. É possível baixar tanto o GZIP quanto o conteúdo original.
Acima de 16 MiB descomprimidos, o navegador pede a abertura explícita do conteúdo
completo; a transmissão ocorre em blocos e não há corte silencioso. A auditoria
aceita nomes antigos e novos, inclusive quando o nome antigo é fornecido para um
resultado que existe somente em GZIP. `routes_sha256` continua sendo o hash dos
bytes XML originais, e o mesmo vale para o hash da agenda pareada. A API
`schedule_file` também aceita a rota comprimida. O comando SUMO registrado nas
métricas mantém o caminho realmente usado na execução; para reutilizar a rota
retida, use o caminho indicado em `generation.routes_file`.

Para recuperar manualmente um arquivo em Linux,
`(set -C; gzip -dc metrics.json.gz > metrics.recuperado.json)` grava o JSON original
sem substituir um destino existente. Em Linux ou Windows, também é possível usar Python (no
Windows, substitua `python3` por `py -3`):

```text
python3 -c "import gzip,shutil; s=gzip.open('metrics.json.gz','rb'); d=open('metrics.recuperado.json','xb'); shutil.copyfileobj(s,d); d.close(); s.close()"
```

O destino `metrics.recuperado.json` deve ser novo; adapte os nomes para rotas e
logs. A descompressão confere o GZIP e recupera os bytes originais, sem exigir o
EDI. A alteração não comprime nem substitui resultados históricos.

Em core/full, referências resumidas substituem o cadastro espacial completo e a calibração.
O catálogo detalhado de rotas fica disponível em diagnostic. A API do gerador também permite
controlar sua publicação com `include_route_details`. Os perfis compartilham a semântica
das métricas comuns e as condições de simulação.

### Leitura científica

Distinga veículos programados, inseridos, concluídos sem teleporte, chegadas após
teleporte, incompletos e sem inserção. Eventos de teleporte podem se repetir para
um mesmo veículo. Ocupação de um trecho (`sampledSeconds > 0`), passagem por uma
seção e conclusão de viagem são observações distintas.

Rotas geradas descrevem intenção de deslocamento. As observações SUMO permitem
avaliar o movimento ocorrido e as restrições de inserção. MAE/WAPE dos sensores
são condicionais à correspondência espacial adotada. A projeção em tempo livre
exclui os efeitos de filas e sinais sobre os instantes de passagem.

Os diagnósticos MetaSettran incluem reconciliação de bordas e acessos internos,
movimentos, progressão e continuidade. Medidas de partida efetiva e atraso ficam
ausentes para veículos sem inserção. `status=completed` registra término do processamento.
A interpretação do tráfego exige os indicadores de integridade e suas populações.

## Programação semafórica

`current` usa os programas incorporados à rede. `settran` aplica um plano fixo
selecionado explicitamente pelo CLI. A interface oferece `current`.

[RondonNorte.xlsx](RondonNorte.xlsx) é a fonte original e
[settran_programs.json](settran_programs.json) contém a normalização e os suplementos.
A fonte tem 36 programas, 128 descrições e 512 tempos/células. Os planos reais
2/4/16/24 aguardam dados de permissões, sequência, transições e referência das
defasagens. O executor recusa seleções incompletas antes da geração de demanda.

Um plano válido produz `inputs/settran.add.xml`. Os estados usam índices de
conexões `linkIndex`, com `G` protegido e `g` permissivo. A posição de uma letra
em `state` identifica o movimento controlado. Conflitos, escopo e transições
precisam de evidência operacional. A rede física continua sendo a entrada comum
aos experimentos com cada controlador.

### Contrato SETTRAN

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


## Validar e medir custo

```bash
make test
python3 -B scripts/correct_signal_infrastructure.py --check
python3 -B scripts/audit_settran.py --check
python3 -B scripts/audit_results.py --episodes outputs/outputs-random/LOTE
```

A suíte verifica demanda, composição temporal, executor, interface e métricas.
Os comandos `--check` conferem os arquivos existentes. A reconstrução da rede é
uma operação de manutenção separada, vinculada à versão e aos hashes do script.

Para investigar cobertura planejada, execute a auditoria com um arquivo de saída novo.

```bash
python3 -B scripts/audit_results.py \
  --routes-file outputs/outputs-metasettran/LOTE/EPISODIO/metasettran.rou.xml.gz \
  --metrics-file outputs/outputs-metasettran/LOTE/EPISODIO/metrics.json.gz \
  --spatial-file SistemaDeSemaforos/demand/metasettran_spatial.json \
  --output outputs/auditoria-distribuicao.json
```

O cadastro reconstrói o catálogo com `duarouter`. O relatório separa conectividade,
rotas disponíveis e ausência no sorteio. Os hashes vinculam as entradas ao episódio.
`--edge-data` acrescenta ocupação observada e `--sumo-log` acrescenta os eventos de
teleporte disponíveis. A auditoria identifica lacunas e logs incompletos.
Para Random, forneça suas rotas disponíveis e omita o cadastro espacial.

O benchmark compara observadores com a mesma rede, demanda e seed SUMO.
Escolha explicitamente a duração e o intervalo de partidas.

```bash
python3 -B scripts/benchmark_observation_pipeline.py \
  --duration 600 --period 1.5 --seed 123 --repetitions 2
```

`benchmark.json` registra tempos, tamanhos e memória de processos separados.
As verificações exigem igualdade dos atributos de viagem e das métricas comuns.
O perfil interno `minimal` é um controle da ferramenta. O custo observado depende
do cenário, da máquina e da carga de execução.

## Manutenção e histórico

| Alteração | Local principal |
| --- | --- |
| Entradas e seleção de execução | `simulation/episode_runner.py` e interface web. |
| Hipóteses de demanda | Cadastro espacial, calibração e gerador em `demand/`. |
| Observações e métricas | Configuração das saídas, coletor e publicação em `metrics/`. |
| Suplemento SETTRAN | `docs/settran_programs.json` e conversor de planos. |
| Importação da planilha | `scripts/audit_settran.py --help`. |
| Correções físicas | Rede e `scripts/correct_signal_infrastructure.py`. |

Configurações operacionais pertencem aos dados estruturados. Resultados, seeds e
condições dos experimentos ficam em outputs. As diretrizes de colaboração orientam
a manutenção do código e da documentação. [Diretrizes](DIRETRIZES_COLABORACAO_IA.txt)

A cronologia extensa das revisões anteriores é recuperável na árvore Git
`refs/codex/checkpoints/edi-before-docs-rewrite-20261107`. Ela preserva o guia integral
anterior à reorganização, incluindo tabelas de ensaios e decisões históricas.
Os resultados existentes continuam em suas pastas de origem. Para reproduzir uma
versão anterior, associe código, cadastro, rede, versão SUMO, seeds e seleção
correspondentes ao experimento.
