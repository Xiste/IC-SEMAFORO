# Como usar a interface

Abra `http://localhost:8501`. A etapa inicial, **Cenário e tráfego**, reúne a rede e o mapa completo. Trocar de etapa não inicia tarefas.

Use **Continuar: preparar o treinamento** para seguir da configuração ao treino. Ao iniciar uma tarefa, a etapa **Resultados** abre para acompanhamento. Também é possível acessar qualquer etapa diretamente.

Na barra lateral, **Começar com um exemplo** abre dez minutos de tráfego com volumes ilustrativos nas entradas de Rondon × Paraná. **Duplicar estudo anterior** abre os ajustes de uma execução compatível como um novo rascunho. A cópia conserva os parâmetros salvos e o arquivo original. As duas ações trocam a configuração da tela. Para simular ou treinar, use os botões de execução.

1. **Cenário e tráfego:** a rede dos nove cruzamentos é preparada ou reutilizada automaticamente. Abra **Detalhes da rede** para consultar os tempos iniciais ou preparar a rede manualmente. Ao carregar uma execução individual antiga, os ajustes de tráfego são reaproveitados na rede completa e o arquivo antigo fica intacto.

   Clique em uma via, semáforo ou travessia para abrir a janela de edição sobre o mapa. Também é possível localizar o objeto pelo nome da rua ou do cruzamento na busca. Por padrão, só os trechos com nome cadastrado aparecem na busca de vias e ficam disponíveis para edição direta. Ative **Mostrar também vias sem nome** para editar os demais trechos da rede simulada. O filtro preserva os volumes já configurados. Ruas presentes apenas no fundo cartográfico ficam fora da busca.

   Na janela da via, ajuste **Veículos por hora** e veja a demanda estimada para aquele sentido durante o episódio. Ative **Incluir pedestres** acima do mapa para usar os fluxos definidos nas travessias. Escolha a duração acima do mapa. O cenário fornece a velocidade de caminhada, o passo do SUMO e o aquecimento. Ao variar o fluxo, distribua 100% dos veículos entre os períodos. Use **Ver uma prévia de 30 segundos** para observar o cenário atual com o programa inicial no SUMO-GUI.
2. **Treinamento:** escolha objetivo, quantidade de decisões e se deseja ver a simulação. Sementes, pesos personalizados, parâmetros PPO e coleta detalhada ficam em **Configurações avançadas**. No mapa, os limites de verde aparecem em cartões com movimentos por extenso e campos separados de mínimo e máximo. O controle adaptativo escolhe aberturas compatíveis conforme sensores virtuais do SUMO e preserva amarelos e limpeza. Antes de executar, a revisão mostra alterações relevantes em relação ao início do rascunho. Quando houver uma pendência, o botão de correção leva à seção correspondente e abre o controlador quando a validação o identifica. Estudos com vários treinamentos ficam no painel de repetições. Veja [controle adaptativo](controle_adaptativo.md) para compatibilidade de modelos e limites da simulação.
3. **Resultados:** acompanhe o progresso, consulte o resumo e use **Baixar resultados em Excel**. A comparação mostra a espera acumulada antes e depois em cada cruzamento com dados pareados. Os totais de viagens concluídas são referentes à rede inteira. A exportação fica disponível ao concluir ou interromper a execução, e os arquivos originais continuam salvos internamente.
4. **Referência técnica:** consulte catálogos SUMO, parâmetros e o dicionário das métricas. Não é necessário editar estes catálogos para treinar.

O Excel reúne todas as métricas registradas em uma planilha, com unidades, origem, contexto e identificação de simulações completas ou parciais. Valores ausentes não viram zero. A geração é reaproveitada enquanto os arquivos não mudarem. Coletas opcionais, como emissões, continuam dependendo da configuração escolhida antes do treino.

Cliques e edições no mapa atualizam apenas a área de configuração, sem refazer os catálogos, resultados ou a preparação dos nove cruzamentos. O mapa conserva sua identidade e seu enquadramento ao editar ou trocar ajustes pelo canvas. A busca aproxima o local escolhido. **Voltar à visão geral do mapa** devolve o enquadramento da rede completa. Os valores ficam guardados durante a edição e são conferidos ao avançar ou executar.

Ao selecionar um semáforo, escolha o grupo que recebe verde junto, informe **Verde**, **Amarelo** e **Todos em vermelho** em segundos e clique em **Aplicar tempos**. A edição mantém os movimentos e a sequência do programa. Os valores precisam respeitar os mínimos do cenário e o limite de ciclo. A simulação usa uma cópia da rede com os tempos aplicados. Abaixo do mapa, **Ciclo e tempos por via** mostra a sequência e o total de cada cor no movimento selecionado. O vermelho de uma via inclui o intervalo em que todos estão fechados e o tempo em que outros grupos estão abertos. **Limites de verde do treinamento** permite ajustar o intervalo disponível ao agente durante o controle adaptativo. A edição do ciclo está disponível na rede preparada com grupos compatíveis.

Configurações inválidas exibem o ajuste necessário junto ao botão de início e bloqueiam o treino. A avaliação exige selecionar um modelo compatível. Passos de treinamento representam decisões do algoritmo; não representam segundos, veículos ou número de episódios. Modelos anteriores exigem seus cenários originais; o controle adaptativo precisa de novo treinamento.

O cenário dos nove cruzamentos continua experimental. Organizar a interface não altera a validade dos dados ou dos resultados científicos. Nenhuma execução começa apenas ao abrir uma aba.

Verificação sem executar modelos: `python scripts/verificar_interface_fluxo.py`. Os verificadores de métricas, diagnóstico e funcionalidades existentes também usam tarefas substituídas ou dados artificiais.


Ao carregar configurações de uma execução, os campos passam a refletir os valores salvos, mesmo que a rede seja a mesma. Edições de uma configuração anterior não são reaplicadas silenciosamente. Campos vazios ou inválidos bloqueiam o início com uma orientação; a tela continua disponível para correção.
