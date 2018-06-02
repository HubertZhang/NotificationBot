import logging
import re
import sqlite3
import threading
from html import escape
from typing import Dict

import sched_cond
from BotPlugin import *


# Hi @User, yet another day! <Description>
## [Action]
# User: from whom
# Target: send to which chat (fail then delete)
# Time: fire time
# Description: description
# Finished: done?
## Action: text on button


class PillRecord:
    def __init__(self, user_id: int, chat_id: int, alarm_time, description):
        self.user_id = user_id
        self.chat_id = chat_id
        self.alarm_time = alarm_time
        self.description = description
        self.timer = None


class PillBot(BotPlugin):
    prefix = "pill"

    def __init__(self, bot: telegram.Bot):
        super().__init__(bot)
        self.db = sqlite3.connect("data/pill_data.sqlite", check_same_thread=False)
        self.scheduler = sched_cond.scheduler_condition(timefunc=time.time, delayfunc=time.sleep)
        threading.Thread(target=self.scheduler.run).start()
        self.records: Dict[int, PillRecord] = dict()
        self.users: Dict[int, User] = dict()

        for record in self.db.execute("SELECT id, user_id, chat_id, alarm_time, description FROM pill_record"):
            if DEBUG:
                if record[1] != 70166446:
                    continue
            user = self.db.execute(
                "SELECT user_id, username, first_name, last_name, language_code FROM main.user WHERE user_id = ?",
                [record[1]]).fetchone()
            self.users[record[1]] = User(*user)
            self.records[record[0]] = PillRecord(*record[1:])
            self.setup_timer(record[0])

        new_day = previous_day_start(0) + DAY_SECONDS
        self.main_timer = self.scheduler.enterabs(new_day, 1, self.new_day)

    def new_day(self, **kwargs):
        logging.debug("new day: {}".format(timestamp_to_str(time.time())))
        new_day = previous_day_start(0) + DAY_SECONDS
        self.main_timer = self.scheduler.enterabs(new_day, 1, self.new_day)

        for record_id in self.records:
            self.setup_timer(record_id)

    def setup_timer(self, record_id):
        r = self.records[record_id]
        if r.alarm_time < 0:
            return
        alarm_time = r.alarm_time
        day_start = previous_day_start(0)
        if day_start + alarm_time < time.time():
            return
        r.timer = self.scheduler.enterabs(day_start + alarm_time, 3, self.timer_fired, argument=[record_id])

    def update_user(self, user: telegram.User):
        self.db.execute(
            "INSERT OR REPLACE INTO user VALUES (?,?,?,?,?)",
            (user.id, user.username, user.first_name, user.last_name, user.language_code)
        )

    def get_user(self, user_id):
        u = self.users.get(user_id)
        if u is None:
            user = self.db.execute("SELECT * FROM main.user WHERE user_id = ?", [user_id]).fetchone()

            if user is None:
                return User(user_id, str(user_id), "", "", "")
            else:
                self.users[user_id] = User(*user)
                return self.users[user_id]
        return u

    def add_record(self, user_id: int, chat_id: int, alarm_time: int, description: str):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO pill_record(user_id, chat_id, alarm_time, description) VALUES (?,?,?,?)",
                       (user_id, chat_id, alarm_time, description))
        record_id = cursor.lastrowid
        self.db.commit()

        self.records[record_id] = PillRecord(user_id, chat_id, alarm_time, description)
        self.setup_timer(record_id)
        return record_id

    def remove_record(self, record_id):
        self.db.execute(
            "DELETE FROM pill_record WHERE id = ?", [record_id]
        )
        self.db.commit()
        self.records.pop(record_id, None)

    def set_record_time(self, record_id, alarm_time):
        if alarm_time is not None:
            self.db.execute(
                "UPDATE pill_record "
                "SET alarm_time=?"
                "WHERE id=?",
                (alarm_time, record_id))
            self.db.commit()
            self.records[record_id].alarm_time = alarm_time

    def set_record_description(self, record_id, description):
        self.db.execute(
            "UPDATE pill_record "
            "SET description=?"
            "WHERE id=?",
            (description, record_id))
        self.db.commit()
        self.records[record_id].description = description

    def handle_command(self, user: telegram.User, chat: telegram.Chat, parameters: [str]):
        if len(parameters) == 0:
            return "<code>/pill add hh:mm [description]</code>  set the notification time (UTC+8)\n" \
                   "<code>/pill list</code>       list all timers\n" \
                   "<code>/pill del record_id</code>      set time for notifications \n" \
                   "<code>/pill settime record_id hh:mm</code>\n" \
                   "<code>/pill setdes record_id [description]</code>"

        if parameters[0] == "add":
            if len(parameters) < 2:
                return "Please set time. Format: hh:mm in UTC+8"
            start = parameters[1]
            r = re.search("(\\d{1,2}):(\\d{1,2})", start)
            if r is None:
                return "Format error! Please set time. Format: hh:mm in UTC+8"
            h = int(r.group(1))
            h = (h + 16) % 24
            m = int(r.group(2))
            if len(parameters) == 2:
                description = None
            else:
                description = escape(" ".join(parameters[2:]))
            self.update_user(user)
            self.add_record(user.id, chat.id, (h * 60 + m) * 60, description)
            return "Added"
        if parameters[0] == "list":
            reply = ""
            if chat.id == user.id:
                for i in self.records:
                    if self.records[i].user_id == user.id:
                        reply += "<code>{:03}</code> <code>{}</code>  {}\n".format(i, day_time_to_str(
                            self.records[i].alarm_time),
                                                                                   self.records[i].description)
            else:
                for i in self.records:
                    if self.records[i].user_id == user.id and self.records[i].chat_id == chat.id:
                        reply += "<code>{:03}</code> <code>{}</code>  {}\n".format(i, day_time_to_str(
                            self.records[i].alarm_time),
                                                                                   self.records[i].description)
            if reply == "":
                return "Not found"
            return "You have following timers:\n" + reply
        # if parameters[0] == "alarm":
        #     if self.users.get(user.id) is None:
        #         return "Please set day start time first"
        #     if len(parameters) == 1:
        #         return escape("Please provide alarm times. Format: \nhh:mm <hh:mm> <hh:mm>... in UTC+8")
        #     if parameters[1] == "reset":
        #         self.change_time_setting(user, None)
        #         return "Alarms reset to default."
        #     u = self.users[user.id]
        #     setting = []
        #     for s in parameters[1:]:
        #         r = re.search("(\\d{1,2}):(\\d{1,2})", s)
        #         if r is None:
        #             return escape(
        #                 "Format error! Please provide alarm times. Format: \nhh:mm <hh:mm> <hh:mm>... in UTC+8")
        #         h = int(r.group(1))
        #         h = (h + 16) % 24
        #         m = int(r.group(2))
        #         new_time = (h * 60 + m) * 60
        #         new_time = (u.start_time - new_time + DAY_SECONDS) % DAY_SECONDS
        #         setting.append(new_time)
        #     setting.sort(reverse=True)
        #     self.change_time_setting(user, setting)
        #     reply = "You will receive notification at:\n" + \
        #             "\n".join([day_time_to_str(u.start_time - x) for x in setting])
        #
        #     return reply
        if parameters[0] == "del":
            if len(parameters) != 2:
                return "Please provide record id"
            try:
                record_id = int(parameters[1])
            except ValueError:
                return "Please provide valid record id"
            self.update_user(user)
            if self.records.get(record_id) is not None:
                record = self.records[record_id]
                if record.user_id != user.id:
                    return "This is not your timer"
                self.remove_record(record_id)
                return "Removed!"
            return "You haven't set up the timer."
        return ""

    def handle_callback(self, callback: telegram.CallbackQuery):
        return "", False
        user_id = callback.from_user.id
        try:
            target_user_id = int(callback.data[len(self.prefix):])
        except ValueError:
            return "Error Callback Data", True
        if user_id != target_user_id:
            return "This is not your timer", True
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
            self.users[user_id].message_records = []

        return "Hack time recorded", False

    def timer_fired(self, record_id, **kwargs):
        logging.debug("fire time: {}".format(timestamp_to_str(kwargs["event"].time)))
        r = self.records.get(record_id)
        if r is None:
            return
        r.timer = None
        if r.description is None:
            description = ""
        else:
            description = r.description

        user = self.get_user(r.user_id)

        msg = "Hi {}, yet another day! {}".format(user.name, description)

        try:
            message = self.bot.send_message(r.chat_id, msg)
        except telegram.TelegramError:
            return
