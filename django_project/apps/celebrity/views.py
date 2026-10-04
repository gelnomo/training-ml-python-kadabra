import hmac
import json
import logging

from django.conf import settings
from adrf.decorators import api_view
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.botAI.bot_core import TelegramBot, forget_update, is_new_update
from apps.celebrity.tasks import telegram_process_update

logger = logging.getLogger(__name__)


def _is_valid_telegram_request(request):
    """
    When BOT_SECRET_TOKEN is set, Telegram sends it back on every webhook call in
    the "X-Telegram-Bot-Api-Secret-Token" header; reject calls without it.
    """
    if not settings.BOT_SECRET_TOKEN:
        return True
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    return hmac.compare_digest(token, settings.BOT_SECRET_TOKEN)


@api_view(["GET", "POST"])
def telegram_bot(request):
    """
    Telegram webhook: validate, queue the update for a Celery worker and answer
    200 right away. Telegram resends updates that aren't answered quickly, so the
    heavy work must not run here.
    """
    if not _is_valid_telegram_request(request):
        return Response(status=status.HTTP_403_FORBIDDEN)
    if not request.body:
        return Response(status=status.HTTP_200_OK)

    try:
        content = json.loads(request.body)
    except ValueError:
        return Response(status=status.HTTP_400_BAD_REQUEST)

    update_id = content.get("update_id")
    if is_new_update(update_id):
        try:
            telegram_process_update.delay(content)
        except Exception:
            # Let Telegram retry: forget the id and answer with an error.
            forget_update(update_id)
            logger.exception("Could not queue Telegram update %s", update_id)
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)
    else:
        logger.info("Ignoring duplicate Telegram update %s", content.get("update_id"))
    return Response(status=status.HTTP_200_OK)


# Webhook management is staff-only: a staff JWT, or a staff user logged in to /admin/.
STAFF_AUTHENTICATION = [JWTAuthentication, SessionAuthentication]


@api_view(["GET"])
@authentication_classes(STAFF_AUTHENTICATION)
@permission_classes([IsAdminUser])
def telegram_subscribe(request):
    return TelegramBot.subscribe()


@api_view(["GET"])
@authentication_classes(STAFF_AUTHENTICATION)
@permission_classes([IsAdminUser])
def telegram_unsubscribe(request):
    return TelegramBot.unsubscribe()
