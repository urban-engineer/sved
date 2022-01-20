#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

from utils import config


def verify_directories():
    input_directory = config.load_input_directory(False)
    output_directory = config.load_output_directory(False)

    if str(input_directory) == str(output_directory):
        raise ValueError("Input and Output directories cannot be the same directory")


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sved.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    verify_directories()
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
