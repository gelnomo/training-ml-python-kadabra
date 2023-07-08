from django.utils import timezone
from django.conf import settings
from rest_framework import views, response, status
from django.http import Http404
from adrf.decorators import api_view
from django.db.models import Q
import requests
from django.http import HttpResponse
import json

from rest_framework.response import Response

from apps.botAI.bot_core import TelegramBot


@api_view(["GET", "POST"])
async def telegram_bot(request):
    await TelegramBot(request).ask()
    return Response(status=status.HTTP_200_OK)


@api_view(["GET"])
def telegram_subscribe(request):
    return TelegramBot(request).subscribe()


@api_view(["GET"])
def telegram_unsubscribe(request):
    return TelegramBot(request).unsubscribe()
