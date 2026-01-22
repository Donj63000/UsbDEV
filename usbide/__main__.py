from __future__ import annotations

import argparse
from pathlib import Path

from usbide.app import USBIDEApp


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="usbide", description="Mini IDE terminal portable (Textual).")
    p.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Dossier racine du workspace (par défaut: répertoire courant).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    app = USBIDEApp(root_dir=args.root)
    app.run()


if __name__ == "__main__":
    main()
