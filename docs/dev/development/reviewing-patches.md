# Reviewing and merging patches

Everyone is encouraged to review open pull requests. We only ask that you try
and think carefully, ask questions and are [excellent to one another](https://speakerdeck.com/ohrite/better-code-review). When
engaging in code review, remember that you are bound by the [Code of Conduct](https://github.com/pypa/.github/blob/main/CODE_OF_CONDUCT.md).
Code review is our opportunity to share knowledge, design ideas and make
friends.

When reviewing a patch try to keep each of these concepts in mind:

## Architecture

* Is the proposed change being made in the correct place?

## Intent

* What is the change being proposed?
* Do we want this feature or is the bug they're fixing really a bug?

## Implementation

* Does the change do what the author claims?
* Are there sufficient tests?
* Should and has it been documented?
* Will this change introduce new bugs?
* Are we ensuring that we set `rel="noopener"` whenever using
  `target="_blank_"` for a hyperlink?

## Grammar and style

These are small things that are not caught by the automated style checkers.

* Does a variable need a better name?
* Should this be a keyword argument?

## Testing branches on your local machine

It can be helpful to check out a branch with a pull request (PR) on it, in
order to test how the changes in it work on your machine.

First, make sure that your local copy of the Warehouse repo is configured with
an `upstream` branch so that the following command:

```shell
git remote -v
```

Has this output:

```shellsession
origin  https://github.com/<username>/warehouse.git (fetch)
origin  https://github.com/<username>/warehouse.git (push)
upstream  https://github.com/pypi/warehouse.git (fetch)
upstream  https://github.com/pypi/warehouse.git (push)
```

In this output, `<username>` is your GitHub username. If you do not have an
`upstream` branch configured, you can add one by running the following
command:

```shell
git remote add upstream git@github.com:pypa/warehouse.git
```

Pull down the PR branch by running these commands:

```shell
git checkout main
git fetch upstream pull/<id>/head:<branchname>
```

In this example, `upstream` refers to the Warehouse repository on GitHub.
`<id>` refers to the sequence of digits after the pull request's title.
`<branchname>` creates a new branch on your machine which has the pull
request on it. If you create a branch in your local repository with the name
`<branchname>` before pulling down the PR branch, this command will fail.

In order to test the branch, first switch to the new branch with the PR on
it that you have pulled down:

```shell
git checkout <branchname>
```

Once you are on the PR branch, it's probably best to rebase the changes
against the current main branch. The older the PR is, the more important
it is to do this, since differences between main and the PR branch will
have accumulated over time. These differences may lead to difficulty
in testing the changes in the PR branch.

```shell
git checkout <branchname>
git fetch upstream
git rebase upstream/main
```

These commands replay the changes in the PR against the main branch.
Once you have completed these steps, you are ready to test the PR branch.

If you have found any bugs in the course of your testing, you can leave a
brief comment describing the issue you encountered on GitHub in the comments
under the issue.

## Testing with twine

If you are testing Warehouse locally, you may want to use [twine](https://github.com/pypa/twine) to try
uploading a test package. First, checkout the branch you would like to test.
Then, start up the development environment (as described in
[Getting Started](getting-started.md)). Once you have the Warehouse site working on
`localhost:80`, you can upload a package to the version of Warehouse running
in your development environment with Twine using the following command:

```shell
twine upload --repository-url http://localhost/legacy/ -u <username> -p password <path to distribution>
```

In the command above,

-   `<path to distribution>` should be a path to a distribution file (or
    directory of distribution files) of the package you would like to test,
    likely created by running `python setup.py sdist`. See the [Python
    Packaging User Guide](https://packaging.python.org/guides/distributing-packages-using-setuptools/#packaging-your-project) for instructions on how to create a distribution
    file or directory.

-   `<username>` is the username of the account you would like to test with.
    Note that your current PyPI username may not exist in the development
    environment.

-   `password` is the literal string "password". All passwords in the
    development environment have been set to this value.

## Merge requirements

* Patches must *never* be pushed directly to `main`, all changes (even the
  most trivial typo fixes!) must be submitted as a pull request.
* A patch that breaks tests, or introduces regressions by changing or removing
  existing tests should not be merged. Tests must always be passing on
  `main`.
* If somehow the tests get into a failing state on `main` (such as by a
  backwards incompatible release of a dependency) no pull requests may be
  merged until this is rectified.
* All merged patches must have 100% test coverage.
* All user facing strings must be marked for translation and the `.pot` and
  `.po` files must be updated.
