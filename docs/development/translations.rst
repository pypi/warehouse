Translations
============

Warehouse has been written to enable translation of the UI elements into
languages other than English.


Marking Strings for Translation
-------------------------------

Warehouse uses `L20n <http://l20n.org/>`_ to handle the translation of content.
In order to mark a bit of HTML translatable you simple need to add a
``data-l10n-id`` attribute to the HTML element to mark it with an ID that will
be used to look up the translation. You may pass args into the translation
string by pass a JSON string via a ``data-l10n-args`` attribute.

In the Jinja2 templates there is a helper that allows easy marking of sections
for translation by simply soing something like:

.. code:: jinja

    <p {{ l20n("basicGreeting", name=user.username) }}>Hello {{ user.username }}</p>


This HTML templates should contain the English translation (using the US
spellings as Python itself does). Translators will then be able to translate
this using something like:

.. code:: html

    <basicGreeting "Hola {{ $name }}">

The L20n does not require any explicit extraction step.
