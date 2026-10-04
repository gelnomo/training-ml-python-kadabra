import hmac

from django.conf import settings
from adrf.decorators import api_view
from rest_framework import status
from rest_framework.response import Response

from apps.botAI.bot_core import TelegramBot


def _is_valid_telegram_request(request):
    """
    When BOT_SECRET_TOKEN is set, Telegram sends it back on every webhook call in
    the "X-Telegram-Bot-Api-Secret-Token" header; reject calls without it.
    """
    if not settings.BOT_SECRET_TOKEN:
        return True
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    return hmac.compare_digest(token, settings.BOT_SECRET_TOKEN)


def _is_staff(request):
    # JWT user (DRF) or the Django admin session user.
    user = getattr(request, "user", None)
    if user is not None and user.is_staff:
        return True
    session_user = getattr(getattr(request, "_request", None), "user", None)
    return bool(session_user is not None and session_user.is_staff)


@api_view(["GET", "POST"])
async def telegram_bot(request):
    if not _is_valid_telegram_request(request):
        return Response(status=status.HTTP_403_FORBIDDEN)
    await TelegramBot(request).ask()
    return Response(status=status.HTTP_200_OK)


@api_view(["GET"])
def telegram_subscribe(request):
    if not _is_staff(request):
        return Response(status=status.HTTP_403_FORBIDDEN)
    return TelegramBot(request).subscribe()


@api_view(["GET"])
def telegram_unsubscribe(request):
    if not _is_staff(request):
        return Response(status=status.HTTP_403_FORBIDDEN)
    return TelegramBot(request).unsubscribe()
