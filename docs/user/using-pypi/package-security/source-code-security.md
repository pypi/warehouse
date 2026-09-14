---
title: Assessing Source Code Security
---

# Assessing Source Code Security

PyPI is a repository for distributing packages, not a service for auditing them. PyPI does not guarantee the quality or security of the code within any given package. **Assessing the trustworthiness of a package's source code is your responsibility**.

When a full code audit is not practical, the signals listed below can help you build confidence and assess the trustworthiness of a new package.

## Security signals

#### Verified project details

- This tells you that the package owner had control over the project's official URLs (e.g. its GitHub repository) at the time of upload to PyPI. You can read more about how this works (including limitations) in the [Project metadata docs](../../project_metadata.md).

<!-- add image -->
Figure: a screenshot of verified project details in the PyPI sidebar

#### Project activity and popularity

- A large community can mean more eyes on the code, potentially finding issues faster

- A high download count suggests wide usage (though is not itself a signal for quality, as many niche or new projects may have fewer downloads)

- An active commit history and recent releases indicate the project is maintained

- Sponsorship or affiliation with reputable organizations may indicate more resources for securing the codebase

#### Security posture

- The presence of a SECURITY.md file in the repository (or a security policy on the project website) shows the project has a formal process for handling vulnerability reports

- How maintainers respond to security issues reported in the project's issue tracker is another key indicator of its security posture

#### Dependencies

- Dependencies are packages that a project relies on. Each dependency of a package you install is another project you are implicitly trusting, which in turn increases your attack surface. Therefore, when assessing a package, a small number of dependencies can be a positive signal.

- You can explore your project's dependencies using the pip freeze command which outputs your dependencies as a flat list, or use [pipdeptree](https://github.com/tox-dev/pipdeptree) to output a dependency tree (showing the dependencies of your dependencies). You can also view dependencies via services like [GitHub's dependency graph](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/exporting-a-software-bill-of-materials-for-your-repository#about-the-dependency-graph-and-sbom-exports).

#### Security advisories / known vulnerabilities

- Security researchers, package maintainers, and other members of the Python community can contribute to the [Python Packaging Advisory Database](https://github.com/pypa/advisory-database) by creating "advisories" for vulnerabilities. This community-owned database helps to warn users about insecure packages.

- The [Python Packaging Advisory Database](https://github.com/pypa/advisory-database) is also the data source for [pip-audit](https://github.com/pypa/pip-audit) - a tool you can use to scan your project's dependencies for known vulnerabilities

- Services like [Socket](https://socket.dev/search?e=pypi&q=) or [Snyk](https://security.snyk.io/vuln/pip) also provide vulnerability information for Python packages

- [GitHub's Dependabot](https://docs.github.com/en/code-security/getting-started/dependabot-quickstart-guide) can also be used to scan your project for dependencies with known vulnerabilities
