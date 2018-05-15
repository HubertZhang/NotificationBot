import logging

import telegram
from telegram.ext import Updater, CallbackQueryHandler, CommandHandler

from HackBot import HackBot
from config import *

hackBot: HackBot = None
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
    ret = hackBot.handle_command(update.message.from_user, update.message.chat, args)
    update.message.reply_text(ret, parse_mode="HTML")


def telegram_error(bot, update, error):
    logging.warning('Update "{}" caused error "{}"'.format(update, error))


if __name__ == '__main__':
    # global hackBot
    bot = telegram.Bot(token=BOT_TOKEN)
    hackBot = HackBot(bot)
    updater = Updater(BOT_TOKEN)
    updater.logger = root
    updater.dispatcher.add_handler(CommandHandler([hackBot.prefix], handleCommands, pass_args=True))
    updater.dispatcher.add_handler(CallbackQueryHandler(handleCallBackQuery))
    updater.dispatcher.add_error_handler(telegram_error)
    updater.start_polling(clean=True)
