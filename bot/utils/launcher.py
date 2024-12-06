import os
import glob
import asyncio
import argparse
from itertools import cycle
import subprocess
import signal
import random

from pyrogram import Client, compose
from better_proxy import Proxy

from bot.config import settings
from bot.utils import logger
from bot.utils.web import run_web_and_tunnel, stop_web_and_tunnel
from bot.core.tapper import run_tappers
from bot.core.registrator import register_sessions  
from bot.utils.proxy_manager import ProxyManager
from bot.utils.updater import UpdateManager

from colorama import Fore, Style, init

init(autoreset=True)

start_text = f"""
{Fore.RED}ВНИМАНИЕ: Эта ферма не предназначена для продажи!{Style.RESET_ALL}
{Fore.RED}WARNING: This farm is not for sale!{Style.RESET_ALL}
{Fore.RED}¡ADVERTENCIA: ¡Esta granja no está a la venta!{Style.RESET_ALL}
{Fore.RED}ATTENTION: Cette ferme n'est pas à vendre!{Style.RESET_ALL}
{Fore.RED}ACHTUNG: Diese Farm ist nicht zum Verkauf bestimmt!{Style.RESET_ALL}
{Fore.RED}ATTENZIONE: Questa fattoria non è in vendita!{Style.RESET_ALL}
{Fore.RED}注意：この農場は販売用ではありません！{Style.RESET_ALL}
{Fore.RED}주의: 이 농장은 판매용이 아닙니다!{Style.RESET_ALL}
{Fore.RED}注意：此农场不用于销售！{Style.RESET_ALL}
{Fore.RED}ATENÇÃO: Esta fazenda não se destina à venda!{Style.RESET_ALL}


{Fore.CYAN} \

 ███▄    █  █    ██ ▄▄▄█████▓  ██████      █████▒▄▄▄       ██▀███   ███▄ ▄███▓
 ██ ▀█   █  ██  ▓██▒▓  ██▒ ▓▒▒██    ▒    ▓██   ▒▒████▄    ▓██ ▒ ██▒▓██▒▀█▀ ██▒
▓██  ▀█ ██▒▓██  ▒██░▒ ▓██░ ▒░░ ▓██▄      ▒████ ░▒██  ▀█▄  ▓██ ░▄█ ▒▓██    ▓██░
▓██▒  ▐▌██▒▓▓█  ░██░░ ▓██▓ ░   ▒   ██▒   ░▓█▒  ░░██▄▄▄▄██ ▒██▀▀█▄  ▒██    ▒██ 
▒██░   ▓██░▒▒█████▓   ▒██▒ ░ ▒██████▒▒   ░▒█░    ▓█   ▓██▒░██▓ ▒██▒▒██▒   ░██▒
░ ▒░   ▒ ▒ ░▒▓▒ ▒ ▒   ▒ ░░   ▒ ▒▓▒ ▒ ░    ▒ ░    ▒▒   ▓▒█░░ ▒▓ ░▒▓░░ ▒░   ░  ░
░ ░░   ░ ▒░░░▒░ ░ ░     ░    ░ ░▒  ░ ░    ░       ▒   ▒▒ ░  ░▒ ░ ▒░░  ░      ░
   ░   ░ ░  ░░░ ░ ░   ░      ░  ░  ░      ░ ░     ░   ▒     ░░   ░ ░      ░   
         ░    ░                    ░                  ░  ░   ░            ░   
                                                                              
 
{Style.RESET_ALL}
{Fore.YELLOW}Select action:{Style.RESET_ALL}

    {Fore.GREEN}1. Create session{Style.RESET_ALL}
    {Fore.GREEN}2. Create session via QR{Style.RESET_ALL}
    {Fore.GREEN}3. Launch clicker{Style.RESET_ALL}
    {Fore.GREEN}4. Upload sessions via web (BETA){Style.RESET_ALL}

{Fore.CYAN}Developed by: @Mffff4{Style.RESET_ALL}
{Fore.CYAN}Our Telegram channel: {Fore.BLUE}https://t.me/+d0sLjg42kJgxZTM6{Style.RESET_ALL}
"""

global tg_clients

shutdown_event = asyncio.Event()

proxy_manager = ProxyManager()

def get_session_names() -> list[str]:
    session_names = glob.glob("sessions/*.session")
    session_names = [
        os.path.splitext(os.path.basename(file))[0] for file in session_names
    ]
    return session_names

def get_proxies() -> list[str]:
    if settings.USE_PROXY_FROM_FILE:
        with open(file="bot/config/proxies.txt", encoding="utf-8-sig") as file:
            proxies = []
            for row in file:
                proxy = row.strip()
                if proxy:
                    proxies.append(proxy)
            return proxies
    return []

async def get_tg_clients() -> list[Client]:
    global tg_clients

    session_names = get_session_names()

    if not session_names:
        logger.warning("No session files found. Please create a session.")
        return []

    if not settings.API_ID or not settings.API_HASH:
        raise ValueError("API_ID and API_HASH not found in the .env file.")

    tg_clients = [
        Client(
            name=session_name,
            api_id=settings.API_ID,
            api_hash=settings.API_HASH,
            workdir="sessions/",
            plugins=dict(root="bot/plugins"),
        )
        for session_name in session_names
    ]

    return tg_clients

async def process() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--action", type=int, help="Action to perform")
    parser.add_argument("--update-restart", action="store_true", help="Indicates if the process was restarted after update")

    logger.info(f"Detected {len(get_session_names())} sessions | {len(get_proxies())} proxies")

    action = parser.parse_args().action

    if not action:
        print(start_text)

        while True:
            action = input("> ")

            if not action.isdigit():
                logger.warning("Action must be a number")
            elif action not in ["1", "2", "3", "4"]:
                logger.warning("Action must be 1, 2, 3, or 4")
            else:
                action = int(action)
                break

    if action == 1:
        await register_sessions()
    elif action == 2:
        session_name = input("Enter the session name for QR code authentication: ")
        print("Initializing QR code authentication...")
        subprocess.run(["python", "-m", "bot.utils.loginQR", "-s", session_name])
        print("QR code authentication was successful!")
    elif action == 3:
        tg_clients = await get_tg_clients()
        if not tg_clients:
            print("No sessions found. You can create sessions using the following methods:")
            print("1. By phone number: python main.py -a 1")
            print("2. By QR code: python main.py -a 2")
            print("3. Upload via web interface (BETA): python main.py -a 4")
            print("\nIf you're using Docker, use these commands:")
            print("1. By phone number: docker compose run bot python3 main.py -a 1")
            print("2. By QR code: docker compose run bot python3 main.py -a 2")
            print("3. Upload via web interface (BETA): docker compose run bot python3 main.py -a 4")
            return
            
        proxies = get_proxies()
        proxies_list = []
        
        for client in tg_clients:
            bound_proxy = proxy_manager.get_proxy(client.name)
            if bound_proxy:
                proxies_list.append(bound_proxy)
            else:
                if proxies:
                    proxy = proxies.pop(0)
                    proxy_manager.set_proxy(client.name, proxy)
                    proxies_list.append(proxy)
                    proxies.append(proxy)
                else:
                    proxies_list.append(None)
                    
        await run_tasks(tg_clients=tg_clients, proxies=proxies_list)
    elif action == 4:
        logger.info("Starting web interface for uploading sessions...")
        
        signal.signal(signal.SIGINT, signal_handler)
        
        try:
            web_task = asyncio.create_task(run_web_and_tunnel())
            await shutdown_event.wait()
        finally:
            web_task.cancel()
            await stop_web_and_tunnel()
            print("Program terminated.")

async def run_tasks(tg_clients: list[Client], proxies: list[str | None]):
    if settings.AUTO_UPDATE:
        update_manager = UpdateManager()
        update_task = asyncio.create_task(update_manager.run())
    else:
        update_task = None
        
    try:
        tasks = []
        for client, proxy in zip(tg_clients, proxies):
            delay = random.uniform(0, 60)
            logger.info(f"{client.name} | Will start in {delay:.1f} seconds")
            
            async def delayed_start(client, proxy, delay):
                await asyncio.sleep(delay)
                await run_tappers([client], [proxy])
                
            tasks.append(delayed_start(client, proxy, delay))
        
        if update_task:
            await asyncio.gather(
                update_task,
                *tasks
            )
        else:
            await asyncio.gather(*tasks)
            
    except asyncio.CancelledError:
        if update_task:
            update_task.cancel()
        raise
    except Exception as e:
        logger.error(f"Error in run_tasks: {str(e)}")
        if update_task:
            update_task.cancel()
        raise

def signal_handler(signum, frame):
    print("\nShutting down...")
    shutdown_event.set()

if __name__ == "__main__":
    try:
        asyncio.run(process())
    except KeyboardInterrupt:
        pass
