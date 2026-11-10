"""Source parsers. Each module turns one kind of downloaded file into rows of one table."""

from collections.abc import Callable, Iterator

import petl

# Progress callback: called with the number of rows processed since the last call.
Tick = Callable[[int], None]

TICK_EVERY = 10_000


class _Ticking(petl.Table):
    def __init__(self, inner: petl.Table, tick: Tick, every: int) -> None:
        self.inner, self.tick, self.every = inner, tick, every

    def __iter__(self) -> Iterator[tuple]:
        it = iter(self.inner)
        yield next(it)  # header
        n = 0
        for row in it:
            yield row
            n += 1
            if n == self.every:
                self.tick(n)
                n = 0
        if n:
            self.tick(n)


def ticking(table: petl.Table, tick: Tick | None, every: int = TICK_EVERY) -> petl.Table:
    """Wrap ``table`` so that iterating it reports progress through ``tick``."""
    return table if tick is None else _Ticking(table, tick, every)
