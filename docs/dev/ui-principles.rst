UI principles
=============

The Warehouse UI aims to be clean, clear and easy to use. Changes and
additions to the UI should follow these four principles:

1. Be consistent
----------------

Creating **consistent** interfaces is more aesthetically pleasing, improves
usability and helps new users master the UI faster.

Before creating a new design, layout or CSS style, always consider reusing
an existing pattern. This may include modifying an existing design or
layout to make it more generic.

Following this principle can also help to reduce the footprint of our frontend
code, which will make Warehouse easier to maintain in the long term.

2. Consider usability and accessibility
---------------------------------------

Ensuring Warehouse follows usability and accessibility best practices will make
the site easier to use for everybody.

Warehouse follows the `WCAG 2.0 AA standard <https://www.w3.org/TR/WCAG20/>`_.
When working on the UI:

- Ensure contrast is high, particularly on text. This can be checked:
   - On Chrome by using `DevTools Accessibility features
     <https://developer.chrome.com/docs/devtools/accessibility/contrast>`_
   - On Firefox by installing the `WCAG Contrast Checker
     <https://addons.mozilla.org/en-US/firefox/addon/wcag-contrast-checker/>`_
- Write `semantic HTML <https://en.wikipedia.org/wiki/Semantic_HTML>`_
- Ensure image `alt tags are present and meaningful
  <https://webaim.org/techniques/alttext/>`_
- Add labels to all form fields (if you want to hide a label visually but leave
  it readable to screen readers, apply ``.sr-only``)
- Where possible add `ARIA roles
  <https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA>`_ to
  the HTML
- Indicate the state of individual UI components with CSS styles.
  For example, darken a button on hover.
- Ensure that keyboard users can easily navigate each page. It is particularly
  important that the ``outline`` is not removed from links.
- Consider color blind users: if using color to convey meaning (e.g. red for an
  error) always use an additional indicator (e.g. an appropriate icon) to
  convey the same meaning.


3. Provide help
---------------

Never assume that all Warehouse users are as familiar with the Python
ecosystem as you are. Something that may seem obvious or second-nature to you
may be a difficult or novel concept for someone else.

Seek out places in the interface where help text should be included - either
as standard text on the page, or by adding a help icon (that links to
help content).


4. Write clearly, with consistent style and terminology
-------------------------------------------------------

Warehouse follows the `Material design writing style guide
<https://web.archive.org/web/20180410101124/https://material.io/guidelines/style/writing.html>`_.

When writing interfaces use direct, clear and simple language. This is
especially important as Warehouse caters to an international audience with
varying proficiency in English. If you're unsure, `check the readability of
your text <https://www.webfx.com/tools/read-able/>`_.
For consistency, we prefer using American English spellings over British
English.

Do not use directional prompts when writing user interface copy. For example
"Click the button on the left" should be avoided.

Be consistent, particularly when it comes to domain specific words. Use this
glossary as a guide:

=============== ===============================================================
 Term           Definition
=============== ===============================================================
 Project        A collection of releases and files, and information about them.
                Projects on Warehouse are made and shared by members of the
                Python community so others can use them.
 Release        A specific version of a project. For example, the requests
                project has many releases, like requests 2.10 and
                requests 1.2.1. A release consists of one or more files.
 File           Something that you can download and install. Because of
                different hardware, operating systems, and file formats,
                a release may have several files, like an archive
                containing source code or a binary wheel.
 Package        A synonym for a file.
 User           A person who has registered an account on Warehouse.
 Maintainer     A user who has permissions to manage a project on Warehouse.
 Owner          A user who has permissions to manage a project on Warehouse,
                **and** has additional permission to add and remove other
                maintainers and owners to a project.
 Author         A free-form piece of information associated with a project.
                This information could be a name of a person, an organization,
                or something else altogether. This information is not linked
                to a user on Warehouse.
=============== ===============================================================
