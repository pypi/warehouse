---
title: Choosing a Project Name
---

# Choosing a Project Name

When selecting a name for your project, it's important to choose a name that is not only memorable and descriptive, but also available and compliant with PyPI's naming policies. This guide provides information on why your desired project name might not be available and how to claim an abandoned or previously registered name.

## Why isn't my desired project name available?

Even if a project doesn't appear on PyPI, your desired name might be unavailable for several reasons:

* **Standard library conflict:** The name conflicts with a module in the Python Standard Library (from version 2.5 to present)  
* **Name similarity:** The name is too similar to an existing project, creating a risk of confusion or "[typosquatting](../../using-pypi/package-security/common-attacks.md#typosquatting)"  
* **Prohibited name:** The name is prohibited by PyPI administrators. For example, requirements.txt is banned to prevent malicious packages from exploiting common typos like pip install requirements.txt  
* **Registered but unused:** The name has been registered by another user who has not yet published any releases

## How do I claim an abandoned or previously registered project name?

To claim an abandoned or unused project name, follow the name transfer process in [PEP 541](https://peps.python.org/pep-0541/).
