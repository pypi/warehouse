Submitting patches
==================

Before you submit a patch, you may want to look at :doc:`our guide to the
Warehouse codebase <../application>`.

As you are working on your patch, please keep the following in mind:

* Always make a new branch for your work.
* Patches should be small to facilitate easier review. `Studies have shown`_
  that review quality falls off as patch size grows. Sometimes this will result
  in many small PRs to land a single large feature.
* You must have legal permission to distribute any code you contribute to
  Warehouse, and it must be available under the Apache Software License Version
  2.0.

If you believe you've identified a security issue in Warehouse, please
follow the directions on the :doc:`security page </security>`.

Code
----

When in doubt, refer to :pep:`8` for Python code. You can check if your code
meets our automated requirements by running ``make lint`` against it.

`Write comments as complete sentences.`_

Class names which contains acronyms or initialisms should always be
capitalized. A class should be named ``HTTPClient``, not ``HttpClient``.

Every code file must start with the boilerplate licensing notice:

.. code-block:: python

    # Licensed under the Apache License, Version 2.0 (the "License");
    # you may not use this file except in compliance with the License.
    # You may obtain a copy of the License at
    #
    # http://www.apache.org/licenses/LICENSE-2.0
    #
    # Unless required by applicable law or agreed to in writing, software
    # distributed under the License is distributed on an "AS IS" BASIS,
    # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    # See the License for the specific language governing permissions and
    # limitations under the License.

You can view :doc:`patterns` to see more patterns that should be used within
Warehouse.


Tests
-----

All code changes must be accompanied by unit tests with 100% code coverage (as
measured by `coverage.py`_).


Documentation
-------------

Important information should be documented with prose in the ``docs`` section.
To ensure it builds and passes `doc8`_ style checks you can run
``make docs`` and ``make lint`` respectively.

Keeping your local branch updated
---------------------------------

As you work, you will need to keep your local ``master`` branch up-to-date with
the ``master`` branch in the main Warehouse repository, which moves forward as
the maintainers merge pull requests. Most people working on the project use
the following workflow.

The following documentation assumes that you have git configured so that when
you run the following command:

.. code-block:: console

  git remote -v

Your output looks like this:

.. code-block:: console

  origin  https://github.com/username/warehouse.git (fetch)
  origin  https://github.com/username/warehouse.git (push)
  upstream  https://github.com/pypa/warehouse.git (fetch)
  upstream  https://github.com/pypa/warehouse.git (push)


In the example above, ``<username>`` is your username on GitHub.

First, fetch the latest changes from the main Warehouse repository,
``upstream``:

.. code-block:: console

  git fetch upstream

Then, check out your local ``master`` branch, and rebase the changes on top of
it:

.. code-block:: console

  git checkout master
  git rebase upstream/master

Next, push the updates you have just made to your local ``master`` branch to
your ``origin`` repository on GitHub:

.. code-block:: console

  git checkout master
  git push origin master

Now your local ``master`` branch and the ``master`` branch in your ``origin``
repo have been updated with the most recent changes from the main Warehouse
repository.

To keep your feature branches updated, the process is similar:

.. code-block:: console

   git checkout awesome-feature
   git fetch upstream
   git rebase upstream/master

Now your feature branch has been updated with the latest changes from the
``master`` branch on the upstream Warehouse repository.

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

The ``master`` branch in the main Warehouse repository gets updated frequently
as dependency upgrades are merged, so you will probably have to update your
feature branch at least once while you are working on it.


.. _`Write comments as complete sentences.`: http://nedbatchelder.com/blog/201401/comments_should_be_sentences.html
.. _`syntax`: http://sphinx-doc.org/domains.html#info-field-lists
.. _`Studies have shown`: https://smartbear.com/smartbear/media/pdfs/wp-cc-11-best-practices-of-peer-code-review.pdf
.. _`doc8`: https://github.com/stackforge/doc8
.. _`coverage.py`: https://pypi.org/project/coverage
