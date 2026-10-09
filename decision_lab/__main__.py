"""Allow ``python3 -m decision_lab``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
