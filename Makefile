# Interface operacional. Opções e manutenção: docs/GUIA_DE_FUNCIONAMENTO.md.
ifeq ($(OS),Windows_NT)
PYTHON ?= py -3
else
PYTHON ?= python3
endif
export PYTHONDONTWRITEBYTECODE := 1
DEMAND_ARGS ?=
RUN_ARGS ?=
INTERFACE_ARGS ?=

.PHONY: demand-random run-random web interface kill-interface test

# Prepara viagens/rotas avulsas, sem iniciar SUMO.
demand-random:
	@$(PYTHON) -m SistemaDeSemaforos.demand.random_demand_generator $(DEMAND_ARGS)

# Gera demanda, simula e grava resultados; RUN_ARGS aceita --episodes e --metrics-profile.
run-random:
	@$(PYTHON) -m SistemaDeSemaforos.simulation.episode_runner $(RUN_ARGS)

# Servidor no terminal; o lote SUMO executa em uma thread.
web interface:
	@$(PYTHON) -m SistemaDeSemaforos.simulation.web_interface $(INTERFACE_ARGS)

# Solicita o encerramento somente da interface desta cópia do projeto.
kill-interface:
	@$(PYTHON) -m SistemaDeSemaforos.simulation.web_interface --stop

# Testes automatizados sem iniciar episódios SUMO.
test:
	$(PYTHON) -m unittest discover -s tests/demand -v
	$(PYTHON) -m unittest discover -s tests/simulation -v
	$(PYTHON) -m unittest discover -s tests/metrics -v
