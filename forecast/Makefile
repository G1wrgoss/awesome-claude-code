# Run from the forecast/ directory.
.PHONY: help test verify site check new resolve

help:
	@echo "make new       record a new prediction (prompts, validates, commits)"
	@echo "make resolve   resolve a prediction whose outcome is known"
	@echo "make verify    check every record against git history"
	@echo "make site      rebuild the dashboard into ../docs"
	@echo "make test      run the test suite"
	@echo "make check     test + verify + site, as CI runs it"

new:
	@./bin/new-prediction

resolve:
	@./bin/resolve

verify:
	@./bin/verify

site:
	@./bin/build-site

test:
	@python3 -m pytest tests -q

check: test verify site
