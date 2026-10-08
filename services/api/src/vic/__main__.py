"""Production entrypoint: python -m vic. One worker only: runs execute inside this process."""
import uvicorn

from vic.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run("vic.main:app", host=settings.host, port=settings.port, workers=1)


if __name__ == "__main__":
    main()