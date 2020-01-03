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

To add a new known locale, add a key/value to the ``KNOWN_LOCALES`` mapping in
`warehouse/i18n/__init__.py
<https://github.com/pypa/warehouse/blob/master/warehouse/i18n/__init__.py>`_.
The key is the locale code, and corresponds to a directory in
``warehouse/locale``, and the value is the human-readable name for the locale,
in the given language.

Then, compile the MO file for the locale by running ``make build-mos``. This
may recompile some existing MO files as well, but should add a new MO file for
the new locale.

Finally, commit these changes and add them to Weblate's pull request (if you
are able) or make a new pull request which adds them.
