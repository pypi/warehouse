---
title: "Planned Updates to the PyPI User Interface"
description: We are rolling out updates to the PyPI user interface to improve security signaling and the display of package details.
authors:
  - nlh
date: 2026-07-22
tags:
  - user-interface
  - security
links:
  - posts/2024-11-14-pypi-now-supports-digital-attestations.md
---

Over the next few months, we will be rolling out changes to the PyPI user interface, improving how we surface security signals and updating the pages where users view package details.

Updates will be staged to [TestPyPI](https://test.pypi.org/) and deployed to production in phases. This approach allows our team to thoroughly test the UI with production-like data, while providing the community with an opportunity to share feedback.

The first phase of changes is now staged on [TestPyPI](https://test.pypi.org/) and ready for users to review!

<!-- more -->

## Context: UI History, User Research and Attestations Style Guide

The PyPI user interface has remained largely unchanged since its 2018 launch. Over the intervening years, both PyPI and the Python ecosystem have grown significantly, while also attracting a higher volume of malicious activity. As a result, PyPI is taking a more active role in helping users assess and understand package security.

In 2024, PyPI [introduced support for digital attestations](2024-11-14-pypi-now-supports-digital-attestations.md). Uploaded by project maintainers when making a new release, attestations serve as a signed record of a release's build or publishing _provenance_, providing a verifiable way for users to see exactly where the release files came from.

While this was a significant milestone, the initial release did not include the necessary UI updates to make those attestations easily understandable or consumable for the average PyPI user.

This isn't a PyPI-specific problem; communicating attestations clearly to end users is a challenge across the open source ecosystem. To address this, the [OpenSSF Securing Software Repositories Working Group](https://repos.openssf.org/) partnered with [Superbloom](https://superbloom.design/) and [Kabu&nbsp;Creative](https://kabucreative.com/) in 2025 to research and develop a standardized [style guide for displaying attestations on software repositories](https://repos.openssf.org/attestations-style-guide). This work included extensive user interviews with package consumers (including PyPI users) to understand how they evaluate package security and trustworthiness.

As a next step, PyPI is adopting the [highest-level recommendations](https://repos.openssf.org/attestations-style-guide/level-aaa) from the style guide, becoming the first package repository to do so. Most notably, this involves adding a new "Security" tab and improving PyPI's user documentation.

We are also using this opportunity to deliver incremental improvements to the project detail pages, fine-tuning our 2018 design to improve information hierarchy and utility.

## What's Changing?

Key changes to the user interface include:

*   **Dedicated Security Tab:** We are introducing a new Security tab to the project page to centralize provenance and attestation metadata, and to provide clear indicators when provenance is missing or has changed.

*   **Navigation Moved to Horizontal Tabs:** We are moving internal navigation out of the sidebar and into a horizontal tab structure. This allows us to reserve the sidebar exclusively for project- and release-related metadata.

*   **Metadata Sidebar Moved to the Right:** We are shifting the sidebar to the right to place critical content (the package description/readme) on the left, aligning with a natural left-to-right reading pattern and mirroring the structure of other major platforms like GitHub and npm.

*   **Labeling Trust Levels:** We are explicitly labeling project data intrinsic to PyPI (like release timestamps) and data provided by a maintainer and verified by PyPI (like upstream source repositories). This will help users weigh the trustworthiness of data according to its source.

*   **Optimized Sidebar Hierarchy:** We are reordering sidebar metadata by utility, prioritizing project links and "freshness" signals (like release dates) at the top, while shifting classification data to the bottom.

*   **Clearer Status Labeling:** We are introducing bolder colors and improved labels for quarantined, yanked, archived, and pre-release states to help users more easily distinguish between these conditions.

These updates are entirely visual and will not require action from project maintainers; existing and future digital attestations will map to the new UI automatically.

## Our Rollout Plan

We are rolling out these changes in four phases. You can follow our progress, view the design prototypes, and participate in the discussion on our [main tracking issue (#19950)](https://github.com/pypi/warehouse/issues/19950).

*   **Phase 1: Project Details** (prototypes and discussion at [#19951](https://github.com/pypi/warehouse/issues/19951), now live on [TestPyPI](https://test.pypi.org/)) – Main page redesign, including updates to the sidebar order and positioning.
*   **Phase 2: Files and Release History** (prototypes and discussion at [#20185](https://github.com/pypi/warehouse/issues/20185)) – Streamlining the file and release history tabs, adding attestation metadata where appropriate.
*   **Phase 3: Security Tab** (prototypes and discussion at [#20069](https://github.com/pypi/warehouse/issues/20069)) – Building a dedicated space for surfacing provenance and attestation data, raising warnings where appropriate.
*   **Phase 4: Documentation Refresh** – Refreshing PyPI's documentation to support the new UI, including adding security guidance.

## We Want Your Feedback

We invite you to test these changes on [TestPyPI](https://test.pypi.org/).

If you have feedback, please share it on [this GitHub issue](https://github.com/pypi/warehouse/issues/20267).

If you find a bug or defect, please open a ticket on [our issue tracker](https://github.com/pypi/warehouse/issues). Please ensure you include browser and device details. This helps our team reproduce and fix the problem quickly.

## Acknowledgments

We would like to thank the [Open&nbsp;Source&nbsp;Security&nbsp;Foundation](https://openssf.org/) for providing the funding for this initiative. We are also deeply grateful to Dustin Ingram, Zach Steindler, and the members of the [OpenSSF Securing Software Repos WG](https://repos.openssf.org/) for proposing this project for funding, and championing the larger effort to introduce attestations.

We also want to extend a sincere thank you to the members of the Python community who participated in our most recent round of [user interviews](https://github.com/pypi/warehouse/issues/20111); your insights were instrumental in shaping the rationale and execution of these designs. Volunteers included:

* Maciej Kopeć
* Yngve Moe
* Nyaosi Mogaka
* Joachim Jablon
* Samuel Mbote

Finally, thank you to the 777 people who participated in our recent [user survey](https://github.com/pypi/warehouse/issues/20058). Your feedback has been invaluable in shaping the design and ordering of the package metadata sidebar.
