Translations
============

Warehouse has been written to enable translation of the UI elements into
languages other than English. It uses a few small utilities to make this all
work however the interface should be familiar for anyone whose ever worked
with translations.


Marking Strings for Translation
-------------------------------

In Python
~~~~~~~~~

Inside of Python code, you can easily translate using either the ``gettext`` or
the ``ngettext`` functions from ``warehouse.i18n``. These functions will return
a ``TranslationString`` instance. This does not act like a normal string,
you cannot combine it with other translated or untranslated content except
through the string formatting via ``%`` interface. This is because you cannot
build up a string iteratively by combining multiple separately translated
strings. Unlike normal strings, you can use the ``%`` multiple times and it
will combine all of the given results until it is finally rendered. Another
difference is the only type of formatting allowed is the named parameter style
(``"%(foo)s"``) and not the positional style(``"%s"``).

It is important to note that the actual translation of a ``TranslationString``
is delayed until ``TranslationString().translate(translation)`` on it passing
in the value of ``request.translation``. If a ``TranslationString`` is being
used inside of a template this can be ignored as the template system will
automatically handle this for you. This means that, unlike many other
translation systems, there is no distinction between lazy and eager strings.

Example:

.. code:: python

    # It is customary to name the gettext function _
    from warehouse.i18n import gettext as _

    MESSAGE = _("This is Translated Message.")

    @view_config(route_name="myroute", renderer="mytemplate.html")
    def my_view(request):
        return {
            "msg": MESSAGE,
            "other": _("This is another translated message"),
        }


In Templates
~~~~~~~~~~~~

Inside of Jinja2 templates the standard
`Jinja2 i18n extension <http://jinja.pocoo.org/docs/dev/extensions/#newstyle-gettext>`_
has been configured with ``newstyle=True``.

You can use it like so:

.. code:: python

    <div>
        {{ _('some string %(var)s', var='foo') }}
    </div>


Working with Translation Files
------------------------------

Extracting New Strings
~~~~~~~~~~~~~~~~~~~~~~

New strings can be extracted from all sources by executing
``make extract-translations`` and committing the resulting updates to the
``.pot`` and ``.po`` files.


Translating Strings
~~~~~~~~~~~~~~~~~~~

TODO: Figure out how this works exactly.


Compiling Translations
~~~~~~~~~~~~~~~~~~~~~~

The ``.po`` files inside of ``warehouse/locale`` can be translated to ``.mo``
files by executing ``make compile-translations``.
