---
title: Yanking
---

!!! note

    PyPI currently only supports yanking of *entire releases*, not individual files.

PyPI supports *yanking* as a non-destructive alternative to deletion.

A *yanked release* is a release that is always ignored by an installer, unless it
is the only release that matches a [version specifier] (using either `==` or `===`).
See [PEP 592] for more information.

[version specifier]: https://packaging.python.org/en/latest/specifications/version-specifiers/

[PEP 592]: https://peps.python.org/pep-0592/

## When should I yank a release?

Like deletion, yanking should be done sparingly since it can be disruptive to
downstream users of a package.

Maintainers should consider yanking a release when:

- The release is broken or uninstallable.
- The release violates its own compatibility guarantees. For example, `sampleproject 1.0.1`
  might be yanked if it's *unintentionally* incompatible with `sampleproject 1.0.0`.
- The release contains a security vulnerability.

## How do I yank a release?

To yank a release, go to the release management page for your project:
`https://pypi.org/manage/project/YOUR-PROJECT/releases/`.

Click on the `Options` button next to the release you wish to yank, then click `Yank`:

![](/assets/release-options-yank.png)

A modal dialogue will appear, asking you to confirm the yank and provide an
optional reason for yanking:

![](/assets/yank-confirm-modal.png)

The reason, if provided, will be displayed on the release page as well
as in the [index APIs](../api/index-api.md) used by installers.

!!! tip

    Providing a reason for yanking is **strongly encouraged**, as it can
    help downstream users determine how to respond to the yank.
