"""Bind gunicorn using os.environ['PORT'] — avoids shell / exec-form $PORT literal bugs on Railway."""

from __future__ import annotations

import os


def main() -> None:
    port = os.environ.get("PORT", "8000")
    argv = [
        "gunicorn",
        "app.main:app",
        "-w",
        "1",
        "-k",
        "uvicorn.workers.UvicornWorker",
        "--bind",
        f"0.0.0.0:{port}",
    ]
    os.execvp(argv[0], argv)


if __name__ == "__main__":
    main()
