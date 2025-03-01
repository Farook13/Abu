import sys
import glob
import importlib
from pathlib import Path
from pyrogram import idle
import logging
import logging.config
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os

# Configure logging
logging.config.fileConfig('logging.conf')
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("aiohttp.web").setLevel(logging.ERROR)

from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from database.ia_filterdb import Media
from database.users_chats_db import db
from info import *
from utils import temp
from Script import script 
from datetime import date, datetime 
import pytz
from aiohttp import web
from plugins import web_server
from lazybot import LazyPrincessBot
from util.keepalive import ping_server
from lazybot.clients import initialize_clients

# Preload plugins in parallel
plugins_dir = "plugins/*.py"
plugin_files = glob.glob(plugins_dir)
executor = ThreadPoolExecutor(max_workers=4)

def load_plugin(file_path):
    with open(file_path, 'r') as f:
        patt = Path(f.name)
        plugin_name = patt.stem
        import_path = f"plugins.{plugin_name}"
        spec = importlib.util.spec_from_file_location(import_path, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[import_path] = module
        return plugin_name

async def preload_plugins():
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(executor, load_plugin, file) for file in plugin_files]
    loaded_plugins = await asyncio.gather(*tasks)
    for plugin_name in loaded_plugins:
        logging.info(f"The Movie Provider Imported => {plugin_name}")

async def lazy_start():
    logging.info("Starting bot initialization")
    
    try:
        await LazyPrincessBot.start()
        logging.info("Bot started successfully")
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        return
    
    bot_info = await LazyPrincessBot.get_me()
    LazyPrincessBot.username = bot_info.username
    logging.info(f"Bot username: @{bot_info.username}")
    
    # Run initialization tasks in parallel
    init_tasks = [
        initialize_clients(),
        preload_plugins(),
        db.setup_indexes(),
        Media.ensure_indexes(),
        db.get_banned()
    ]
    try:
        results = await asyncio.gather(*init_tasks)
        logging.info("Initialization tasks completed")
    except Exception as e:
        logging.error(f"Initialization failed: {e}")
        return
    
    b_users, b_chats = results[-1]
    temp.BANNED_USERS = b_users
    temp.BANNED_CHATS = b_chats
    
    me = await LazyPrincessBot.get_me()
    temp.ME = me.id
    temp.U_NAME = me.username
    temp.B_NAME = me.first_name
    LazyPrincessBot.username = '@' + me.username
    
    logging.info(f"{me.first_name} with Pyrogram v{__version__} (Layer {layer}) started on {me.username}.")
    logging.info(LOG_STR)
    logging.info(script.LOGO)
    
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    time = now.strftime("%H:%M:%S %p")
    logging.info(f"Current time: {time}")
    
    # Start web server
    PORT = int(os.environ.get("PORT", 8000))
    app = web.AppRunner(await web_server())
    await app.setup()
    await web.TCPSite(app, "0.0.0.0", PORT).start()
    logging.info(f"Web server started on port {PORT}")
    
    if ON_HEROKU:
        asyncio.create_task(ping_server())
        logging.info("Keep-alive task started")
    
    logging.info("Bot is now idling and ready to receive updates")
    await idle()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(lazy_start())
    except KeyboardInterrupt:
        logging.info('Service Stopped Bye 👋')
    finally:
        executor.shutdown(wait=False)
        logging.info("Executor shutdown complete")