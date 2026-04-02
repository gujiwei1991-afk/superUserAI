import asyncio
import logging

from app.worker import Worker


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


async def main() -> None:
    configure_logging()
    worker = Worker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
