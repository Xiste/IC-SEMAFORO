# Interface operacional. Opções e manutenção: docs/GUIA_DE_FUNCIONAMENTO.md.
PYTHON ?= python3
export PYTHONDONTWRITEBYTECODE := 1
DEMAND_ARGS ?=
RUN_ARGS ?=

.PHONY: demand-random run-random test

# Prepara viagens/rotas avulsas, sem iniciar SUMO.
demand-random:
	@$(PYTHON) -m SistemaDeSemaforos.demand.random_demand_generator $(DEMAND_ARGS)

# Gera demanda, simula e grava resultados; RUN_ARGS aceita --episodes e --metrics-profile.
run-random:
	@$(PYTHON) -m SistemaDeSemaforos.simulation.episode_runner $(RUN_ARGS)

# Testes automatizados sem iniciar episódios SUMO.
test:
	$(PYTHON) -m unittest discover -s tests/demand -v
	$(PYTHON) -m unittest discover -s tests/simulation -v
	$(PYTHON) -m unittest discover -s tests/metrics -v
