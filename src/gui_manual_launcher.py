from __future__ import annotations

import sys

import gui


if __name__ == "__main__":
    if "--no-browser" not in sys.argv[1:]:
        sys.argv.append("--no-browser")
    gui.main()
