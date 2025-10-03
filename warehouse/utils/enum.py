# SPDX-License-Identifier: Apache-2.0

import enum

from typing import Self


class StrLabelEnum(str, enum.Enum):
    """Base class for Enum with string value and display label."""

    label: str

    # Name = "value", _("Label")
    def __new__(cls, value: str, label: str) -> Self:
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        return obj
