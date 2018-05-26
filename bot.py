import logging
from typing import List

import telegram
from telegram.ext import Updater, CallbackQueryHandler, CommandHandler

from BotPlugin import BotPlugin
from HackBot import HackBot
from TimerBot import TimerBot
from PillBot import PillBot
from config import *

BotPlugins: List[BotPlugin] = []
root = logging.getLogger()
if DEBUG:
    root.setLevel(logging.DEBUG)


def handleCallBackQuery(bot: telegram.Bot, update: telegram.Update):
    if update.callback_query is None:
        return

    callback_query: telegram.CallbackQuery = update.callback_query
    if callback_query.data is not None and callback_query.data.startswith(hackBot.prefix):
        notification, alert = hackBot.handle_callback(callback_query)
    else:
        notification = "Error callback!"
        alert = False
    callback_query.answer(text=notification, show_alert=alert)


def handleCommands(bot: telegram.Bot, update: telegram.Update, args):
    logging.info('Handling command')
    command = update.message.text[1:].split(None, 1)[0].split('@')[0].lower()
    for plugin in BotPlugins:
        if plugin.prefix == command:
            ret = plugin.handle_command(update.message.from_user, update.message.chat, args)
            update.message.reply_text(ret, parse_mode="HTML")


def telegram_error(bot, update, error):
    logging.warning('Update "{}" caused error "{}"'.format(update, error))


if __name__ == '__main__':
    # global hackBot
    updater = Updater(BOT_TOKEN, request_kwargs=request_kwargs)

    bot = updater.bot
    hackBot = HackBot(bot)
    timerBot = TimerBot(bot)
    pillBot = PillBot(bot)
    BotPlugins.append(hackBot)
    BotPlugins.append(timerBot)
    BotPlugins.append(pillBot)

    updater.logger = root
    updater.dispatcher.add_handler(CommandHandler([x.prefix for x in BotPlugins], handleCommands, pass_args=True))
    updater.dispatcher.add_handler(CallbackQueryHandler(handleCallBackQuery))
    updater.dispatcher.add_error_handler(telegram_error)
    updater.start_polling(clean=True)
