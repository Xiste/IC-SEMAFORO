# Controle dos nove cruzamentos pela interface

Abra `python -m streamlit run interface.py` com o Python do ambiente virtual.

1. Em **Cruzamentos controlados**, selecione **Nove cruzamentos: cenário experimental**.
2. Clique em **Preparar e verificar os nove cruzamentos**. A interface cria uma cópia da rede corrigida e configura os 17 controladores associados aos nove locais. Não altera a rede original nem declara os planos reais validados.
3. Confira a tabela de controladores e ciclos. O horizonte padrão é aumentado para dois ciclos do controlador mais longo. Se mudar as durações, confira novamente o horizonte necessário.
4. Configure **Volume por via** na tabela, ou use a taxa sintética total. Destino vazio significa destino sintético alcançável. A demanda padrão não garante fluxo em todos os cruzamentos; contagens reais e destinos continuam necessários para representatividade.
5. Clique em **Testar cenário no SUMO por 30 segundos**. Marque SUMO-GUI para visualizar. O teste verifica carregamento e funcionamento, não percorre todas as fases nem prova ausência de conflitos em campo.
6. Para testar a infraestrutura sem algoritmo, clique em **Executar simulação sem treinamento**. Para treinar, configure o orçamento e clique em **Iniciar treinamento PPO**.
7. Ao concluir, clique em **Atualizar lista de modelos treinados**, selecione o modelo em **Selecionar modelo treinado** e clique em **Avaliar PPO e referência**. Use o mesmo cenário e limites do treino.
8. Exporte os CSVs e relatórios apresentados. A avaliação compara PPO, programa experimental de referência e heurística em sementes independentes.

Para voltar depois, selecione o cenário na lista **Cenário conjunto salvo** e clique em **Usar cenário salvo**. Não há edição obrigatória de JSON ou caminhos de arquivos.

## Programa experimental

A preparação usa `netconvert --tls.rebuild --tls.ungroup-signals` sobre a rede corrigida, preservando IDs. A matriz `foes` identifica movimentos conflitantes; movimentos sem conflito podem receber verde juntos, seguidos de amarelo e vermelho de limpeza. Convergências para a mesma faixa também são tratadas como conflitos. A auditoria verifica cobertura de todos os índices, estados, transições, tempos geométricos mínimos e controladores independentes no mesmo nó. São programas experimentais protegidos; não reproduzem planos reais.

Os demais controladores mantêm estados e tempos anteriores, traduzidos para os índices reconstruídos. Quatro programas externos sem atendimento verde são substituídos por grupos experimentais auditados: `FAM_RONDON_RIO_DE_JANEIRO`, `FAM_MARANHAO_MONSENHOR_EDUARDO`, `5494111593` e `2042693363`. Estes quatro operam como referência fixa; não entram nas ações dos nove cruzamentos.

Referência das opções usadas: [documentação oficial do netconvert](https://sumo.dlr.de/docs/netconvert.html).

Travessias usam um piso de duração calculado pelo comprimento e velocidade experimental de 0,8 m/s, com margem de dois segundos. A limpeza das conexões usa comprimento/velocidade com margem; travessias têm limpeza pelo tempo geométrico. Esses valores são premissas sintéticas, não certificação de segurança nem tempos reais de campo. A rede recebe hash SHA-256; mudanças invalidam a preparação. Pisos das travessias e tempos originais de amarelo/limpeza não podem ser reduzidos pelo PPO.

Na preparação verificada, os ciclos iniciais dos 17 alvos ficaram entre 67 e 221 s, com máximo permitido de 296 s considerando os limites de todas as fases. O algoritmo ajusta durações; os grupos e a ordem são definidos na preparação. A existência de travessias não injeta demanda de pedestres automaticamente. Cenários antigos `serial_links_v1` continuam carregáveis, mas precisam ser preparados novamente para obter agrupamento e correções externas. Modelos devem ser usados com o cenário e limites correspondentes.

Dez épocas são passagens de otimização por coleta, não garantia de convergência. O orçamento piloto de 2.048 passos pode ser insuficiente para 17 controladores. A interface mostra a dimensão atual das ações e o orçamento estimado. Avalie filas, viagens incompletas e dispersão em várias sementes antes de afirmar melhoria.

## Contagens por via e formulários

Em **Volume por via**, selecione o significado dos números:

- **Novos veículos gerados no trecho**: cada linha adiciona viagens; não representa uma contagem interna de veículos que já vêm de outra rua.
- **Contagens observadas: calibrar entradas da rede**: ajusta taxas de rotas entre bordas para explicar contagens em trechos internos. Duas contagens de 600 veículos/h em trechos consecutivos podem ser atendidas pelos mesmos 600 veículos/h. Zero só é usado como medição quando a opção de zero medido estiver marcada.

Clique em **Calibrar demanda e conferir contagens** para comparar valores informados e ajustados antes de executar. Ajustes acima da tolerância impedem a execução. Os destinos continuam sintéticos; o método considera rotas candidatas e não substitui dados reais de origem/destino. Durante a simulação, detectores E1 contam veículos distintos por trecho. `flow_counts.csv` mostra fluxo informado, ajustado e efetivamente observado, que pode mudar por filas, partidas pendentes e início da simulação.

Perfil horário, composição de veículos, distribuição de destinos, pares origem/destino e limites por fase são tabelas. Percentuais devem somar 100%; janelas devem cobrir o episódio sem lacunas. A soma dos maiores tempos por controlador respeita o teto de ciclo. O preview gera a demanda do episódio completo e executa apenas seus primeiros 30 s, preservando inclusive janelas iniciais sem tráfego.
