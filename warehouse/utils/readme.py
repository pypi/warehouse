# SPDX-License-Identifier: Apache-2.0

"""Utils for rendering and updating package descriptions (READMEs)."""

import functools

from email.message import EmailMessage
from importlib.metadata import PackageNotFoundError, distribution

import readme_renderer.markdown
import readme_renderer.rst
import readme_renderer.txt

_RENDERERS = {
    None: readme_renderer.rst,  # Default if description_content_type is None
    "": readme_renderer.rst,  # Default if description_content_type is None
    "text/plain": readme_renderer.txt,
    "text/x-rst": readme_renderer.rst,
    "text/markdown": readme_renderer.markdown,
}

# Packages that readme-renderer relies on to actually produce its output.
# A version bump in any of these can change the rendered HTML for a given
# description, even if readme-renderer's own version hasn't changed, so they
# need to be considered when deciding whether a description is stale.
# See https://github.com/pypi/warehouse/issues/19232
_RENDERER_DEPENDENCIES = ["docutils", "Pygments", "nh3", "cmarkgfm", "comrak"]


def render(value, content_type=None, use_fallback=True):
    if value is None:
        return value

    # Necessary because `msg.get_content_type()` returns `text/plain` for
    # invalid or missing input, per RFC 2045, which changes our behavior.
    if content_type:
        msg = EmailMessage()
        msg["content-type"] = content_type
        content_type = msg.get_content_type()

    # Get the appropriate renderer
    renderer = _RENDERERS.get(content_type, readme_renderer.txt)

    # Actually render the given value, this will not only render the value, but
    # also ensure that it's had any disallowed markup removed.
    rendered = renderer.render(value)

    # Wrap plaintext as preformatted to preserve whitespace.
    if content_type == "text/plain":
        rendered = f"<pre>{rendered}</pre>"

    # If the content was not rendered, we'll render as plaintext instead. The
    # reason it's necessary to do this instead of just accepting plaintext is
    # that readme_renderer will deal with sanitizing the content.
    # Skip the fallback option when validating that rendered output is ok.
    if use_fallback and rendered is None:
        rendered = readme_renderer.txt.render(value)

    return rendered


@functools.cache
def renderer_version():
    versions = [f"readme-renderer=={distribution('readme-renderer').version}"]
    for package in _RENDERER_DEPENDENCIES:
        try:
            versions.append(f"{package}=={distribution(package).version}")
        except PackageNotFoundError:
            # Not all of readme-renderer's rendering dependencies are
            # installed in every environment (e.g. its markdown backend has
            # changed over time), so skip whichever aren't present.
            continue
    return ",".join(versions)
