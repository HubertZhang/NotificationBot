import logging
import re
import threading
from html import escape
from typing import Dict

import sched_cond
from BotPlugin import *

WalkrState = [
    ("打造舰队", 1000000, 100000, 0, 0, 6000, 1),
    ("前往淘金小镇办事", 1080000, 0, 0, 0, 12000, 2),
    ("路上遭遇盗贼抢劫-选择贿赂", 0, 0, 0, 0, 12000, 2),
    ("付钱了事", 1200000, 0, 0, 0, 18000, 3),
    ("沙漠盗贼的邀约", 900000, 5000, 0, 0, 18000, 3),
    ("偷到世界宝藏的庆功宴", 0, 0, 20000, 26000, 18000, 3),
    ("世纪对决劝和", 0, 0, 24000, 20000, 18000, 3),
    ("互送礼物1", 1250000, 0, 0, 0, 18000, 3),
    ("互送礼物2", 0, 0, 18000, 28000, 18000, 3),
    ("和乐融融在酒馆里畅饮", 0, 0, 0, 0, 0, 0)
]
header = ["金币", "食物", "资源1", "资源2"]


# start
# next
# change
# text
class WalkrProgress:
    # states = [
    #     (1,"打造舰队", 1000000, 100000, 0, 0, 6000, 1),
    #     (2,"前往淘金小镇办事", 1080000, 0, 0, 0, 12000, 2),
    #     (2,"路上遭遇到贼抢劫-选择抵抗", 0, 0, 0, 0, 12000, 2),
    #     (3,"奋力抵抗", 0, 0, 20000, 26000, 18000, 3),
    #     (3,"牛仔警察协助", 0, 0, 22000, 22000, 18000, 3),
    #     (3,"与警察一起击退盗匪", 600000, 40000, 0, 0, 18000, 3),
    #     (3,"世纪对决劝和", 0, 0, 20000, 24000, 18000, 3),
    #     (3,"互送礼物1", 1250000, 0, 0, 0, 18000, 3),
    #     (3,"互送礼物2", 0, 0, 18000, 28000, 18000, 3),
    # ]

    def __init__(self):
        self.state = 0
        self.next_timer: sched_cond.Event = None
        self.description = ""
        pass

    def next(self):
        if self.state >= len(WalkrState) - 1:
            return -1, "传说已完成，请在 Walkr 中领取奖励"
        current_state = WalkrState[self.state]
        delay = current_state[-1] * 60 - 5
        self.state += 1
        next_state = WalkrState[self.state]

        needs = "，".join([str(x) + " " + header[i] for i, x in enumerate(next_state[1:5]) if x != 0])
        msg = "\"{}\" 已完成，飞行时间 {} 小时。\n" \
              "下一阶段： {}\n" \
              "须捐赠 {}\n" \
              "将在 {} 通知".format(current_state[0], current_state[-1], next_state[0], needs,
                                timestamp_to_str(time.time() + delay * 60))
        return delay, msg

    def notification_text(self):
        if self.state >= len(WalkrState) - 1:
            return "传说已完成，请在 Walkr 中领取奖励。" + self.description
        current_state = WalkrState[self.state]
        needs = "，".join([str(x) + " " + header[i] for i, x in enumerate(current_state[1:5]) if x != 0])
        msg = "\"{}\" 即将开始，\n" \
              "须捐赠 {}。\n" \
              "{}".format(current_state[0], needs, self.description)
        return msg


class WalkrBot(BotPlugin):
    prefix = "walkr"

    def __init__(self, bot: telegram.Bot):
        super().__init__(bot)
        self.scheduler = sched_cond.scheduler_condition(timefunc=time.time, delayfunc=time.sleep)
        threading.Thread(target=self.scheduler.run).start()

        self.records: Dict[int, WalkrProgress] = dict()
        # self.users: Dict[int, HackUser] = dict()
        #
        # for user in self.db.execute("SELECT user.user_id, username, first_name, last_name, "
        #                             "language_code, start_time, time_setting, latest_hack_time "
        #                             "FROM user LEFT OUTER JOIN latest_hack "
        #                             "ON user.user_id=latest_hack.user_id"):
        #     if DEBUG:
        #         if user[0] != 70166446:
        #             continue
        #     self.users[user[0]] = HackUser(*user)
        #     self.setup_timer(user[0])

    def handle_command(self, user: telegram.User, chat: telegram.Chat, parameters: [str]):
        if len(parameters) == 0:
            return ""
        if parameters[0] == "start":
            if self.records.get(chat.id) is not None:
                return "当前对话仍有未做完的传说"
            record = WalkrProgress()
            self.records[chat.id] = record
            return "传说提醒已创建。当前传说： 小酒馆的对决"

        if parameters[0] == "next":
            if self.records.get(chat.id) is None:
                return "未找到对应传说"
            record = self.records[chat.id]
            delay, description = record.next()
            if delay > 0:
                if record.next_timer is not None:
                    self.scheduler.cancel(record.next_timer)
                record.next_timer = self.scheduler.enter(delay * 60, 1, self.timer_fired, (chat.id,))
            else:
                del self.records[chat.id]
            return description
        if parameters[0] == "change":
            if self.records.get(chat.id) is None:
                return "未找到对应传说"
            if len(parameters) == 1:
                return escape("请指定下一阶段倒计时。请输入 分钟数 或 小时:分钟")
            record = self.records[chat.id]
            time_str: str = parameters[1]
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
                return "未能解析倒计时"
            if record.next_timer is not None:
                self.scheduler.cancel(record.next_timer)
            record.next_timer = self.scheduler.enter(delay * 60, 1, self.timer_fired, (chat.id,))
            return "下一提醒时间设定为：" + timestamp_to_str(time.time() + delay * 60)
        if parameters[0] == "text":
            if self.records.get(chat.id) is None:
                return "未找到对应传说"
            if len(parameters) == 1:
                return escape("已清空提醒文字")
            record = self.records[chat.id]
            record.description = " ".join(parameters[1:])
            return "提醒文字已设定"
        return ""

    def timer_fired(self, chat_id, **kwargs):
        logging.debug("fire time: {}".format(timestamp_to_str(kwargs["event"].time)))
        if self.records.get(chat_id) is None:
            return
        record = self.records[chat_id]
        record.next_timer = None

        msg = record.notification_text()
        try:
            message = self.bot.send_message(chat_id, msg)
        except telegram.TelegramError as e:
            logging.warning(str(e))
            return


if __name__ == '__main__':
    # global hackBot
    from telegram.ext import Updater, CommandHandler

    BOT_TOKEN = ""
    request_kwargs = None
    updater = Updater(BOT_TOKEN, request_kwargs=request_kwargs)

    bot = updater.bot
    root = logging.getLogger()
    plugin = WalkrBot(bot)


    def main_handle_commands(bot: telegram.Bot, update: telegram.Update, args):
        logging.info('Handling command')
        command = update.message.text[1:].split(None, 1)[0].split('@')[0].lower()
        new_args = list(args)
        new_args.insert(0, command)
        ret = plugin.handle_command(update.message.from_user, update.message.chat, new_args)
        update.message.reply_text(ret, parse_mode="HTML")


    def main_telegram_error(bot, update, error):
        logging.warning('Update "{}" caused error "{}"'.format(update, error))


    updater.logger = root
    updater.dispatcher.add_handler(
        CommandHandler(["start", "text", "change", "next"], main_handle_commands, pass_args=True))
    updater.dispatcher.add_error_handler(main_telegram_error)
    updater.start_polling(clean=True)
