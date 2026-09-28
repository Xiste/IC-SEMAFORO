# Comandos principais. Use DEMAND_ARGS e RUN_ARGS para opções adicionais.
# Documentação: docs/GUIA_DE_FUNCIONAMENTO.md e docs/GUIA_DE_EXECUCAO_E_TESTES.md.
PYTHON ?= python3
# Execuções e testes não deixam bytecode/caches Python no projeto.
export PYTHONDONTWRITEBYTECODE := 1
DEMAND_ARGS ?=
RUN_ARGS ?=

.PHONY: demand-random run-random test

# Gera random.trips.xml e random.rou.xml. Não inicia a simulação.
demand-random:
	$(PYTHON) -m SistemaDeSemaforos.demand.random_demand_generator $(DEMAND_ARGS)

# Gera demanda, executa e registra cada episódio em outputs/outputs-random/.
run-random:
	$(PYTHON) -m SistemaDeSemaforos.simulation.episode_runner $(RUN_ARGS)

# Executa os testes automatizados sem abrir o SUMO.
test:
	$(PYTHON) -m unittest discover -s tests/demand -v
	$(PYTHON) -m unittest discover -s tests/simulation -v
	$(PYTHON) -m unittest discover -s tests/metrics -v
