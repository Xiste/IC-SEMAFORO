# Controle dos nove cruzamentos pela interface

Abra `python -m streamlit run interface.py` com o Python do ambiente virtual.

1. Em **Cruzamentos controlados**, selecione **Nove cruzamentos: cenário experimental**.
2. Clique em **Preparar e verificar os nove cruzamentos**. A interface cria uma cópia da rede corrigida e configura os 17 controladores associados aos nove locais. Não altera a rede original nem declara os planos reais validados.
3. Confira a tabela de controladores e ciclos. O horizonte padrão é aumentado para dois ciclos do controlador mais longo. Se mudar as durações, confira novamente o horizonte necessário.
4. Configure **Volume por via** na tabela, ou use a taxa sintética total. Destino vazio significa destino sintético alcançável. A demanda padrão não garante fluxo em todos os cruzamentos; contagens reais e destinos continuam necessários para representatividade.
5. Clique em **Testar cenário no SUMO por 30 segundos**. Marque SUMO-GUI para visualizar. O teste verifica carregamento e funcionamento, não percorre todas as fases nem prova ausência de conflitos em campo.
6. Configure o orçamento e clique em **Iniciar treinamento PPO**.
7. Ao concluir, clique em **Atualizar lista de modelos treinados**, selecione o modelo em **Selecionar modelo treinado** e clique em **Avaliar PPO e referência**. Use o mesmo cenário e limites do treino.
8. Exporte os CSVs e relatórios apresentados. A avaliação compara PPO, programa experimental de referência e heurística em sementes independentes.

Para voltar depois, selecione o cenário na lista **Cenário conjunto salvo** e clique em **Usar cenário salvo**. Não há edição obrigatória de JSON ou caminhos de arquivos.

## Programa experimental

A preparação usa `netconvert --tls.rebuild --tls.ungroup-signals` sobre a rede corrigida, preservando IDs. Depois cria atendimento sequencial: um índice de movimento verde por controlador, amarelo e intervalo vermelho antes do próximo. Índices compartilhados só são aceitos para duas direções da mesma travessia. Controladores distintos no mesmo nó são rejeitados. Todos os índices recebem atendimento; nenhum permanece desligado.

Os controladores fora dos nove mantêm estados e tempos dos programas anteriores, traduzidos para os índices reconstruídos. Existem avisos SUMO de movimentos sem verde em quatro desses controladores externos; a preparação dos nove não resolve essas pendências da rede inteira.

Referência das opções usadas: [documentação oficial do netconvert](https://sumo.dlr.de/docs/netconvert.html).

Travessias usam um piso de duração calculado pelo comprimento e velocidade experimental de 0,8 m/s, com margem de dois segundos. A limpeza das conexões usa comprimento/velocidade com margem; travessias têm limpeza pelo tempo geométrico. Esses valores são premissas sintéticas, não certificação de segurança nem tempos reais de campo. A rede recebe hash SHA-256; mudanças invalidam a preparação. Pisos das travessias e tempos originais de amarelo/limpeza não podem ser reduzidos pelo PPO.

O atendimento serial evita abrir movimentos distintos simultaneamente em um controlador, mas gera ciclos longos e pode piorar filas. Não representa uma referência competitiva com planos reais. Uma evolução posterior é agrupar movimentos compatíveis com auditoria da matriz de conflitos, encurtando ciclos. O PPO aqui ajusta durações; não agrupa movimentos ou altera ordem/estados das fases. A existência de travessias não injeta demanda de pedestres automaticamente.

Dez épocas são passagens de otimização por coleta, não garantia de convergência. O orçamento piloto de 2.048 passos pode ser insuficiente para 17 controladores e 450 componentes de ação. Avalie curvas de recompensa, filas, viagens incompletas e dispersão em várias sementes antes de afirmar melhoria.
