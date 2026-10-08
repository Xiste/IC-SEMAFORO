# Arquitetura do projeto

## Responsabilidades

| Camada | Local | Responsabilidade |
| --- | --- | --- |
| Cenário | semaforos/cenario | Ler e validar configuração, rede, demanda, medições e mapeamento. |
| Simulação | semaforos/simulacao | Executar SUMO/TraCI e expor observações, ações, recompensa e métricas via Gymnasium. |
| Algoritmos | semaforos/algoritmos | Construir/carregar o algoritmo escolhido, heurísticas e busca de tempos fixos. |
| Experimentos | semaforos/experimentos | Treinar, salvar, cancelar, avaliar nas mesmas condições e registrar proveniência. |
| Relatórios | semaforos/relatorios | Agregar métricas, emitir arquivos/gráficos e fornecer legendas/catálogos. |
| Apresentação | semaforos/apresentacao | Editar cenário, iniciar processos e exibir/exportar resultados. |

```mermaid
flowchart TD
    UI[Interface / CLI] --> EX[Experimentos]
    UI --> C[Cenário]
    EX --> A[Registro de algoritmos]
    EX --> E[Ambiente Gymnasium]
    E --> C
    E --> S[SUMO / TraCI]
    EX --> R[Métricas e relatórios]
    UI --> R
```

PPO conhece o ambiente pela interface Gymnasium. experimentos/rl.py compartilha treino, salvamento, cancelamento e avaliação. algoritmos/heuristicas.py mantém a referência de filas fora do PPO. Configurações do construtor são definidas uma única vez em algoritmos/ppo.py e usadas pelo treino e catálogo.

caminhos.PROJECT_ROOT evita que mudanças de pasta alterem a localização de dados e configurações. pipeline.py e interface.py são entradas pequenas e preservam os comandos usados pelo usuário. Os caminhos de importação internos foram migrados; scripts externos que importavam módulos antigos precisam usar os novos caminhos.

## Acrescentar outro algoritmo de aprendizado

O adaptador Algorithm é para modelos compatíveis com o ciclo Stable-Baselines3: construtor com env, learn(total_timesteps, callback), predict(observation, deterministic), save, load, num_timesteps e device. O ambiente atual usa observações Box e ações **MultiDiscrete**. Um algoritmo com espaço de ações diferente exige um adaptador do ambiente e testes adicionais.

Exemplo de um novo adaptador A2C, para implementação futura:

```python
# semaforos/algoritmos/a2c.py
from stable_baselines3 import A2C
from .registro import Algorithm

def constructor_parameters(config):
    params = config.get("a2c", {})
    return dict(policy="MlpPolicy", n_steps=int(params.get("n_steps", 128)),
                seed=config["seeds"][0], verbose=0)

A2C_ALGORITHM = Algorithm("A2C", A2C, "a2c", constructor_parameters)
```

Na função _ensure_builtins de registro.py, importar e registrar uma vez o adaptador, de modo semelhante ao PPO. O registro explícito impede carregar código arbitrário a partir do JSON. Selecionar algorithm: "A2C" no cenário e criar a2c: {"n_steps": 128, "total_timesteps": 2048}. Na interface, o seletor mostra os algoritmos registrados; parâmetros específicos são informados no campo JSON. Criar também as legendas correspondentes para campos novos.

```python
# Acrescentar dentro de _ensure_builtins, após o registro PPO:
if "A2C" not in _ALGORITHMS:
    from .a2c import A2C_ALGORITHM
    register_algorithm(A2C_ALGORITHM)
```

```powershell
.\.venv\Scripts\python.exe pipeline.py algorithms
.\.venv\Scripts\python.exe pipeline.py rl-train --algorithm A2C --config config/meu_cenario.json
.\.venv\Scripts\python.exe pipeline.py rl-eval --algorithm A2C --model resultados/PASTA/a2c_model.zip
```

Esses comandos A2C passam a funcionar **após implementar e registrar** o adaptador. Só PPO é publicado nesta revisão. O teste de integração registra A2C temporariamente e executa o mesmo fluxo para comprovar a extensão, sem disponibilizá-lo como produto.

Os controles comuns podem ficar em control: intervalo de decisão, modo, tipos de fase, limites, opções por fase e GUI. Arquivos existentes que mantêm esses campos em ppo continuam aceitos. Os hiperparâmetros do otimizador ficam na chave de seu adaptador. Manifestos PPO antigos e ppo_model.zip continuam aceitos quando rede, mapeamento e espaço de ações são compatíveis.

## Outros métodos de otimização

Algoritmos que procuram tempos fixos, como busca aleatória ou métodos evolutivos, usam simulacao/execucao.py::simulate com um candidato por ID:índice. A implementação existente fica em algoritmos/busca_surrogate.py; recebe cenário e diretório de resultados. Esses métodos têm outro ciclo de otimização e precisam de integração própria ao CLI/UI; o registro de modelos RL não os transforma automaticamente em agentes Gymnasium.

O reaproveitamento é de rede, demanda, coleta e avaliação SUMO. Métodos que mudam observações, ações, sequência de fases ou recompensa precisam testar esses contratos e treinar novos modelos.

## Limpeza realizada

### Revisão de organização em 07/10/2026

A divisão atual em seis camadas atende ao pipeline. Não é necessário mover módulos ou alterar imports nesta revisão. `apresentacao/app.py` concentra os formulários e a composição do painel; é o principal candidato a divisão por telas caso a interface cresça. Essa divisão deve preservar as chaves dos widgets e a recuperação das tarefas.

| Recurso | Módulos responsáveis |
| --- | --- |
| Preparar grupos compatíveis e conferir conflitos | `cenario/preparacao.py`, `cenario/grupos.py`, `cenario/experimental.py` |
| Importar contagens/OD e calibrar demanda | `cenario/importacao.py`, `cenario/calibracao.py`, `cenario/demanda.py` |
| Gerar e observar pedestres | `cenario/pedestres.py`, `simulacao/pedestres.py` |
| Medir cruzamentos, contagens e acompanhamento ao vivo | `simulacao/observacao.py`, `simulacao/contagens.py` |
| Executar referência sem treino | `experimentos/referencia.py` |
| Persistir tarefas, reconhecer processos e cancelar | `experimentos/tarefas.py` |
| Exportar episódios completos e parciais | `relatorios/episodios.py` |
| Escrever arquivos compartilhados de forma atômica | `arquivos.py` |

#### Critérios para manter ou apagar arquivos

- `config/` e `dados/`: entradas e evidências. O mapeamento dos planos reais e o mapeamento experimental têm finalidades distintas; ambos são úteis.
- `scripts/`: manutenção, auditoria, benchmark e verificações da interface/GUI. Não fazem parte da inicialização diária, mas continuam necessários para reproduzir verificações.
- `tests/`: contratos de comportamento e regressões. Nomes relacionados a pendências registram o contexto dos testes e não indicam que estejam obsoletos.
- `docs/catalogos/`: exportações para consulta, inclusive fora da interface; são regeneráveis pelo exportador atual.
- `resultados/`: execuções locais. Modelos podem depender das redes e configurações geradas nessa pasta. Antes de apagar um cenário, conferir os manifestos dos modelos que o utilizam.
- `.venv/` e `.venv-verificacao/`: ambientes locais. O inicializador utiliza o ambiente isolado; eles não devem entrar no Git.
- `__pycache__/`: cache regenerável, pode ser removido com os processos encerrados.

Nesta revisão foram identificados para exclusão o script pontual `resultados/extra_ir_snapshot.py`, a resolução temporária do pip `resultados/instalacao_resolvida.json` e o arquivo vazio `resultados/eval_research_console.json`, além dos caches de código do projeto. Não são entradas do pipeline nem resultados científicos. A política automática de execução bloqueou o comando de exclusão; esses arquivos e caches permanecem no disco.

Removidos arquivos duplicados/obsoletos: ajuda estática opcoes_sumo_1.27.1.txt, template estático modelo_todas_opcoes.sumocfg, gerador antigo gerar_catalogo_sumo.py e script pontual verificar_relatorios_catalogos.py, que dependia de um experimento datado e reescrevia resultados históricos. O exportador atual gera CSV e Markdown diretamente da instalação. A migração temporária também foi removida.

Os antigos módulos planos foram movidos para as camadas; não há cópias duplicadas. A busca antiga permanece disponível porque tem implementação e comando ativos. Redes, fontes, medições, evidências, modelos e resultados anteriores são preservados. A limpeza de caches é limitada ao código do projeto, sem alterar .venv ou .git.
