#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import os
from datetime import datetime

base_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..")

# -- General configuration ------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.doctest",
    "sphinx.ext.todo",
    "sphinxcontrib.httpdomain",
    "myst_parser",
    "sphinxcontrib.mermaid",
    "sphinx_copybutton",
    "sphinx_reredirects",
]

redirects = {
    "api-reference/feeds": "https://docs.pypi.org/api/feeds/",
    "api-reference/json": "https://docs.pypi.org/api/json/",
    "api-reference/legacy": "https://docs.pypi.org/api/index-api/",
    "api-reference/stats": "https://docs.pypi.org/api/stats/",
    "api-reference/integration-guide": "https://docs.pypi.org/api/#integration-guide",
    "api-reference/bigquery-datasets": "https://docs.pypi.org/api/bigquery",
}

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# The suffix of source filenames.
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# The master toctree document.
master_doc = "index"

# General information about the project.
project = "Warehouse"
copyright = str(datetime.now().year)

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ["_build"]

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

# Patterns to during `make linkcheck`
linkcheck_ignore = [
    r"http://localhost.*",
    "http://134.122.111.11",  # example IP
    "https://web.libera.chat/#pypa,#pypa-dev",  # can't visit anchors
]


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = "furo"

html_static_path = ["_static"]
html_css_files = [
    "css/extra.css",
]

# Output file base name for HTML help builder.
htmlhelp_basename = "Warehousedoc"

# Enable display of todos
todo_include_todos = True
