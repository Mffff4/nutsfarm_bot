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

from bot.core.user_agents import load_or_generate_user_agent
from bot.exceptions import InvalidSession
from aiohttp import ClientResponseError, ClientSession, ClientTimeout
import json

from pyrogram import raw
from bot.utils.logger import logger
from bot.config import settings

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
        self.user_id = 0
        self.username = None
        self.first_name = None
        self.last_name = None
        self.token = None
        self.client_lock = asyncio.Lock()
        self.user_agent = load_or_generate_user_agent(self.session_name)
        self.retry_count = 0
        self.balance = 0
        self.game_energy = 0
        self.referral_code = None
        self.crypton_profile_username = None
        self.ton_wallet = None

    def get_headers(self, with_auth: bool = False):
        headers = {
            'Host': 'nutsfarm.crypton.xyz',
            'Sec-Fetch-Site': 'same-origin',
            'Accept-Language': 'ru',
            'Connection': 'keep-alive', 
            'Sec-Fetch-Mode': 'cors',
            'Accept': '*/*',
            'User-Agent': self.user_agent,
            'Sec-Fetch-Dest': 'empty',
            'Referer': f'{settings.BASE_URL}/'
        }
        
        if with_auth and self.token:
            headers['Authorization'] = f'Bearer {self.token}'
            
        return headers

    async def get_tg_web_data(self, proxy: str | None) -> str:
        async with self.client_lock:
            logger.info(f"{self.session_name} | Started obtaining tg_web_data")
            if proxy:
                proxy = Proxy.from_str(proxy)
                if settings.LOG_PROXY:
                    logger.info(f"{self.session_name} | Using proxy: {proxy.host}:{proxy.port}")
                proxy_dict = dict(
                    scheme=proxy.protocol,
                    hostname=proxy.host,
                    port=proxy.port,
                    username=proxy.login,
                    password=proxy.password
                )
            else:
                proxy_dict = None
                if settings.LOG_PROXY:
                    logger.info(f"{self.session_name} | Proxy not used")

            self.tg_client.proxy = proxy_dict

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

                self.start_param = random.choices([settings.REF_ID, "DTGYWCIWEZSAGUB"], weights=[50, 50], k=1)[0]
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

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> dict | None:
        if not self.token and kwargs.get('with_auth', True):
            return None
            
        url = f"{settings.API_URL}/{endpoint}"
        headers = self.get_headers(with_auth=kwargs.pop('with_auth', True))
        
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
            
        retry_count = 0
        
        while retry_count < settings.MAX_RETRIES:
            try:
                async with ClientSession() as session:
                    timeout = random.uniform(settings.REQUEST_TIMEOUT[0], settings.REQUEST_TIMEOUT[1])
                    async with getattr(session, method.lower())(
                        url=url,
                        headers=headers,
                        ssl=False,
                        timeout=ClientTimeout(total=timeout),
                        **kwargs
                    ) as response:
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

    async def get_user_info(self) -> dict | None:
        data = await self._make_request('GET', 'user/current', params={'lang': 'RU'})
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
        tasks = await self._make_request('GET', 'task/active', params={'lang': 'ru'})
        if not tasks:
            return None
            
        logger.success(f"{self.session_name} | Found {len(tasks)} total tasks")
        
        current_tasks = await self.get_current_tasks()
        claimed_task_ids = []
        completed_tasks = []
        
        if current_tasks:
            for current_task in current_tasks:
                task_id = current_task['taskId']
                status = current_task['status']
                
                if status == 'CLAIMED':
                    claimed_task_ids.append(task_id)
                elif status == 'COMPLETED':
                    completed_tasks.append(current_task)
        
        filtered_tasks = []
        tasks_to_complete = 0
        
        for task in tasks:
            task_info = task['task']
            task_type = task_info['type']
            reward = task_info['reward']
            title = task['title']
            task_id = task_info['id']
            
            if task_id in claimed_task_ids:
                continue
            
            completed_task = next((t for t in completed_tasks if t['taskId'] == task_id), None)
            if completed_task:
                tasks_to_complete += 1
                logger.info(
                    f"{self.session_name} | "
                    f"Task: {title} | "
                    f"Type: {task_type} | "
                    f"Reward: {reward} | "
                    f"✅ Added to queue (need to claim reward)"
                )
                filtered_tasks.append(task)
                continue
            
            if task_type in ['TELEGRAM_CHANNEL_SUBSCRIPTION', 'URL']:
                if not settings.ENABLE_CHANNEL_SUBSCRIPTIONS and task_type == 'TELEGRAM_CHANNEL_SUBSCRIPTION':
                    continue
                    
                tasks_to_complete += 1
                channel_id = task.get('telegramChannelId')
                task_type_str = "Channel subscription" if task_type == 'TELEGRAM_CHANNEL_SUBSCRIPTION' else "URL"
                
                logger.info(
                    f"{self.session_name} | "
                    f"Task: {title} | "
                    f"Type: {task_type_str} | "
                    f"{'Channel ID: ' + str(channel_id) + ' | ' if channel_id else ''}"
                    f"Reward: {reward} | "
                    f"✅ Added to queue"
                )
                filtered_tasks.append(task)
            else:
                logger.info(
                    f"{self.session_name} | "
                    f"Task: {title} | "
                    f"Type: {task_type} | "
                    f"Reward: {reward} | "
                    f"⚠️ Skipped (unsupported type)"
                )
        
        if tasks_to_complete > 0:
            logger.info(f"{self.session_name} | {tasks_to_complete} tasks to complete")
        else:
            logger.info(f"{self.session_name} | No tasks to complete")
            
        return filtered_tasks

    async def claim_farming_reward(self) -> bool:
        result = await self._make_request(
            'POST', 
            'farming/claim',
            headers={'Origin': settings.BASE_URL}
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
            headers={'Origin': settings.BASE_URL}
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
            logger.info(f"{self.session_name} | Notifications disabled")

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
            logger.info(f"{self.session_name} | Channel added to archive")
        except RPCError as e:
            logger.warning(f"{self.session_name} | Error while configuring channel: {str(e)}")

    async def complete_task(self, task: dict) -> bool:
        task_info = task['task']
        task_type = task_info['type']
        task_id = task_info['id']
        title = task['title']
        reward = task_info['reward']

        logger.info(
            f"{self.session_name} | "
            f"Starting task completion: {title} | "
            f"Type: {task_type} | "
            f"Reward: {reward}"
        )

        current_tasks = await self.get_current_tasks()
        if current_tasks:
            for current_task in current_tasks:
                if current_task['taskId'] == task_id:
                    status = current_task['status']
                    logger.info(f"{self.session_name} | Current task status: {status}")
                    
                    if status == 'CLAIMED':
                        logger.info(f"{self.session_name} | Task already completed and reward claimed")
                        return True
                    elif status == 'COMPLETED':
                        logger.info(f"{self.session_name} | Task already completed, claiming reward")
                        received_reward = await self.claim_task_reward(current_task['id'])
                        return received_reward > 0
                    elif status == 'PENDING':
                        logger.info(f"{self.session_name} | Task already started, verifying")
                        
                        if task_type == 'TELEGRAM_CHANNEL_SUBSCRIPTION':
                            channel_id = task['telegramChannelId']
                            channel_url = task['link']
                            
                            if not await self.join_telegram_channel(channel_id, channel_url):
                                logger.error(f"{self.session_name} | Failed to subscribe to channel {channel_url}")
                                return False
                                
                            await asyncio.sleep(random.uniform(2, 4))
                            
                            if not await self.verify_task(current_task['id'], task_type, channel_id):
                                logger.error(f"{self.session_name} | Failed to verify task")
                                return False

                        max_attempts = 10
                        for attempt in range(max_attempts):
                            await asyncio.sleep(random.uniform(3, 5))
                            check_tasks = await self.get_current_tasks()
                            if check_tasks:
                                for check_task in check_tasks:
                                    if check_task['id'] == current_task['id']:
                                        if check_task['status'] == 'COMPLETED':
                                            logger.success(f"{self.session_name} | Task completed, claiming reward")
                                            received_reward = await self.claim_task_reward(check_task['id'])
                                            return received_reward > 0
                                        logger.info(f"{self.session_name} | Task status: {check_task['status']}, waiting...")
                    
                        logger.error(f"{self.session_name} | Task completion timeout exceeded")
                        return False

        logger.info(f"{self.session_name} | Starting new task {task_id}")
        completion_id = await self.start_task(task_id, task_type)
        if not completion_id:
            logger.error(f"{self.session_name} | Failed to start task")
            return False
            
        await asyncio.sleep(random.uniform(2, 4))

        if task_type == 'TELEGRAM_CHANNEL_SUBSCRIPTION':
            channel_id = task['telegramChannelId']
            channel_url = task['link']
            
            if not await self.join_telegram_channel(channel_id, channel_url):
                logger.error(f"{self.session_name} | Failed to subscribe to channel {channel_url}")
                return False
                
            await asyncio.sleep(random.uniform(2, 4))
            
            if not await self.verify_task(completion_id, task_type, channel_id):
                logger.error(f"{self.session_name} | Failed to verify task")
                return False
                        
        max_attempts = 10
        for attempt in range(max_attempts):
            await asyncio.sleep(random.uniform(3, 5))
            current_tasks = await self.get_current_tasks()
            if current_tasks:
                for current_task in current_tasks:
                    if current_task['id'] == completion_id:
                        if current_task['status'] == 'COMPLETED':
                            logger.success(f"{self.session_name} | Task completed, claiming reward")
                            await asyncio.sleep(random.uniform(2, 4))
                            received_reward = await self.claim_task_reward(completion_id)
                            return received_reward > 0
                        logger.info(f"{self.session_name} | Task status: {current_task['status']}, waiting...")
                            
        logger.error(f"{self.session_name} | Task completion timeout exceeded")
        return False

    async def start_task(self, task_id: str, task_type: str) -> str | None:
        data = {
            "taskId": task_id,
            "type": task_type,
            "lang": "RU"
        }
        
        result = await self._make_request(
            'POST',
            'task/start',
            headers={
                'Origin': settings.BASE_URL,
                'Content-Type': 'application/json',
                'Referer': f'{settings.BASE_URL}/tasks'
            },
            json=data
        )
        
        if result:
            completion_id = result.get('id')
            if completion_id:
                logger.success(f"{self.session_name} | Task {task_id} started successfully")
                return completion_id
            logger.error(f"{self.session_name} | Failed to get task ID")
        return None

    async def claim_task_reward(self, completion_id: str) -> int:
        result = await self._make_request(
            'POST',
            f'task/claim/{completion_id}',
            headers={'Origin': settings.BASE_URL}
        )
        
        if isinstance(result, (int, float)):
            logger.success(f"{self.session_name} | Reward claimed: {result}")
            return int(result)
        logger.error(f"{self.session_name} | Invalid reward format: {result}")
        return 0

    async def get_current_tasks(self) -> list | None:
        return await self._make_request('GET', 'task/current')

    async def login(self, auth_data: str) -> bool:
        url = 'https://nutsfarm.crypton.xyz/api/v1/auth/login'
        headers = self.get_headers()
        headers['Origin'] = 'https://nutsfarm.crypton.xyz'
        headers['Content-Type'] = 'text/plain;charset=UTF-8'
        
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
                        logger.success(f"{self.session_name} | Successful authorization")
                        return True
                    else:
                        logger.error(f"{self.session_name} | Authorization error: invalid response format")
                        return False
                        
        except Exception as error:
            logger.error(f"{self.session_name} | Error during authorization: {str(error)}")
            return False

    async def register(self, auth_data: str, referral_code: str = None) -> bool:
        url = 'https://nutsfarm.crypton.xyz/api/v1/auth/register'
        headers = {
            'Host': 'nutsfarm.crypton.xyz',
            'Accept': '*/*',
            'Sec-Fetch-Site': 'same-origin',
            'Accept-Language': 'ru',
            'Sec-Fetch-Mode': 'cors',
            'Origin': 'https://nutsfarm.crypton.xyz',
            'User-Agent': self.user_agent,
            'Referer': f'https://nutsfarm.crypton.xyz/?startapp=ref_nutsfarm_bot&tgWebAppStartParam=ref_{referral_code}' if referral_code else 'https://nutsfarm.crypton.xyz/',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Content-Type': 'application/json'
        }
        
        if not referral_code and 'start_param=' in auth_data:
            try:
                start_param = auth_data.split('start_param=')[1].split('&')[0]
                if start_param.startswith('ref_'):
                    referral_code = start_param.replace('ref_', '')
            except Exception:
                pass
        
        data = {
            "authData": auth_data,
            "language": "RU"
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

    async def claim_start_bonus(self) -> bool:
        result = await self._make_request(
            'POST',
            'farming/startBonus',
            headers={'Origin': settings.BASE_URL}
        )
        
        if isinstance(result, (int, float)):
            logger.success(f"{self.session_name} | Start bonus received: {result}")
            return True
        logger.error(f"{self.session_name} | Invalid start bonus format: {result}")
        return False

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
            headers={'Origin': settings.BASE_URL}
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
        """Получает статус фарминга и время до его окончания"""
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

    async def verify_task(self, user_task_id: str, task_type: str, telegram_channel_id: int = None) -> bool:
        data = {
            "userTaskId": user_task_id,
            "type": task_type
        }
        
        if task_type == 'TELEGRAM_CHANNEL_SUBSCRIPTION':
            data["telegramChannelId"] = telegram_channel_id
        elif task_type == 'URL':
            pass
            
        result = await self._make_request(
            'POST',
            'task/verify',
            headers={
                'Origin': settings.BASE_URL,
                'Content-Type': 'application/json',
                'Referer': f'{settings.BASE_URL}/tasks'
            },
            json=data
        )
        
        if result:
            status = result.get('status')
            if status == 'VERIFYING':
                logger.success(f"{self.session_name} | Task sent for verification")
                return True
            logger.error(f"{self.session_name} | Unexpected verification status: {status}")
        return False

    async def get_active_stories(self) -> list | None:
        """Получает список всех доступных историй"""
        return await self._make_request('GET', 'story/active')

    async def get_current_stories(self) -> list | None:
        """Получает список текущих историй пользователя"""
        return await self._make_request('GET', 'story/current')

    async def read_story(self, story_id: str) -> int | None:
        """Отмечает историю как прочитанную и получает награду"""
        result = await self._make_request(
            'POST',
            f'story/read/{story_id}',
            headers={'Origin': settings.BASE_URL}
        )
        
        if isinstance(result, (int, float)):
            logger.success(f"{self.session_name} | Story reward received: {int(result)}")
            return int(result)
        return None

    async def process_stories(self) -> None:
        """Обрабатывает все доступные истории"""
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

                    await tapper.process_stories()
                    
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
