# Revisão da interface do laboratório de trânsito

Revisão aplicada em 21/10/2026. Público: estudante que conhece o objetivo da pesquisa, mas não precisa conhecer SUMO, aprendizado por reforço ou códigos da rede para executar um estudo.

## Diagnóstico e mudanças

| Etapa | Dificuldade encontrada | Solução aplicada |
| --- | --- | --- |
| Navegação | Botões Continuar atualizavam o estado, mas podiam manter a aba anterior no navegador. | Seletor nativo com estado controlado e seções visíveis conforme a escolha; confirmação visual dos botões Voltar e Continuar no navegador. |
| Cenário | Conferências, tabelas e movimentos ocupavam o caminho básico de configuração. | Escolha do local, indicação de preparo e ação Continuar em primeiro plano; tempos e mapa disponíveis sob consulta. |
| Tráfego | Veículos/h, tempo simulado e medição exigiam explicação fora da tela. | Exemplo por minuto junto ao volume, seções por assunto e explicação de avaliação do período após o aquecimento. |
| Treinamento | Tamanhos de treino pareciam durações e as opções avançadas interrompiam as decisões principais. | Explicação imediata dos três tamanhos e separação entre decisões, segundos simulados e tempo no computador; resultados coletados antes dos ajustes avançados. |
| Limites | Tabela longa com repetição de cruzamentos e códigos internos duplicados. | Seletores de cruzamento, conjunto e etapa; apenas três tempos editáveis; estado separado para manter edições das demais etapas. |
| Resultados | Uma tabela numérica exigia interpretação para descobrir o que mudou. | Cartões com espera, viagem e viagens concluídas; diferença em relação aos tempos iniciais, unidades e direção desejável explicadas. |
| Estados vazios e bloqueios | Botões desativados sem indicação local do próximo passo. | Situação da configuração na lateral, explicação de execução ativa e ação para retornar à etapa que precisa de ajuste. |
| Visual | Baixa hierarquia e aparência semelhante entre informação principal e detalhe técnico. | Tema claro, identidade azul e verde, títulos numerados, foco visível, controles maiores e estilos para telas estreitas. |
| Referência técnica | Termos técnicos sem uma introdução curta para iniciantes. | Dicionário de simulação, treinamento, decisão, etapa, ciclo e avaliação. |

## Princípios usados

- Mostrar primeiro as decisões necessárias; revelar os detalhes sob demanda.
- Cada etapa deve explicar o que configurar e qual é o próximo passo.
- Nomes, números e unidades precisam ter o mesmo significado na configuração, execução e comparação.
- Não afirmar convergência, melhora estatística ou fidelidade ao trânsito real com base apenas na conclusão de um treino.
- Manter a tecnologia existente quando ela resolve o problema sem introduzir novas dependências.

Referências consultadas:

- [NN/g — Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/).
- [GOV.UK — Complete multiple tasks](https://design-system.service.gov.uk/patterns/complete-multiple-tasks/).
- [NN/g — Recognition and Recall](https://www.nngroup.com/articles/recognition-and-recall/).
- [Anthropic — Prompt engineering overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview): critérios de sucesso verificáveis antes de refinar um prompt.

## Como avaliar se ficou didático

Verificação técnica realizada: testes de navegação, configuração enviada ao treinamento, seleção de análise detalhada, preservação de limites, mapas e pedestres; dois roteiros de interface com início de tarefas substituído. No navegador, foram conferidos cenário, tráfego, treinamento, estado vazio dos resultados e a navegação. Em largura de 390 px, a página manteve `scrollWidth` igual à largura disponível, sem transbordamento horizontal do documento. Não foi executado treinamento real para validar a repaginação.

Uma revisão técnica e visual não substitui observar usuários. Teste com pessoas que ainda não usaram o sistema, sem explicar os controles antes:

1. Configurar um cruzamento com 600 veículos/h e duração de 600 s.
2. Explicar quantos veículos serão planejados, a diferença entre segundos simulados e decisões de treinamento e o objetivo escolhido.
3. Localizar uma entrada no mapa e configurar seu volume.
4. Alterar um limite, consultar outra etapa e retornar sem perder a alteração.
5. Iniciar um teste, localizar seu progresso e comparar o modelo concluído.
6. Dizer se a espera caiu e conferir se as viagens concluídas e pendentes também foram consideradas.

Registre os pontos em que precisaram de ajuda, interpretações incorretas e passos desnecessários. Não classifique a interface como totalmente compreensível apenas porque os testes automatizados passaram.

## Prompts reutilizáveis para novas revisões

Os prompts abaixo foram elaborados para este projeto, com base nas referências; não são transcrições de prompts de terceiros.

### Auditoria de entendimento

> Revise a interface como uma pessoa que pesquisa semáforos, mas não conhece SUMO nem aprendizado por reforço. Percorra cenário, tráfego, treinamento e resultados. Para cada controle, diga: o que a pessoa entende, qual decisão precisa tomar, qual informação falta e qual texto ou interação resolve o problema. Priorize problemas que impedem configurar ou executar. Preserve os significados científicos e as unidades. Entregue achado, evidência, impacto, mudança proposta e forma de verificar. Não atribua uma nota de usabilidade sem teste com usuários.

### Revisão visual e implementação

> Reorganize a tela para destacar uma tarefa principal por etapa. Use componentes nativos do projeto, espaçamento consistente, contraste legível, foco de teclado e apresentação em telas estreitas. Mostre exemplos junto a escolhas ambíguas e recolha detalhes avançados. Não esconda estados de erro nem use somente cor para transmitir significado. Preserve a configuração enviada ao simulador. Implemente e confira no navegador: estado inicial, erro, execução em andamento e resultado concluído.

### Verificação de resultados

> Revise a apresentação dos resultados sem inferir sucesso a partir da pontuação do treinamento. Compare apenas execuções completas e pareadas. Mostre referência, controle avaliado, diferença e unidade. Explique a direção desejável de cada indicador e confira viagens concluídas, pendentes e ainda em andamento. Diferencie descrição de diferenças de evidência de melhora estatística. Liste dados ausentes sem tratá-los como zero.

### Revisão de regressão

> Após alterar a interface, verifique se selecionar outra etapa preserva edições anteriores, se Voltar e Continuar mudam a aba visível, se configurações inválidas bloqueiam a execução com uma instrução útil e se o treinamento recebe algoritmo, prioridades, limites e coleta escolhidos. Use tarefas substituídas nos testes de interface; execute simulações reais apenas quando necessárias à mudança. Registre o que foi verificado e as limitações.
