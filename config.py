import os

from pyrogram.filters import create
from marco.authdb import is_authorized

def auth_or_owner_filter_func(_, __, message):
    userid = message.from_user.id
    return is_authorized(userid)  # MongoDB se user check hoga

auth_or_owner_filter = create(auth_or_owner_filter_func)


# Configuration values - only from this file, not from environment variables
API_ID = 29457553
API_HASH = "cab744661ee57afac6b131508f4289cb"
BOT_TOKEN = "8466950580:AAHsE9A0rW64Uj9PxnjJFO6zBJsd8VPc_GM"
PASS_DB = 721
OWNER = 8228219942
LOG = -1003133889122

# ADMINS list
ADMINS = [8228219942]
ADMINS.append(OWNER)


# Default credit used in captions when /uc config uses df
CREDIT = "Mrs.UC"
