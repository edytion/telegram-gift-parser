from .i18n import tr
import asyncio
import ctypes
import logging
import math
import os
import shutil
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler


class FatalError(RuntimeError):
    pass


class Stop:
    def __init__(self):
        self.event = asyncio.Event()
        self.reason = None

    def fail(self, message):
        if not self.event.is_set():
            self.reason = message
            logging.getLogger('collector').critical(message)
            self.event.set()

    def check(self):
        if self.event.is_set():
            raise FatalError(self.reason)

    async def guard(self, coroutine):
        work = asyncio.create_task(coroutine)
        stopped = asyncio.create_task(self.event.wait())
        try:
            done, _ = await asyncio.wait([work, stopped], return_when=asyncio.FIRST_COMPLETED)
            self.check()
            return await work
        finally:
            for task in (work, stopped):
                if not task.done():
                    task.cancel()
            await asyncio.gather(work, stopped, return_exceptions=True)


@dataclass
class Counts:
    success: int = 0
    errors: int = 0
    warnings: int = 0


class CountLogs(logging.Filter):
    def __init__(self, counts, level=None):
        super().__init__()
        self.counts, self.level = counts, level

    def filter(self, record):
        if self.level is None:
            if record.levelno >= logging.ERROR:
                self.counts.errors += 1
            elif record.levelno == logging.WARNING:
                self.counts.warnings += 1
        return self.level is None or record.levelno >= self.level


def configure_logs(root, counts):
    folder = root / 'logs'
    folder.mkdir(exist_ok=True)
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.INFO)
    for filename, level in [('latest.log', None), ('errors.log', logging.ERROR), ('warnings.log', logging.WARNING)]:
        handler = RotatingFileHandler(folder / filename, maxBytes=5_000_000, backupCount=3, encoding='utf-8')
        if (folder / filename).stat().st_size:
            handler.doRollover()
        handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s'))
        handler.addFilter(CountLogs(counts, level))
        logger.addHandler(handler)
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.info(tr('Начало запуска', 'Starting'))


class Progress:
    def __init__(self, counts):
        self.counts = counts
        self.total = self.finished = self.complete = 0
        self.overall_total = self.base_done = 0
        self.name = tr('Подготовка', 'Preparing')
        self.found = self.issued = self.attempts = 0
        self.phase = tr('Подготовка', 'Preparing')
        self.active = False
        self.drawn = False
        self.tty = sys.stdout.isatty()
        self.task = None

    @staticmethod
    def bar(done, total, width=20):
        ratio = min(1, done / total) if total else 0
        filled = int(ratio * width)
        return '█' * filled + '░' * (width - filled), ratio * 100

    def draw(self):
        one, pct = self.bar(self.base_done + self.found, self.overall_total)
        two, cur = self.bar(self.found, self.issued)
        lines = [tr(f'Всего [{one}] {pct:6.2f}% | {self.base_done + self.found}/{self.overall_total} | коллекции: {self.finished}/{self.total}', f'Total [{one}] {pct:6.2f}% | {self.base_done + self.found}/{self.overall_total} | collections: {self.finished}/{self.total}'),
                 tr(f'{self.name} [{two}] {cur:6.2f}% | {self.found}/{self.issued} | проверено: {self.attempts}', f'{self.name} [{two}] {cur:6.2f}% | {self.found}/{self.issued} | checked: {self.attempts}'),
                 tr(f'{self.counts.success} успешно | {self.counts.errors} ошибок | {self.counts.warnings} предупреждений | {self.phase}', f'{self.counts.success} successful | {self.counts.errors} errors | {self.counts.warnings} warnings | {self.phase}')]
        if self.tty:
            width = max(40, shutil.get_terminal_size((120, 24)).columns - 1)
            prefix = '\x1b[3F' if self.drawn else ''
            sys.stdout.write(prefix + ''.join('\x1b[2K\x1b[37m' + line[:width] + '\x1b[0m\n' for line in lines))
            sys.stdout.flush()
            self.drawn = True
        elif not self.active:
            print('\n'.join(lines), flush=True)

    async def _refresh(self):
        while self.active:
            self.draw()
            await asyncio.sleep(0.2)

    async def start(self):
        if os.name == 'nt' and self.tty:
            kernel = ctypes.windll.kernel32
            kernel.GetStdHandle.argtypes = [ctypes.c_long]
            kernel.GetStdHandle.restype = ctypes.c_void_p
            kernel.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            kernel.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            handle = kernel.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel.SetConsoleMode(handle, mode.value | 4)
        self.active = True
        self.task = asyncio.create_task(self._refresh())

    async def close(self):
        self.active = False
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.draw()


class Pacer:
    def __init__(self, interval):
        if not math.isfinite(interval) or interval < 0.05:
            raise ValueError(tr('Интервал должен быть не меньше 0.05 секунды.', 'Interval must be at least 0.05 seconds.'))
        self.interval, self.next_at = interval, 0.0

    async def wait(self):
        await asyncio.sleep(max(0, self.next_at - time.monotonic()))
        self.next_at = time.monotonic() + self.interval
