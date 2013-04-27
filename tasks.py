import sys

import coverage as _coverage
import invoke
import pytest


@invoke.task
def tests(suite=None, coverage=False, pdb=False):
    if suite is None:
        coverage = True
        markers = []
    elif suite == "unit":
        markers = ["unit"]
    elif suite == "functional":
        markers = ["functional"]
    elif suite == "coverage":
        coverage = True
        markers = ["unit"]
    else:
        raise ValueError("Invalid name for suite. Must be one of unit, "
                                                        "functional, coverage")

    args = []

    # Add markers to the arguments
    if markers:
        args += ["-m", " and ".join(markers)]

    # Add coverage to the arguments
    if coverage:
        args += ["--cov", "warehouse"]

    # Add pdb to the arguments
    if pdb:
        args += ["--pdb"]

    exitcode = pytest.main(args)
    if exitcode:
        sys.exit(exitcode)

    if suite == "coverage":
        # When testing for coverage we want to fail the test run if we do not
        #   have 100% coverage.
        cov = _coverage.coverage(config_file="coverage.cfg")
        cov.load()

        with open("/dev/null", "w") as devnull:
            covered = cov.report(file=devnull)

        if int(covered) < 100:
            print("")
            sys.exit("[FAILED] Coverage is less than 100%")


@invoke.task
def compile():
    # Compile the css for Warehouse
    invoke.run(
        "bundle exec compass compile --force warehouse/static")


@invoke.task
def run():
    # Use foreman to start up all our development processes
    invoke.run("bundle exec foreman start -d devel -e devel/env", pty=True)
