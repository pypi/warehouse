---
title: "PyPI and Shai-Hulud: Staying Secure Amid Emerging Threats"
description: Shai-Hulud is a great worm, not yet a snake. Attack on npm ecosystem may have implications for PyPI.
date: 2025-11-26
authors:
  - miketheman
tags:
  - publishing
  - security
meta:
  - name: fediverse:creator
    content: "@miketheman@hachyderm.io"
---

An attack on the npm ecosystem continues to evolve, exploiting compromised accounts to publish malicious packages.
This campaign, dubbed _Shai-Hulud_, has targeted large volumes of packages in the JavaScript ecosystem,
exfiltrating credentials to further propagate itself.

**PyPI has not been exploited**, however some PyPI credentials were found exposed in compromised repositories.
We've revoked these tokens as a precaution, there's no evidence they have been used maliciously.
This post raises awareness about the attack and encourages proactive steps to secure your accounts,
especially if you're using build platforms to publish packages to PyPI.

<!-- more -->

## How does this relate to PyPI?

This week, a security researcher disclosed long-lived PyPI credentials exposed as part of the Shai-Hulud campaign.
The credentials were found in GitHub repositories (stored as repository secrets), and were still valid.
We saw an attack with insecure workflow settings for [Ultralytics in 2024](2024-12-11-ultralytics-attack-analysis.md).

While the campaign primarily targets npm, some projects use [monorepo](https://en.wikipedia.org/wiki/Monorepo) setups,
publishing both JavaScript packages to npmjs.com and Python packages to PyPI from the same repository.
When attackers compromise these repositories, they can extract credentials for multiple platforms.

We investigated the reported credentials and found they were associated with accounts that hadn't published recently.
We've revoked these credentials and reached out to affected users to advise them to rotate any remaining tokens.

## What can I do to protect my PyPI account?

Here are security practices to protect your PyPI account:

- **Use Trusted Publishing:** If you are using a build platform to publish packages to PyPI,
    consider using a [Trusted Publisher](https://docs.pypi.org/trusted-publishers/).
    This eliminates the need to manage long-lived authentication tokens, reducing the risk of credential exposure.
    Trusted Publishing uses short-lived, scoped tokens for each build, minimizing the impact of any potential compromise.
    This approach has [risen in popularity](2025-11-10-trusted-publishers-coming-to-orgs.md),
    with other registries like [Crates.io](https://crates.io/docs/trusted-publishing),
    [RubyGems](https://guides.rubygems.org/trusted-publishing/),
    and [npmjs.com](https://docs.npmjs.com/trusted-publishers) adopting similar models.

    When using GitHub Actions, consider layering in additional security measures,
    like requiring human approval via [GitHub Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) before publishing.
    [This blog post from pyOpenSci](https://www.pyopensci.org/blog/python-packaging-security-publish-pypi.html)
    has detailed guidance on adding manual review steps to GitHub Actions workflows.

- **Audit your workflows for misconfiguration:** Review your GitHub Actions workflows for any potential security issues.
    Tools like [zizmor](https://docs.zizmor.sh/) and [CodeQL](https://codeql.github.com/)
    can help identify vulnerabilities in your CI/CD pipelines.
    Adopt scanning as automated actions for the repository to catch future issues.

- **Review your account activity:** Regularly check your PyPI account activity for any unauthorized actions.
    If you notice any suspicious activity, [report it to the PyPI security team](https://pypi.org/security/) immediately.

Taking any of these steps helps mitigate the risk of compromise and keeps packages secure.

## References

Some blog posts covering the attack behaviors and mitigation steps:

- [Aikido](https://www.aikido.dev/blog/shai-hulud-strikes-again-hitting-zapier-ensdomains)
- [CISA](https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem)
- [Datadog](https://securitylabs.datadoghq.com/articles/shai-hulud-2.0-npm-worm/)
- [HelixGuard](https://helixguard.ai/blog/malicious-sha1hulud-2025-11-24)
- [ReversingLabs](https://www.reversinglabs.com/blog/shai-hulud-worm-npm)
- [Socket](https://socket.dev/blog/shai-hulud-strikes-again-v2)
- [StepSecurity](https://www.stepsecurity.io/blog/sha1-hulud-the-second-coming-zapier-ens-domains-and-other-prominent-npm-packages-compromised)
- [Wiz](https://www.wiz.io/blog/shai-hulud-2-0-ongoing-supply-chain-attack)
