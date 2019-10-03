Translations
============

We use `Weblate <https://weblate.org/>`_ to manage PyPI translations. Visit the
`Warehouse project on Weblate <https://hosted.weblate.org/projects/pypa/warehouse/>`_
to contribute.

If you are experiencing issues as a translator, please let us know by opening a
`translation issue on the Warehouse issue tracker <https://github.com/pypa/warehouse/issues/new?template=translation-issue.md>`_.

To add a new translation:

- Merge the pull request from Weblate
- Add the locale in ``warehouse/i18n/__init__.py`` -- Babel's default
  locale format is ``cc_lc`` where ``cc`` is the country code, in lower
  case, and ``lc`` is the language code, in upper case
- Check ``warehouse/templates/base.html`` for ``{% if
  KNOWN_LOCALES|length > 1 %}`` and, if present, remove
