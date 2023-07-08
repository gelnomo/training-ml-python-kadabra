from django.urls import path
from apps.celebrity.views import telegram_bot, telegram_subscribe, telegram_unsubscribe

urlpatterns = [
    path("webhook/", telegram_bot, name="bot"),
    path("webhook/subscribe", telegram_subscribe, name="subscribe"),
    path("webhook/unsubscribe", telegram_unsubscribe, name="unsubscribe"),
]
