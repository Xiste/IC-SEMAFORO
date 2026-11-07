# Interface operacional. Opções e manutenção: docs/GUIA_DE_FUNCIONAMENTO.md.
PYTHON ?= python3
export PYTHONDONTWRITEBYTECODE := 1
DEMAND_ARGS ?=
RUN_ARGS ?=

.PHONY: demand-random run-random web interface kill-interface test

# Prepara viagens/rotas avulsas, sem iniciar SUMO.
demand-random:
	@$(PYTHON) -m SistemaDeSemaforos.demand.random_demand_generator $(DEMAND_ARGS)

# Gera demanda, simula e grava resultados; RUN_ARGS aceita --episodes e --metrics-profile.
run-random:
	@$(PYTHON) -m SistemaDeSemaforos.simulation.episode_runner $(RUN_ARGS)

# Interface local no navegador, com execução em segundo plano.
web interface:
	@$(PYTHON) -m SistemaDeSemaforos.simulation.web_interface

# Encerra todas as interfaces iniciadas pelo módulo, mesmo fora desta pasta.
kill-interface:
	@pids="$$(ps -eo pid=,args= | awk '$$0 ~ /(^|[[:space:]])-m[[:space:]]+SistemaDeSemaforos\.simulation\.web_interface([[:space:]]|$$)/ {print $$1}')"; \
	if [ -n "$$pids" ]; then kill -INT $$pids; else echo "Nenhuma interface em execução."; fi

# Testes automatizados sem iniciar episódios SUMO.
test:
	$(PYTHON) -m unittest discover -s tests/demand -v
	$(PYTHON) -m unittest discover -s tests/simulation -v
	$(PYTHON) -m unittest discover -s tests/metrics -v
