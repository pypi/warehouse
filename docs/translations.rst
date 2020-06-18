Translations
============

We use `Weblate <https://weblate.org/>`_ to manage PyPI translations. Visit the
`Warehouse project on Weblate <https://hosted.weblate.org/projects/pypa/warehouse/>`_
to contribute.

If you are experiencing issues as a translator, please let us know by opening a
`translation issue on the Warehouse issue tracker <https://github.com/pypa/warehouse/issues/new?template=translation-issue.md>`_.

Adding a newly completed translation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Weblate will automatically add commits to a pull request as translations are
updated.

When a translation reaches 100%, it should be added as a known locale and have
it's MO file (Machine Object file) compiled.

To add a new known locale:

1. Check for `outstanding Weblate pull requests
   <https://github.com/pypa/warehouse/pulls/weblate>`_ and merge them if so.
2. In a new branch, add a key/value to the ``KNOWN_LOCALES`` mapping in
   |warehouse/i18n/__init__.py|_.
   The key is the locale code, and corresponds to a directory in
   ``warehouse/locale``.
3. Compile the MO file for the locale by running ``make build-mos``. This may
   recompile some existing MO files as well, but should add a new MO file for
   the new locale.
4. Commit these changes (including all ``*.mo`` files) and  make a new pull
   request which adds them.

.. |warehouse/i18n/__init__.py| replace:: ``warehouse/i18n/__init__.py``
.. _warehouse/i18n/__init__.py: https://github.com/pypa/warehouse/blob/master/warehouse/i18n/__init__.py
