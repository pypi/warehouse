default:
	@echo "Must call a specific subcommand"
	@exit 1

update-deps:
	pip-compile requirements.in > requirements.txt

.PHONY: default update-deps
