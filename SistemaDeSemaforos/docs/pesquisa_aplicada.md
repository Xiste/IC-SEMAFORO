# Pesquisa aplicada ao cenário Rondon Norte

Esta nota separa resultados publicados das decisões de implementação deste
projeto. Nenhum dos artigos valida a rede local ou seus planos operacionais.

| Fonte primária | O que orienta aqui | Ação no projeto |
| --- | --- | --- |
| [RESCO, NeurIPS 2021](https://datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/f0935e4cd5920aa6c7c996a5ee53a70f-Abstract-round1.html) | Comparações de RL dependem de cenários, topologia e observação realistas; inclui referências convencionais. | Comparar PPO com programa da rede e heurística reativa nas mesmas sementes; reportar dispersão. |
| [PressLight, KDD 2019](https://kdd.org/kdd2019/accepted-papers/view/presslight-learning-max-pressure-control-for-signalized-intersections-in-ar) | Pressão de filas é um sinal importante para controle de rede. | A heurística adicionada usa filas de entrada como referência simples. **Não é max-pressure:** faltam filas de saída e pesos de movimento. |
| [CoLight, CIKM 2019](https://arxiv.org/abs/1905.05717) | Cooperação entre sinais importa em rede arterial. | O PPO atual reúne observações de todos os alvos, mas ainda não modela vizinhança ou coordenação explícita; avaliar isso após mapear os nove. |
| [PedSLight, 2026](https://www.frontiersin.org/journals/future-transportation/articles/10.3389/ffutr.2026.1953597/full) | Avalia eficiência e risco para veículos e pedestres com fases predefinidas; recompensa ponderada não garante segurança rígida. | Manter transições fixas e exigir validação dos estágios; métricas e demanda de pedestres aguardam reconstrução da rede. |
| [SUMO: dados de contagem](https://sumo.dlr.de/docs/Tools/Turns.html) | `routeSampler.py` pode combinar contagens por via, conversão e OD, mas contagens incompletas não determinam rotas únicas. | O gerador atual usa hipóteses sintéticas explícitas; integrar `routeSampler` quando houver contagens e rotas candidatas verificadas. |
| [SUMO: programas semafóricos](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html) e [NetEdit](https://sumo.dlr.de/docs/Netedit/editModesNetwork.html) | Estados são associados a índices de links; programas e travessias podem ser inspecionados e corrigidos. | Exportar IDs, links, fases e posições para revisão antes de alterar o programa ou ampliar o PPO. |

## O que já foi resolvido com os arquivos atuais

`python pipeline.py mapping-review --output resultados/revisao_RENOMEIE` produz:

- `controllers_map.png`: posição dos 28 controladores na rede, numerados por `review_index`;
- `controllers.csv`: ID, posição local SUMO, nós, links e eventual nome conhecido;
- `links.csv`: índice e faixa de origem/destino de cada movimento controlado;
- `phases.csv`: estados e duração das fases;
- `nearby_pairs.csv`: controladores a até 60 m, apenas **candidatos** a agrupamento;
- `summary.json`: projeção da rede, cobertura do mapeamento e presença de infraestrutura pedestre.

A avaliação `ppo-eval` agora inclui `queue_actuated`, que observa as filas nas
faixas servidas pelo verde atual e pelo próximo verde configurado. Ela escolhe
encurtar, manter ou estender o verde pelos mesmos limites do ambiente PPO.
É um controle reativo simples, incluído como comparação adicional; não reproduz
o método dos artigos PressLight ou RESCO.

## Dependências externas ainda necessárias

1. Coordenadas ou desenho de cada cruzamento, para ligar os nove nomes aos
   controladores e verificar se um cruzamento tem vários IDs.
2. Planos operacionais completos, estados de todos os movimentos, amarelos,
   limpeza, travessias e fonte responsável pela validação. O plano 4 do Paraná
   tem quatro estágios; o programa nominal SUMO tem dois verdes.
3. Travessias e rotas de pedestres, se o experimento avaliar pedestres. A rede
   entregue contém zero arestas `crossing` e zero `walkingarea`.
4. Contagens por aproximação e intervalo, conversões ou OD, e dados para
   confrontar velocidades, filas e tempos de viagem simulados com observações.

Até esses itens serem resolvidos, o piloto não sustenta conclusões sobre os
nove cruzamentos reais.
