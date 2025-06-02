# SPDX-License-Identifier: Apache-2.0

"""
TypoSnyper [sic]

Detect if a project name is a typo of another project name.

**NOTE**: Attempt to keep this module free of dependencies on other parts of the
warehouse codebase, so that it could potentially be extracted into its own package.
This may be an ugly module, as long as it is self-contained and can be refactored later.

Takes inspiration from the `typoguard` paper & project,
and the `typomania` Rust project.
"""

from itertools import permutations

# Ensure all checks return a similar type,
# where the first string is the check name,
# followed by the matched project name,
# or None if no match was found
type TypoCheckMatch = tuple[str, str] | None


# TODO: This is manually dumped here for the purposes of testing.
#       A fuller implementation of the top list needs to happen.
#       The query to produce this list took ~4 minutes on production.
#       This list is the top 200 "most relied upon" projects on PyPI.
_TOP_PROJECT_NAMES = {
    "numpy",
    "requests",
    "pytest",
    "pandas",
    "matplotlib",
    "scipy",
    "pyyaml",
    "click",
    "pytest-cov",
    "tqdm",
    "pydantic",
    "odoo",
    "sphinx",
    "scikit-learn",
    "pillow",
    "black",
    "torch",
    "flake8",
    "setuptools",
    "coverage",
    "beautifulsoup4",
    "jinja2",
    "python-dateutil",
    "typing-extensions",
    "mypy",
    "aiohttp",
    "six",
    "bug",
    "rich",
    "twine",
    "urllib3",
    "django",
    "pre-commit",
    "isort",
    "python-dotenv",
    "sqlalchemy",
    "boto3",
    "flask",
    "lxml",
    "httpx",
    "psutil",
    "source",
    "packaging",
    "sphinx-rtd-theme",
    "repository",
    "seaborn",
    "wheel",
    "opencv-python",
    "ipython",
    "colorama",
    "typer",
    "documentation",
    "networkx",
    "pytz",
    "cryptography",
    "ruff",
    "tox",
    "fastapi",
    "tabulate",
    "pylint",
    "certifi",
    "build",
    "openai",
    "transformers",
    "openpyxl",
    "loguru",
    "toml",
    "protobuf",
    "tensorflow",
    "zope",
    "importlib-metadata",
    "attrs",
    "h5py",
    "plotly",
    "uvicorn",
    "pyarrow",
    "scikit-image",
    "jsonschema",
    "joblib",
    "torchvision",
    "numba",
    "pygments",
    "pytest-mock",
    "redis",
    "validators",
    "idna",
    "pytest-asyncio",
    "gitpython",
    "pytest-xdist",
    "pyjwt",
    "pyqt5",
    "nltk",
    "bs4",
    "selenium",
    "pycryptodome",
    "discordautochat",
    "discorudo",
    "mock",
    "statsmodels",
    "shapely",
    "pymongo",
    "plone",
    "ipywidgets",
    "tomli",
    "psycopg2-binary",
    "mkdocs",
    "ipykernel",
    "termcolor",
    "jupyter",
    "websockets",
    "pyparsing",
    "docker",
    "chardet",
    "cython",
    "aws-cdk",
    "docutils",
    "charset-normalizer",
    "sphinx-copybutton",
    "ruamel",
    "grpcio",
    "myst-parser",
    "astropy",
    "xarray",
    "markdown",
    "mkdocs-material",
    "check-manifest",
    "pyserial",
    "regex",
    "dask",
    "appdirs",
    "future",
    "sympy",
    "markupsafe",
    "tenacity",
    "nbsphinx",
    "djangorestframework",
    "streamlit",
    "furo",
    "werkzeug",
    "pip",
    "sphinx-autodoc-typehints",
    "pymysql",
    "typeguard",
    "datasets",
    "cffi",
    "aiofiles",
    "orjson",
    "argparse",
    "geopandas",
    "dill",
    "importlib-resources",
    "psycopg2",
    "langchain",
    "cachetools",
    "tiktoken",
    "spacy",
    "paramiko",
    "winrt-windows",
    "numpydoc",
    "google-api-python-client",
    "more-itertools",
    "platformdirs",
    "xlrd",
    "biopython",
    "oslo",
    "xmltodict",
    "requests-toolbelt",
    "mkdocstrings",
    "graphviz",
    "websocket-client",
    "prompt-toolkit",
    "types-requests",
    "tornado",
    "jupyterlab",
    "prettytable",
    "pygame",
    "jax",
    "pydantic-settings",
    "einops",
    "hypothesis",
    "watchdog",
    "imageio",
    "botocore",
    "google-auth",
    "filelock",
    "fire",
    "pyperclip",
    "fsspec",
    "sklearn",
    "publication",
    "jsii",
    "pywin32",
    "typing",
    "gunicorn",
    "docopt",
    "keyring",
    "sentencepiece",
    "typing_extensions",
    "keras",
    "pyopenssl",
}


# Dictionary containing reasonable typos for each of the allowed characters
# based on QWERTY keyboard locality and visual similarity
_TYPO_MAP = {
    "1": ["2", "q", "i", "l"],
    "2": ["1", "q", "w", "3"],
    "3": ["2", "w", "e", "4"],
    "4": ["3", "e", "r", "5"],
    "5": ["4", "r", "t", "6", "s"],
    "6": ["5", "t", "y", "7"],
    "7": ["6", "y", "u", "8"],
    "8": ["7", "u", "i", "9"],
    "9": ["8", "i", "o", "0"],
    "0": ["9", "o", "p", "-"],
    "-": ["_", "0", "p", ".", ""],
    "_": ["-", "0", "p", ".", ""],
    "q": ["1", "2", "w", "a"],
    "w": ["2", "3", "e", "s", "a", "q", "vv"],
    "e": ["3", "4", "r", "d", "s", "w"],
    "r": ["4", "5", "t", "f", "d", "e"],
    "t": ["5", "6", "y", "g", "f", "r"],
    "y": ["6", "7", "u", "h", "t", "i"],
    "u": ["7", "8", "i", "j", "y", "v"],
    "i": ["1", "8", "9", "o", "l", "k", "j", "u", "y"],
    "o": ["9", "0", "p", "l", "i"],
    "p": ["0", "-", "o"],
    "a": ["q", "w", "s", "z"],
    "s": ["w", "d", "x", "z", "a", "5"],
    "d": ["e", "r", "f", "c", "x", "s"],
    "f": ["r", "g", "v", "c", "d"],
    "g": ["t", "h", "b", "v", "f"],
    "h": ["y", "j", "n", "b", "g"],
    "j": ["u", "i", "k", "m", "n", "h"],
    "k": ["i", "o", "l", "m", "j"],
    "l": ["i", "o", "p", "k", "1"],
    "z": ["a", "s", "x"],
    "x": ["z", "s", "d", "c"],
    "c": ["x", "d", "f", "v"],
    "v": ["c", "f", "g", "b", "u"],
    "b": ["v", "g", "h", "n"],
    "n": ["b", "h", "j", "m"],
    "m": ["n", "j", "k", "rn"],
    ".": ["-", "_", ""],
}


def _repeated_characters(project_name: str, corpus: set[str]) -> TypoCheckMatch:
    """
    Removes any identical consecutive characters to check for typosquatting
    by repeated characters.
    For example, 'reequests' could be typosquatting 'requests'.

    Returns a possible typosquatting target from the given names list.
    """

    # Loop through each character in the project name
    for idx, character in enumerate(project_name):
        # If the next character in the given project_name is the same as the current one
        if idx + 1 < len(project_name) and project_name[idx + 1] == character:
            # Build a new name by removing the duplicated character
            deduplicated = project_name[:idx] + project_name[idx + 1 :]
            # If the new name is in the list of popular names, return it
            if deduplicated in corpus:
                return "repeated_characters", deduplicated

    return None


def _omitted_characters(project_name: str, corpus: set[str]) -> TypoCheckMatch:
    """
    Inserts allowed characters into name to check for typosquatting by omission.
    For example, 'evnt-stream' could be typosquatting 'event-stream'.

    Returns possible typosquatting target from the given names list.

    Note: Performance-wise, this is the slowest check, but is straightforward.
    We're talking 178 microseconds vs 40 microseconds, so it's fine for our use case.
    """
    allowed_characters = "abcdefghijklmnopqrstuvwxyz1234567890.-_"

    # Do not apply this check to short project names, to reduce false positives
    if len(project_name) < 4:
        return None

    # Loop through every position in the given package_name
    for idx in range(len(project_name) + 1):
        # Loop through every character in the list of allowed characters
        for character in allowed_characters:
            # Build new name by inserting the current character in the current position
            constructed = project_name[:idx] + character + project_name[idx:]
            # If the new name is in the list of popular names, return it
            if constructed in corpus:
                return "omitted_characters", constructed

    return None


def _swapped_characters(project_name: str, corpus: set[str]) -> TypoCheckMatch:
    """
    Swaps adjacent characters to check for typosquatting by swapped characters.
    For example, 'spihnx' could be typosquatting 'sphinx'.
    """

    # Loop through all pairs of consecutive characters in the given name
    for index in range(len(project_name) - 1):
        # Swap the two characters to create a new name
        char_list = list(project_name)
        temp = char_list[index]
        char_list[index] = char_list[index + 1]
        char_list[index + 1] = temp
        swapped_string = "".join(char_list)

        # If the new name is in the list of popular names, return it
        if swapped_string in corpus:
            return "swapped_characters", swapped_string

    return None


def _swapped_words(project_name: str, corpus: set[str]) -> TypoCheckMatch:
    """
    Reorders project_name substrings separated by `-` to look for typosquatting.
    For example, 'stream-event' could be  squatting 'event-stream'.
    """

    # Input is a canonicalized name, split it on `-` to we can swap them around
    tokens = project_name.split("-")
    if (
        # Project names with no delimiters are not candidates for this check
        len(tokens) < 2
        # This function has factorial time complexity. To avoid
        # extremely long execution times, limit the number of tokens
        # allowed to be processed
        or len(tokens) > 8
    ):
        return None

    # Get all possible permutations of the words in the name
    for p in permutations(tokens):
        # Join the words using `-` to create a new name
        reconstructed = "-".join(p)
        # If the new name is in the list of popular names, return it
        if reconstructed != project_name and reconstructed in corpus:
            return "swapped_words", reconstructed

    return None


def _common_typos(project_name: str, corpus: set[str]) -> TypoCheckMatch:
    """
    Applies each of the common typos to each of the characters in the given name.
    Checks if each result is in the list of popular names.
    """
    # Loop through all characters in the given package_name
    for idx, character in enumerate(project_name):
        # Ensure the character is in the common typo dict
        if character in _TYPO_MAP:
            # Loop through each common typo for the given character
            for t in _TYPO_MAP[character]:
                # Build a new name, swapping character with the current typo character
                typo_project_name_chars = list(project_name)
                typo_project_name_chars[idx] = t
                typo_project_name = "".join(typo_project_name_chars)

                # Check if the new package name is in the list of popular packages
                if typo_project_name in corpus:
                    return "common_typos", typo_project_name

    return None


def typo_check_name(project_name: str, corpus=None) -> TypoCheckMatch:
    """
    Check if the given project name is a typo of another project name.

    Runs multiple checks, and if any of them match, returns the matched name.
    """
    if corpus is None:
        # Fall back to the static list if not provided
        corpus = _TOP_PROJECT_NAMES

    # Run each check in order
    for check in (
        _repeated_characters,
        _omitted_characters,
        _swapped_characters,
        _swapped_words,
        _common_typos,
    ):
        if result := check(project_name, corpus=corpus):
            return result
    return None
