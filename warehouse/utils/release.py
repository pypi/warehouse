# SPDX-License-Identifier: Apache-2.0


def strip_keywords(keywords: list[str]) -> list[str]:
    """
    Remove empties.
    Useful to cleanse user input prior to storing in Release.keywords_array.
    """
    return [keyword for keyword in keywords if keyword]
