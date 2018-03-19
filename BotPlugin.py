import math
import time
from datetime import datetime

import pytz
import telegram

DAY_SECONDS = 24 * 60 * 60
HOUR_SECONDS = 60 * 60
MINUTE_SECONDS = 60


def previous_day_start(start_time):
    return math.floor((time.time() - start_time) / DAY_SECONDS) * DAY_SECONDS + start_time


def timestamp_to_str(t: int):
    timezone_local = pytz.FixedOffset(480)
    dt = pytz.utc.localize(datetime.utcfromtimestamp(t))
    return dt.astimezone(timezone_local).strftime("%Y-%m-%d %H:%M:%S")


class BotPlugin:
    prefix = ""

    def __init__(self, bot: telegram.Bot):
        self.bot = bot

    def handle_command(self, user: telegram.User, chat: telegram.Chat, parameters: [str]):
        return ""

    def handle_callback(self, callback: telegram.CallbackQuery):
        return "", False
