[2026-09-24 23:54 -03:00]: Base de simulação e treinamento SUMO para Rondon Norte
Responsável: agente Codex.
Objetivo: executar cenários sem interface, carregar a rede e os planos fornecidos, permitir demanda sintética e futura demanda por via, registrar métricas e treinar um modelo substituto para escolher tempos verdes.
Alterações: `SistemaDeSemaforos/pipeline.py` implementa inspeção, demanda, simulação, coleta e treinamento; `config.json` define o cenário; `dados/RondonNorte.xlsx` é a cópia da planilha fornecida; `dados/inventario.json` registra planos e semáforos; `docs/` traz a lista completa de opções do SUMO 1.27.1; `README.md`, `requirements.txt` e `.gitignore` documentam o uso.
Justificativa: usar as fases existentes da rede evita aplicar diretamente estágios da planilha a um programa SUMO com estrutura diferente. A rede neural substituta escolhe candidatos após avaliações iniciais e cada candidato é confirmado pelo simulador.
Verificação: compilação Python; leitura da planilha e inventário; execução sem interface com viagens aleatórias (60 partidas, 48 chegadas em 600 s); execução com fluxo definido por via (4 partidas em 120 s); treinamento com três tentativas, incluindo a etapa de seleção por rede neural (melhor pontuação 1509 no cenário sintético testado). Não foi verificada correspondência geográfica dos demais cruzamentos nem aderência dos fluxos sintéticos ao trânsito real.
Impactos e pendências: o plano 4 do cruzamento Rondon Pacheco × Paraná tem quatro estágios e ciclo de 110 s na planilha; a rede SUMO possui dois verdes e ciclo de 90 s para `FAM_RONDON_PARANA`. O exemplo otimiza os verdes da rede e não representa ainda o plano real. Mapear os outros cruzamentos, conferir fases, ajustar a rede ou os planos e acrescentar demanda medida quando disponível. Treinar novamente após mudar a demanda.
Continuidade: usar `inspect` e o inventário para validar IDs e fases com o responsável pelo mapa; então preencher `targets` e `demand.flows`, repetir os cenários com várias sementes e comparar o melhor candidato com a base.

[2026-09-25 00:09 -03:00]: Organização da arquitetura do pipeline
Responsável: agente Codex.
Objetivo: separar arquivos e responsabilidades sem alterar os comandos e resultados da simulação.
Alterações: `pipeline.py` passou a conter só a interface de comandos; os módulos `semaforos/configuracao.py`, `planos.py`, `rede.py`, `demanda.py`, `simulacao.py` e `treinamento.py` concentram cada etapa. O cenário foi movido para `config/cenario.json`, a rede para `dados/rede/` e a planilha para `dados/planos/`. O README descreve a estrutura e os novos caminhos.
Justificativa: entradas, lógica e saídas ficam em locais claros, e cada módulo tem uma responsabilidade principal.
Verificação: compilação dos módulos; `inspect` retornou nove cruzamentos e 28 semáforos; `options` retornou 1042 linhas; `run` repetiu 60 partidas, 48 chegadas e pontuação 1590; `train` com três tentativas repetiu pontuações 1590, 1509 e 1537, incluindo a etapa neural.
Impactos e pendências: scripts externos que apontavam para `config.json`, para o `.net.xml` na raiz ou para `dados/RondonNorte.xlsx` precisam usar os novos caminhos. O comando `python pipeline.py` permanece. O mapeamento dos demais cruzamentos e a diferença entre planilha e rede permanecem pendentes.
Continuidade: editar `config/cenario.json` para novos fluxos e semáforos; manter novas entradas da planilha em `dados/planos/` e redes SUMO em `dados/rede/`.

[2026-09-25 00:20 -03:00]: Guia de treinamento e comandos
Responsável: agente Codex.
Objetivo: documentar como preparar o ambiente, rodar a referência, treinar e interpretar os resultados.
Alterações: criado `SistemaDeSemaforos/docs/treinamento.md` com comandos PowerShell, campos de `config/cenario.json`, sequência do treinamento, pontuação, arquivos gerados e limites do cenário; adicionado link no `README.md`.
Justificativa: oferecer um procedimento reproduzível e explicar exatamente o papel da rede neural e do SUMO, sem misturar o guia operacional com a documentação geral da arquitetura.
Verificação: comandos, parâmetros, nomes de arquivos e cálculo da pontuação conferidos contra `pipeline.py`, `simulacao.py`, `treinamento.py` e `config/cenario.json`. Nenhuma nova simulação foi executada nesta etapa de documentação.
Impactos e pendências: não há mudança de comportamento no código. O mapeamento dos demais cruzamentos e a diferença entre o plano da planilha e o programa da rede continuam pendentes.
Continuidade: usar o guia ao configurar novas demandas e atualizar seus exemplos quando os comandos ou o formato do cenário mudarem.

[2026-09-25 00:44 -03:00]: Treino das durações verde, amarela e totalmente vermelha
Responsável: agente Codex.
Objetivo: permitir que a rede neural teste durações de todos os tipos de fase presentes no semáforo selecionado.
Alterações: `config/cenario.json` seleciona as seis fases de `FAM_RONDON_PARANA` e define mínimos para amarelo e vermelho de limpeza. `semaforos/rede.py` classifica fases e calcula limites por tipo; `semaforos/treinamento.py` usa esses limites; `semaforos/simulacao.py` aplica e valida candidatos para todas as fases. `README.md`, `docs/treinamento.md` e a ajuda de `pipeline.py` descrevem o novo comportamento.
Justificativa: as durações de verde, amarelo e limpeza são variáveis de treinamento distintas na rede SUMO. O amarelo e a limpeza mantêm pelo menos os tempos já presentes na rede; a ordem e os estados das fases permanecem.
Verificação: compilação Python; classificação e limites das seis fases conferidos; treino de três tentativas com seleção neural executado no SUMO (pontuações 1590, 1602 e 1456); a segunda tentativa alterou verde, amarelo e limpeza; reaplicação do melhor candidato produziu novamente 1456 com a mesma semente.
Impactos e pendências: o formato `best_candidate.json` agora inclui também índices de amarelo e limpeza. Configurações antigas com apenas verdes continuam possíveis se `targets` selecionar só esses índices, mas a configuração padrão usa seis fases. O vermelho de cada via continua dependente das demais fases, não há duração vermelha independente por via. A planilha e o programa SUMO ainda divergem, e o tráfego usado é sintético.
Continuidade: validar a correspondência dos demais semáforos e os tempos mínimos com as regras operacionais locais antes de ampliar os alvos ou usar resultados fora da simulação.

[2026-09-25 01:11 -03:00]: Catálogo Markdown das configurações do SUMO
Responsável: agente Codex.
Objetivo: entregar em Markdown a configuração-base carregada pelo projeto e a lista completa das opções configuráveis do executável SUMO instalado.
Alterações: `SistemaDeSemaforos/docs/configuracoes_sumo.md` apresenta valores atuais, fases do programa-base, argumentos usados pelo pipeline e 462 opções principais do `sumo` 1.27.1 em 27 categorias, com tipo, padrão e aliases. `SistemaDeSemaforos/scripts/gerar_catalogo_sumo.py` regenera o documento a partir do template local e de `config/cenario.json`. O `README.md` aponta para o catálogo.
Justificativa: gerar a lista diretamente do executável instalado evita omissões e permite atualizá-la ao mudar de versão. O documento distingue opções do `sumo` de configurações internas do pipeline e de outros executáveis SUMO.
Verificação: gerador executado com sucesso; comparação independente encontrou 462 nomes no Markdown e 462 no template, sem faltantes nem extras; 27 categorias no documento. Nenhuma simulação foi executada nesta etapa de documentação.
Impactos e pendências: não houve mudança no comportamento do pipeline. O catálogo reflete o SUMO 1.27.1 local; versões futuras exigem regeneração. Atributos XML e métodos TraCI não integram esse catálogo de opções de linha de comando.
Continuidade: após atualizar o SUMO, gerar novo template com `sumo --save-template ... --save-commented` e executar `python scripts/gerar_catalogo_sumo.py`; conferir a versão no novo documento.

[2026-09-25 01:17 -03:00]: Inventário dos parâmetros efetivamente usados na simulação
Responsável: agente Codex.
Objetivo: documentar todos os valores definidos pelo cenário e pelo código que afetam geração de veículos, execução SUMO, controle TraCI, pontuação e treino.
Alterações: criado `SistemaDeSemaforos/docs/parametros_simulacao.md`, ligado no `README.md`. O documento separa campos do JSON, argumentos de `randomTrips.py`, 11 opções explícitas de `sumo` (incluindo porta TraCI dinâmica), chamadas TraCI, limites das fases e hiperparâmetros da MLP; remete ao catálogo de 462 opções para os padrões não sobrescritos.
Justificativa: distinguir parâmetros realmente usados dos apenas disponíveis no SUMO e registrar a origem de cada valor para reprodução dos experimentos.
Verificação: valores e fórmulas conferidos com `config/cenario.json`, `configuracao.py`, `demanda.py`, `simulacao.py`, `rede.py` e `treinamento.py`; código instalado de `traci.start()` confirmado como origem de `--remote-port`; comparação com o template SUMO encontrou 11 opções explícitas entre 462 e 451 não sobrescritas. Nenhuma nova simulação foi executada nesta etapa documental.
Impactos e pendências: não há mudança de comportamento no código. O inventário reflete o cenário e a versão SUMO atuais; precisa ser atualizado se mudarem parâmetros, alvos ou versão. Dados reais de demanda e reconciliação planilha/rede permanecem pendentes.
Continuidade: manter este inventário e o catálogo de opções alinhados a futuras alterações em `config/cenario.json` e nos comandos montados pelo pipeline.

[2026-09-25 01:23 -03:00]: Reescrita dos itens 2 e 3 para leitura mais simples
Responsável: agente Codex.
Objetivo: facilitar a compreensão das configurações-base e dos parâmetros usados, sem perder os inventários completos solicitados.
Alterações: `docs/configuracoes_sumo.md` agora é uma visão curta dos valores-base, fontes de configuração e comandos; `docs/parametros_simulacao.md` acompanha uma execução em cinco passos com valores concretos e exemplo de pontuação. Os detalhes integrais foram preservados em `docs/catalogo_completo_sumo.md` (462 opções) e `docs/referencia_parametros.md`. `scripts/gerar_catalogo_sumo.py` agora atualiza o anexo técnico, e o README liga as páginas curtas e os anexos.
Justificativa: separar a explicação operacional das listas exaustivas permite começar pelo fluxo do projeto e consultar detalhes somente quando necessários.
Verificação: links locais dos quatro documentos conferidos sem caminhos inválidos; o anexo regenerado contém 462 opções; páginas principais têm 48 e 77 linhas. Nenhuma simulação foi executada, pois não houve mudança no comportamento do código.
Impactos e pendências: scripts ou referências que apontavam para a lista de 462 opções dentro de `docs/configuracoes_sumo.md` devem usar `docs/catalogo_completo_sumo.md`; detalhes técnicos dos parâmetros passaram para `docs/referencia_parametros.md`. Conteúdo do cenário e limites anteriores permanecem.
Continuidade: atualizar primeiro as páginas curtas quando o fluxo mudar; regenerar o anexo de opções após atualizar o SUMO e manter a referência detalhada alinhada ao código.
