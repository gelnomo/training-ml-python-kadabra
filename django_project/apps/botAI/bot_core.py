import io
from time import sleep
from django.http import HttpResponse
import requests
import telegram
from PIL import Image
from django.conf import settings
import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from apps.botAI.search_image import SearchImage
from apps.botAI.search_text import SearchText


class TelegramBot:
    def __init__(self, request):
        self.telegram_bot = telegram.Bot(token=settings.BOT_TOKEN)
        self.request = request

    @staticmethod
    async def cancel(update, user):
        await update.message.reply_text(
            f"Bye {user.first_name}! I hope we can talk again some day.", reply_markup=ReplyKeyboardRemove()
        )

    @staticmethod
    async def start(update, user):
        # print the welcoming message
        bot_welcome = f"""
<b>Hi {user.first_name}! This is a FilmSleuth</b>

I'm here to help you find the movie you are watching, whether it's by image or synopsis. 🎥🔍

To begin, you can send me a <b>PHOTO</b> of the movie or provide a <b>TEXT</b> synopsis. For better accuracy, try taking a photo where the main characters are on the screen.

Let's get started on our movie-finding adventure! 🎬✨        
"""
        await update.message.reply_text(bot_welcome, parse_mode='HTML')

        # option_buttons = [
        #     [InlineKeyboardButton("YES", callback_data="model_nlp_k")],
        #     [InlineKeyboardButton("NO", callback_data="model_cv_k")],
        # ]
        # reply_markup = ReplyKeyboardMarkup(keyboard=option_buttons, is_persistent=False, resize_keyboard=True, one_time_keyboard=True)
        #
        # reply_markup = InlineKeyboardMarkup(option_buttons)
        # await update.message.reply_text("[Optional] Select a Model:", reply_markup=reply_markup)

    @staticmethod
    async def callbacks(query):
        selected_option = query.data
        if selected_option == 'model_nlp_k':
            await query.message.reply_text('You selected NLP Model K!')

    async def is_command(self, message, update, user):
        if not message:
            return False

        if message == "/start":
            await self.start(update, user)
            return True
        elif message == "/cancel":
            await self.cancel(update, user)
            return True

        return False

    async def ask(self):
        if not self.request.body:
            return None

        message = None

        content = json.loads(self.request.body)
        update = telegram.Update.de_json(content, self.telegram_bot)

        try:
            query = update.callback_query

            if query:
                await self.callbacks(query)
                return

            await update.message.reply_chat_action(action="typing")
            user = update.message.from_user

            if update.message.text:
                message = update.message.text.encode("utf-8").decode()

            if not await self.is_command(message, update, user):
                await self.conversation(update, message, user)
        except Exception as ex:
            print(ex)
            await update.message.reply_text(
                f"There was an error.", reply_markup=ReplyKeyboardRemove()
            )

    @staticmethod
    async def conversation(update, message, user):
        celebrities = None
        await update.message.reply_text(
            f"Thank you {user.first_name.capitalize()}!\nI am taking a look at my movie collection, hold on....")
        await update.message.reply_chat_action(action="typing")

        if update.message.photo:
            photo = await update.message.photo[-1].get_file()
            img = Image.open(io.BytesIO(await photo.download_as_bytearray()))
            celebrities = SearchImage(img).process()

        if not message and not celebrities:
            await update.message.reply_text(
                f"Sorry {user.first_name.capitalize()}, I need to describe a movie with text or photo")
            return

        movie = SearchText(message, celebrities).process()

        if movie:
            await update.message.reply_text(movie, parse_mode='HTML')
        else:
            replay_message = f"Sorry!. There is not enough information about the movie you describe."
            await update.message.reply_text(text=replay_message, parse_mode='HTML')

    @staticmethod
    def subscribe():
        url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/setWebhook?url={settings.BOT_URL}"

        headers = {"accept": "application/json", "content-type": "application/json"}

        response = requests.get(url, headers=headers)

        django_response = HttpResponse(
            content=response.content,
            status=response.status_code,
            content_type=response.headers["Content-Type"],
        )

        return django_response

    @staticmethod
    def unsubscribe():
        url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/setWebhook?remove="

        headers = {"accept": "application/json", "content-type": "application/json"}

        response = requests.get(url, headers=headers)

        django_response = HttpResponse(
            content=response.content,
            status=response.status_code,
            content_type=response.headers["Content-Type"],
        )

        return django_response
