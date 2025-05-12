---
title: "PyPI has completed its first security audit"
description: We are proud to announce PyPI's first external security audit.
authors:
  - di
date: 2023-11-14T00:00:00
tags:
  - security
  - transparency
links:
  - posts/2023-11-14-2-security-audit-remediation-warehouse.md
  - posts/2023-11-14-3-security-audit-remediation-cabotage.md
---

_This is part one in a three-part series. See [part two here](2023-11-14-2-security-audit-remediation-warehouse.md), and [part three here](2023-11-14-3-security-audit-remediation-cabotage.md)_

We are proud to announce that PyPI has completed its first ever external security audit.
This work was funded in partnership with the [Open Technology Fund](https://www.opentech.fund/) (OTF), [a previous supporter](https://www.opentech.fund/results/supported-projects/pypi-improvements/) of security-related improvements to PyPI.

<!-- more -->

The Open Technology Fund selected [Trail of Bits](https://www.trailofbits.com/), an industry-leading cybersecurity firm with significant open-source and Python experience, to perform the audit.
Trail of Bits spent a total of 10 engineer-weeks of effort identifying issues, presenting those findings to the PyPI team, and assisting us as we remediated the findings.

## Scope

The audit was focused on "Warehouse", the open-source codebase that powers <https://pypi.org>, and on "cabotage", the custom open-source container orchestration framework we use to deploy Warehouse.
It included code review of both codebases, prioritizing areas that accept user input, provide APIs and other public surfaces.
The audit also covered the continuous integration / continuous deployment (CI/CD) configurations for both codebases.

## Findings

Overall, the auditors determined the Warehouse codebase "was adequately tested and conformed to widely accepted best practices for secure Python and web development," and that while the cabotage codebase lacks the same level of testing, they did not identify any high severity issues in either codebase.

## Results & Impact

As a result of the audit, Trail of Bits detailed 29 different advisories discovered across both codebases.
When evaluating severity level of each advisory, 14 were categorized as "informational", 6 as "low", 8 as "medium" and zero as "high".
At the time of writing, the PyPI team has remediated all advisories that posed a significant risk in both codebases where possible, and has worked with third-party teams to unblock additional remediations where necessary.

## More details

In the interest of transparency, today we are publishing the [full results of the audit](https://github.com/trailofbits/publications#technology-product-reviews), as prepared by Trail of Bits.
You can read more about the audit from their perspective in their [accompanying blog post](https://blog.trailofbits.com/2023/11/14/our-audit-of-pypi/).

Additionally, in two additional blog posts published today, Mike Fiedler (PyPI Security & Safety Engineer) goes into detail about [how we remediated these findings in Warehouse](2023-11-14-2-security-audit-remediation-warehouse.md) and Ee Durbin (Python Software Foundation Director of Infrastructure) [similarly details remediation's in cabotage](2023-11-14-3-security-audit-remediation-cabotage.md).

## Acknowledgements

We would like to thank the Open Technology Fund for their continued support of PyPI and specifically for this significant security milestone for the Python ecosystem.
We would also like to thank Trail of Bits for being a dependable, thorough and thoughtful partner throughout the process.
