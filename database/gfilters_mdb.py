import logging
from motor.motor_asyncio import AsyncIOMotorClient
from info import DATABASE_URI, DATABASE_NAME
from pyrogram import enums

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

# Initialize async MongoDB client
client = AsyncIOMotorClient(DATABASE_URI)
mydb = client[DATABASE_NAME]

async def ensure_indexes(gfilters):
    """Ensure text index exists for efficient searching."""
    mycol = mydb[str(gfilters)]
    await mycol.create_index([("text", "text")])

async def add_gfilter(gfilters, text, reply_text, btn, file, alert):
    """Add or update a global filter in the database."""
    mycol = mydb[str(gfilters)]
    
    data = {
        'text': text,
        'reply': reply_text,
        'btn': btn,
        'file': file,
        'alert': alert
    }
    
    try:
        await mycol.update_one({'text': text}, {"$set": data}, upsert=True)
        logger.info(f"Added/Updated gfilter '{text}' in '{gfilters}'")
    except Exception as e:
        logger.exception(f"Error adding gfilter '{text}': {e}")

async def find_gfilter(gfilters, name):
    """Find a global filter by name."""
    mycol = mydb[str(gfilters)]
    
    try:
        # Use find_one for efficiency instead of iterating
        doc = await mycol.find_one({"text": name})
        if doc:
            return (
                doc['reply'],
                doc['btn'],
                doc.get('alert'),  # Use .get() to handle missing field
                doc['file']
            )
        return None, None, None, None
    except Exception as e:
        logger.exception(f"Error finding gfilter '{name}': {e}")
        return None, None, None, None

async def get_gfilters(gfilters):
    """Get all filter texts in a gfilters collection."""
    mycol = mydb[str(gfilters)]
    
    try:
        texts = [doc['text'] async for doc in mycol.find({}, {'text': 1})]
        return texts
    except Exception as e:
        logger.exception(f"Error retrieving gfilters for '{gfilters}': {e}")
        return []

async def delete_gfilter(message, text, gfilters):
    """Delete a specific global filter."""
    mycol = mydb[str(gfilters)]
    
    try:
        result = await mycol.delete_one({'text': text})
        if result.deleted_count == 1:
            await message.reply_text(
                f"'`{text}`' deleted. I'll not respond to that gfilter anymore.",
                quote=True,
                parse_mode=enums.ParseMode.MARKDOWN
            )
        else:
            await message.reply_text(
                "Couldn't find that gfilter!",
                quote=True
            )
    except Exception as e:
        logger.exception(f"Error deleting gfilter '{text}': {e}")
        await message.reply_text("Error occurred while deleting gfilter!", quote=True)

async def del_allg(message, gfilters):
    """Delete all global filters in a collection."""
    collection_name = str(gfilters)
    if collection_name not in await mydb.list_collection_names():
        await message.edit_text("Nothing to Remove!")
        return

    mycol = mydb[collection_name]
    try:
        await mycol.drop()
        await message.edit_text(f"All gfilters in '{gfilters}' have been removed!")
    except Exception as e:
        logger.exception(f"Error dropping collection '{gfilters}': {e}")
        await message.edit_text("Couldn't remove all gfilters!")

async def count_gfilters(gfilters):
    """Count the number of filters in a collection."""
    mycol = mydb[str(gfilters)]
    
    try:
        count = await mycol.count_documents({})
        return count if count > 0 else False
    except Exception as e:
        logger.exception(f"Error counting gfilters in '{gfilters}': {e}")
        return False

async def gfilter_stats():
    """Get statistics on all gfilter collections."""
    try:
        collections = await mydb.list_collection_names()
        if "CONNECTION" in collections:
            collections.remove("CONNECTION")

        total_count = 0
        for collection in collections:
            count = await mydb[collection].count_documents({})
            total_count += count

        return len(collections), total_count
    except Exception as e:
        logger.exception(f"Error calculating gfilter stats: {e}")
        return 0, 0