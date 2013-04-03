#!/usr/bin/env python
import argparse
import os
import sys

from django.core import management


def main():
    # Preparse out -c/--config and -e/--environment
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-c", "--config",
        help=("Path to a local Warehouse config file. If this is not provided "
              "WAREHOUSE_CONF will be used instead."),
    )
    parser.add_argument("-e", "--environment",
        help=("Warehouse Environment to use. If this is not provided "
              "WAREHOUSE_ENV will be used instead. Defaults to DEVELOPMENT."),
    )
    args, remaining = parser.parse_known_args(sys.argv)

    # Apply the config and environment settings
    if args.config:
        os.environ["WAREHOUSE_CONF"] = args.config
    if args.environment:
        os.environ["WAREHOUSE_ENV"] = args.environment

    management.execute_from_command_line(remaining)


if __name__ == "__main__":
    main()
