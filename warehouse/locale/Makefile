GITHUB_ACTIONS := $(shell echo "$${GITHUB_ACTIONS:-false}")

compile-pot:
	cd ../../; \
	PYTHONPATH=$(PWD) pybabel extract \
		-F babel.cfg \
		--omit-header \
		--ignore-dirs='.* _* *dist*' 'warehouse/migrations/' \
		--output="warehouse/locale/messages.pot" \
		warehouse

init-po:
	cd ../../; \
	pybabel init \
		--input-file="warehouse/locale/messages.pot" \
		--output-dir="warehouse/locale/" \
		--locale="$(L)"

update-po:
	cd ../../; \
	pybabel update \
		--input-file="warehouse/locale/messages.pot" \
		--output-file="warehouse/locale/$(L)/LC_MESSAGES/messages.po" \
		--locale="$(L)"

compile-po:
	cd ../../; \
	pybabel compile \
		--input-file="warehouse/locale/$(L)/LC_MESSAGES/messages.po" \
		--directory="warehouse/locale/" \
		--locale="$(L)"

build-mos: compile-pot
	cd ../../; \
	$(eval LOCALES := $(shell python -c "from warehouse.i18n import KNOWN_LOCALES; print(' '.join(set(KNOWN_LOCALES)-{'en'}))")) ; \
	for LOCALE in $(LOCALES) ; do \
		L=$$LOCALE $(MAKE) compile-po ; \
		done

translations: compile-pot
ifneq ($(GITHUB_ACTIONS), false)
	cd ../../; \
	cmp -s ./warehouse/locale/messages.pot /opt/warehouse/src/warehouse/locale/messages.pot || (echo "There are outstanding translations, run 'make translations' and commit the changes."; exit 1)
else
endif

.PHONY: compile-pot
