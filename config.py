import os

from pyrogram.filters import create
from marco.authdb import is_authorized

def auth_or_owner_filter_func(_, __, message):
    userid = message.from_user.id
    return is_authorized(userid)  # MongoDB se user check hoga

auth_or_owner_filter = create(auth_or_owner_filter_func)


# Configuration values - only from this file, not from environment variables
API_ID = 25426069
API_HASH = "b301a913521454b646fb7cf22e0ce131"
BOT_TOKEN = "8420037149:AAF2oIQQkeWM12GyYjXSYJN3pnS2JfsGocQ"
PASS_DB = 721
OWNER = 7885776783
LOG = -1002773979194

# ADMINS list
ADMINS = [7885776783]
ADMINS.append(OWNER)
