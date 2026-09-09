.PHONY: test demo
test:
	coverage run -m pytest && coverage report --fail-under=80

demo:
	docker compose -f demo/docker-compose.demo.yml up --build -d
	@sleep 8
	python demo/inject.py http://localhost:8000 http://localhost:9090
	@echo "Open http://localhost:8000  (make demo-down to stop)"

demo-down:
	docker compose -f demo/docker-compose.demo.yml down -v
