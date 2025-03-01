import logging
import re
import base64
from struct import pack
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import DATABASE_URI, DATABASE_NAME, COLLECTION_NAME, USE_CAPTION_FILTER, MAX_B_TN
from utils import get_settings, save_group_settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Initialize MongoDB client
client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)

@instance.register
class Media(Document):
    file_id = fields.StrField(attribute='_id', required=True)
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        indexes = [('$file_name',), ('file_id',)]  # Added file_id index
        collection_name = COLLECTION_NAME

async def ensure_indexes():
    """Ensure indexes are created for efficient querying."""
    await Media.ensure_indexes()

async def save_file(media):
    """Save file in database and return (success, status_code)."""
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"[_+.-]+", " ", media.file_name.strip())  # Simplified regex

    try:
        file = Media(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
        )
        await file.commit()
        logger.info(f"Saved '{file_name}' to database")
        return True, 1
    except ValidationError as e:
        logger.exception(f"Validation error while saving '{file_name}': {e}")
        return False, 2
    except DuplicateKeyError:
        logger.warning(f"'{file_name}' is already in database")
        return False, 0
    except Exception as e:
        logger.exception(f"Unexpected error saving '{file_name}': {e}")
        return False, -1

async def get_search_results(chat_id, query, file_type=None, max_results=3, offset=0, filter=False):
    """
    Search for files matching query.
    Returns (results, next_offset, total_results).
    """
    if chat_id is not None:
        settings = await get_settings(int(chat_id))
        max_results = MAX_B_TN if not settings.get('max_btn', False) else 8
        # Ensure settings are saved if missing
        if 'max_btn' not in settings:
            await save_group_settings(int(chat_id), 'max_btn', False)
            settings = await get_settings(int(chat_id))
            max_results = MAX_B_TN if not settings.get('max_btn', False) else 8

    query = query.strip()
    if not query:
        raw_pattern = '.'
    else:
        raw_pattern = r'\b' + re.escape(query) + r'\b' if ' ' not in query else query.replace(' ', r'.*[\s\.\+\-_]')

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except re.error as e:
        logger.error(f"Invalid regex pattern '{raw_pattern}': {e}")
        return [], '', 0

    mongo_filter = (
        {'$or': [{'file_name': regex}, {'caption': regex}]} if USE_CAPTION_FILTER 
        else {'file_name': regex}
    )
    if file_type:
        mongo_filter['file_type'] = file_type

    try:
        total_results = await Media.count_documents(mongo_filter)
        next_offset = offset + max_results if offset + max_results < total_results else ''

        cursor = Media.find(mongo_filter).sort('$natural', -1).skip(offset).limit(max_results)
        files = await cursor.to_list(length=max_results)
        return files, next_offset, total_results
    except Exception as e:
        logger.exception(f"Error in search: {e}")
        return [], '', 0

async def get_bad_files(query, file_type=None, filter=False):
    """
    Get all files matching query (no pagination).
    Returns (results, total_results).
    """
    query = query.strip()
    if not query:
        raw_pattern = '.'
    else:
        raw_pattern = r'\b' + re.escape(query) + r'\b' if ' ' not in query else query.replace(' ', r'.*[\s\.\+\-_]')

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except re.error as e:
        logger.error(f"Invalid regex pattern '{raw_pattern}': {e}")
        return [], 0

    mongo_filter = (
        {'$or': [{'file_name': regex}, {'caption': regex}]} if USE_CAPTION_FILTER 
        else {'file_name': regex}
    )
    if file_type:
        mongo_filter['file_type'] = file_type

    try:
        cursor = Media.find(mongo_filter).sort('$natural', -1)
        files = await cursor.to_list(length=None)  # Fetch all
        total_results = len(files)
        return files, total_results
    except Exception as e:
        logger.exception(f"Error in get_bad_files: {e}")
        return [], 0

async def get_file_details(file_id):
    """Get file details by file_id."""
    try:
        cursor = Media.find({'file_id': file_id}).limit(1)
        return await cursor.to_list(length=1)
    except Exception as e:
        logger.exception(f"Error fetching file details for '{file_id}': {e}")
        return []

# File ID encoding/decoding utilities
def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22, 4]):  # Simplified padding
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")

def unpack_new_file_id(new_file_id):
    """Return (file_id, file_ref) from a Pyrogram file ID."""
    try:
        decoded = FileId.decode(new_file_id)
        file_id = encode_file_id(
            pack("<iiqq", decoded.file_type, decoded.dc_id, decoded.media_id, decoded.access_hash)
        )
        file_ref = encode_file_ref(decoded.file_reference)
        return file_id, file_ref
    except Exception as e:
        logger.exception(f"Error unpacking file ID '{new_file_id}': {e}")
        return None, None