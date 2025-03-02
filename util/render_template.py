#Thanks @DeletedFromEarth for helping in this journey 

import jinja2
from info import *
from lazybot import LazyPrincessBot
from util.human_readable import humanbytes
from util.file_properties import get_file_ids
from server.exceptions import InvalidHash
import urllib.parse
import logging
import aiohttp