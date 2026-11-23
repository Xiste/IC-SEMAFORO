# Como usar a interface

Abra `http://localhost:8501`. A etapa inicial, **Cenário e tráfego**, reúne a rede e o mapa completo. Trocar de etapa não inicia tarefas.

Use **Continuar: preparar o treinamento** para seguir da configuração ao treino. Ao iniciar uma tarefa, a etapa **Resultados** abre para acompanhamento. Também é possível acessar qualquer etapa diretamente.

Em **Cenário e tráfego**, a interface prepara a rede e abre a configuração de demanda. Em **Resultados**, escolha **Treinos e simulações**, **Modelo × tempos iniciais** ou **Modelo × modelo**. Use **Execução** para consultar um treino ou uma simulação e **Comparação salva** para consultar um teste já feito. Use **Carregar configurações desta execução** para abrir os ajustes como um rascunho editável.

1. **Cenário e tráfego:** a rede dos nove cruzamentos é preparada ou reutilizada automaticamente. Em caso de falha, use **Tentar novamente**. Ao carregar uma execução individual antiga, os ajustes de tráfego são reaproveitados na rede completa e o arquivo antigo fica intacto.

   Na aba **Mapa**, clique em uma via destacada, semáforo ou travessia para abrir a janela de edição. Inicialmente, a busca e os destaques incluem as entradas selecionadas para os nove cruzamentos. A rede continua visível no fundo. Em **Filtros**, ative **Mostrar outros trechos da rede** para localizar e editar acessos adicionais. Volumes salvos continuam ativos ao ocultar esses trechos.

   Na aba **Tabela**, escolha **Volumes das vias** ou **Tempos dos semáforos**. Se **Incluir pedestres** estiver ligado, use **Travessias** para preencher pessoas por hora por cruzamento e sentido. O filtro de vias adicionais habilita **Outros trechos** na tabela. Preencha as células e aplique os valores. Mapa e tabela usam o mesmo rascunho.

   Para informar demanda, use o trecho em que os veículos entram. Contagens dos mesmos veículos mais adiante servem para conferir o resultado. Em Porto Alegre, Niterói e João Naves, as continuações consecutivas da mesma chegada ficam em **Outros trechos**. A entrada da Rua Alagoas usa o fim da rua antes da ligação com a Rua Ricardo Siquierolli Tucci. Na rede, a Rua Rotary Club é a entrada lateral e permite seguir para a Rua Antônio Crescêncio, que é uma das saídas. Os volumes vêm das contagens do estudo. [Alagoas no OpenStreetMap](https://www.openstreetmap.org/way/30620978), [ligação pela Ricardo Siquierolli Tucci](https://www.openstreetmap.org/way/403166934), [Antônio Crescêncio](https://www.openstreetmap.org/way/303101571) e [Rotary Club](https://www.openstreetmap.org/way/463014795).

   Digite a duração em segundos inteiros. O volume por hora de cada via vale para toda a simulação. Ative **Incluir pedestres** para mostrar as travessias no mapa e na busca e usar os fluxos configurados. Desativar a opção oculta as travessias e conserva os volumes no rascunho. Depois de preencher, confira o resumo e clique em **Simular com os tempos iniciais**.
2. **Treinamento:** escolha o algoritmo (**PPO** ou **A2C**) e a quantidade de decisões. PPO é o padrão de um estudo novo. O treino usa por padrão pesos iguais para espera, filas e tempo de viagem. Os limites de verde, a visualização do SUMO, as sementes, os pesos personalizados, os parâmetros do algoritmo escolhido e a coleta detalhada ficam em **Configurações avançadas**. O controle adaptativo escolhe aberturas compatíveis conforme sensores virtuais do SUMO e preserva amarelos e limpeza. O botão de correção leva à seção correspondente quando há uma pendência. Estudos com vários treinamentos ficam no painel de repetições. Veja [controle adaptativo](controle_adaptativo.md) para compatibilidade de modelos e limites da simulação.
3. **Resultados:** em **Treinos e simulações**, acompanhe o progresso, consulte as métricas e baixe o Excel da execução. Em **Modelo × tempos iniciais → Rodar nova comparação**, escolha o modelo treinado e selecione o cenário **Salvo no treino** ou **Em edição**. O teste roda os dois controles sob a mesma demanda por semente e salva um novo resultado com tabelas e Excel.

Em **Modelo × modelo**, selecione o **Modelo A** que você quer avaliar e o **Modelo B** que servirá de referência. São necessários dois modelos salvos compatíveis com o mesmo cenário. A comparação usa a mesma demanda e sementes para ambos e mostra as diferenças de A em relação a B.
4. **Referência técnica:** consulte catálogos SUMO, parâmetros e o dicionário das métricas. Não é necessário editar estes catálogos para treinar.

O Excel reúne os indicadores coletados na aba **Métricas**, com unidades, origem, contexto e identificação de simulações completas ou parciais. Faixas, emissões e consumo, eventos, recursos computacionais, movimentos, dinâmica dos veículos e classes são coletados automaticamente nas novas execuções. Indicadores ausentes nas execuções antigas continuam sem valor.

Em **Resultado por cruzamento**, escolha o cruzamento para comparar quantos veículos ficaram parados ao mesmo tempo, em média e no pior momento. Em **Tempos por semáforo**, escolha o cruzamento e o controle para ver **Verde**, **Amarelo** e **Vermelho**, em segundos por movimento. Em controles treinados, os valores são médias de trechos completos de cada cor, observados durante a simulação. A espera e a fila somadas em veículo·s ficam disponíveis no Excel, na aba **Resultado por cruzamento**.

Cliques e edições no mapa atualizam apenas a área de configuração. A busca aproxima o local escolhido. Para editar, clique no item no mapa. Limpe o campo de busca pelo **×** para voltar ao enquadramento dos nove cruzamentos. Os valores ficam guardados durante a edição e são conferidos ao avançar ou executar.

Ao selecionar um semáforo, escolha uma opção em **Quem recebe verde**. Os nomes mostram as vias e os sentidos atendidos juntos. Informe **Verde**, **Amarelo** e **Todos em vermelho** em segundos e clique em **Aplicar tempos**. Na tabela, a coluna **Quem recebe verde** usa os mesmos nomes. Os valores precisam respeitar os mínimos do cenário e o limite de ciclo.

Configurações inválidas exibem o ajuste necessário junto ao botão de início e bloqueiam o treino. A avaliação exige selecionar um modelo compatível. Passos de treinamento representam decisões do algoritmo; não representam segundos, veículos ou número de episódios. Modelos anteriores exigem seus cenários originais; o controle adaptativo precisa de novo treinamento.

O cenário dos nove cruzamentos continua experimental. Organizar a interface não altera a validade dos dados ou dos resultados científicos. Nenhuma execução começa apenas ao abrir uma aba.

Verificação sem executar modelos: `python scripts/verificar_interface_fluxo.py`. Os verificadores de métricas, diagnóstico e funcionalidades existentes também usam tarefas substituídas ou dados artificiais.


Ao carregar configurações de uma execução, os campos passam a refletir os valores salvos, mesmo que a rede seja a mesma. Edições de uma configuração anterior não são reaplicadas silenciosamente. Campos vazios ou inválidos bloqueiam o início com uma orientação; a tela continua disponível para correção.
