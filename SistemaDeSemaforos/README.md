# Simulação e otimização semafórica — Rondon Norte

Pipeline de pesquisa com SUMO/TraCI, Gymnasium, PPO e Streamlit. A estrutura separa cenário, simulação, algoritmos, experimentos e apresentação. Consulte a [arquitetura e extensão dos algoritmos](docs/arquitetura.md).

## Executar

Na pasta SistemaDeSemaforos, em PowerShell:

```powershell
.\.venv\Scripts\python.exe -m streamlit run interface.py
.\.venv\Scripts\python.exe pipeline.py inspect
.\.venv\Scripts\python.exe pipeline.py algorithms
.\.venv\Scripts\python.exe pipeline.py rl-train --algorithm PPO --config config/cenario.json
.\.venv\Scripts\python.exe pipeline.py rl-eval --model resultados/PASTA_DO_TREINO/ppo_model.zip
```

Interface: http://localhost:8501. Os comandos ppo-train e ppo-eval continuam disponíveis. train executa a busca com modelo substituto, separada do aprendizado por reforço. run executa a referência da rede ou um candidato de tempos fixos.

Para instalação nova: instale SUMO, exponha sumo no PATH ou defina SUMO_HOME, crie o ambiente Python e instale requirements.txt. Os resultados são gravados em diretórios novos; não são sobrescritos.

## Estrutura

```text
SistemaDeSemaforos/
├── pipeline.py                 # entrada CLI, mantida
├── interface.py                # entrada Streamlit, mantida
├── semaforos/
│   ├── cli.py                  # roteamento dos comandos
│   ├── caminhos.py             # raiz do projeto
│   ├── cenario/                # configuração, rede, demanda, planos e mapeamento
│   ├── simulacao/              # ambiente Gymnasium e execução SUMO/TraCI
│   ├── algoritmos/             # registro, PPO, heurísticas e busca substituta
│   ├── experimentos/           # treino/avaliação compartilhados e proveniência
│   ├── relatorios/             # métricas, exportação, catálogos e legendas
│   └── apresentacao/           # interface Streamlit
├── config/                     # cenários e mapeamentos
├── dados/                      # redes, planilha, contagens e evidências
├── scripts/                    # manutenção e auditoria
├── tests/                      # testes unitários e integração SUMO
├── docs/                       # documentação e tabelas regeneráveis
└── resultados/                 # experimentos locais, fora do Git
```

## Estado do experimento

O cenário padrão mantém o piloto com um controlador. Pela interface, **Nove cruzamentos: cenário experimental** prepara uma cópia da rede com os 17 controladores associados e atendimento de todos os movimentos e travessias. Permite salvar/reutilizar o cenário, testar no SUMO, treinar e selecionar o modelo para avaliação. Programas sintéticos seriais geram ciclos longos e não reproduzem planos reais. Veja o [passo a passo e as limitações](docs/controle_nove_interface.md).

O único adaptador publicado é PPO. Outro algoritmo precisa de implementação, registro e teste de compatibilidade com as observações e ações do ambiente. Não há garantia de convergência ou ótimo global.

## Documentação

- [Arquitetura e extensão dos algoritmos](docs/arquitetura.md).
- [Interface, legendas e exportação CSV](docs/interface_catalogos.md).
- [PPO e durações de fases](docs/ppo_duracoes.md).
- [Cadastro dos nove cruzamentos](docs/cadastro_nove_cruzamentos.md).
- [Conferência visual e evidências](docs/conferencia_visual_nove_cruzamentos.md).
- [Rede corrigida e medições](docs/rede_corrigida_e_medicoes.md).
- [Métricas coletadas](docs/catalogo_metricas.md).
- [Catálogo completo SUMO](docs/catalogo_completo_sumo.md).

Os guias treinamento.md, parametros_simulacao.md e referencia_parametros.md documentam também a busca anterior de tempos fixos. O registro incremental da equipe fica em ../RELATORIO_INCREMENTAL.md.

## Manutenção e verificações

```powershell
.\.venv\Scripts\python.exe scripts/exportar_catalogos.py
.\.venv\Scripts\python.exe scripts/verificar_interface_catalogos.py
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

O catálogo é gerado pelo executável SUMO instalado; pipeline.py options consulta a ajuda atual. Os snapshots duplicados de ajuda/template foram removidos. Dados e resultados científicos existentes foram preservados.
