#!/usr/bin/env python3
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# The suffix of source filenames.
source_suffix = {
    ".rst": 'restructuredtext',
    ".md": 'markdown',
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
    r'http://localhost.*',
    'http://134.122.111.11',  # example IP
    'https://web.libera.chat/#pypa,#pypa-dev',  # can't visit anchors
]


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = "furo"

# Output file base name for HTML help builder.
htmlhelp_basename = "Warehousedoc"

# Enable display of todos
todo_include_todos = True
