import logging
import re
import sqlite3
import threading
from typing import Tuple, Dict, List

import sched_cond
from BotPlugin import *

DEBUG = False

time_remain_template = "Please remember to hack a portal! {} remaining."

time_remain = [
    (DAY_SECONDS - 18 * HOUR_SECONDS, "18 hours"),
    (DAY_SECONDS - 12 * HOUR_SECONDS, "12 hours"),
    (DAY_SECONDS - 6 * HOUR_SECONDS, "6 hours"),
    (DAY_SECONDS - 1 * HOUR_SECONDS, "1 hour"),
    (DAY_SECONDS - 30 * MINUTE_SECONDS, "30 minutes"),
    (DAY_SECONDS - 15 * MINUTE_SECONDS, "15 minutes"),
    (DAY_SECONDS - 10 * MINUTE_SECONDS, "10 minutes"),
    (DAY_SECONDS - 5 * MINUTE_SECONDS, "5 minutes"),
    (DAY_SECONDS - 2 * MINUTE_SECONDS, "2 minutes"),
    (DAY_SECONDS - 1 * MINUTE_SECONDS, "1 minutes"),
]

thirty_six_template = "Your previous hack is too early. Please remember to hack a portal within 36h after previous hack! {} remaining."
emergency_remain = [
    (36 * HOUR_SECONDS - 3 * HOUR_SECONDS, "3 hours"),
    (36 * HOUR_SECONDS - 2 * HOUR_SECONDS, "2 hours"),
    (36 * HOUR_SECONDS - 1 * HOUR_SECONDS, "1 hours"),
    (36 * HOUR_SECONDS - 30 * MINUTE_SECONDS, "30 minutes"),
    (36 * HOUR_SECONDS - 15 * MINUTE_SECONDS, "15 minutes"),
    (36 * HOUR_SECONDS - 10 * MINUTE_SECONDS, "10 minutes"),
    (36 * HOUR_SECONDS - 5 * MINUTE_SECONDS, "5 minutes"),
]

if DEBUG:
    time_remain = [
        (5, "5 seconds"),
        (10, "10 seconds"),
        (15, "15 seconds"),
        (20, "20 seconds"),
        (25, "25 seconds"),
        (45, "45 seconds"),

    ]


class User:
    def __init__(self, user_id, username, first_name, last_name, language_code):
        self.user_id = int(user_id)
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.language_code = language_code

    @property
    def name(self):
        if self.username:
            return '@%s' % self.username
        if self.last_name:
            return '%s %s' % (self.first_name, self.last_name)
        return self.first_name


class HackUser(User):
    def __init__(self, user_id, username, first_name, last_name, language_code, start_time, last_hack_time):
        super().__init__(user_id, username, first_name, last_name, language_code)
        self.start_time = start_time
        self.last_hack_time = last_hack_time


class HackBot(BotPlugin):
    prefix = "hack"

    def __init__(self, bot: telegram.Bot):
        super().__init__(bot)
        self.db = sqlite3.connect("data/hack_data.sqlite", check_same_thread=False)
        self.scheduler = sched_cond.scheduler_condition(timefunc=time.time, delayfunc=time.sleep)
        threading.Thread(target=self.scheduler.run).start()
        self.users: Dict[int, HackUser] = dict()
        self.events: Dict[int, List[sched_cond.Event]] = dict()
        self.message_records: Dict[int, List[Tuple[int, int]]] = dict()

        for user in self.db.execute("SELECT user.user_id, username, first_name, last_name,"
                                    " language_code, start_time, latest_hack_time "
                                    "FROM user JOIN latest_hack "
                                    "WHERE user.user_id=latest_hack.user_id"):
            self.users[user[0]] = HackUser(*user)
            self.events[user[0]] = []
            self.message_records[user[0]] = []
            self.setup_timer(user[0], user[5])

    def setup_timer(self, user_id, start_time):
        previous_day = previous_day_start(start_time)
        for i, delay in enumerate(time_remain):
            if previous_day + delay[0] > time.time():
                self.events[user_id].append(
                    self.scheduler.enterabs(previous_day + delay[0], 3, self.timer_fired,
                                            argument=(user_id, time_remain_template.format(delay[1]))))

        self.events[user_id].append(
            self.scheduler.enterabs(previous_day + DAY_SECONDS, 2, self.new_day, argument=[user_id]))

    def add_user(self, user: telegram.User, start_time):
        self.users[user.id] = HackUser(user.id, user.username, user.first_name, user.last_name, user.language_code,
                                       start_time, None)
        self.events[user.id] = []
        self.message_records[user.id] = []

        self.db.execute("INSERT INTO user VALUES (?,?,?,?,?,?)", (
            user.id, user.username, user.first_name, user.last_name, user.language_code, start_time))
        self.db.commit()

        self.setup_timer(user.id, start_time)

    def change_time(self, user: telegram.User, start_time):
        self.users[user.id].start_time = start_time
        self.users[user.id].last_hack_time = None
        for event in self.events[user.id]:
            self.scheduler.cancel(event)
        self.events[user.id] = []
        self.message_records[user.id] = []

        self.db.execute(
            "UPDATE user "
            "SET username=?,"
            "first_name=?,"
            "last_name=?,"
            "language_code=?,"
            "start_time=? "
            "WHERE user_id=?",
            (user.username, user.first_name, user.last_name, user.language_code, start_time, user.id))
        self.db.commit()

        self.setup_timer(user.id, start_time)

    def add_record(self, user_id, date):
        if self.users.get(user_id) is None:
            return
        self.users[user_id].last_hack_time = date
        self.db.execute("INSERT INTO hack_record VALUES (?,?)", (user_id, date))
        self.db.commit()

    def handle_command(self, user: telegram.User, chat: telegram.Chat, parameters: [str]):
        if len(parameters) == 0:
            return "<code>/hack set hh:mm</code>  set the start point of each \"hack\" day (UTC+8)\n" \
                   "<code>/hack query</code>      list all following timers\n"
        if parameters[0] == "set":
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
        if parameters[0] == "query":
            if self.events.get(user.id) is None:
                return "No timer is set"
            return "Timer time:\n" + "\n".join([timestamp_to_str(x.time) for x in self.events[user.id]])

    def handle_callback(self, callback: telegram.CallbackQuery):
        user_id = callback.from_user.id
        try:
            target_user_id = int(callback.data[len(self.prefix):])
        except ValueError:
            return "Error Callback Data", True
        if user_id != target_user_id:
            pass
        t = time.time()
        if self.users.get(user_id) is None:
            return "You haven't setup the starting point", True
        self.add_record(user_id, t)
        if callback.message is not None:
            button = telegram.InlineKeyboardButton("Portal hacked", callback_data=self.prefix + str(user_id))
            callback.message.edit_text(
                "Portal hacked at {}".format(timestamp_to_str(t)),
                reply_markup=telegram.InlineKeyboardMarkup([[button]])
            )
            self.message_records[user_id] = []

        return "Hack time recorded", False

    def new_day(self, user_id, **kwargs):
        logging.debug("new day: {}".format(timestamp_to_str(kwargs["event"].time)))
        self.events[user_id].remove(kwargs["event"])
        for event in self.events[user_id]:
            self.scheduler.cancel(event)
        self.events[user_id] = []

        start_time = self.users[user_id].start_time
        next_day_time = previous_day_start(start_time) + DAY_SECONDS
        self.events[user_id].append(
            self.scheduler.enterabs(next_day_time, 2, self.new_day, argument=[user_id]))

        hacked_too_early = False
        for i, delay in enumerate(time_remain):
            self.events[user_id].append(
                self.scheduler.enter(delay[0], 3, self.timer_fired,
                                     argument=(user_id, time_remain_template.format(delay[1]))))

        last_hack_time = self.users[user_id].last_hack_time
        if last_hack_time is not None and last_hack_time < start_time - 12 * HOUR_SECONDS:
            hacked_too_early = True
            for i, delay in enumerate(emergency_remain):
                self.events[user_id].append(
                    self.scheduler.enterabs(last_hack_time + delay[0], 3, self.timer_fired,
                                            argument=(user_id, thirty_six_template.format(delay[1]))))

        button = telegram.InlineKeyboardButton("Portal hacked", callback_data=self.prefix + str(user_id))

        text_message = "Hello {}! Yet another day! Please remember to hack a portal today!" \
            .format(self.users[user_id].name)
        message = self.bot.send_message(user_id, text_message,
                                        reply_markup=telegram.InlineKeyboardMarkup([[button]]))
        self.message_records[user_id] = []
        self.message_records[user_id].append((message.chat_id, message.message_id))

    def timer_fired(self, user_id, description, **kwargs):
        logging.debug("fire time: {}".format(timestamp_to_str(kwargs["event"].time)))
        self.events[user_id].remove(kwargs["event"])
        start_time = self.users[user_id].start_time
        current_day_start_time = previous_day_start(start_time)

        if self.users[user_id].last_hack_time is not None \
                and self.users[user_id].last_hack_time > current_day_start_time:
            return
        button = telegram.InlineKeyboardButton("Portal hacked", callback_data=self.prefix + str(user_id))
        message = self.bot.send_message(user_id, description, reply_markup=telegram.InlineKeyboardMarkup([[button]]))
        if self.message_records.get(user_id) is None:
            self.message_records[user_id] = []
        if len(self.message_records[user_id]) > 0:
            for i in self.message_records[user_id]:
                self.bot.delete_message(i[0], i[1])
            self.message_records[user_id] = []
        self.message_records[user_id].append((message.chat_id, message.message_id))
