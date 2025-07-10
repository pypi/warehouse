# SPDX-License-Identifier: Apache-2.0


from warehouse.cli import warehouse


@warehouse.group()
def projects():
    """
    Group for projects commands.
    """
