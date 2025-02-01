# Webhooks for external integrations.
import time

from django.http import HttpRequest, HttpResponse

from zerver.decorator import webhook_view
from zerver.lib.response import json_success
from zerver.lib.typed_endpoint import JsonBodyPayload, typed_endpoint
from zerver.lib.validator import WildValue, check_float, check_int, check_string, check_union
from zerver.lib.webhooks.common import check_send_webhook_message
from zerver.models import UserProfile

MESSAGE_TEMPLATE = (
    "You are going to derail from goal **{goal_name}** in **{time:0.1f} hours**. "
    "You need **{limsum}** to avoid derailing.\n"
    "* Pledge: **${pledge}** {expression}\n"
)


def get_time(payload: WildValue) -> float:
    losedate = payload["goal"]["losedate"].tame(check_int)
    time_remaining = (losedate - time.time()) / 3600
    return time_remaining


@webhook_view("Beeminder")
@typed_endpoint
def api_beeminder_webhook(
    request: HttpRequest,
    user_profile: UserProfile,
    *,
    payload: JsonBodyPayload[WildValue],
) -> HttpResponse:
    goal_name = payload["goal"]["slug"].tame(check_string)
    limsum = payload["goal"]["limsum"].tame(check_string)
    pledge = payload["goal"]["pledge"].tame(check_union([check_int, check_float]))
    time_remain = get_time(payload)  # time in hours
    # To show user's probable reaction by looking at pledge amount
    if pledge > 0:
        expression = ":worried:"
    else:
        expression = ":relieved:"

    topic_name = "beekeeper"
    body = MESSAGE_TEMPLATE.format(
        goal_name=goal_name,
        time=time_remain,
        limsum=limsum,
        pledge=pledge,
        expression=expression,
    )
    check_send_webhook_message(request, user_profile, topic_name, body)
    return json_success(request)
