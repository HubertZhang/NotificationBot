import logging
import re
import sqlite3
import threading
from html import escape
from typing import Dict, List, Optional

import sched_cond
from BotPlugin import *

time_remain_template = "Please remember to hack a portal! {} remaining."
time_remain = [
    18 * HOUR_SECONDS,
    12 * HOUR_SECONDS,
    6 * HOUR_SECONDS,
    1 * HOUR_SECONDS,
    30 * MINUTE_SECONDS,
    15 * MINUTE_SECONDS,
    10 * MINUTE_SECONDS,
    5 * MINUTE_SECONDS,
    2 * MINUTE_SECONDS,
    1 * MINUTE_SECONDS,
]

thirty_six_template = (
    "Your previous hack is too early. "
    "Please remember to hack a portal within 36h "
    "after previous hack! {} remaining."
)
emergency_remain = [
    3 * HOUR_SECONDS,
    2 * HOUR_SECONDS,
    1 * HOUR_SECONDS,
    30 * MINUTE_SECONDS,
    15 * MINUTE_SECONDS,
    10 * MINUTE_SECONDS,
    5 * MINUTE_SECONDS,
]

if DEBUG:
    time_remain = [55, 45, 35, 25, 15, 5]


class HackUser(User):
    def __init__(
        self,
        user_id,
        username,
        first_name,
        last_name,
        language_code,
        start_time,
        time_setting,
        last_hack_time,
    ):
        super().__init__(user_id, username, first_name, last_name, language_code)
        self.start_time = start_time
        self.last_hack_time = last_hack_time

        if time_setting is not None:
            self.timer_setting = [int(x) for x in time_setting.split()]
        else:
            self.timer_setting = None
        self.main_timer: Optional[sched_cond.Event] = None
        self.timers: List[sched_cond.Event] = []
        self.message_records = []


class HackBot(BotPlugin):
    prefix = "hack"

    def __init__(self, bot: telegram.Bot):
        super().__init__(bot)
        self.db = sqlite3.connect("data/hack_data.sqlite", check_same_thread=False)
        self.scheduler = sched_cond.scheduler_condition(
            timefunc=time.time, delayfunc=time.sleep
        )
        threading.Thread(target=self.scheduler.run).start()
        self.users: Dict[int, HackUser] = dict()

        for user in self.db.execute(
            "SELECT user.user_id, username, first_name, last_name, "
            "language_code, start_time, time_setting, latest_hack_time "
            "FROM user LEFT OUTER JOIN latest_hack "
            "ON user.user_id=latest_hack.user_id"
        ):
            if DEBUG:
                if user[0] != 70166446:
                    continue
            self.users[user[0]] = HackUser(*user)
            self.setup_timer(user[0])

    def setup_timer(self, user_id):
        u = self.users[user_id]
        if u.start_time < 0:
            return
        next_day = previous_day_start(u.start_time) + DAY_SECONDS
        if u.timer_setting is None:
            timer_setting = time_remain
        else:
            timer_setting = u.timer_setting
        for i, delay in enumerate(timer_setting):
            if next_day - delay > time.time():
                u.timers.append(
                    self.scheduler.enterabs(
                        next_day - delay, 3, self.timer_fired, argument=(user_id, i)
                    )
                )
                break

        u.main_timer = self.scheduler.enterabs(
            next_day, 2, self.new_day, argument=[user_id]
        )

    def add_user(self, user: telegram.User, start_time):
        self.users[user.id] = HackUser(
            user.id,
            user.username,
            user.first_name,
            user.last_name,
            user.language_code,
            start_time,
            None,
            None,
        )

        self.db.execute(
            "INSERT INTO user VALUES (?,?,?,?,?,?, NULL)",
            (
                user.id,
                user.username,
                user.first_name,
                user.last_name,
                user.language_code,
                start_time,
            ),
        )
        self.db.commit()

        self.setup_timer(user.id)

    def change_time(self, user: telegram.User, start_time):
        u = self.users[user.id]
        u.last_hack_time = None
        for event in u.timers:
            self.scheduler.cancel(event)
        u.timers = []
        if u.main_timer is not None:
            self.scheduler.cancel(u.main_timer)
            u.main_timer = None

        u.start_time = start_time
        self.db.execute(
            "UPDATE user "
            "SET username=?,"
            "first_name=?,"
            "last_name=?,"
            "language_code=?,"
            "start_time=? "
            "WHERE user_id=?",
            (
                user.username,
                user.first_name,
                user.last_name,
                user.language_code,
                start_time,
                user.id,
            ),
        )
        self.db.commit()
        if start_time >= 0:
            if u.timer_setting is not None:
                new_setting = [
                    (x + start_time - u.start_time + DAY_SECONDS) % DAY_SECONDS
                    for x in u.timer_setting
                ]
                new_setting.sort(reverse=True)
                u.timer_setting = new_setting

        self.setup_timer(user.id)

    def change_time_setting(self, user: telegram.User, time_setting):
        u = self.users[user.id]
        for event in u.timers:
            self.scheduler.cancel(event)
        u.timers = []
        if u.main_timer is not None:
            self.scheduler.cancel(u.main_timer)
            u.main_timer = None

        u.timer_setting = time_setting
        if time_setting is not None:
            time_setting_str = " ".join([str(x) for x in time_setting])
        else:
            time_setting_str = None
        self.db.execute(
            "UPDATE user "
            "SET username=?,"
            "first_name=?,"
            "last_name=?,"
            "language_code=?,"
            "time_setting=? "
            "WHERE user_id=?",
            (
                user.username,
                user.first_name,
                user.last_name,
                user.language_code,
                time_setting_str,
                user.id,
            ),
        )
        self.db.commit()
        self.setup_timer(user.id)

    def add_record(self, user_id, date):
        if self.users.get(user_id) is None:
            return
        if (
            self.users[user_id].last_hack_time is None
            or date > self.users[user_id].last_hack_time
        ):
            self.users[user_id].last_hack_time = date
            self.db.execute("INSERT INTO hack_record VALUES (?,?)", (user_id, date))
            self.db.commit()

    def handle_command(
        self, user: telegram.User, chat: telegram.Chat, parameters: List[str]
    ):
        if len(parameters) == 0:
            return (
                '<code>/hack start hh:mm</code>  set the start point of each "hack" day (UTC+8)\n'
                "<code>/hack status</code>       list all following timers\n"
                "<code>/hack alarm hh:mm hh:mm ...</code>      set time for notifications \n"
                "<code>/hack stop</code>      stop notifications \n"
                "<code>/hack record hh:mm</code>      record hack time in previous day \n"
            )
        if parameters[0] == "start":
            return self._handle_start(parameters, user)
        if parameters[0] == "status":
            return self._handle_status(parameters, user)
        if parameters[0] == "alarm":
            return self._handle_alarm(parameters, user)
        if parameters[0] == "stop":
            return self._handle_stop(parameters, user)
        if parameters[0] == "record":
            return self._handle_record(parameters, user)
        return ""

    def _handle_record(self, parameters: List[str], user: telegram.User):
        if self.users.get(user.id) is None:
            return "Please set day start time first"
        u = self.users[user.id]
        if len(parameters) != 2:
            return "Format error! Please provide hack times. Format: \nhh:mm in UTC+8"
        s = parameters[1]
        r = re.search("(\\d{1,2}):(\\d{1,2})", s)
        if r is None:
            return "Format error! Please provide hack times. Format: \nhh:mm in UTC+8"
        h = int(r.group(1))
        h = (h + 16) % 24
        m = int(r.group(2))
        new_time = (h * 60 + m) * 60
        t = previous_day_start(u.start_time) + new_time
        self.add_record(user.id, t)

    def _handle_stop(self, parameters: List[str], user: telegram.User):
        if self.users.get(user.id) is not None:
            if self.users[user.id].start_time > 0:
                self.change_time(user, -1)
                return "Timers removed."
        return "You haven't set up the timer."

    def _handle_alarm(self, parameters: List[str], user: telegram.User):
        if self.users.get(user.id) is None:
            return "Please set day start time first"
        if len(parameters) == 1:
            return escape(
                "Please provide alarm times. Format: \nhh:mm <hh:mm> <hh:mm>... in UTC+8"
            )
        if parameters[1] == "reset":
            self.change_time_setting(user, None)
            return "Alarms reset to default."
        u = self.users[user.id]
        setting = []
        for s in parameters[1:]:
            r = re.search("(\\d{1,2}):(\\d{1,2})", s)
            if r is None:
                return escape(
                    "Format error! Please provide alarm times. Format: \nhh:mm <hh:mm> <hh:mm>... in UTC+8"
                )
            h = int(r.group(1))
            h = (h + 16) % 24
            m = int(r.group(2))
            new_time = (h * 60 + m) * 60
            new_time = (u.start_time - new_time + DAY_SECONDS) % DAY_SECONDS
            setting.append(new_time)
        setting.sort(reverse=True)
        self.change_time_setting(user, setting)
        reply = "You will receive notification at:\n" + "\n".join(
            [day_time_to_str(u.start_time - x) for x in setting]
        )
        return reply

    def _handle_status(self, parameters: List[str], user: telegram.User):
        if self.users.get(user.id) is None:
            return "No timer is set"
        u = self.users[user.id]
        reply = "Current timers:\n"
        if u.timer_setting is not None:
            setting = u.timer_setting
        else:
            setting = time_remain
        i = 0
        for x in u.timers:
            while x.argument[1] > i:
                reply += "{} (past)\n".format(
                    day_time_to_str(u.start_time - setting[i])
                )
                i += 1
            reply += "{} (set)\n".format(day_time_to_str(u.start_time - setting[i]))
        i += 1
        for j in range(i, len(setting)):
            reply += "{} (will set)\n".format(
                day_time_to_str(u.start_time - setting[j])
            )
        reply += "{} (next day)\n".format(day_time_to_str(u.start_time))
        return reply

    def _handle_start(self, parameters: List[str], user: telegram.User):
        if len(parameters) != 2:
            return "Please set time. Format: hh:mm in UTC+8"
        start = parameters[1]
        r = re.search("(\\d{1,2}):(\\d{1,2})", start)
        if r is None:
            return "Format error! Please set time. Format: hh:mm in UTC+8"
        h = int(r.group(1))
        h = (h + 16) % 24
        m = int(r.group(2))
        if self.users.get(user.id) is not None:
            self.change_time(user, (h * 60 + m) * 60)
            return "Changed"
        else:
            self.add_user(user, (h * 60 + m) * 60)
            return "Set"

    async def handle_callback(self, callback: telegram.CallbackQuery):
        user_id = callback.from_user.id
        if callback.data is None or len(callback.data) <= len(self.prefix):
            return "Error Callback Data", True
        try:
            target_user_id = int(callback.data[len(self.prefix) :])
        except ValueError:
            return "Error Callback Data", True
        if user_id != target_user_id:
            return "This is not your timer", True
        t = time.time()
        if self.users.get(user_id) is None:
            return "You haven't setup the starting point", True
        self.add_record(user_id, t)
        if callback.message is not None:
            button = telegram.InlineKeyboardButton(
                "Portal hacked", callback_data=self.prefix + str(user_id)
            )
            if callback.message.is_accessible:
                await self.bot.edit_message_text(
                    text="Portal hacked at {}".format(timestamp_to_str(t)),
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    reply_markup=telegram.InlineKeyboardMarkup([[button]]),
                )
            self.users[user_id].message_records = []

        return "Hack time recorded", False

    async def new_day(self, user_id, **kwargs):
        logging.debug("new day: {}".format(timestamp_to_str(kwargs["event"].time)))
        u = self.users[user_id]

        for event in u.timers:
            self.scheduler.cancel(event)
        u.timers = []

        start_time = u.start_time
        previous_day = previous_day_start(start_time)
        next_day = previous_day + DAY_SECONDS
        u.main_timer = self.scheduler.enterabs(
            next_day, 2, self.new_day, argument=[user_id]
        )

        hacked_too_early = False
        if u.timer_setting is not None:
            delay = u.timer_setting[0]
        else:
            delay = time_remain[0]
        u.timers.append(
            self.scheduler.enterabs(
                next_day - delay, 3, self.timer_fired, argument=(user_id, 0)
            )
        )

        last_hack_time = u.last_hack_time
        if (
            last_hack_time is not None
            and previous_day - DAY_SECONDS
            < last_hack_time
            < previous_day - 12 * HOUR_SECONDS
        ):
            hacked_too_early = True
            for i, delay in enumerate(emergency_remain):
                if last_hack_time + delay > start_time:
                    u.timers.append(
                        self.scheduler.enterabs(
                            last_hack_time + 36 * HOUR_SECONDS - emergency_remain[0],
                            3,
                            self.timer_fired,
                            argument=(user_id, -1),
                        )
                    )
                    break

        button = telegram.InlineKeyboardButton(
            "Portal hacked", callback_data=self.prefix + str(user_id)
        )

        text_message = (
            "Hello {}! Yet another day! Please remember to hack a portal today!".format(
                self.users[user_id].name
            )
        )
        if hacked_too_early:
            text_message += "\nYour previous hack is too early. Please remember to hack a portal within 36h after previous hack!"
        try:
            message = await self.bot.send_message(
                user_id,
                text_message,
                reply_markup=telegram.InlineKeyboardMarkup([[button]]),
            )
            u.message_records.append((message.chat_id, message.message_id))
        except telegram.error.TelegramError:
            pass

    async def timer_fired(self, user_id, seq, **kwargs):
        logging.debug("fire time: {}".format(timestamp_to_str(kwargs["event"].time)))
        u = self.users[user_id]
        u.timers.remove(kwargs["event"])

        start_time = u.start_time
        current_day = previous_day_start(start_time)

        if u.last_hack_time is not None and u.last_hack_time > current_day:
            return

        if seq < 0 and u.last_hack_time is not None:
            seq = -seq - 1
            delay = emergency_remain[seq]
            msg = thirty_six_template.format(time_interval_to_remain(delay))
            if seq + 1 < len(emergency_remain):
                u.timers.append(
                    self.scheduler.enterabs(
                        u.last_hack_time
                        + 36 * HOUR_SECONDS
                        - emergency_remain[seq + 1],
                        3,
                        self.timer_fired,
                        argument=(user_id, -seq - 2),
                    )
                )

        else:
            if u.timer_setting is None:
                setting = time_remain
            else:
                setting = u.timer_setting
            delay = setting[seq]
            msg = time_remain_template.format(time_interval_to_remain(delay))
            if seq + 1 < len(setting):
                u.timers.append(
                    self.scheduler.enterabs(
                        current_day + DAY_SECONDS - setting[seq + 1],
                        3,
                        self.timer_fired,
                        argument=(user_id, seq + 1),
                    )
                )

        button = telegram.InlineKeyboardButton(
            "Portal hacked", callback_data=self.prefix + str(user_id)
        )
        try:
            message = await self.bot.send_message(
                user_id, msg, reply_markup=telegram.InlineKeyboardMarkup([[button]])
            )
        except telegram.error.TelegramError:
            return
        if len(u.message_records) > 0:
            for i in u.message_records:
                try:
                    await self.bot.delete_message(i[0], i[1])
                except telegram.error.TelegramError:
                    pass
            u.message_records = []
        u.message_records.append((message.chat_id, message.message_id))
