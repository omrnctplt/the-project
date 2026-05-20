# Inference Hub - DevOps shortcuts
# Kullanim:  make help

SHELL := /usr/bin/env bash
COMPOSE := docker compose
COMPOSE_GPU := docker compose -f docker-compose.yml -f docker-compose.gpu.yml

.PHONY: help preflight up up-gpu down restart logs ps health test test-watch \
        build pull-base reset clean catalog seed sim grafana-open prom-open

help:  ## Bu yardim
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

preflight:  ## Port, daemon, disk kontrolu yap
	@bash scripts/preflight.sh

up: preflight  ## Preflight + tum servisleri ayaga kaldir
	$(COMPOSE) up -d --build gateway ollama prometheus grafana
	@echo ""
	@echo "Servisler ayaga kalkti. URL'ler:"
	@echo "  Gateway UI    -> http://localhost:8080"
	@echo "  API docs      -> http://localhost:8080/docs"
	@echo "  Grafana       -> http://localhost:3000  (admin/admin)"
	@echo "  Prometheus    -> http://localhost:9090"

up-gpu: preflight  ## GPU overlay ile ayaga kaldir
	$(COMPOSE_GPU) up -d --build gateway ollama prometheus grafana

down:  ## Tum servisleri durdur (volume korunur)
	$(COMPOSE) down --remove-orphans

restart: down up  ## Down + up

logs:  ## Tum servislerin canli loglari
	$(COMPOSE) logs -f --tail=80

logs-gw:  ## Sadece gateway loglari
	$(COMPOSE) logs -f --tail=120 gateway

logs-ollama:  ## Sadece ollama loglari
	$(COMPOSE) logs -f --tail=120 ollama

ps:  ## Container durumlari
	$(COMPOSE) ps

health:  ## Tum endpoint saglik kontrolu
	@echo "Gateway healthz : $$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/healthz)"
	@echo "Gateway readyz  : $$(curl -s http://localhost:8080/readyz)"
	@echo "Ollama          : $$(curl -s -o /dev/null -w '%{http_code}' http://localhost:11434/api/tags)"
	@echo "Prometheus      : $$(curl -s -o /dev/null -w '%{http_code}' http://localhost:9090/-/healthy)"
	@echo "Grafana         : $$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/api/health)"

test:  ## Birim testleri (host venv)
	.venv/Scripts/python -m pytest -q tests/ || python -m pytest -q tests/

test-watch:  ## Test'leri her dosya degisikliginde tekrar calistir
	while inotifywait -r -e modify app/ tests/ 2>/dev/null; do $(MAKE) test; done

build:  ## Sadece gateway image'ini yeniden build et (cache kullanir)
	$(COMPOSE) build gateway

pull-base:  ## Base image'leri onceden cek (python, ollama)
	docker pull python:3.12-slim
	docker pull ollama/ollama:latest
	docker pull prom/prometheus:v2.55.0
	docker pull grafana/grafana:11.2.0

sim:  ## Yuk simulatorunu calistir (profile=sim)
	$(COMPOSE) --profile sim up --build simulator

reset:  ## Tum container ve volume'leri SIL (data kaybolur)
	$(COMPOSE) down --volumes --remove-orphans
	rm -rf data/

clean:  ## Lokal data'yi temizle (kullanici DB + override)
	rm -rf data/

catalog:  ## Mevcut katalogu yazdir
	@cat config/model_catalog.yaml | head -40

grafana-open:  ## Grafana'yi tarayicida ac
	@command -v xdg-open >/dev/null && xdg-open http://localhost:3000 \
		|| command -v open >/dev/null && open http://localhost:3000 \
		|| start http://localhost:3000

prom-open:  ## Prometheus'u tarayicida ac
	@command -v xdg-open >/dev/null && xdg-open http://localhost:9090 \
		|| command -v open >/dev/null && open http://localhost:9090 \
		|| start http://localhost:9090
