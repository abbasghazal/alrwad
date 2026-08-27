import asyncio
from typing import Awaitable, Callable, List, Optional


class Scheduler:
    def __init__(self) -> None:
        self._tasks: List[asyncio.Task] = []
        self.ready = False

    def every(self, seconds: int, job: Callable[[], Optional[Awaitable[None]]]) -> None:
        async def runner() -> None:
            while True:
                result = job()
                if asyncio.iscoroutine(result):
                    await result
                await asyncio.sleep(seconds)

        self._tasks.append(asyncio.create_task(runner()))
        self.ready = True

    def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self.ready = False
