# Como usar a interface

Abra `http://localhost:8501` e siga as abas numeradas. Os ajustes ficam disponíveis em todas as abas e trocar de aba não inicia tarefas.

Os botões **Continuar** levam à próxima etapa. Ao iniciar uma tarefa, a aba **Resultados** abre para acompanhamento. Também é possível acessar qualquer aba diretamente.

1. **Cenário:** escolha o piloto ou prepare/carregue o cenário experimental dos nove cruzamentos. Arquivos, mapeamento e auditorias ficam recolhidos para consulta.
2. **Tráfego:** informe a quantidade total ou os veículos por hora de cada entrada. Entradas e percursos de pedestres são organizados por cruzamento; trocar a seleção mantém as edições. Configure duração e aquecimento. Ao variar o fluxo, distribua 100% dos veículos entre os períodos da simulação. A estimativa por período usa o mesmo arredondamento por entrada da geração da demanda.
3. **Treinamento:** escolha objetivo, quantidade de decisões e se deseja ver a simulação. O algoritmo disponível aparece discretamente. Sementes, pesos personalizados, parâmetros PPO e coleta detalhada ficam em **Configurações avançadas**. Em **Ajustar limites dos tempos**, selecione o cruzamento e edite os limites de verde das entradas atendidas. Não há seleção por etapa semafórica. O controle adaptativo escolhe aberturas compatíveis conforme sensores virtuais do SUMO e preserva amarelos e limpeza. Inicie pelo botão **Iniciar treinamento**. Estudos com vários treinamentos ficam no painel de repetições. Veja [controle adaptativo](controle_adaptativo.md) para compatibilidade de modelos e limites da simulação.
4. **Resultados:** acompanhe o progresso, consulte o resumo e use **Baixar resultados em Excel**. Não há tabelas de métricas nem lista de arquivos técnicos nessa tela. A exportação fica disponível ao concluir ou interromper a execução. Os arquivos originais continuam salvos internamente.
5. **Referência técnica:** consulte catálogos SUMO, parâmetros e o dicionário das métricas. Não é necessário editar estes catálogos para treinar.

O Excel reúne todas as métricas registradas em uma planilha, com unidades, origem, contexto e identificação de simulações completas ou parciais. Valores ausentes não viram zero. A geração é reaproveitada enquanto os arquivos não mudarem. Coletas opcionais, como emissões, continuam dependendo da configuração escolhida antes do treino.

Configurações inválidas exibem o ajuste necessário junto ao botão de início e bloqueiam o treino. A avaliação exige selecionar um modelo compatível. Passos de treinamento representam decisões do algoritmo; não representam segundos, veículos ou número de episódios. Modelos anteriores exigem seus cenários originais; o controle adaptativo precisa de novo treinamento.

O cenário dos nove cruzamentos continua experimental. Organizar a interface não altera a validade dos dados ou dos resultados científicos. Nenhuma execução começa apenas ao abrir uma aba.

Verificação sem executar modelos: `python scripts/verificar_interface_fluxo.py`. Os verificadores de métricas, diagnóstico e funcionalidades existentes também usam tarefas substituídas ou dados artificiais.


Ao carregar configurações de uma execução, os campos passam a refletir os valores salvos, mesmo que a rede seja a mesma. Edições de uma configuração anterior não são reaplicadas silenciosamente. Campos vazios ou inválidos bloqueiam o início com uma orientação; a tela continua disponível para correção.
