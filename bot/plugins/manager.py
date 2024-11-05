from pyrogram import Client, filters
from pyrogram.types import Message

from bot.utils import scripts
from bot.utils.logger import logger
from bot.utils.emojis import StaticEmoji
from bot.utils.launcher import tg_clients, run_tasks
from bot.utils.proxy_manager import ProxyManager

proxy_manager = ProxyManager()


@Client.on_message(filters.me & filters.chat("me") & filters.command("help", prefixes="/"))
async def send_help(_: Client, message: Message):
    help_text = scripts.get_help_text()

    await message.edit(text=help_text)


@Client.on_message(filters.me & filters.chat("me") & filters.command("tap", prefixes="/"))
@scripts.with_args("<b>This command does not work without arguments\n"
                   "Type <code>/tap on</code> to start or <code>/tap off</code> to stop</b>")
async def launch_tapper(client: Client, message: Message):
    flag = scripts.get_command_args(message, "tap")

    flags_to_start = ["on", "start"]
    flags_to_stop = ["off", "stop"]

    if flag in flags_to_start:
        logger.info(f"The tapper is launched with the command /tap {flag}\n")

        await message.edit(
            text=f"<b>{StaticEmoji.ACCEPT} Tapper launched! {StaticEmoji.START}</b>")
        await run_tasks(tg_clients=tg_clients)
    elif flag in flags_to_stop:
        logger.info(f"Tapper stopped with /tap command {flag}\n")

        await scripts.stop_tasks(client=client)
        await message.edit(
            text=f"<b>{StaticEmoji.ACCEPT} Tapper stopped! {StaticEmoji.STOP}</b>")
    else:
        await message.edit(
            text=f"<b>{StaticEmoji.DENY} This command only accepts the following arguments: on/off | start/stop</b>")


@Client.on_message(filters.me & filters.chat("me") & filters.command("proxy", prefixes="/"))
async def manage_proxy(client: Client, message: Message):
    args = message.text.split()[1:]
    if not args:
        # Показать текущую привязку
        proxy = proxy_manager.get_proxy(client.name)
        if proxy:
            await message.edit(f"Current proxy: {proxy}")
        else:
            await message.edit("No proxy bound to this session")
        return

    command = args[0].lower()
    if command == "bind" and len(args) > 1:
        # Привязать прокси
        proxy = args[1]
        proxy_manager.set_proxy(client.name, proxy)
        await message.edit(f"Bound proxy {proxy} to session {client.name}")
    elif command == "unbind":
        # Отвязать прокси
        proxy_manager.remove_proxy(client.name)
        await message.edit(f"Unbound proxy from session {client.name}")
    else:
        await message.edit("Invalid command. Use: /proxy bind <proxy> or /proxy unbind")
