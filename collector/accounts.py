from .i18n import tr
import asyncio
import logging
import re
from getpass import getpass

from telethon import TelegramClient, errors
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import InputUserSelf

from .runtime import FatalError, Pacer

log = logging.getLogger('collector.accounts')


class GiftUnavailable(Exception):
    pass


class Account:
    def __init__(self, settings, directory, interval, stop):
        self.name = settings['name']
        self.stop = stop
        session = settings.get('session', 'telegram_' + self.name)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', session):
            raise ValueError(tr('Некорректное имя session.', 'Invalid session name.'))
        self.client = TelegramClient(
            str(directory / session), int(settings['api_id']), settings['api_hash'],
            flood_sleep_threshold=0, request_retries=5, raise_last_call_error=True,
            auto_reconnect=False, connection_retries=0, timeout=20)
        self.pacer = Pacer(interval)
        self.lock = asyncio.Lock()
        self.closing = False

    async def login(self):
        print(tr(f'Вход в аккаунт {self.name}...', f'Signing in to account {self.name}...'), flush=True)
        try:
            await self.client.start(
                phone=lambda: input(tr(f'[{self.name}] Номер телефона: ', f'[{self.name}] Phone number: ')).strip(),
                code_callback=lambda: input(tr(f'[{self.name}] Код входа: ', f'[{self.name}] Login code: ')).strip(),
                password=lambda: getpass(tr(f'[{self.name}] Пароль двухэтапной защиты: ', f'[{self.name}] Two-step verification password: ')))
            me = await self.client.get_me()
            if not me or me.bot:
                raise ValueError(tr('Требуется пользовательский аккаунт.', 'A user account is required.'))
            # Pinned Telethon 1.45: login can migrate DC, collection must fail fast.
            self.client._request_retries = 0
            log.info(tr('%s: авторизация выполнена', '%s: signed in successfully'), self.name)
            return me.id
        except Exception as exc:
            self.stop.fail(tr(f'{self.name}: ошибка авторизации: {type(exc).__name__}: {exc}', f'{self.name}: sign-in error: {type(exc).__name__}: {exc}'))
            raise FatalError(self.stop.reason) from exc

    async def call(self, request):
        while True:
            async with self.lock:
                self.stop.check()
                await self.pacer.wait()
                self.stop.check()
                try:
                    return await self.client(request)
                except (errors.FloodWaitError, errors.FloodPremiumWaitError) as exc:
                    pause = max(1, exc.seconds) + 1
                    log.warning(tr('%s: FLOOD_WAIT %s секунд', '%s: FLOOD_WAIT %s seconds'), self.name, pause)
                except errors.RPCError as exc:
                    if getattr(exc, 'message', '') in {'STARGIFT_SLUG_INVALID', 'STARGIFT_NOT_FOUND', 'STARGIFT_INVALID'}:
                        raise GiftUnavailable(str(exc)) from exc
                    self.stop.fail(f'{self.name}: RPC {type(exc).__name__}: {exc}')
                    raise FatalError(self.stop.reason) from exc
                except (OSError, asyncio.TimeoutError, ConnectionError) as exc:
                    self.stop.fail(tr(f'{self.name}: соединение потеряно: {type(exc).__name__}: {exc}', f'{self.name}: connection lost: {type(exc).__name__}: {exc}'))
                    raise FatalError(self.stop.reason) from exc
                except Exception as exc:
                    self.stop.fail(tr(f'{self.name}: критическая ошибка: {type(exc).__name__}: {exc}', f'{self.name}: critical error: {type(exc).__name__}: {exc}'))
                    raise FatalError(self.stop.reason) from exc
            # Release the request lock during a flood pause: health monitoring stays active.
            await asyncio.sleep(pause)

    async def monitor(self):
        async def disconnected():
            await asyncio.shield(self.client.disconnected)
            if not self.closing:
                self.stop.fail(tr(f'{self.name}: Telegram-соединение закрыто. Весь сбор остановлен.', f'{self.name}: Telegram connection closed. All collection has stopped.'))

        async def health():
            while not self.closing:
                await asyncio.sleep(20)
                await self.call(GetFullUserRequest(InputUserSelf()))

        tasks = [asyncio.create_task(disconnected()), asyncio.create_task(health())]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.stop.fail(tr(f'{self.name}: проверка состояния не пройдена: {type(exc).__name__}: {exc}', f'{self.name}: health check failed: {type(exc).__name__}: {exc}'))
        finally:
            await cancel_tasks(tasks)

    async def close(self):
        self.closing = True
        await self.client.disconnect()


async def cancel_tasks(tasks):
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
