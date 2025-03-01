import sys
import glob
import importlib
from pathlib import Path
from pyrogram import idle
import logging
import logging.config
import asyncio
from concurrent.futures import ThreadPoolExecutor

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
executor = ThreadPoolExecutor(max_workers=4)  # Adjust based on CPU cores

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
        print(f"The Movie Provider Imported => {plugin_name}")

async def lazy_start():
    print('\nInitializing The Movie Provider Bot')
    
    # Start bot and fetch info concurrently
    await LazyPrincessBot.start()
    bot_info = await LazyPrincessBot.get_me()
    LazyPrincessBot.username = bot_info.username
    
    # Run initialization tasks in parallel
    init_tasks = [
        initialize_clients(),
        preload_plugins(),
        Media.ensure_indexes(),
        db.get_banned()
    ]
    results = await asyncio.gather(*init_tasks)
    
    # Process banned users/chats
    b_users, b_chats = results[-1]
    temp.BANNED_USERS = b_users
    temp.BANNED_CHATS = b_chats
    
    # Set bot info
    me = await LazyPrincessBot.get_me()
    temp.ME = me.id
    temp.U_NAME = me.username
    temp.B_NAME = me.first_name
    LazyPrincessBot.username = '@' + me.username
    
    # Log startup info
    logging.info(f"{me.first_name} with Pyrogram v{__version__} (Layer {layer}) started on {me.username}.")
    logging.info(LOG_STR)
    logging.info(script.LOGO)
    
    # Timezone info (optional, can be removed if not needed in responses)
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    time = now.strftime("%H:%M:%S %p")
    
    # Start web server
    app = web.AppRunner(await web_server())
    await app.setup()
    bind_address = "0.0.0.0"
    await web.TCPSite(app, bind_address, PORT).start()
    
    # Keep alive for Heroku
    if ON_HEROKU:
        asyncio.create_task(ping_server())
    
    await idle()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(lazy_start())
    except KeyboardInterrupt:
        logging.info('Service Stopped Bye 👋')
    finally:
        executor.shutdown(wait=False)