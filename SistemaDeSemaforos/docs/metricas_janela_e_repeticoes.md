# Métricas, aquecimento e estudos repetidos

A interface inclui 185 campos no catálogo, contando indicadores, variantes estatísticas e informações de cobertura. Nem todos são medidos em todo cenário: emissões são opcionais, pedestres exigem demanda de pessoas e passagens por movimento exigem faixa interna identificável exclusivamente. Ausência de amostras produz valor vazio, não uma melhoria artificial.

## Como configurar

1. Em **Volume por via**, abra **Volume total por cruzamento e distribuição pelas entradas**. Preencha veículos/h por cruzamento e os percentuais das entradas, totalizando 100%. Clique em **Aplicar volumes por cruzamento**. A distribuição inicial é uniforme; ajuste os sentidos conforme as contagens. Para fluxos que atravessam vários cruzamentos, escolha contagens observadas e calibração para evitar gerar veículos novamente nos trechos internos.
2. Em **Aquecimento e janela de medição**, informe o aquecimento e, opcionalmente, início/fim da medição. Os tempos devem ser múltiplos do passo SUMO e respeitar `0 ≤ aquecimento ≤ início < fim ≤ duração`. O padrão continua sem aquecimento, preservando cenários existentes.
3. Em **Métricas opcionais**, escolha detalhes de faixas/movimentos, classes, dinâmica e emissões. Os limiares de ocupação, espera longa, frenagem e TTC ficam registrados na configuração.
4. Em **Treinamentos independentes e avaliações automáticas**, informe sementes de treino diferentes das sementes reservadas de avaliação. O plano mostra custo solicitado e número de episódios. A execução só começa pelo botão; cada repetição cria um modelo novo e compara referência, heurística e modelo com as mesmas demandas.

## O que é medido

- Rede: espera e fila integradas, fila média/picos/percentis, atividade, distância, inserções e chegadas/h, atendimento, exposição à espera longa e instantes com todos os veículos parados.
- Faixa: fila em veículos e metros pelos detectores E2, percentis, densidade, ocupação, velocidade, espera, novas paradas e possível transbordamento.
- Movimento: verde/amarelo/vermelho, maior vermelho contínuo, verde sem demanda, utilização do verde, fluxo/h, passagens por hora de verde, pressão de filas e verde com saída ocupada e fila parada.
- Viagens: média, mediana, mínimo, máximo, desvio e percentis 50/90/95/99 de duração, espera, perda de tempo, paradas, distância e atraso de inserção.
- Classes SUMO: veículos distintos, atividade, distância, velocidade média, tempo parado e espera. A coleta separa as classes presentes; não cria automaticamente ônibus ou motos na demanda.
- Pedestres: atividade, caminhada, espera, maior espera por travessia, passagens e percentis da duração das caminhadas.
- Dinâmica exploratória: novas paradas, frenagens fortes, excesso de velocidade e variação da aceleração; TTC longitudinal baseado no veículo líder.
- Ambiente e execução: poluentes/combustível/eletricidade totais e por km, eventos de colisão/teletransporte, CPU/memória e cobertura da janela.

As integrais e eventos consideram apenas os passos da janela. `total_departed` e `total_arrived` cobrem o episódio inteiro. Veículos ativos e partidas atrasadas são registrados no fim da janela, mesmo se o episódio continuar. Partidas futuras não são tratadas como inserções bloqueadas. As estatísticas de viagem selecionam chegadas na janela e usam a duração completa da viagem, inclusive seu trecho no aquecimento; não representam apenas a permanência dentro da janela.

O aquecimento mantém o programa de referência para todos os controles e não conta como passos de aprendizado. Entre o aquecimento e o início escolhido da medição, o controle já pode atuar, mas suas métricas permanecem excluídas. Ter tráfego ao iniciar a medição depende da demanda e do tempo de aquecimento escolhido; o programa não garante ocupação mínima automaticamente. Perfis variáveis de demanda alteram a taxa da janela: confira se o período escolhido representa as contagens informadas.

## Resultados na interface

As tabelas de resultados exibem os detalhes e permitem baixar `lanes.csv`, `movements.csv` e `vehicle_classes.csv`. O mapa destaca redução/aumento médio de fila e indicadores de bloqueio/transbordamento. As posições são aproximadas pelas entradas; redes sem projeção usam coordenadas locais. Cor verde não comprova significância estatística. Os relatórios existentes não ganham medições que não foram coletadas; os novos detalhes aparecerão nas próximas execuções.

Estudos repetidos exportam plano, comparações, repetições completas e agregado. O intervalo exploratório é calculado entre médias dos treinamentos independentes; sementes de avaliação compartilhadas não são contadas como novos treinamentos. Repetições interrompidas ficam fora do agregado, e o estudo é identificado como incompleto. Os diretórios individuais preservam os relatórios e mapas de cada avaliação.

TTC/frenagem são indicadores exploratórios, sem conflitos laterais ou validação de acidentes. Verde bloqueado e transbordamento dependem dos limiares e da geometria; não certificam bloqueio físico. Passagens por hora de verde não equivalem a capacidade ou fluxo de saturação. Taxas sem chegadas, distância ou verde têm valor vazio.

## Verificação nesta implementação

Não foram executados modelos, treinamentos ou simulações SUMO. Foram usados testes de cálculos, exportação, execução com TraCI substituído e interface Streamlit com início de tarefas substituído. A validação integrada de detectores no SUMO e o desempenho das coletas ampliadas em carga real precisam ser conferidos quando a execução for solicitada.
