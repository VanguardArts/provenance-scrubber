"""Entry point for the standalone CLI binary (PyInstaller)."""

import sys

from image_scrub.cli import main

if __name__ == "__main__":
    sys.exit(main())
