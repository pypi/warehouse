# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
        cov = _coverage.coverage(config_file=".coveragerc")
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
