"""Generate paper figures from logged results.

Figure implementations are added alongside the measurements they visualize. Hand-authored output
figures do not belong in this module.
"""

from pathlib import Path


FIGURES_DIR = Path(__file__).with_name("figures")


def main() -> None:
    """Ensure the generated-figure output directory exists."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main()
