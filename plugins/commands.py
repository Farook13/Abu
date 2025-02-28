@Client.on_message(filters.command('channel') & filters.user(ADMINS))
async def channel_info(bot, message):
    if isinstance(CHANNELS, (int, str)):
        channels = [CHANNELS]
    elif isinstance(CHANNELS, list):
        channels = CHANNELS
    else:
        raise ValueError("Unexpected type of CHANNELS")
    
    text = '📑 **Indexed Channels/Groups List:**\n'
    for channel in channels:
        chat = await bot.get_chat(channel)
        if chat.username:
            text += '\n@' + chat.username
        else:
            text += '\n' + (chat.title or chat.first_name)
    
    text += f'\n\n**Total:** {len(CHANNELS)}'
    
    if len(text) < 4096:
        await message.reply(text)
    else:
        file = 'Indexed_channels.txt'
        with open(file, 'w', encoding='utf-8') as f:
            f.write(text)
        await message.reply_document(file)
        os.remove(file)

@Client.on_message(filters.command('delete') & filters.user(ADMINS))
async def delete(bot, message):
    reply = message.reply_to_message
    if reply and reply.media:
        msg = await message.reply("Processing...⏳", quote=True)
    else:
        await message.reply('Reply to a file to delete it.')
        return
    
    for file_type in ("document", "video", "audio"):
        media = getattr(reply, file_type, None)
        if media is not None:
            break
    else:
        await msg.edit('This is not a supported file type.')
        return
    
    file_id, file_ref = unpack_new_file_id(media.file_id)
    result = await Media.collection.delete_one({'_id': file_id})
    
    if result.deleted_count:
        await msg.edit('File deleted successfully from database.')
    else:
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
        result = await Media.collection.delete_many({
            'file_name': file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type
        })
        if result.deleted_count:
            await msg.edit('File deleted successfully from database.')
        else:
            result = await Media.collection.delete_many({
                'file_name': media.file_name,
                'file_size': media.file_size,
                'mime_type': media.mime_type
            })
            if result.deleted_count:
                await msg.edit('File deleted successfully from database.')
            else:
                await msg.edit('File not found in database.')

@Client.on_message(filters.command('deleteall') & filters.user(ADMINS))
async def delete_all_index(bot, message):
    await message.reply_text(
        'This will delete all your indexed files. Are you sure?',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="⚠️ Yes ⚠️", callback_data="autofilter_delete")],
            [InlineKeyboardButton(text="❌ No ❌", callback_data="close_data")]
        ]),
        quote=True
    )

@Client.on_callback_query(filters.regex(r'^autofilter_delete'))
async def delete_all_index_confirm(bot, message):
    await Media.collection.drop()
    await message.answer('Maintained by: HP')
    await message.message.edit('All files deleted successfully from database.')