# Auditoria do sistema de RL — 11/11/2026

## Escopo e conclusão

Revisados os fluxos centrais de simulação, observação, controle adaptativo, recompensa, geração/calibração de demanda, treino PPO, comparação, repetições, relatórios e exportação. Esta é uma análise de código com verificações direcionadas, não uma certificação da rede física ou um novo estudo de desempenho. Nenhuma lógica do aplicativo foi alterada nesta revisão.

O projeto tem infraestrutura de experimentação e controle adaptativo funcionando. Ainda há falhas de medição e lacunas na formulação do problema que devem ser tratadas antes de investir em treino longo. Não foi encontrada evidência suficiente de aprendizado útil do novo modo adaptativo nos modelos preservados.

## Achados prioritários

### 1. Tempo por sinal atribuído ao estado seguinte — confirmado, prioridade alta

Em `simulacao/ambiente.py`, depois de `simulationStep`, o controle adaptativo executa `tick(current)` e pode trocar o sinal. Só depois são coletados os indicadores de movimento e incrementado `phase_seconds`. Assim, o intervalo que acabou de transcorrer pode ser atribuído ao estado recém-ativado.

Reprodução real: piloto, modo adaptativo, decisão de 1 s, horizonte de 30 s, solicitando o segundo verde. Transições registradas: verde 0 até t=24; amarelo até t=27; limpeza até t=28; verde 3 até t=30. Durações esperadas pela linha do tempo: 24/3/1/2 s. `signal_metrics.phase_seconds` retornou 23/3/1/3 s. O controle cumpriu os tempos, mas o relatório deslocou uma amostra.

Correção sugerida: armazenar o estado efetivamente aplicado ao intervalo antes do avanço e usá-lo para integrar os indicadores; separar medições do intervalo encerrado de comandos para o próximo. Revisar também verde utilizado/desperdiçado, bloqueio sob verde e vermelho contínuo. Criar teste que reconcilie a soma por estado com a linha do tempo das transições, em passos de 1 s e 0,5 s.

### 2. Parte do estado do controlador está oculta para a rede — confirmado, prioridade alta

`AdaptiveSignals` usa `pending` e `last_served` para escolher o próximo verde e intervir depois de 120 s sem abertura. `_observation()` não inclui esses valores. O tempo restante retornado pelo TraCI também é artificial neste modo: o controlador renova `setPhaseDuration` a cada passo para evitar trocas automáticas.

Reprodução controlada: com mesmo estado todos vermelhos, mesmo tempo decorrido e mesma ação solicitada, `pending=3` resultou no verde 3 e `pending=6` no verde 6. Essa diferença não está representada nas observações do agente.

Consequência: o problema tem observabilidade parcial também por informação interna conhecida que poderia ser fornecida. PPO com MLP ainda pode aprender, mas precisa inferir efeitos que não observa diretamente.

Sugestão: incluir abertura atual em codificação categórica, abertura comprometida na transição, tempo até ser permitido trocar, tempo até o máximo e tempo sem abertura de cada grupo compatível. Registrar ação solicitada, ação executada, motivo de bloqueio/intervenção e proporção de decisões efetivamente executadas. Só considerar memória/LSTM depois de corrigir os estados internos conhecidos e medir a necessidade de histórico de sensores.

### 3. Horizonte finito sem relógio observável — confirmado, prioridade alta

O ambiente retorna `terminated=True` ao atingir `duration_seconds`, sempre com `truncated=False`, e aplica penalidade terminal. A observação não informa o tempo restante do episódio. O mesmo trânsito pode ter retorno futuro diferente perto do fim, sem que o agente consiga distinguir essa condição.

É preciso definir o objetivo: (a) tarefa realmente finita, com relógio restante observado e custo terminal justificado; ou (b) controle contínuo, interrompido artificialmente para coleta, com truncamento e bootstrap corretos. Não trocar o sinal de término sem revisar a penalidade e a definição do experimento. Referência: https://gymnasium.farama.org/tutorials/gymnasium_basics/handling_time_limits/

### 4. Recompensa não representa todos os objetivos declarados — confirmado e riscos a investigar

A recompensa usa espera de veículos da rede, fila das entradas controladas e tempo de veículos ativos, com escalas fixas do piloto; no fim acrescenta penalidade por veículos ainda em viagem/aguardando inserção. Pedestres, colisões, teletransportes e emissões são medidos, mas não entram diretamente nessa expressão. Limites de transição são impostos pelo controlador externo, não aprendidos pela recompensa.

Não é obrigatório incluir todos os indicadores na recompensa. É necessário definir objetivos e restrições explicitamente. Para veículos e pedestres, considerar espera acumulada em pessoa-segundos, atendimento mínimo e limites de espera como critérios separados. Eventos críticos devem invalidar uma política na avaliação, sem depender apenas de uma penalidade pequena.

Riscos ainda não demonstrados: favorecer retenção de veículos fora da rede porque a espera de inserção só é penalizada no fim; concentrar benefício em aproximações movimentadas e prejudicar acessos menores; beneficiar viagens curtas ou simplesmente terminar o episódio com veículos que não tiveram tempo de chegar. Fazer testes adversariais antes de trocar pesos. Normalização e pesos devem ser escolhidos usando dados de treino/referência, sem ajustar com base no teste final.

### 5. Ambiente Python herdando Anaconda — falha reproduzida

`.venv/pyvenv.cfg` tem `include-system-site-packages=true`. Uma importação isolada de `torch` encerrou o processo com `OMP Error #15`, indicando runtimes OpenMP duplicados. O fato de outros caminhos de importação terem funcionado não elimina a instabilidade.

`.venv-verificacao` tem `include-system-site-packages=false`; a importação do PyTorch funcionou nesse ambiente (`2.12.1+cpu`, CUDA indisponível). Padronizar execução, testes e instalação nesse ambiente isolado ou recriar um equivalente. Não mascarar o erro com `KMP_DUPLICATE_LIB_OK`. O script `iniciar_interface.ps1` já usa o ambiente isolado; a orientação anterior de iniciar pelo `.venv` deve ser substituída.

## Limitações experimentais e incrementos recomendados

- **Demanda:** calibração NNLS e conferência de fluxos existem; destinos sem dados continuam sintéticos. Em volumes por entrada, partidas são regularmente espaçadas; pedestres também têm partidas determinísticas. Variar sementes não substitui cenários de volumes, conversões e formas temporais diferentes. Introduzir chegadas estocásticas e pelotões como alternativas explícitas, mantendo a mesma demanda materializada entre controles.
- **Sensores e transferência:** o agente acessa contagens, velocidades e ocupações ideais de faixas inteiras do SUMO. Uma câmera ou laço físico tem alcance, taxa de atualização, ruído e falhas diferentes. Definir posição, cobertura, frequência e campos medidos de cada sensor; acrescentar atraso, perda e erro controlados no simulador antes de integrar hardware. Não há processamento de vídeo nem conexão física implementados.
- **Um ou vários agentes:** atualmente há uma política centralizada que escolhe uma ação por controlador via `MultiDiscrete`, e não um agente independente por cruzamento. Isso é um início válido. Fazer primeiro um cruzamento, depois poucos vizinhos e então a rede. Comparar política compartilhada ou multiagente apenas se a política centralizada mostrar limites de escala/coordenação.
- **Algoritmo:** manter PPO como referência inicial para as ações discretas atuais. SAC padrão não corresponde diretamente a esse espaço de ações; DQN padrão exigiria outra fatoração ou ações combinadas. Não há motivo comprovado para trocar de algoritmo agora. A MLP atual usa duas camadas de 64 unidades por política/valor e parâmetros fixos. Testar arquiteturas maiores, representação por aproximação ou grafos somente por comparação controlada.
- **Exploração e ações:** `ent_coef=0` não significa política determinística; a distribuição do PPO ainda é amostrada no treino. Porém não há incentivo explícito de entropia. Medir entropia, frequência das ações e intervenções antes de ajustar esse coeficiente ou introduzir máscaras de ações. Amarelo e limpeza não devem ser interrompidos por uma máscara mal definida.
- **Persistência:** o modelo é salvo ao fim de `learn`. Faltam checkpoints periódicos e retomada validada. Acrescentar salvamento intermediário, avaliação em conjunto de validação e preservação do melhor modelo. Reservar sementes/cenários finais que não sejam usados para escolher hiperparâmetros/checkpoints.
- **Avaliação:** já existem comparação pareada, sementes reservadas, verificação de demanda idêntica, referências e repetições de treinamento. Acrescentar conjuntos de cenários não vistos, curvas de aprendizado por múltiplos treinos, custo computacional e análise de perdas por aproximação. Comparar também com uma política por pressão/ocupação a jusante e uma referência fixa razoavelmente ajustada, não apenas uma referência fraca.
- **Garantias do controlador:** a intervenção de 120 s mede tempo sem abertura de grupos, não espera máxima individual de pessoas/veículos. Pode abrir um grupo sem demanda. Tornar esse comportamento explícito, medir intervenções e revisar atendimento por aproximação/demanda. Não remover grupos compatíveis e transições para tornar o controle adaptativo.
- **Relatórios:** uma grande quantidade de códigos/exportações não equivale a igual quantidade de objetivos independentes. Definir poucos indicadores principais, deixando diagnósticos e históricos no Excel. A tabela unificada relê arquivos completos a cada atualização, o que pode pesar em treinos longos; considerar cache por versão dos arquivos e agregação incremental.
- **Versionamento:** há código e testes novos ainda sem commit. Antes dos experimentos finais, registrar uma versão e guardar hash do código junto de dependências, configuração, rede e demanda. Não inferir reprodutibilidade apenas das sementes.

## Evidência encontrada e verificações desta revisão

- Dez testes direcionados de controle adaptativo, diagnósticos e exportação passaram em 4,99 s. Não foi repetida a suíte completa nesta revisão.
- Uma simulação nova de 30 s em pasta temporária confirmou o desvio de atribuição dos tempos. Não foi alterada a rede e nenhum resultado científico existente foi substituído.
- Reprodução com TraCI substituído confirmou efeito de `pending` sobre a transição sem correspondente variável observada.
- Inventário de manifestos preservados com `action_mode`: cinco de `phase_durations` e um de `adaptive_signals`. O adaptativo preservado tem um alvo e orçamento de 24 decisões. Testes temporários anteriores não são modelos preservados de pesquisa.
- Demonstração preservada `ui_3c792f77a48b/execucao`: 120 s simulados, 60 veículos partidos, oito chegadas, 52 em viagem; oito pedestres partidos e zero chegadas; zero colisões/teletransportes registrados. Isso demonstra coleta, não convergência, falha de pedestres ou qualidade do controle. O horizonte curto exige cautela.
- Máquina local identificada: Ryzen 7 5700G, oito núcleos/16 processadores lógicos, aproximadamente 15,4 GiB de RAM. Ambiente isolado testado usa PyTorch CPU, sem CUDA. Não foi feito benchmark para prometer duração de estudos maiores.

## Próximo passo concreto

1. Corrigir medição temporal, estado observado e definição do horizonte; criar testes de regressão físicos e de término.
2. Padronizar o ambiente isolado e acrescentar checkpoints e rastreamento de intervenções.
3. Fechar um cenário piloto com tráfego suficiente para produzir filas e viagens completas; comparar controle fixo e por filas antes do PPO.
4. Fazer um experimento de orçamento progressivo com PPO, começando, como hipótese de trabalho, em 20 mil decisões e medindo curva/custo. Esse valor não garante aprendizado. Usar ao menos três treinamentos independentes inicialmente, sementes/cenários distintos para validação e teste e aumentar o orçamento apenas se os diagnósticos justificarem.
5. Escalar o número de cruzamentos e o realismo dos sensores somente depois de estabelecer aprendizado e vantagem no piloto.

Referência complementar de boas práticas: https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html
