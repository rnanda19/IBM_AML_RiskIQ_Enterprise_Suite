.PHONY: install lint format test test-all bandit typecheck lock precommit docker-verify clean

install:
	pip install -r requirements.txt
	pip install -e .

lint:
	black --check src/ tests/
	flake8 src/ tests/
	isort --check-only src/ tests/

typecheck:
	mypy src/

format:
	black src/ tests/
	isort src/ tests/

test:
	pytest tests/ -v

test-all: lint typecheck bandit test
	@echo "All quality gates passed."

bandit:
	bandit -r src/ -x tests/,notebooks/,github_repo/

# Regenerates the pinned requirements.txt from requirements.in (the human-authored, abstract
# >= spec) via pip-compile, producing a fully-pinned, reproducible lockfile for CI/Docker installs.
lock:
	pip-compile requirements.in --output-file=requirements.txt

precommit:
	pre-commit run --all-files

# Static check only -- confirms each BP's Dockerfile COPY paths resolve against its declared build
# context without requiring a real `docker build` (this sandbox has no registry access; the user's own
# machine can run a real build). See src/docker/<bp>/Dockerfile header for each BP's build-context note.
docker-verify:
	@for d in src/docker/*/; do \
		echo "--- $$d ---"; \
		test -f "$$d/Dockerfile" && echo "  Dockerfile present" || echo "  MISSING Dockerfile"; \
		test -f "$$d/docker-compose.yml" && echo "  docker-compose.yml present" || echo "  MISSING docker-compose.yml"; \
		test -f "$$d/.dockerignore" && echo "  .dockerignore present" || echo "  MISSING .dockerignore"; \
	done
	@echo "--- COPY-path check (the real check this target's comment describes) ---"
	python3 scripts/check_docker_copy_paths.py

clean:
	find . -type d -name "__pycache__" -not -path "./github_repo/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -not -path "./github_repo/*" -delete 2>/dev/null || true
