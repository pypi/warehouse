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

import re

import packaging.utils
import sentry_sdk

_PLATFORMS = [
    (re.compile(r"^win_(.*?)$"), lambda m: f"Windows {_normalize_arch(m.group(1))}"),
    (re.compile(r"^win32$"), lambda m: "Windows x86"),
    (
        re.compile(r"^manylinux2010_(.*?)$"),
        lambda m: f"manylinux: glibc 2.12+ {_normalize_arch(m.group(1))}",
    ),
    (
        re.compile(r"^manylinux_(\d+)_(\d+)_(.*?)$"),
        lambda m: (
            f"manylinux: glibc "
            f"{m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))}"
        ),
    ),
    (
        re.compile(r"^musllinux_(\d+)_(\d+)_(.*?)$"),
        lambda m: (
            f"musllinux: musl {m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))}"
        ),
    ),
    (
        re.compile(r"^macosx_(\d+)_(\d+)_(.*?)$"),
        lambda m: f"macOS {m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))}",
    ),
]

_ARCHS = {
    "amd64": "x86-64",
    "aarch64": "ARM64",
    "x86_64": "x86-64",
    "universal2": "universal2 (ARM64, x86-64)",
    "arm64": "ARM64",
    "armv7l": "ARMv7l",
}


def _normalize_arch(a: str) -> str:
    return _ARCHS.get(a, a)


def _format_version(s: str) -> str:
    return f"{s[0]}.{s[1:]}"


def filename_to_pretty_tags(filename: str) -> list[str]:
    if not filename.endswith(".whl"):
        return ["Source"]

    try:
        _, _, _, tags = packaging.utils.parse_wheel_filename(filename)
    except packaging.utils.InvalidWheelFilename:
        return []

    pretty_tags = set()
    for tag in tags:
        if tag.platform != "any":
            for prefix_re, tmpl in _PLATFORMS:
                if match := prefix_re.match(tag.platform):
                    pretty_tags.add(tmpl(match))

        if tag.interpreter.startswith("pp"):
            # PyPy tags are a disaster, give up.
            pretty_tags.add("PyPy")
        elif tag.interpreter == "py3":
            pretty_tags.add("Python 3")
        elif tag.interpreter == "py2":
            pretty_tags.add("Python 2")
        elif tag.abi == "abi3":
            assert tag.interpreter.startswith("cp")
            version = _format_version(tag.interpreter.removeprefix("cp"))
            pretty_tags.add(f"CPython {version}+")
        elif tag.abi.startswith("cp"):
            version = _format_version(tag.abi.removeprefix("cp"))
            pretty_tags.add(f"CPython {version}")
        elif tag.interpreter.startswith("cp"):
            version = _format_version(tag.interpreter.removeprefix("cp"))
            pretty_tags.add(f"CPython {version}")
        else:
            with sentry_sdk.push_scope() as scope:
                scope.fingerprint = [str(tag)]
                sentry_sdk.capture_message(
                    f"wheel has unrecognized interpreter tag: {tag}. "
                    f"Filename: {filename}."
                )

    return sorted(pretty_tags)
