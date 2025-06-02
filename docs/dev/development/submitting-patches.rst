Submitting patches
==================

Before you submit a patch, you may want to look at :doc:`our guide to the
Warehouse codebase <../application>`.

As you work on your patch, keep this in mind:

* Always make a new branch for your work.
* Patches should be small to facilitate easier review. `Studies have shown`_
  that review quality falls off as patch size grows. Sometimes this will result
  in many small PRs to land a single large feature.
* You must have legal permission to distribute any code you contribute to
  Warehouse, and it must be available under the Apache Software License Version
  2.0.

If you believe you've identified a security issue in Warehouse, follow the
directions on the :doc:`security page </security/index>`.

Code
----

When in doubt, refer to `the Black Code Style`_ for Python code formatting. You
can reformat your code according to this code style by running ``make reformat``
against it. You can check if your code meets all our automated requirements by
running ``make lint`` against it.

`Write comments as complete sentences.`_

Class names which contains acronyms or initialisms should always be
capitalized. A class should be named ``HTTPClient``, not ``HttpClient``.

Every code file must start with the boilerplate licensing notice:

.. code-block:: python

    # SPDX-License-Identifier: Apache-2.0

You can view :doc:`patterns` to see more patterns that should be used within
Warehouse.


Tests
-----

All code changes must be accompanied by unit tests with 100% code coverage (as
measured by `coverage.py`_).


Documentation
-------------

Important information should be documented with prose in the ``docs`` section.
To ensure it builds and passes documentation style checks you can run
``make dev-docs user-docs`` and ``make lint`` respectively.


Translations
------------

When making changes to files with strings marked for translation, it's
necessary to update references to these files any time source strings are change, or the
line numbers of the source strings in the source files. This can be done by running ``make translations``.

For instructions on how to mark strings and views for translation,
see the :doc:`../translations` docs.


Keeping your local branch updated
---------------------------------

As you work, you will need to keep your local ``main`` branch up-to-date with
the ``main`` branch in the main Warehouse repository, which moves forward as
the maintainers merge pull requests. Most people working on the project use
the following workflow.

This assumes that you have Git configured so that when you run the following
command:

.. code-block:: console

  git remote -v

Your output looks like this:

.. code-block:: console

  origin  https://github.com/username/warehouse.git (fetch)
  origin  https://github.com/username/warehouse.git (push)
  upstream  https://github.com/pypi/warehouse.git (fetch)
  upstream  https://github.com/pypi/warehouse.git (push)


In the example above, ``<username>`` is your username on GitHub.

First, fetch the latest changes from the main Warehouse repository,
``upstream``:

.. code-block:: console

  git fetch upstream

Then, check out your local ``main`` branch, and rebase the changes on top of
it:

.. code-block:: console

  git checkout main
  git rebase upstream/main

Next, push the updates you have just made to your local ``main`` branch to
your ``origin`` repository on GitHub:

.. code-block:: console

  git checkout main
  git push origin main

Now your local ``main`` branch and the ``main`` branch in your ``origin``
repo have been updated with the most recent changes from the main Warehouse
repository.

To keep your feature branches updated, the process is similar:

.. code-block:: console

   git checkout awesome-feature
   git fetch upstream
   git rebase upstream/main

Now your feature branch has been updated with the latest changes from the
``main`` branch on the upstream Warehouse repository.

It's good practice to back up your feature branches by pushing them to your
``origin`` on GitHub as you are working on them. To push a feature branch,
run this command:

.. code-block:: console

    git push origin awesome-feature

In this example, ``<awesome-feature>`` is the name of your feature branch. This
will push the feature branch you are working on to GitHub, but will not
create a PR.

Once you have pushed your feature branch to your ``origin``, if you need to
update it again, you will have to force push your changes by running the
following command:

.. code-block:: console

    git push -f origin awesome-feature

The ``-f`` (or ``--force``) flag after ``push`` forces updates from your local
branch to update your ``origin`` feature branch. If you have a PR open on your
feature branch, force pushing will update your PR. (This is a useful command
when someone requests changes on a PR.)

If you get an error message like this:

.. code-block:: console

    ! [rejected]        awesome-feature -> awesome-feature (non-fast-forward)
    error: failed to push some refs to 'https://github.com/USERNAME/warehouse.git'
    hint: Updates were rejected because the tip of your current branch is behind
    hint: its remote counterpart. Integrate the remote changes (e.g.
    hint: 'git pull ...') before pushing again.
    hint: See the 'Note about fast-forwards' in 'git push --help' for details.

Try force-pushing your feature branch with ``push -f``.

The ``main`` branch in the main Warehouse repository gets updated frequently
as dependency upgrades are merged, so you will probably have to update your
feature branch at least once while you are working on it.


.. _`Write comments as complete sentences.`: https://nedbatchelder.com/blog/201401/comments_should_be_sentences.html
.. _`syntax`: https://sphinx-doc.org/domains.html#info-field-lists
.. _`Studies have shown`: https://static1.smartbear.co/support/media/resources/cc/book/code-review-cisco-case-study.pdf
.. _`coverage.py`: https://pypi.org/project/coverage
.. _`the Black Code Style`: https://github.com/psf/black#the-black-code-style
