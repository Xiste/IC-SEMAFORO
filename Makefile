# Comandos principais. Use DEMAND_ARGS e RUN_ARGS para opções adicionais.
# Documentação: docs/DEMANDA.md e docs/COMANDOS_TESTE.md.
PYTHON ?= python3
DEMAND_ARGS ?=
RUN_ARGS ?=

.PHONY: demand-random run-random test

# Gera random.trips.xml e random.rou.xml. Não inicia a simulação.
demand-random:
	$(PYTHON) -m SistemaDeSemaforos.demand.generator $(DEMAND_ARGS)

# Gera uma demanda nova e executa o SUMO em cada episódio.
run-random:
	$(PYTHON) -m SistemaDeSemaforos.simulation.runner $(RUN_ARGS)

# Executa os testes automatizados sem abrir o SUMO.
test:
	$(PYTHON) -m unittest discover -s tests/demand -v
	$(PYTHON) -m unittest discover -s tests/simulation -v
