import random
import asyncio
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote

from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import (
    Unauthorized, 
    UserDeactivated, 
    AuthKeyUnregistered,
    UsernameNotOccupied,
    FloodWait,
    UserBannedInChannel,
    RPCError,
    UsernameInvalid
)
from pyrogram.raw.functions.messages import RequestAppWebView
from pyrogram.raw import types
from rich.console import Console
import logging

import aiohttp
from bot.core.user_agents import load_or_generate_user_agent
from bot.exceptions import InvalidSession
from aiohttp import ClientResponseError, ClientSession, ClientTimeout, BasicAuth
import json

from pyrogram import raw
from bot.utils.logger import logger
from bot.config import settings
from bot.config.config import Settings
from bot.core.headers import (
    get_headers, 
    get_task_headers,
    get_farming_headers,
    get_auth_headers,
    get_proxy_check_headers,
    get_referral_headers
)
from rich.table import Table

console = Console()

logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("pyrogram.session.auth").setLevel(logging.WARNING)
logging.getLogger("pyrogram.session.session").setLevel(logging.WARNING)

def format_number(num):
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    else:
        return str(num)

class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.settings = Settings()
        self.user_id = 0
        self.username = None
        self.first_name = None
        self.last_name = None
        self.token = None
        self.refresh_token = None
        self.client_lock = asyncio.Lock()
        self.user_agent = load_or_generate_user_agent(self.session_name)
        self.retry_count = 0
        self.balance = 0
        self.game_energy = 0
        self.referral_code = None
        self.crypton_profile_username = None
        self.ton_wallet = None
        self.proxy_dict = None
        self.completed_lessons = set()
        self.proxy_country = None

    def get_headers(self, with_auth: bool = False) -> dict:
        return get_headers(self.user_agent, with_auth, self.token, self.proxy_country)

    async def setup_proxy(self, proxy: str | None) -> None:
        if proxy:
            proxy_obj = Proxy.from_str(proxy)
            if settings.LOG_PROXY:
                logger.info(f"{self.session_name} | Using proxy: {proxy_obj.host}:{proxy_obj.port}")
            self.proxy_dict = dict(
                scheme=proxy_obj.protocol,
                hostname=proxy_obj.host,
                port=proxy_obj.port,
                username=proxy_obj.login,
                password=proxy_obj.password
            )
            self.tg_client.proxy = self.proxy_dict
        else:
            self.proxy_dict = None
            self.tg_client.proxy = None
            if settings.LOG_PROXY:
                logger.info(f"{self.session_name} | Proxy not used")

    async def get_tg_web_data(self, proxy: str | None) -> str:
        async with self.client_lock:
            logger.info(f"{self.session_name} | Started obtaining tg_web_data")
            await self.setup_proxy(proxy)

            try:
                with_tg = True
                logger.info(f"{self.session_name} | Checking connection to Telegram")

                if not self.tg_client.is_connected:
                    with_tg = False
                    logger.info(f"{self.session_name} | Connecting to Telegram...")
                    try:
                        await self.tg_client.connect()
                        logger.success(f"{self.session_name} | Successfully connected to Telegram")
                    except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                        logger.error(f"{self.session_name} | Session is invalid")
                        raise InvalidSession(self.session_name)
                    except Exception as e:
                        logger.error(f"{self.session_name} | Error connecting to Telegram: {str(e)}")
                        raise

                self.start_param = random.choices([settings.REF_ID, "DTGYWCIWEZSAGUB"], weights=[70, 30], k=1)[0]
                if not self.start_param.startswith('ref_'):
                    self.start_param = f"ref_{self.start_param}"

                logger.info(f"{self.session_name} | Obtaining peer ID for nutsfarm bot")
                peer = await self.tg_client.resolve_peer('nutsfarm_bot')
                InputBotApp = types.InputBotAppShortName(bot_id=peer, short_name="nutscoin")

                logger.info(f"{self.session_name} | Requesting web view")
                web_view = await self.tg_client.invoke(RequestAppWebView(
                    peer=peer,
                    app=InputBotApp,
                    platform='android',
                    write_allowed=True,
                    start_param=self.start_param
                ))

                auth_url = web_view.url
                logger.info(f"{self.session_name} | Received authorization URL")
                
                tg_web_data = unquote(
                    string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0])
                logger.success(f"{self.session_name} | Successfully obtained web view data")

                try:
                    if self.user_id == 0:
                        logger.info(f"{self.session_name} | Obtaining user information")
                        information = await self.tg_client.get_me()
                        self.user_id = information.id
                        self.first_name = information.first_name or ''
                        self.last_name = information.last_name or ''
                        self.username = information.username or ''
                        logger.info(f"{self.session_name} | User: {self.username} ({self.user_id})")
                except Exception as e:
                    logger.warning(f"{self.session_name} | Failed to obtain user information: {str(e)}")

                if not with_tg:
                    logger.info(f"{self.session_name} | Disconnecting from Telegram")
                    await self.tg_client.disconnect()

                return tg_web_data

            except InvalidSession as error:
                raise error
            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error during authorization: {str(error)}")
                await asyncio.sleep(settings.RETRY_DELAY[0])
                return None

    async def check_proxy(self) -> bool:
        if not self.proxy_dict:
            self.proxy_country = None
            return True
            
        try:
            headers = {
                'Host': 'speed.cloudflare.com',
                'Accept': 'application/json, text/plain, */*',
                'Origin': self.settings.BASE_URL.rstrip('/'),
                'Connection': 'keep-alive',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'cross-site',
                'User-Agent': self.user_agent,
                'Referer': f'{self.settings.BASE_URL}',
                'Sec-Fetch-Dest': 'empty',
                'Accept-Language': 'ru'
            }
            
            async with ClientSession() as session:
                proxy_url = f"{self.proxy_dict['scheme']}://{self.proxy_dict['hostname']}:{self.proxy_dict['port']}"
                proxy_auth = None
                if self.proxy_dict.get('username') and self.proxy_dict.get('password'):
                    proxy_auth = BasicAuth(self.proxy_dict['username'], self.proxy_dict['password'])
                    
                async with session.get(
                    'https://speed.cloudflare.com/meta',
                    headers=headers,
                    proxy=proxy_url,
                    proxy_auth=proxy_auth,
                    ssl=False,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.proxy_country = data.get('country')
                        if settings.LOG_PROXY_CHECK:
                            logger.info(
                                f"{self.session_name} | "
                                f"Proxy check successful | "
                                f"IP: {data.get('clientIp')} | "
                                f"Location: {data.get('city')}, {self.proxy_country} | "
                                f"ISP: {data.get('asOrganization')}"
                            )
                        return True
                    if settings.LOG_PROXY_CHECK:
                        logger.warning(f"{self.session_name} | Proxy check failed with status {response.status}")
                    return False
        except Exception as e:
            if settings.LOG_PROXY_CHECK:
                logger.warning(f"{self.session_name} | Proxy check failed: {str(e)}")
            return False

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> dict | None:
        if not self.token and kwargs.pop('with_auth', True):
            return None
            
        if self.proxy_dict and not await self.check_proxy():
            logger.error(f"{self.session_name} | Proxy check failed, skipping request")
            return None
            
        url = f"{self.settings.BASE_URL}api/{self.settings.API_VERSION}/{endpoint}"
        headers = self.get_headers(with_auth=kwargs.pop('with_auth', True))
        
        if 'headers' in kwargs:
            if isinstance(kwargs['headers'], dict):
                headers.update(kwargs['headers'])
            kwargs.pop('headers')
            
        if 'params' in kwargs and isinstance(kwargs['params'], dict):
            if 'lang' in kwargs['params']:
                kwargs['params']['lang'] = 'EN' if self.proxy_country and self.proxy_country != 'RU' else 'RU'

        retry_count = 0
        auth_retry_count = 0
        max_auth_retries = 2
        
        while retry_count < settings.MAX_RETRIES:
            try:
                async with ClientSession() as session:
                    timeout = random.uniform(settings.REQUEST_TIMEOUT[0], settings.REQUEST_TIMEOUT[1])
                    
                    request_kwargs = {
                        'url': url,
                        'headers': headers,
                        'ssl': False,
                        'timeout': ClientTimeout(total=timeout),
                        **kwargs
                    }

                    if self.proxy_dict:
                        proxy_url = f"{self.proxy_dict['scheme']}://{self.proxy_dict['hostname']}:{self.proxy_dict['port']}"
                        request_kwargs['proxy'] = proxy_url
                        if self.proxy_dict.get('username') and self.proxy_dict.get('password'):
                            request_kwargs['proxy_auth'] = BasicAuth(
                                self.proxy_dict['username'],
                                self.proxy_dict['password']
                            )
                    
                    async with getattr(session, method.lower())(**request_kwargs) as response:
                        if response.status in [401, 403]:
                            if auth_retry_count < max_auth_retries:
                                auth_retry_count += 1
                                if await self.refresh_access_token():
                                    headers = self.get_headers(with_auth=True)
                                    request_kwargs['headers'] = headers
                                    continue
                                else:
                                    tg_web_data = await self.get_tg_web_data(None)
                                    if tg_web_data and await self.authorize(tg_web_data):
                                        headers = self.get_headers(with_auth=True)
                                        request_kwargs['headers'] = headers
                                        continue
                            logger.error(f"{self.session_name} | Authorization failed after {auth_retry_count} attempts")
                            return None
                                
                        if response.status == 429: 
                            retry_after = int(response.headers.get('Retry-After', 60))
                            logger.warning(f"{self.session_name} | Rate limit exceeded, waiting {retry_after} seconds")
                            await asyncio.sleep(retry_after)
                            continue
                            
                        response.raise_for_status()
                        
                        if response.status == 204:
                            return {}
                            
                        content_type = response.headers.get('Content-Type', '')
                        
                        if 'application/json' in content_type:
                            return await response.json()
                        elif 'text/plain' in content_type:
                            text = await response.text()
                            try:
                                return json.loads(text)
                            except json.JSONDecodeError:
                                try:
                                    return float(text)
                                except ValueError:
                                    return text
                        else:
                            try:
                                return await response.json()
                            except:
                                text = await response.text()
                                try:
                                    return json.loads(text)
                                except:
                                    try:
                                        return float(text)
                                    except:
                                        return text
                        
            except ClientResponseError as error:
                if error.status == 429:  
                    retry_after = int(error.headers.get('Retry-After', 60))
                    logger.warning(f"{self.session_name} | Rate limit exceeded, waiting {retry_after} seconds")
                    await asyncio.sleep(retry_after)
                    continue
                    
                retry_count += 1
                if retry_count < settings.MAX_RETRIES:
                    delay = random.uniform(settings.RETRY_DELAY[0], settings.RETRY_DELAY[1])
                    logger.warning(f"{self.session_name} | Error {error.status}, retrying in {delay:.1f} sec...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"{self.session_name} | Request failed after {settings.MAX_RETRIES} attempts")
                    return None
            except Exception as error:
                retry_count += 1
                if retry_count < settings.MAX_RETRIES:
                    delay = random.uniform(settings.RETRY_DELAY[0], settings.RETRY_DELAY[1])
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"{self.session_name} | Request failed after {settings.MAX_RETRIES} attempts")
                    return None

    def _get_language(self) -> str:
        return 'EN' if self.proxy_country and self.proxy_country != 'RU' else 'RU'

    async def get_user_info(self) -> dict | None:
        data = await self._make_request('GET', 'user/current', params={'lang': self._get_language()})
        if data:
            self.balance = data.get('balance', 0)
            self.username = data.get('username')
            self.first_name = data.get('firstname')
            self.last_name = data.get('lastname')
            self.crypton_profile_username = data.get('cryptonProfileUsername')
            self.ton_wallet = data.get('tonWallet')
            
            logger.info(
                f"{self.session_name} | "
                f"User info: {self.username or 'Unknown'} | "
                f"Balance: {self.balance}"
            )
        return data

    async def get_tasks(self) -> list | None:
        tasks = await self._make_request('GET', 'task/active', params={'lang': self._get_language()})
        if not tasks:
            return None
            
        logger.success(f"{self.session_name} | Found {len(tasks)} total tasks")
        
        current_tasks = await self.get_current_tasks()
        claimed_task_ids = []
        verified_tasks = []
        verifying_task_ids = []
        
        if current_tasks:
            for current_task in current_tasks:
                task_id = current_task['taskId']
                status = current_task['status']
                
                if status == 'CLAIMED':
                    claimed_task_ids.append(task_id)
                elif status == 'COMPLETED':
                    original_task = next((t for t in tasks if t['task']['id'] == task_id), None)
                    if original_task:
                        verified_tasks.append({
                            **original_task,
                            'id': current_task['id'],
                            'status': 'COMPLETED'
                        })
                elif status == 'VERIFYING':
                    verifying_task_ids.append(task_id)
        
        filtered_tasks = []
        learn_tasks = []
        other_tasks = []
        tasks_to_complete = 0
        
        referrals_count = None

        table = Table(
            "№", "Title", "Type", "Reward", "Status",
            title=f"Tasks for {self.session_name}",
            title_style="bold magenta",
            header_style="bold cyan",
            border_style="bright_black"
        )
        
        task_number = 1
        
        for task in verified_tasks:
            tasks_to_complete += 1
            filtered_tasks.append(task)
            
            table.add_row(
                str(task_number),
                task['title'],
                task['task']['type'],
                str(task['task']['reward']),
                "[green]✓ Verified[/green]"
            )
            task_number += 1

        for task in tasks:
            task_info = task['task']
            task_type = task_info['type']
            reward = task_info['reward']
            title = task['title']
            task_id = task_info['id']
            
            if task_id in claimed_task_ids:
                continue
                
            if task_id in [t['task']['id'] for t in verified_tasks]:
                continue
                
            if task_id in verifying_task_ids:
                table.add_row(
                    str(task_number),
                    title,
                    task_type,
                    str(reward),
                    "[yellow]⌛ Verifying[/yellow]"
                )
                task_number += 1
                continue
            
            status = ""
            
            if task_type in ['TELEGRAM_CHANNEL_SUBSCRIPTION', 'URL', 'LEARN_LESSON']:
                if not settings.ENABLE_CHANNEL_SUBSCRIPTIONS and task_type == 'TELEGRAM_CHANNEL_SUBSCRIPTION':
                    continue
                    
                tasks_to_complete += 1
                if task_type == 'LEARN_LESSON':
                    learn_tasks.append(task)
                    status = "[yellow]In queue (Lesson)[/yellow]"
                else:
                    other_tasks.append(task)
                    status = "[yellow]In queue[/yellow]"
                    
                table.add_row(
                    str(task_number),
                    title,
                    task_type,
                    str(reward),
                    status
                )
                task_number += 1
                    
            elif task_type == 'RECRUIT_REFERRALS':
                if referrals_count is None:
                    referrals_count = await self.get_referrals_count() or 0
                    
                try:
                    required_refs = int(''.join(filter(str.isdigit, title)))
                    if referrals_count >= required_refs:
                        tasks_to_complete += 1
                        other_tasks.append(task)
                        status = f"[yellow]In queue ({referrals_count}/{required_refs})[/yellow]"
                    else:
                        status = f"[red]Skipped ({referrals_count}/{required_refs})[/red]"
                        
                    table.add_row(
                        str(task_number),
                        title,
                        "Referrals",
                        str(reward),
                        status
                    )
                    task_number += 1
                except ValueError:
                    logger.error(f"{self.session_name} | Failed to parse required referrals count from title: {title}")
            else:
                table.add_row(
                    str(task_number),
                    title,
                    task_type,
                    str(reward),
                    "[red]Not supported[/red]"
                )
                task_number += 1
        
        filtered_tasks.extend(learn_tasks)
        filtered_tasks.extend(other_tasks)
        
        if tasks_to_complete > 0:
            logger.info(f"{self.session_name} | {tasks_to_complete} tasks to complete")
        else:
            logger.info(f"{self.session_name} | No tasks to complete")
            
        console.print(table)
            
        return filtered_tasks

    async def claim_farming_reward(self) -> bool:
        result = await self._make_request(
            'POST', 
            'farming/claim',
            headers={'Origin': self.settings.BASE_URL.rstrip('/')}
        )
        
        if result is not None:
            if not result: 
                logger.success(f"{self.session_name} | Farming reward claimed")
                return True
                
            try:
                reward = float(result)
                logger.success(f"{self.session_name} | Farming reward claimed: {reward}")
                return True
            except ValueError:
                logger.error(f"{self.session_name} | Invalid reward format: {result}")
        return False

    async def farm(self) -> bool:
        result = await self._make_request(
            'POST', 
            'farming/farm',
            headers={'Origin': self.settings.BASE_URL.rstrip('/')}
        )
        
        if result is not None:
            logger.success(f"{self.session_name} | Farming started successfully")
            return True
        return False

    async def join_telegram_channel(self, channel_id: int, channel_url: str) -> bool:
        was_connected = self.tg_client.is_connected
        
        if not settings.ENABLE_CHANNEL_SUBSCRIPTIONS:
            logger.warning(f"{self.session_name} | Channel subscriptions are disabled in settings")
            return False
        
        try:
            logger.info(f"{self.session_name} | Subscribing to channel {channel_url}")
            
            if not was_connected:
                logger.info(f"{self.session_name} | Connecting to Telegram...")
                await self.tg_client.connect()

            try:
                if 'short.trustwallet.com' in channel_url or ('t.me/' not in channel_url and 'telegram.me/' not in channel_url):
                    async with ClientSession() as session:
                        async with session.get(channel_url, allow_redirects=True, ssl=False) as response:
                            if response.status == 200:
                                text = await response.text()
                                if 'tg://resolve?domain=' in text:
                                    channel_username = text.split('tg://resolve?domain=')[1].split('"')[0]
                                    logger.info(f"{self.session_name} | Found Telegram channel: {channel_username}")
                                    channel_url = f"https://t.me/{channel_username}"
            
                channel_username = channel_url.split('/')[-1]
                
                try:
                    await self.tg_client.join_chat(channel_username)
                    logger.success(f"{self.session_name} | Successfully subscribed to channel {channel_username}")
                    
                    chat = await self.tg_client.get_chat(channel_username)
                    await self._mute_and_archive_channel(chat.id)
                    return True
                    
                except FloodWait as e:
                    logger.warning(f"{self.session_name} | Flood wait for {e.value} seconds")
                    await asyncio.sleep(e.value)
                    return await self.join_telegram_channel(channel_id, channel_url)
                except UserBannedInChannel:
                    logger.error(f"{self.session_name} | Account is banned in the channel")
                    return False
                except (UsernameNotOccupied, UsernameInvalid):
                    logger.warning(f"{self.session_name} | Invalid channel name: {channel_username}")
                    return False
                except RPCError as e:
                    logger.error(f"{self.session_name} | Error while subscribing: {str(e)}")
                    return False
                    
            except Exception as e:
                logger.error(f"{self.session_name} | Error while subscribing to channel: {str(e)}")
                return False

        finally:
            if not was_connected and self.tg_client.is_connected:
                await self.tg_client.disconnect()

    async def _mute_and_archive_channel(self, channel_id: int) -> None:
        try:
            try:
                await self.tg_client.invoke(
                    raw.functions.account.UpdateNotifySettings(
                        peer=raw.types.InputNotifyPeer(
                            peer=await self.tg_client.resolve_peer(channel_id)
                        ),
                        settings=raw.types.InputPeerNotifySettings(
                            mute_until=2147483647
                        )
                    )
                )
            except RPCError:
                pass

            try:
                await self.tg_client.invoke(
                    raw.functions.folders.EditPeerFolders(
                        folder_peers=[
                            raw.types.InputFolderPeer(
                                peer=await self.tg_client.resolve_peer(channel_id),
                                folder_id=1
                            )
                        ]
                    )
                )
            except RPCError:
                pass

        except Exception:
            pass

    async def verify_task(self, user_task_id: str, task_type: str, telegram_channel_id: int = None) -> bool:
        data = {
            "userTaskId": user_task_id,
            "type": task_type,
            "lang": self._get_language()
        }
        
        if task_type == 'TELEGRAM_CHANNEL_SUBSCRIPTION' and telegram_channel_id:
            data["telegramChannelId"] = telegram_channel_id
            
        if task_type == 'LEARN_LESSON':
            result = await self._make_request(
                'POST',
                'task/verify',
                headers=get_task_headers(self.proxy_country),
                json=data
            )
            
            if result:
                status = result.get('status')
                if status in ['VERIFYING', 'FARMING', 'COMPLETED']:
                    for attempt in range(3):
                        await asyncio.sleep(5)
                        current_tasks = await self.get_current_tasks()
                        if not current_tasks:
                            continue
                            
                        current_task = next((t for t in current_tasks if t['id'] == user_task_id), None)
                        if not current_task:
                            continue
                            
                        current_status = current_task.get('status')
                        logger.info(f"{self.session_name} | Verification status: {current_status}")
                        
                        if current_status == 'COMPLETED':
                            return True
                            
                    return False
                    
                logger.error(f"{self.session_name} | Verification failed: {status}")
                return False
                
        else:
            result = await self._make_request(
                'POST',
                'task/verify',
                headers=get_task_headers(self.proxy_country),
                json=data
            )
            
            if result:
                status = result.get('status')
                if status in ['VERIFYING', 'FARMING', 'COMPLETED']:
                    return True
                logger.error(f"{self.session_name} | Verification failed: {status}")
                
        return False

    async def complete_task(self, task: dict) -> bool:
        task_info = task['task']
        task_type = task_info['type']
        task_id = task_info['id']
        title = task['title']
        reward = task_info['reward']

        logger.info(f"{self.session_name} | Task: {title} | {task_type} | {reward} NUTS")
        
        current_tasks = await self.get_current_tasks()
        if current_tasks:
            current_task = next((t for t in current_tasks if t['taskId'] == task_id), None)
            if current_task:
                status = current_task['status']
                logger.info(f"{self.session_name} | Current task status: {status}")
                
                if status == 'CLAIMED':
                    logger.info(f"{self.session_name} | Task already claimed")
                    return True
                    
                elif status == 'COMPLETED':
                    received_reward = await self.claim_task_reward(current_task['id'])
                    if received_reward > 0:
                        logger.success(f"{self.session_name} | Received {received_reward} NUTS")
                        await asyncio.sleep(random.uniform(8, 12))
                        return True
                    return False
                    
                elif status == 'VERIFYING':
                    logger.info(f"{self.session_name} | Task is being verified")
                    for attempt in range(3):
                        await asyncio.sleep(5)
                        updated_tasks = await self.get_current_tasks()
                        if not updated_tasks:
                            continue
                            
                        updated_task = next((t for t in updated_tasks if t['taskId'] == task_id), None)
                        if not updated_task:
                            continue
                            
                        updated_status = updated_task.get('status')
                        logger.info(f"{self.session_name} | Updated task status: {updated_status}")
                        
                        if updated_status == 'COMPLETED':
                            received_reward = await self.claim_task_reward(updated_task['id'])
                            if received_reward > 0:
                                logger.success(f"{self.session_name} | Received {received_reward} NUTS")
                                await asyncio.sleep(random.uniform(8, 12))
                                return True
                        elif updated_status == 'CLAIMED':
                            return True
                            
                    logger.error(f"{self.session_name} | Verification timeout")
                    return False
                    
                elif status == 'PENDING':
                    if not await self.verify_task(current_task['id'], task_type, task.get('telegramChannelId')):
                        return False
                    await asyncio.sleep(random.uniform(5, 8))
                    return True

        completion_id = await self.start_task(task_id, task_type)
        if not completion_id:
            return False
            
        await asyncio.sleep(random.uniform(5, 8))

        if task_type == 'URL':
            url = task.get('link')
            if not url:
                return False
                
            if 'short.trustwallet.com' in url or 't.me/' in url:
                try:
                    async with ClientSession() as session:
                        async with session.get(url, allow_redirects=True, ssl=False) as response:
                            if response.status == 200:
                                text = await response.text()
                                if 'tg://resolve?domain=' in text:
                                    channel_username = text.split('tg://resolve?domain=')[1].split('"')[0]
                                    if not await self.join_telegram_channel(None, f"https://t.me/{channel_username}"):
                                        return False
                except Exception as e:
                    logger.error(f"{self.session_name} | URL task error: {str(e)}")
                    return False

        elif task_type == 'TELEGRAM_CHANNEL_SUBSCRIPTION':
            channel_id = task.get('telegramChannelId')
            channel_url = task.get('link')
            
            if not await self.join_telegram_channel(channel_id, channel_url):
                return False

        elif task_type == 'RECRUIT_REFERRALS':
            try:
                required_refs = int(''.join(filter(str.isdigit, title)))
                current_refs = await self.get_referrals_count()
                if current_refs is None or current_refs < required_refs:
                    return False
            except ValueError:
                return False

        await asyncio.sleep(random.uniform(5, 8))
        
        if not await self.verify_task(completion_id, task_type):
            return False
            
        await asyncio.sleep(random.uniform(5, 8))
        
        received_reward = await self.claim_task_reward(completion_id)
        if received_reward > 0:
            logger.success(f"{self.session_name} | Received {received_reward} NUTS")
            await asyncio.sleep(random.uniform(8, 12))
            return True
            
        return False

    async def start_task(self, task_id: str, task_type: str) -> str | None:
        data = {
            "taskId": task_id,
            "type": task_type,
            "lang": self._get_language()
        }
        
        result = await self._make_request(
            'POST',
            'task/start',
            headers=get_task_headers(self.proxy_country),
            json=data
        )
        
        if result:
            completion_id = result.get('id')
            if completion_id:
                return completion_id
        return None

    async def claim_start_bonus(self) -> bool:
        result = await self._make_request(
            'POST',
            'farming/startBonus',
            headers={'Origin': self.settings.BASE_URL.rstrip('/')}
        )
        
        if isinstance(result, (int, float)):
            logger.success(f"{self.session_name} | Start bonus received: {result}")
            return True
        logger.error(f"{self.session_name} | Invalid start bonus format: {result}")
        return False

    async def claim_task_reward(self, completion_id: str) -> int:
        result = await self._make_request(
            'POST',
            f'task/claim/{completion_id}',
            headers={
                'accept': '*/*',
                'accept-language': 'ru',
                'content-type': 'application/json',
                'origin': 'https://nutsfarm.crypton.xyz',
                'referer': 'https://nutsfarm.crypton.xyz/',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site'
            }
        )
        
        if isinstance(result, (int, float)):
            logger.success(f"{self.session_name} | Reward claimed: {result}")
            return int(result)
        logger.error(f"{self.session_name} | Invalid reward format: {result}")
        return 0

    async def get_current_tasks(self) -> list | None:
        return await self._make_request('GET', 'task/current')

    async def login(self, auth_data: str) -> bool:
        settings = Settings()
        url = f"{settings.BASE_URL}api/{settings.API_VERSION}/auth/login"
        headers = self.get_headers()
        headers['content-type'] = 'text/plain;charset=UTF-8'
        
        try:
            async with ClientSession() as session:
                async with session.post(
                    url=url,
                    headers=headers,
                    data=auth_data,
                    ssl=False
                ) as response:
                    if response.status == 404:
                        logger.info(f"{self.session_name} | Account not found, registration required")
                        return False
                        
                    response.raise_for_status()
                    auth_result = await response.json()
                    
                    if auth_result.get('accessToken'):
                        self.token = auth_result['accessToken']
                        self.refresh_token = auth_result.get('refreshToken')
                        logger.success(f"{self.session_name} | Successful authorization")
                        return True
                    else:
                        logger.error(f"{self.session_name} | Authorization error: invalid response format")
                        return False
                        
        except Exception as error:
            logger.error(f"{self.session_name} | Error during authorization: {str(error)}")
            return False

    async def refresh_access_token(self) -> bool:
        if not self.refresh_token:
            return False
            
        result = await self._make_request(
            'POST',
            'auth/token',
            headers=get_auth_headers(self.proxy_country),
            json={"refreshToken": self.refresh_token},
            with_auth=False
        )
        
        if result and result.get('accessToken'):
            self.token = result['accessToken']
            self.refresh_token = result.get('refreshToken')
            logger.success(f"{self.session_name} | Token successfully refreshed")
            return True
            
        return False

    async def register(self, auth_data: str, referral_code: str = None) -> bool:
        settings = Settings()
        base_url = settings.BASE_URL.rstrip('/')
        url = f"{base_url}/api/{settings.API_VERSION}/auth/register"
        headers = self.get_headers()
        headers['content-type'] = 'application/json'
        
        if not referral_code and 'start_param=' in auth_data:
            try:
                start_param = auth_data.split('start_param=')[1].split('&')[0]
                if start_param.startswith('ref_'):
                    referral_code = start_param.replace('ref_', '')
            except Exception:
                pass
        
        data = {
            "authData": auth_data,
            "language": self._get_language()
        }
        
        if referral_code:
            if not referral_code.startswith('ref_'):
                referral_code = f"ref_{referral_code}"
            data["referralCode"] = referral_code.replace('ref_', '')
            
        try:
            async with ClientSession() as session:
                async with session.post(
                    url=url,
                    headers=headers,
                    json=data,
                    ssl=False
                ) as response:
                    response.raise_for_status()
                    auth_result = await response.json()
                    
                    if auth_result.get('accessToken'):
                        self.token = auth_result['accessToken']
                        self.refresh_token = auth_result.get('refreshToken')
                        logger.success(f"{self.session_name} | Successful registration")
                        return True
                    else:
                        logger.error(f"{self.session_name} | Registration error: invalid response format")
                        return False
                        
        except ClientResponseError as error:
            logger.error(f"{self.session_name} | Registration error: {error.status}")
            return False
        except Exception as error:
            logger.error(f"{self.session_name} | Registration error")
            return False

    async def authorize(self, auth_data: str, referral_code: str = None) -> bool:
        if await self.login(auth_data):
            return True
            
        return await self.register(auth_data, referral_code)

    async def check_and_claim_streak(self) -> bool:
        streak_info = await self._make_request(
            'GET',
            'streak/current/info',
            params={'timezone': 'Europe/Moscow'}
        )
        
        if not streak_info:
            return False
            
        if streak_info.get('streakRewardReceivedToday'):
            logger.info(f"{self.session_name} | Streak reward already claimed today")
            return False

        days_missed = streak_info.get('daysMissed', 0)
        freeze_cost = streak_info.get('missedDaysFreezeCost', 0)
        
        use_freeze = False
        if days_missed > 0 and freeze_cost > 0:
            if self.balance >= freeze_cost:
                use_freeze = True
                logger.info(
                    f"{self.session_name} | "
                    f"Days missed: {days_missed}, "
                    f"freeze cost: {freeze_cost} NUTS. "
                    f"Using freeze."
                )
            else:
                logger.warning(
                    f"{self.session_name} | "
                    f"Not enough NUTS to freeze streak. "
                    f"Required: {freeze_cost}, Balance: {self.balance}"
                )
                
        result = await self._make_request(
            'POST',
            'streak/current/claim',
            params={
                'timezone': 'Europe/Moscow',
                'payForFreeze': str(use_freeze).lower()
            },
            headers={'Origin': self.settings.BASE_URL.rstrip('/')}
        )
        
        if result:
            today_info = streak_info.get('todayStreakInfo', {})
            day_number = today_info.get('dayNumber', 1)
            nuts_reward = today_info.get('nutsReward', 0)
            
            logger.success(
                f"{self.session_name} | "
                f"Streak reward claimed for day {day_number}: {nuts_reward} NUTS"
            )
            return True
        return False

    async def get_farming_status(self) -> dict | None:
        status = await self._make_request('GET', 'farming/current')
        if not status:
            return None

        status_type = status.get('status')
        logger.info(f"{self.session_name} | Farming status: {status_type}")
        
        if status_type == 'FARMING':
            finish_time = status.get('lastFarmingFinishAt')
            if finish_time:
                try:
                    end_datetime = datetime.fromisoformat(finish_time.replace('Z', '+00:00'))
                    seconds_left = (end_datetime - datetime.now(timezone.utc)).total_seconds()
                    if seconds_left > 0:
                        hours = int(seconds_left // 3600)
                        minutes = int((seconds_left % 3600) // 60)
                        logger.info(f"{self.session_name} | Farming will end in {hours}h {minutes}m")
                        return {'status': 'FARMING', 'seconds_left': seconds_left}
                except Exception as e:
                    logger.error(f"{self.session_name} | Error parsing farming end time: {e}")
                    
        return {'status': status_type}

    async def get_active_stories(self) -> list | None:
        return await self._make_request('GET', 'story/active')

    async def get_current_stories(self) -> list | None:
        return await self._make_request('GET', 'story/current')

    async def read_story(self, story_id: str) -> int | None:
        result = await self._make_request(
            'POST',
            f'story/read/{story_id}',
            headers={'Origin': 'https://nutsfarm.crypton.xyz'}
        )
        
        if isinstance(result, (int, float)):
            logger.success(f"{self.session_name} | Story reward received: {int(result)}")
            return int(result)
        return None

    async def process_stories(self) -> None:
        active_stories = await self.get_active_stories()
        if not active_stories:
            return

        current_stories = await self.get_current_stories()
        completed_story_ids = []
        
        if current_stories:
            completed_story_ids = [story['story']['id'] for story in current_stories]

        total_reward = 0
        for story in active_stories:
            story_id = story['id']
            if story_id not in completed_story_ids:
                reward = await self.read_story(story_id)
                if reward:
                    total_reward += reward
                    await asyncio.sleep(random.uniform(settings.ACTION_DELAY[0], settings.ACTION_DELAY[1]))

        if total_reward > 0:
            logger.info(f"{self.session_name} | Total story rewards: {total_reward}")

    async def get_referral_reward_amount(self) -> float | None:
        result = await self._make_request(
            'GET', 
            'user/current/referrals/amount',
            headers=get_referral_headers(self.proxy_country)
        )
        if isinstance(result, (int, float)):
            logger.info(f"{self.session_name} | Available referral reward: {result}")
            return float(result)
        return None
    
    async def get_referral_claim_time(self) -> datetime | None:
        result = await self._make_request(
            'GET', 
            'user/current/referrals/time',
            headers=get_referral_headers(self.proxy_country)
        )
        if isinstance(result, str):
            try:
                claim_time = datetime.fromisoformat(result.replace('Z', '+00:00'))
                logger.info(f"{self.session_name} | Referral reward claim time: {claim_time}")
                return claim_time
            except ValueError:
                logger.error(f"{self.session_name} | Invalid claim time format: {result}")
        return None
    
    async def claim_referral_reward(self) -> float | None:
        result = await self._make_request(
            'POST', 
            'user/current/referrals/claim',
            headers=get_referral_headers(self.proxy_country)
        )
        if isinstance(result, (int, float)):
            logger.success(f"{self.session_name} | Referral reward claimed: {result}")
            return float(result)
        return None
    
    async def check_and_claim_referral_reward(self) -> bool:
        try:
            reward_amount = await self.get_referral_reward_amount()
            if not reward_amount or reward_amount <= 0:
                logger.info(f"{self.session_name} | No referral reward available")
                return False
                
            claim_time = await self.get_referral_claim_time()
            if not claim_time:
                return False
                
            current_time = datetime.now(timezone.utc)
            if current_time < claim_time:
                time_left = (claim_time - current_time).total_seconds()
                hours = int(time_left // 3600)
                minutes = int((time_left % 3600) // 60)
                logger.info(f"{self.session_name} | Referral reward will be available in {hours}h {minutes}m")
                
                next_run = claim_time + timedelta(minutes=1)
                logger.info(f"{self.session_name} | Next referral claim attempt scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                return False
                
            claimed_amount = await self.claim_referral_reward()
            return claimed_amount is not None and claimed_amount > 0
            
        except Exception as e:
            logger.error(f"{self.session_name} | Error checking referral reward: {str(e)}")
            return False

    async def get_referrals_count(self) -> int | None:
        result = await self._make_request(
            'GET',
            'user/current/referrals',
            params={'page': 1, 'size': 1}
        )
        
        if isinstance(result, dict):
            total = result.get('total')
            if total is not None:
                logger.info(f"{self.session_name} | Total referrals: {total}")
                return int(total)
        return None
    
    async def get_available_lessons(self) -> list:
        result = await self._make_request(
            'GET',
            'learn/active',
            params={'lang': self._get_language()}
        )
        if not result:
            return []
        available_lessons = []
        for module in result:
            if not module.get('isActive') or not module.get('isPublished'):
                continue
            lessons = module.get('lessons', [])
            for lesson in lessons:
                if lesson.get('reward', 0) > 0 and not lesson.get('isClaimed'):
                    lesson['moduleId'] = module['id']
                    lesson['moduleTitle'] = module['title']
                    available_lessons.append(lesson)
        return sorted(available_lessons, key=lambda x: (x['pageNumber'], x['reward']))

    async def claim_lesson_reward(self, lesson_id: str) -> int:
        if lesson_id in self.completed_lessons:
            logger.info(f"{self.session_name} | Lesson {lesson_id} is already completed")
            return 0
        result = await self._make_request(
            'POST',
            f'learn/claim/{lesson_id}',
            headers={'Origin': 'https://nutsfarm.crypton.xyz'}
        )
        if isinstance(result, (int, float)):
            reward = int(result)
            self.completed_lessons.add(lesson_id)
            logger.success(f"{self.session_name} | Reward claimed for lesson: {reward}")
            return reward
        return 0

    async def process_lessons(self) -> None:
        available_lessons = await self.get_available_lessons()
        if not available_lessons:
            logger.info(f"{self.session_name} | No available lessons")
            return
        total_reward = 0
        completed = 0
        for lesson in available_lessons:
            lesson_id = lesson['id']
            title = lesson['title']
            reward = lesson['reward']
            module_title = lesson['moduleTitle']
            delay = random.uniform(5, 10)
            logger.info(f"{self.session_name} | Waiting {delay:.1f} seconds before processing lesson...")
            await asyncio.sleep(delay)
            logger.info(
                f"{self.session_name} | "
                f"Processing lesson: {title} | "
                f"Module: {module_title} | "
                f"Reward: {reward}"
            )
            reward = await self.claim_lesson_reward(lesson_id)
            if reward > 0:
                total_reward += reward
                completed += 1
                delay = random.uniform(8, 15)
                logger.info(f"{self.session_name} | Waiting {delay:.1f} seconds...")
                await asyncio.sleep(delay)
        if completed > 0:
            logger.info(
                f"{self.session_name} | "
                f"Lessons completed: {completed} | "
                f"Total reward: {total_reward}"
            )
            
async def run_tappers(tg_clients: list[Client], proxies: list[str | None]):
    session_sleep_times = {}
    active_sessions = set()
    
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            sessions_to_run = []
            
            for client, proxy in zip(tg_clients, proxies):
                session_name = client.name
                
                if session_name in session_sleep_times:
                    wake_time = session_sleep_times[session_name]
                    if current_time < wake_time:
                        time_left = (wake_time - current_time).total_seconds()
                        hours = int(time_left // 3600)
                        minutes = int((time_left % 3600) // 60)
                        logger.info(f"{session_name} | Still sleeping for {hours}h {minutes}m")
                        continue
                    else:
                        logger.info(f"{session_name} | Waking up from sleep")
                        session_sleep_times.pop(session_name)
                        active_sessions.add(session_name)
                        sessions_to_run.append((client, proxy))
                else:
                    active_sessions.add(session_name)
                    sessions_to_run.append((client, proxy))

            for client, proxy in sessions_to_run:
                tapper = Tapper(client)
                try:
                    logger.info(f"{'='*50}")
                    logger.info(f"Processing session: {tapper.session_name}")

                    tg_web_data = await tapper.get_tg_web_data(proxy)
                    if not tg_web_data:
                        logger.error(f"{tapper.session_name} | Failed to get authorization data")
                        continue

                    if not await tapper.authorize(tg_web_data):
                        logger.error(f"{tapper.session_name} | Authorization error")
                        continue

                    initial_balance = 0
                    user_info = await tapper.get_user_info()
                    if user_info:
                        initial_balance = tapper.balance
                        logger.info(f"{tapper.session_name} | Initial balance: {initial_balance}")
                        
                        if not user_info.get('isStartBonusClaimed'):
                            if await tapper.claim_start_bonus():
                                logger.success(f"{tapper.session_name} | Start bonus claimed")
                    
                    if await tapper.check_and_claim_streak():
                        logger.success(f"{tapper.session_name} | Streak reward claimed")

                    if await tapper.check_and_claim_referral_reward():
                        logger.success(f"{tapper.session_name} | Referral reward claimed")

                    await tapper.process_stories()
                    
                    await tapper.process_lessons()
                    
                    completed_tasks = 0
                    total_rewards = 0
                    
                    tasks = await tapper.get_tasks()
                    if tasks:
                        for task in tasks:
                            if await tapper.complete_task(task):
                                completed_tasks += 1
                                total_rewards += task['task']['reward']
                                delay = random.uniform(5, 10)
                                logger.info(f"{tapper.session_name} | Waiting {delay:.1f} sec...")
                                await asyncio.sleep(delay)
                    
                    farming_status = await tapper.get_farming_status()
                    if farming_status:
                        status = farming_status.get('status')
                        seconds_left = farming_status.get('seconds_left', 0)
                        
                        if status == 'FARMING' and seconds_left > 0:
                            next_run = current_time + timedelta(seconds=seconds_left + 60)
                            session_sleep_times[tapper.session_name] = next_run
                            if tapper.session_name in active_sessions:
                                active_sessions.remove(tapper.session_name)
                            hours = int(seconds_left // 3600)
                            minutes = int((seconds_left % 3600) // 60)
                            logger.info(f"{tapper.session_name} | Going to sleep for {hours}h {minutes}m")
                            logger.info(f"{tapper.session_name} | Next run scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        elif status == 'READY_TO_FARM':
                            if await tapper.farm():
                                logger.success(f"{tapper.session_name} | Farming started")
                                updated_status = await tapper.get_farming_status()
                                if updated_status and updated_status.get('seconds_left', 0) > 0:
                                    seconds_left = updated_status['seconds_left']
                                    next_run = current_time + timedelta(seconds=seconds_left + 60)
                                    session_sleep_times[tapper.session_name] = next_run
                                    if tapper.session_name in active_sessions:
                                        active_sessions.remove(tapper.session_name)
                                    hours = int(seconds_left // 3600)
                                    minutes = int((seconds_left % 3600) // 60)
                                    logger.info(f"{tapper.session_name} | Going to sleep for {hours}h {minutes}m")
                                    logger.info(f"{tapper.session_name} | Next run scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        else:
                            if await tapper.claim_farming_reward():
                                logger.success(f"{tapper.session_name} | Farming reward claimed")
                                if await tapper.farm():
                                    logger.success(f"{tapper.session_name} | Farming started")
                                    updated_status = await tapper.get_farming_status()
                                    if updated_status and updated_status.get('seconds_left', 0) > 0:
                                        seconds_left = updated_status['seconds_left']
                                        next_run = current_time + timedelta(seconds=seconds_left + 60)
                                        session_sleep_times[tapper.session_name] = next_run
                                        if tapper.session_name in active_sessions:
                                            active_sessions.remove(tapper.session_name)
                                        hours = int(seconds_left // 3600)
                                        minutes = int((seconds_left % 3600) // 60)
                                        logger.info(f"{tapper.session_name} | Going to sleep for {hours}h {minutes}m")
                                        logger.info(f"{tapper.session_name} | Next run scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S UTC')}")

                    final_balance = initial_balance
                    user_info = await tapper.get_user_info()
                    if user_info:
                        final_balance = tapper.balance
                    
                    logger.info(f"\n{tapper.session_name} | Summary:")
                    logger.info(f"├── Completed tasks: {completed_tasks}")
                    logger.info(f"├── Total rewards: {total_rewards}")
                    logger.info(f"├── Initial balance: {initial_balance}")
                    logger.info(f"── Final balance: {final_balance}")
                    logger.info(f"└── Gain: {final_balance - initial_balance}")

                except Exception as e:
                    logger.error(f"{tapper.session_name} | Unexpected error: {e}")
                finally:
                    logger.info(f"Session processing completed: {tapper.session_name}")
                    logger.info(f"{'='*50}\n")

            if active_sessions:
                await asyncio.sleep(10)
            else:
                if session_sleep_times:
                    next_wake = min(session_sleep_times.values())
                    sleep_seconds = max(10, (next_wake - datetime.now(timezone.utc)).total_seconds())
                    next_session = min(session_sleep_times.items(), key=lambda x: x[1])[0]
                    hours = int(sleep_seconds // 3600)
                    minutes = int((sleep_seconds % 3600) // 60)
                    logger.info(f"All sessions are sleeping. {next_session} will wake up in {hours}h {minutes}m")
                    await asyncio.sleep(sleep_seconds)
                else:
                    logger.warning("No active or sleeping sessions found")
                    await asyncio.sleep(60)

        except Exception as e:
            delay = random.randint(settings.RETRY_DELAY[0], settings.RETRY_DELAY[1])
            logger.error(f"Critical error: {e}")
            logger.info(f"⏳ Waiting {delay} sec before retrying...")
            await asyncio.sleep(delay)

async def run_tapper(tg_client: Client, proxy: str | None):
    await run_tappers([tg_client], [proxy])
