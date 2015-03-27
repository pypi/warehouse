default:
	@echo "Must call a specific subcommand"
	@exit 1

.tox/translations:
	tox -e translations --notest

clean:
	rm -rf .tox/translations

extract-translations: .tox/translations
	.tox/translations/bin/pybabel extract -F babel.cfg --sort-output \
		--project Warehouse --version $(shell python setup.py --version) \
		--copyright-holder "Individual contributors" \
		--msgid-bugs-address "distutils-sig@python.org" \
		-o warehouse/translations/warehouse.pot \
		warehouse/
	.tox/translations/bin/pybabel update --ignore-obsolete \
		-D warehouse \
		-i warehouse/translations/warehouse.pot -d warehouse/translations

init-translations: .tox/translations
	.tox/translations/bin/pybabel init \
		-l $(L) -D warehouse \
		-i warehouse/translations/warehouse.pot -d warehouse/translations

compile-translations: .tox/translations
	.tox/translations/bin/pybabel compile -f -D warehouse -d warehouse/translations

.PHONY: clean extract-translations init-translations compile-translations
