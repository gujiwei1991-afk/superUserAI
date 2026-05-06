"""Run the Dev Agent against a single pending task and exit.

Used for the manual end-to-end smoke test instead of the 30s polling loop.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from app.worker import Worker


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    log = logging.getLogger("oneshot")

    worker = Worker()
    try:
        tasks = await worker.poll_tasks()
        log.info("pending tasks fetched: %d", len(tasks))
        if not tasks:
            log.warning("no pending task — nothing to do")
            return 0

        task = tasks[0]
        log.info("processing task: %s", task)
        await worker.process_task(task)
        log.info("done")
        return 0
    finally:
        await worker.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
