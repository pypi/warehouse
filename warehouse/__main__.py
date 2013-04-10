#!/usr/bin/env python
import sys

from configurations import management


def main():
    management.execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
