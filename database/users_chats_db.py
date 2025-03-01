import motor.motor_asyncio
from info import (
    DATABASE_NAME, DATABASE_URI, IMDB, IMDB_TEMPLATE, MELCOW_NEW_USERS, 
    P_TTI_SHOW_OFF, SINGLE_BUTTON, SPELL_CHECK_REPLY, PROTECT_CONTENT, 
    AUTO_DELETE, MAX_BTN, AUTO_FFILTER, SHORTLINK_API, SHORTLINK_URL, 
    IS_SHORTLINK, TUTORIAL, IS_TUTORIAL
)
import datetime
import pytz
import logging
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.users = self.db.users  # Collection for users
        self.groups = self.db.groups  # Collection for groups
        self.requests = self.db.requests  # Collection for join requests

    async def setup_indexes(self):
        """Set up indexes for commonly queried fields."""
        try:
            await asyncio.gather(
                self.users.create_index("id", unique=True),
                self.groups.create_index("id", unique=True),
                self.requests.create_index("id", unique=True),
                self.users.create_index("expiry_time")
            )
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.error(f"Failed to create database indexes: {e}")

    # Join Request Methods
    async def find_join_req(self, id):
        return bool(await self.requests.find_one({'id': id}))

    async def add_join_req(self, id):
        await self.requests.insert_one({'id': id})

    async def del_join_req(self):
        await self.requests.drop()

    # User Factory Methods
    @staticmethod
    def new_user(id, name):
        return {
            "id": id,
            "name": name,
            "ban_status": {
                "is_banned": False,
                "ban_reason": "",
            },
            "has_free_trial": False,
            "expiry_time": None
        }

    @staticmethod
    def new_group(id, title):
        return {
            "id": id,
            "title": title,
            "chat_status": {
                "is_disabled": False,
                "reason": "",
            }
        }

    # User Management
    async def add_user(self, id, name):
        user = self.new_user(id, name)
        await self.users.insert_one(user)

    async def is_user_exist(self, id):
        return bool(await self.users.find_one({'id': int(id)}))

    async def total_users_count(self):
        return await self.users.count_documents({})

    async def remove_ban(self, id):
        await self.users.update_one(
            {'id': int(id)},
            {'$set': {'ban_status': {"is_banned": False, "ban_reason": ""}}}
        )

    async def ban_user(self, user_id, ban_reason="No Reason"):
        await self.users.update_one(
            {'id': int(user_id)},
            {'$set': {'ban_status': {"is_banned": True, "ban_reason": ban_reason}}}
        )

    async def get_ban_status(self, id):
        default = {"is_banned": False, "ban_reason": ""}
        user = await self.users.find_one({'id': int(id)})
        return user.get('ban_status', default) if user else default

    async def get_all_users(self):
        return self.users.find({})

    async def delete_user(self, user_id):
        await self.users.delete_many({'id': int(user_id)})

    # Banned Users/Chats
    async def get_banned(self):
        banned_users = [user['id'] async for user in self.users.find({'ban_status.is_banned': True})]
        banned_chats = [chat['id'] async for chat in self.groups.find({'chat_status.is_disabled': True})]
        return banned_users, banned_chats

    # Chat Management
    async def add_chat(self, chat, title):
        chat_doc = self.new_group(chat, title)
        await self.groups.insert_one(chat_doc)

    async def get_chat(self, chat):
        chat = await self.groups.find_one({'id': int(chat)})
        return chat.get('chat_status') if chat else False

    async def re_enable_chat(self, id):
        await self.groups.update_one(
            {'id': int(id)},
            {'$set': {'chat_status': {"is_disabled": False, "reason": ""}}}
        )

    async def update_settings(self, id, settings):
        await self.groups.update_one({'id': int(id)}, {'$set': {'settings': settings}})

    async def get_settings(self, id):
        default = {
            'button': SINGLE_BUTTON,
            'botpm': P_TTI_SHOW_OFF,
            'file_secure': PROTECT_CONTENT,
            'imdb': IMDB,
            'spell_check': SPELL_CHECK_REPLY,
            'welcome': MELCOW_NEW_USERS,
            'auto_delete': AUTO_DELETE,
            'auto_ffilter': AUTO_FFILTER,
            'max_btn': MAX_BTN,
            'template': IMDB_TEMPLATE,
            'shortlink': SHORTLINK_URL,
            'shortlink_api': SHORTLINK_API,
            'is_shortlink': IS_SHORTLINK,
            'tutorial': TUTORIAL,
            'is_tutorial': IS_TUTORIAL
        }
        chat = await self.groups.find_one({'id': int(id)})
        return chat.get('settings', default) if chat else default

    async def disable_chat(self, chat, reason="No Reason"):
        await self.groups.update_one(
            {'id': int(chat)},
            {'$set': {'chat_status': {"is_disabled": True, "reason": reason}}}
        )

    async def total_chat_count(self):
        return await self.groups.count_documents({})

    async def get_all_chats(self):
        return self.groups.find({})

    async def get_db_size(self):
        stats = await self.db.command("dbstats")
        return stats['dataSize']

    # Premium User Management
    async def get_user(self, user_id):
        return await self.users.find_one({"id": int(user_id)})

    async def update_user(self, user_data):
        await self.users.update_one(
            {"id": user_data["id"]},
            {"$set": user_data},
            upsert=True
        )

    async def has_premium_access(self, user_id):
        user_data = await self.get_user(user_id)
        if not user_data:
            return False
        expiry_time = user_data.get("expiry_time")
        if expiry_time is None:
            return False
        now = datetime.datetime.now(pytz.UTC)
        if isinstance(expiry_time, datetime.datetime) and now <= expiry_time:
            return True
        await self.remove_premium_access(user_id)
        return False

    async def update_one(self, filter_query, update_data):
        try:
            result = await self.users.update_one(filter_query, update_data)
            return result.matched_count > 0
        except Exception as e:
            logger.error(f"Error updating document: {e}")
            return False

    async def get_expired(self, current_time):
        return [user async for user in self.users.find({"expiry_time": {"$lt": current_time}})]

    async def remove_premium_access(self, user_id):
        return await self.update_one(
            {"id": int(user_id)},
            {"$set": {"expiry_time": None}}
        )

    async def check_trial_status(self, user_id):
        user_data = await self.get_user(user_id)
        return user_data.get("has_free_trial", False) if user_data else False

    async def give_free_trial(self, user_id):
        seconds = 5 * 60  # 5 minutes
        expiry_time = datetime.datetime.now(pytz.UTC) + datetime.timedelta(seconds=seconds)
        user_data = {
            "id": int(user_id),
            "expiry_time": expiry_time,
            "has_free_trial": True
        }
        await self.users.update_one({"id": int(user_id)}, {"$set": user_data}, upsert=True)

# Instantiate the database (indexes will be set up later)
db = Database(DATABASE_URI, DATABASE_NAME)