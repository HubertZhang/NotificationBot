import logging
from typing import List

import telegram
from telegram.ext import CallbackQueryHandler, CallbackContext, CommandHandler, ApplicationBuilder
from telegram.error import TelegramError

from BotPlugin import BotPlugin
from HackBot import HackBot
from TimerBot import TimerBot
from PillBot import PillBot
from config import *

BotPlugins: List[BotPlugin] = []
root = logging.getLogger()
if DEBUG:
    root.setLevel(logging.DEBUG)


async def handleCallBackQuery(update: telegram.Update, context: CallbackContext):
    if update.callback_query is None:
        return

    callback_query: telegram.CallbackQuery = update.callback_query
    if callback_query.data is not None and callback_query.data.startswith(hackBot.prefix):
        notification, alert = await hackBot.handle_callback(callback_query)
    else:
        notification = "Error callback!"
        alert = False
    return callback_query.answer(text=notification, show_alert=alert)


def telegram_error(error: TelegramError):
    logging.warning('Update "{}" caused error "{}"'.format(error.message))

def toHandler(bp: BotPlugin) -> CommandHandler:
    async def handle_command(update: telegram.Update, context: CallbackContext):
        if update.message is None:
            return
        if update.message.from_user is None:
            return
        ret = bp.handle_command(update.message.from_user, update.message.chat, context.args or [])
        if ret:
            return await update.message.reply_html(ret)

    return CommandHandler(bp.prefix, handle_command)

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    hackBot = HackBot(application.bot)
    timerBot = TimerBot(application.bot)
    pillBot = PillBot(application.bot)

    application.add_handler(toHandler(hackBot))
    application.add_handler(toHandler(timerBot))
    application.add_handler(toHandler(pillBot))
    application.add_handler(CallbackQueryHandler(handleCallBackQuery))
    application.run_polling(drop_pending_updates=True)
