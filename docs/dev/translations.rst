Translations
============

We use `Weblate <https://weblate.org/>`_ to manage PyPI translations across several languages. Visit the
`Warehouse project on Weblate <https://hosted.weblate.org/projects/pypa/warehouse/>`_
to contribute.

If you are experiencing issues as a translator, please let us know by opening a
`translation issue on the Warehouse issue tracker <https://github.com/pypi/warehouse/issues/new?template=translation-issue.md>`_.

Adding a newly completed translation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Weblate will automatically add commits to a pull request as translations are
updated.

When a translation reaches 100%, it should be added as a known locale and have
it's MO file (Machine Object file) compiled.

To add a new known locale:

1. Check for `outstanding Weblate pull requests
   <https://github.com/pypi/warehouse/pulls/weblate>`_ and merge them if so.
2. In a new branch for |pypi/warehouse|_, add the new language identifier to
   ``KNOWN_LOCALES`` in |warehouse/i18n/__init__.py|_ and |webpack.plugin.localize.js|_.
   The value is the locale code, and corresponds to a directory in
   ``warehouse/locale``.
3. Commit these changes and make a new pull request to |pypi/warehouse|_.
4. In a new branch for |pypi/infra|_, add the new identifier to the
   ``accept.language_lookup`` call in `PyPI's VCL configuration
   <https://github.com/pypi/infra/blob/main/terraform/warehouse/vcl/main.vcl>`_.
   The value is the `IANA language subtag
   <https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry>`_
   string for the locale.

   .. note::

      This value may differ from the identifier used for ``KNOWN_LOCALES``,
      e.g. ``pt-BR`` vs ``pt_BR``.

5. Commit these change and make a new pull request to |pypi/infra|_ referencing
   your pull request to |pypi/warehouse|_.

.. |pypi/warehouse| replace:: ``pypi/warehouse``
.. _pypi/warehouse: https://github.com/pypi/warehouse
.. |warehouse/i18n/__init__.py| replace:: ``warehouse/i18n/__init__.py``
.. _warehouse/i18n/__init__.py: https://github.com/pypi/warehouse/blob/main/warehouse/i18n/__init__.py
.. |webpack.plugin.localize.js| replace:: ``webpack.plugin.localize.js``
.. _webpack.plugin.localize.js: https://github.com/pypi/warehouse/blob/main/webpack.plugin.localize.js
.. |pypi/infra| replace:: ``pypi/infra``
.. _pypi/infra: https://github.com/pypi/infra

Marking new strings for translation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In an HTML template, use the :code:`{% trans %}` and :code:`{% endtrans %}`
tags to mark a string for translation.

In Python, given a request context, call :code:`request._(message)` to mark
:code:`message` for translation. Without a request context, you can do the following:

.. code-block:: python

   from warehouse.i18n import localize as _
   message = _("Your message here.")

In javascript, use :code:`gettext("singular", ...placeholder_values)` and
:code:`ngettext("singular", "plural", count, ...placeholder_values)`.
The function names are important because they need to be recognised by pybabel.

.. code-block:: javascript

   import { gettext, ngettext } from "../utils/messages-access";
   gettext("Get some fruit");
   // -> (en) "Get some fruit"
   ngettext("Yesterday", "In the past", numDays);
   // -> (en) numDays is 1: "Yesterday"; numDays is 3: "In the past"


Passing non-translatable values to translated strings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In html, to pass values you don't want to be translated into
translated strings, define them inside the :code:`{% trans %}` tag.
For example, to pass a non-translatable link
:code:`request.route_path('classifiers')` into a string, instead of
placing it directly in the string like so:

.. code-block:: html

      {% trans %}
      Filter by <a href="request.route_path('classifiers')">classifier</a>
      {% endtrans %}

Instead, define it inside the :code:`{% trans %}` tag:

.. code-block:: html

      {% trans href=request.route_path('classifiers') %}
      Filter by <a href="{{ href }}">classifier</a>
      {% endtrans %}

In javascript, use :code:`%1`, :code:`%2`, etc as
placeholders and provide the placeholder values:

.. code-block:: javascript

   import { ngettext } from "../utils/messages-access";
   ngettext("Yesterday", "About %1 days ago", numDays, numDays);
   // -> (en) numDays is 1: "Yesterday"; numDays is 3: "About 3 days ago"


Marking new strings for pluralization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To pluralize a translated string in an HTML template,
use the :code:`{% pluralize %}` tag to separate the singular and plural
variants of a string, for example:

.. code-block:: html
      :emphasize-lines: 3

      {% trans n_hours=n_hours %}
      This link will expire in {{ n_hours }} hour.
      {% pluralize %}
      This link will expire in {{ n_hours }} hours.
      {% endtrans %}

This is not yet directly possible in Python for Warehouse.

In javascript, use :code:`ngettext()` as described above.

Marking views as translatable
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If a view's renderer uses translations, you should mark the view as
translatable by setting the :code:`has_translations` option in
the view's configuration:

.. code-block:: python
   :emphasize-lines: 4

   @viewconfig(
      route_name="sample.route",
      renderer="translatable_sample.html",
      has_translations=True,
   )
   class SampleViews:


You may have to :ref:`rebuild the translation files <building-translations>`.
