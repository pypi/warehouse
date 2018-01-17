Reviewing and merging patches
=============================

Everyone is encouraged to review open pull requests. We only ask that you try
and think carefully, ask questions and are `excellent to one another`_. When engaging in code review, please remember that you are bound by the `Code of Conduct`_. Code review is our opportunity to share knowledge, design ideas and make friends.

When reviewing a patch try to keep each of these concepts in mind:

Architecture
------------

* Is the proposed change being made in the correct place?

Intent
------

* What is the change being proposed?
* Do we want this feature or is the bug they're fixing really a bug?

Implementation
--------------

* Does the change do what the author claims?
* Are there sufficient tests?
* Should and has it been documented?
* Will this change introduce new bugs?

Grammar and style
-----------------

These are small things that are not caught by the automated style checkers.

* Does a variable need a better name?
* Should this be a keyword argument?

Merge requirements
------------------

* Patches must *never* be pushed directly to ``master``, all changes (even the
  most trivial typo fixes!) must be submitted as a pull request.
* A patch that breaks tests, or introduces regressions by changing or removing
  existing tests should not be merged. Tests must always be passing on
  ``master``.
* If somehow the tests get into a failing state on ``master`` (such as by a
  backwards incompatible release of a dependency) no pull requests may be
  merged until this is rectified.
* All merged patches must have 100% test coverage.
* All user facing strings must be marked for translation and the ``.pot`` and
  ``.po`` files must be updated.

.. _`excellent to one another`: https://speakerdeck.com/ohrite/better-code-review

.. _`Code of Conduct`: https://www.pypa.io/en/latest/code-of-conduct/

