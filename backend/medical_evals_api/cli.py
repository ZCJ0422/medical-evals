import argparse

import uvicorn

from .config import settings
from .db import connect


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["api", "init-db"])
    args = parser.parse_args()
    if args.command == "init-db":
        with connect(settings.database_path):
            pass
        return
    uvicorn.run("medical_evals_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
