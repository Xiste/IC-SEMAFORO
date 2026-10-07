# Revisão do projeto — 06/10/2026

## Parecer

O projeto tem um pipeline executável de pesquisa: rede SUMO, controle TraCI, ambiente Gymnasium, PPO, interface, avaliação e exportação. O controle dos nove cruzamentos está disponível como cenário experimental com 17 controladores. Ainda não há evidência de que o PPO produza melhoria conjunta de trânsito. O próximo trabalho deve concentrar-se na modelagem do controle e da demanda antes de um treinamento longo.

A geometria é uma premissa aceita pelo usuário. Planos reais foram deixados fora do escopo desta etapa; recuperá-los não é condição para prosseguir com experimentos sintéticos. Validar conflitos, atendimento, tempos e hipóteses do cenário sintético continua necessário.

## Os quatro requisitos

| Requisito | Disponível | Falta para concluir o planejamento |
|---|---|---|
| 1. Carregar Rondon Norte | Rede original/corrigida, planilha, cadastro dos nove, preparação experimental automática | Validar operação em ciclos completos, melhorar agrupamento de movimentos e tratar interferências dos sinais externos |
| 2. Carregar configurações-base e listar opções | JSON-base, campos na interface, catálogo de 462 opções SUMO instalado, parâmetros efetivos e versões | Tornar ajustes avançados acessíveis sem JSON, corrigir dependências declaradas e consolidar a documentação; catálogo não significa aplicação de todas as opções |
| 3. Executar simulações e PPO | Treino, teste curto, cancelamento, modelo salvo e avaliação PPO/referência/heurística com sementes distintas | Treinamento conjunto suficiente, variedade de demandas e sementes de treino, acompanhamento da otimização e medição de custo dos nove |
| 4. Gerar relatório com muitas métricas | CSV/JSON/Markdown, gráficos, métricas por controlador, viagens, emissões e recursos opcionais | Agregação por cruzamento físico/rota, séries e curvas, intervalos de confiança, cobertura da demanda e critérios explícitos de melhoria |

Dez épocas são passagens de otimização por coleta, não dez episódios de simulação e não uma comprovação de convergência.

## Pontos fortes

- Camadas separadas: cenário, simulação, algoritmos, experimentos, relatórios e apresentação. Outro algoritmo compatível pode reutilizar o ambiente e a avaliação; somente PPO está publicado. A2C é prova de integração no teste.
- Interface prepara, salva/reutiliza e seleciona o cenário conjunto sem edição obrigatória de arquivos no fluxo básico. Inclui nomes de 33/34 entradas, sentidos aproximados e mapa local para identificação.
- O ambiente controla as durações mantendo a ordem dos estados. Há pisos de verde/travessia e intervalos originais de amarelo/limpeza. A validação experimental confere atendimento serial, sequência, nós compartilhados e hash.
- Manifestos e configurações por episódio registram rede, alvos, ações, sementes, comando SUMO e parâmetros. A avaliação rejeita redes/alvos/limites incompatíveis com o modelo.
- Métricas distinguem concluídos e incompletos. Espera, filas, velocidade, ocupação, tempos de viagem, percentis, emissões, colisões/teletransportes e CPU/RAM têm coleta ou relatório implementados.
- A avaliação usa a mesma geração de demanda por semente para PPO, referência e heurística. Há média/desvio padrão e exportação em português.

## Principais limitações para o objetivo de reduzir trânsito

### 1. Atendimento serial precisa evoluir — prioridade alta

`cenario/experimental.py` cria um verde, amarelo e vermelho de limpeza para cada índice, com apenas um índice aberto por controlador. Na cópia inspecionada são 150 índices/450 fases ajustáveis: o PPO tem 450 componentes de ação e 102 observações.

Os ciclos iniciais variam de 112 a 961 segundos. No maior ciclo isso equivale a aproximadamente 16 minutos. Pelas maiores durações permitidas, o ciclo pode chegar a 1.872 segundos, cerca de 31 minutos. A duração padrão de episódio nessa cópia é 1.922 segundos, suficiente para dois ciclos iniciais, porém não para dois ciclos máximos.

Isso é uma referência conservadora e pouco eficiente. Melhorar durações sobre ela não demonstra superioridade sobre um programa bem organizado. O PPO não agrupa movimentos nem muda sua ordem. Próxima evolução: grupos compatíveis conferidos com a matriz de conflitos, tempo máximo de espera/sem atendimento e limites de ciclo. A exclusão de verdes simultâneos sozinha não prova que o intervalo de limpeza é suficiente em todas as situações.

### 2. Observação não distingue filas por movimento — prioridade alta

`simulacao/ambiente.py::_observation` agrega fila, quantidade de veículos e velocidade das faixas de cada controlador em seis valores. Filas em aproximações opostas podem gerar observações iguais. Um controlador com 24 movimentos não informa separadamente suas 24 necessidades.

Faltam filas/ocupação por aproximação ou movimento, disponibilidade de espaço a jusante e informação adequada de travessias. Isso limita a adaptação dinâmica e a prevenção de bloqueio de cruzamento. Mais passos de treino não recuperam informação que a observação não fornece.

### 3. Contagem medida não é taxa de geração — prioridade alta

`cenario/demanda.py::create_edge_volume_demand` transforma veículos/h em **novas viagens começando no trecho**. Não é uma restrição de quantos veículos totais passam pela rua.

Exemplo: se A e B são trechos consecutivos com contagem medida de 600 veículos/h, gerar 600 viagens em A e outras 600 em B pode contar duas vezes a mesma população. O tráfego vindo de A também entra em B. Para usar contagens de ruas internas, é preciso gerar demanda nas origens/bordas e calibrar rotas/conversões até reproduzir os fluxos observados. O CSV de medições disponível é resumido, mas ainda não alimenta essa calibração.

O modo aleatório é da rede inteira e não garante tráfego representativo nos nove locais. Os destinos automáticos são sintéticos. Faltam dados ou cenários sintéticos definidos de pico/vale, conversões e validação de entrada planejada versus inserida.

### 4. Escopo da recompensa e da segurança — prioridade alta

A recompensa usa espera global, filas nas faixas dos alvos e veículo-segundos ativos como aproximação de viagem, com escalas fixas do piloto. Não há objetivo explícito de equidade por via/rota, penalidade por bloqueio a jusante ou espera máxima. As filas globais são relatadas, mas não são o termo de fila usado na recompensa.

O vermelho individual resulta do restante do programa; o componente controlado diretamente é o vermelho de limpeza. Não há busca irrestrita de três durações independentes por lâmpada.

Quatro controladores externos preservados ainda geram avisos SUMO de movimentos sem verde: FAM_RONDON_RIO_DE_JANEIRO, FAM_MARANHAO_MONSENHOR_EDUARDO, 5494111593 e 2042693363. Podem afetar rotas que passam por eles. Há travessias programadas nos nove, mas não há geração de demanda de pedestres para testar seu atendimento em uso.

### 5. Experimento completo ainda falta — prioridade alta

Foram encontrados nove arquivos de modelo persistidos em resultados, todos com um alvo nos respectivos manifestos. O teste automatizado conjunto faz quatro passos de treino e avalia episódios de vinte segundos; confere integração, não desempenho nem todos os ciclos. Esses arquivos temporários são removidos ao encerrar o teste.

O padrão de 2.048 passos com decisões de cinco segundos equivale a 10.240 segundos simulados ao longo do treino. Com episódios de 1.922 segundos, são aproximadamente cinco episódios completos. Não há justificativa experimental para considerar esse orçamento suficiente para 17 controladores.

Faltam várias demandas de treinamento, diferentes sementes de treinamento da política, cenários reservados para avaliação e critérios de comparação. O PPO atual mantém learning_rate, gamma, arquitetura e outros parâmetros fixos no adaptador. Não salva checkpoints periódicos nem oferece retomada na interface; salva o modelo final ou o parcial após cancelamento cooperativo. Não registra séries de loss/KL/entropia em arquivos próprios.

## Problemas concretos de software e acabamento

1. **Teste curto com perfil horário:** `preview_experimental` muda o horizonte para 30 s, porém mantém o perfil temporal original. Reprodução: perfil válido de 0 a 1.922 s retorna ValueError na validação da demanda. É necessário recortar/recriar o perfil para o teste.
2. **Arquivos de progresso:** o callback grava JSON diretamente e a interface lê sem proteção contra escrita parcial. Existe risco de erro transitório de leitura; não foi reproduzido por concorrência nesta revisão. Usar gravação atômica e leitura tolerante resolveria esse risco concreto do código.
3. **Configurações avançadas ainda em JSON:** destinos por proporção, perfil temporal, tipos e limites por fase exigem texto estruturado na interface. O fluxo básico dispensa JSON; todos os ajustes avançados ainda não estão disponíveis por tabelas/formulários.
4. **Compatibilidade da instalação:** requirements.txt aceita Streamlit 1.35, mas usa st.fragment, disponibilizado na versão 1.37 ([documentação oficial](https://docs.streamlit.io/develop/concepts/architecture/fragments)). Outras APIs recentes também devem ser conferidas antes de fixar um mínimo compatível. O ambiente atual herda pacotes do Anaconda; faltam versões fixadas e teste de instalação limpa.
5. **Relatórios e documentação:** signals.csv agrega por ID de controlador, não automaticamente os múltiplos IDs do mesmo cruzamento. Os gráficos não mostram dispersão e o report.md é curto. Trechos históricos de requisitos ainda descrevem só o piloto; existe atualização no topo, mas é necessário consolidar um estado vigente único.
6. **Episódio final parcial:** training_episodes.csv só recebe episódios concluídos. O fim/cancelamento do treino pode deixar um episódio parcial fora da tabela; o resumo não substitui todas as métricas dele.

## Ordem sugerida de execução

1. Agrupar movimentos compatíveis e verificar conflitos, limites de ciclo/espera e operação durante ciclos completos; tratar controladores externos que afetem as rotas.
2. Separar taxa de geração de contagem observada. Definir cenários de demanda e verificar fluxo nas 34 entradas, conversões e destinos; usar dados sintéticos explícitos enquanto não houver medição.
3. Dar ao PPO informações por aproximação/movimento e a jusante; calibrar recompensa global e por via. Acrescentar equidade e atendimento de travessias.
4. Corrigir teste curto/perfil, progresso, ajustes avançados e instalação. Acrescentar checkpoints e métricas de otimização.
5. Medir custo conjunto, treinar em diferentes sementes/demandas e avaliar cenários reservados com a referência agrupada e a heurística. Relatar chegada, fila, atraso, viagens incompletas e pior caso por via, além das médias.

O critério de conclusão deve ser evidência de redução de filas/atraso sem piorar indevidamente vias secundárias ou viagens incompletas, em várias condições. Não é simplesmente concluir um comando de treinamento.

## Verificação desta revisão

- Leitura das camadas de cenário, geração de demanda, controle, PPO, treino/avaliação, interface, métricas/relatórios, CLI, dependências, documentação e testes.
- Inspeção dos manifestos dos nove modelos persistidos e da cópia experimental mais recente.
- Reprodução do erro de teste curto com perfil de episódio completo.
- AppTest/verificador de catálogo executado com sucesso: 462 opções, 27 categorias e 596 consultas TraCI. Essas consultas não equivalem a 596 métricas coletadas.
- Suíte completa de 24 testes passou nesta revisão em 252,083 segundos, incluindo PPO e A2C_TEST, controle conjunto, save/load/avaliação e transições. Esse tempo da suíte não mede custo do treinamento completo dos nove.
- Não executado treinamento longo, validação em campo ou estudo de convergência. Nenhuma alteração na lógica de controle nesta revisão.
