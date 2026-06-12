# Inference Hub - DevOps shortcuts
# Kullanim:  make help

SHELL := /usr/bin/env bash
COMPOSE := docker compose
COMPOSE_GPU := docker compose -f docker-compose.yml -f docker-compose.gpu.yml
COMPOSE_ROCM := docker compose -f docker-compose.yml -f docker-compose.rocm.yml

.PHONY: help preflight up up-gpu up-rocm up-cpu up-tls down restart logs ps health test test-watch \
        build pull-base reset clean catalog seed sim grafana-open prom-open \
        backup restore

help:  ## Bu yardim
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

preflight:  ## Port, daemon, disk kontrolu yap
	@bash scripts/preflight.sh

up: preflight  ## Preflight + GPU otomatik algilama + tum servisleri ayaga kaldir
	docker compose $$(bash scripts/detect_gpu.sh) up -d --build
	@echo ""
	@echo "Servisler ayaga kalkti. URL'ler:"
	@echo "  Gateway UI    -> http://localhost:8888"
	@echo "  API docs      -> http://localhost:8888/docs"
	@echo "  Grafana       -> http://localhost:3000  (admin/admin)"
	@echo "  Prometheus    -> http://localhost:9090"

up-gpu: preflight  ## NVIDIA GPU overlay'ini zorla
	$(COMPOSE_GPU) up -d --build

up-rocm: preflight  ## AMD (ROCm) overlay'ini zorla
	$(COMPOSE_ROCM) up -d --build

up-cpu: preflight  ## GPU olsa bile CPU modunda kur
	$(COMPOSE) up -d --build

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
	@echo "Gateway healthz : $$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8888/healthz)"
	@echo "Gateway readyz  : $$(curl -s http://localhost:8888/readyz)"
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

up-tls: preflight  ## HTTPS (Caddy) overlay ile ayaga kaldir — LAN icin onerilir (GPU otomatik algilanir)
	docker compose $$(bash scripts/detect_gpu.sh) -f docker-compose.tls.yml up -d --build

backup:  ## data/ klasorunu (kullanici DB + audit + config) tarihli arsivle
	@mkdir -p backups
	@tar czf backups/inference-hub-data-$$(date +%Y%m%d-%H%M%S).tgz data/
	@ls -lh backups/ | tail -3

restore:  ## En son yedegi geri yukle (once servisleri durdurur)
	@LATEST=$$(ls -t backups/inference-hub-data-*.tgz 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then echo "backups/ icinde yedek yok"; exit 1; fi; \
	echo "Geri yukleniyor: $$LATEST"; \
	$(COMPOSE) stop gateway; \
	tar xzf "$$LATEST"; \
	$(COMPOSE) start gateway; \
	echo "Tamam — gateway yeniden baslatildi."

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
