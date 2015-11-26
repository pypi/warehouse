Submitting patches
==================

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
meets our automated requirements by running ``tox -e pep8`` against it.

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


Translations
------------

All user facing content must be marked for translation. More details about the
Warehouse translation mechanism can be found in :doc:`translations`.


Documentation
-------------

Important information should be documented with prose in the ``docs`` section.
To ensure it builds and passes `doc8`_ style checks you can run
``tox -e docs``.

.. _`Write comments as complete sentences.`: http://nedbatchelder.com/blog/201401/comments_should_be_sentences.html
.. _`syntax`: http://sphinx-doc.org/domains.html#info-field-lists
.. _`Studies have shown`: https://smartbear.com/smartbear/media/pdfs/wp-cc-11-best-practices-of-peer-code-review.pdf
.. _`doc8`: https://github.com/stackforge/doc8
.. _`coverage.py`: https://pypi.python.org/pypi/coverage
