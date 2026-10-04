import io
from html import escape
from constance import config
from django.http import HttpResponse
import requests
import telegram
from PIL import Image
from django.conf import settings
import json

from apps.document.schema import Movies
from ms_data_mining.redis_tools import Utils as rd, TimeTypeEnum
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from apps.botAI.search_image import SearchImage
from apps.botAI.search_text import SearchText


class TelegramBot:
    def __init__(self, request):
        self.telegram_bot = telegram.Bot(token=settings.BOT_TOKEN)
        self.request = request

    @staticmethod
    async def cancel(update, user):
        await update.message.reply_text(
            f"Bye {user.first_name}! I hope we can talk again some day.",
            reply_markup=ReplyKeyboardRemove(),
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
        await update.message.reply_text(bot_welcome, parse_mode="HTML")

        # option_buttons = [
        #     [InlineKeyboardButton("YES", callback_data="model_nlp_k")],
        #     [InlineKeyboardButton("NO", callback_data="model_cv_k")],
        # ]
        # reply_markup = ReplyKeyboardMarkup(keyboard=option_buttons, is_persistent=False, resize_keyboard=True, one_time_keyboard=True)
        #
        # reply_markup = InlineKeyboardMarkup(option_buttons)
        # await update.message.reply_text("[Optional] Select a Model:", reply_markup=reply_markup)

    @staticmethod
    async def movie_listing(update, user):
        # The listing is the same for every user, so cache it once (keyed by size).
        hash_key = rd.get_unique_name("movie", f"list.{config.SIZE_MOVIE_LISTING}")
        cache = rd()
        payload = cache.get_data(hash_key)
        if payload is None:
            time_type = TimeTypeEnum(config.MOVIE_LIST_TIME_TYPE)
            time_value = config.MOVIE_LIST_TIME_VALUE

            movies = Movies()
            payload = movies.query_movie_listing()
            _movie_listing = []
            for item, hit in enumerate(payload["hits"]["hits"]):
                title = escape(str(hit["_source"]["title"]), quote=False)
                _movie_listing.append(f'<b>{item + 1}</b>. {title} ({hit["_source"]["year"]})')
            payload = f"🎥 <b>TOP {config.SIZE_MOVIE_LISTING} - MOVIE LIST:</b>\n\n"
            payload += "\n".join(_movie_listing)
            cache.set_data(hash_key, payload, time_type, time_value)

        await update.message.reply_text(payload, parse_mode="HTML")

    @staticmethod
    async def callbacks(query):
        selected_option = query.data
        if selected_option == "model_nlp_k":
            await query.message.reply_text("You selected NLP Model K!")

    async def is_command(self, message, update, user):
        if not message:
            return False

        if message == "/start":
            await self.start(update, user)
            return True
        elif message == "/cancel":
            await self.cancel(update, user)
            return True
        elif message == "/list":
            await self.movie_listing(update, user)
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

            if update.message is None:
                # edited messages, channel posts, etc. are not handled
                return

            await update.message.reply_chat_action(action="typing")
            user = update.message.from_user

            if update.message.text:
                message = update.message.text.encode("utf-8").decode()

            if not await self.is_command(message, update, user):
                await self.conversation(update, message, user)
        except Exception as ex:
            print(ex)
            if update.message is not None:
                await update.message.reply_text(
                    "There was an error.", reply_markup=ReplyKeyboardRemove()
                )

    @staticmethod
    async def conversation(update, message, user):
        celebrities = None
        await update.message.reply_text(
            f"Thank you {user.first_name.capitalize()}!\nI am taking a look at my movie collection, hold on...."
        )
        await update.message.reply_chat_action(action="typing")

        if update.message.photo:
            photo = await update.message.photo[-1].get_file()
            img = Image.open(io.BytesIO(await photo.download_as_bytearray()))
            celebrities = SearchImage(img).process()

        if not message and not celebrities:
            await update.message.reply_text(
                f"Sorry {user.first_name.capitalize()}, I need to describe a movie with text or photo"
            )
            return

        movie = SearchText(message, celebrities).process()

        if movie:
            await update.message.reply_text(movie, parse_mode="HTML")
        else:
            replay_message = (
                f"Sorry!. There is not enough information about the movie you describe."
            )
            await update.message.reply_text(text=replay_message, parse_mode="HTML")

    @staticmethod
    def __telegram_api(method, params):
        url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/{method}"
        headers = {"accept": "application/json", "content-type": "application/json"}

        # requests URL-encodes the parameters (BOT_URL may contain query strings).
        response = requests.get(url, params=params, headers=headers, timeout=15)

        return HttpResponse(
            content=response.content,
            status=response.status_code,
            content_type=response.headers.get("Content-Type", "application/json"),
        )

    @staticmethod
    def subscribe():
        params = {"url": settings.BOT_URL}
        if settings.BOT_SECRET_TOKEN:
            params["secret_token"] = settings.BOT_SECRET_TOKEN
        return TelegramBot.__telegram_api("setWebhook", params)

    @staticmethod
    def unsubscribe():
        # An empty url removes the webhook integration.
        return TelegramBot.__telegram_api("setWebhook", {"url": ""})
