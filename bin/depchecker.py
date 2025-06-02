# SPDX-License-Identifier: Apache-2.0

import sys

from pip_api import parse_requirements

left, right = sys.argv[1:3]
left_reqs = parse_requirements(left).keys()
right_reqs = parse_requirements(right).keys()

extra_in_left = left_reqs - right_reqs
extra_in_right = right_reqs - left_reqs

if extra_in_left:
    for dep in sorted(extra_in_left):
        print(f"- {dep}")

if extra_in_right:
    for dep in sorted(extra_in_right):
        print(f"+ {dep}")

if extra_in_left or extra_in_right:
    sys.exit(1)
