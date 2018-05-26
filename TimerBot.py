import logging
import re
import threading
from html import escape
from typing import Dict, List

import sched_cond
from BotPlugin import *


class TimerBot(BotPlugin):
    prefix = "timer"

    def __init__(self, bot: telegram.Bot):
        super().__init__(bot)
        self.events: Dict[int, List[sched_cond.Event]] = dict()
        self.scheduler = sched_cond.scheduler_condition(timefunc=time.time, delayfunc=time.sleep)
        threading.Thread(target=self.scheduler.run).start()

    def setup_timer(self, user_id: int, delay: int, description: str = ""):
        u = self.events[user_id]
        event = self.scheduler.enter(delay, 3, self.timer_fired, argument=(user_id, delay, description))
        u.append(event)

    def handle_command(self, user: telegram.User, chat: telegram.Chat, parameters: [str]):
        if len(parameters) == 0:
            return "<code>/timer mm &lt;description&gt;</code>     set a timer after <code>mm</code> minutes\n" \
                   "<code>/timer hh:mm &lt;description&gt;</code>  set a timer after <code>hh</code> hours and <code>mm</code> minutes\n" \
                   "<code>/timer status</code>               list all following timers\n" \
                   "<code>/timer del id</code>               remove a timer"
        if parameters[0] == "del":
            if len(parameters) != 2:
                return "Please provide timer's id"
            if self.events.get(user.id) is None:
                return "You haven't set any timer."
            u = self.events[user.id]
            try:
                timer_id = int(parameters[1])
            except ValueError:
                timer_id = -1
            if len(u) < timer_id or timer_id < 0:
                return "Timer not found"
            event = u[timer_id]
            self.scheduler.cancel(event)
            u.remove(event)
            return "Removed"

        if parameters[0] == "status":
            if self.events.get(user.id) is None:
                return "You haven't set any timer."
            u = self.events[user.id]
            if len(u) == 0:
                return "You haven't set any timer."
            reply = "Current timers:\n"
            for i, x in enumerate(u):
                if x.argument[2] != "":
                    des = x.argument[2]
                else:
                    des = "(no description)"
                reply += "{:04}  at {} {}\n".format(i, day_time_to_str(int(x.time)), des)
            return reply

        time_str: str = parameters[0]
        delay = -1
        if re.fullmatch("\\d+:\\d{1,2}", time_str):
            try:
                h_m = time_str.split(":")
                h = int(h_m[0])
                m = int(h_m[1])
                if m > 60:
                    raise ValueError
                delay = h * 60 + m
            except ValueError:
                delay = -1
        elif time_str.isdigit():
            try:
                delay = int(time_str)
            except ValueError:
                delay = -1

        if delay == -1:
            return "Wrong time format"
        if delay > 1440:
            return "Time is too long"
        if len(parameters) > 1:
            des = " ".join(parameters[1:])
        else:
            des = ""

        if self.events.get(user.id) is None:
            self.events[user.id] = []
        u = self.events[user.id]
        if DEBUG:
            event = self.scheduler.enter(delay, 3, self.timer_fired, (user.id, delay, des))
        else:
            event = self.scheduler.enter(delay * 60, 3, self.timer_fired, (user.id, delay * 60, des))
        u.append(event)
        return "Timer set"

    def handle_callback(self, callback: telegram.CallbackQuery):
        return "", False

    def timer_fired(self, user_id, delay: int, description: str, **kwargs):
        logging.debug("fire time: {}".format(timestamp_to_str(kwargs["event"].time)))
        u = self.events[user_id]
        u.remove(kwargs["event"])
        if description != "":
            msg = "Time's up! Timer description:\n"+escape(description, quote=False)
        else:
            msg = "Time's up! {} elapsed.".format(time_interval_to_remain(delay))
        try:
            message = self.bot.send_message(user_id, msg)
        except telegram.TelegramError as e:
            print(e)
            return
