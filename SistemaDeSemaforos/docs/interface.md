# Como usar a interface

Abra `http://localhost:8501` e siga as abas numeradas. Os ajustes ficam disponíveis em todas as abas e trocar de aba não inicia tarefas.

Os botões **Continuar** levam à próxima etapa. Ao iniciar uma tarefa, a aba **Resultados** abre para acompanhamento. Também é possível acessar qualquer aba diretamente.

1. **Cenário:** escolha o piloto ou prepare/carregue o cenário experimental dos nove cruzamentos. Arquivos, mapeamento e auditorias ficam recolhidos para consulta.
2. **Tráfego:** escolha volume total da rede, volumes por cruzamento/entrada ou origens e destinos. Configure duração e aquecimento. Em volumes por cruzamento, distribua 100% pelas entradas e aplique. As ações de calibração, validação e simulação sem treino estão nesta aba.
3. **Treinamento:** escolha algoritmo e total de passos. Sementes, pesos dos objetivos e parâmetros de coleta ficam em **Ajustes avançados do treinamento**. Confira o resumo e inicie. Para avaliar, abra **Selecionar modelo para avaliação**, atualize a lista e escolha o modelo. Estudos com vários treinamentos ficam no painel de repetições.
4. **Resultados:** acompanhe a execução, veja as comparações e o mapa, ou abra relatórios anteriores. Informações técnicas completas ficam recolhidas. A barra lateral permite recuperar o acompanhamento de uma execução existente.
5. **Referência técnica:** consulte catálogos SUMO, parâmetros e o dicionário das métricas. Não é necessário editar estes catálogos para treinar.

Configurações inválidas exibem o ajuste necessário no resumo e bloqueiam o início do treino. A avaliação exige selecionar um modelo. Passos de treinamento representam decisões do algoritmo; não representam segundos, veículos ou número de episódios.

O cenário dos nove cruzamentos continua experimental. Organizar a interface não altera a validade dos dados ou dos resultados científicos. Nenhuma execução começa apenas ao abrir uma aba.

Verificação sem executar modelos: `python scripts/verificar_interface_fluxo.py`. Os verificadores de métricas, diagnóstico e funcionalidades existentes também usam tarefas substituídas ou dados artificiais.
