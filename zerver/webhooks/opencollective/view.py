from django.http import HttpRequest, HttpResponse

from zerver.decorator import webhook_view
from zerver.lib.response import json_success
from zerver.lib.typed_endpoint import JsonBodyPayload, typed_endpoint
from zerver.lib.validator import WildValue, check_string
from zerver.lib.webhooks.common import check_send_webhook_message
from zerver.models import UserProfile

MEMBER_NAME_TEMPLATE = "{name}"
AMOUNT_TEMPLATE = "{amount}"


@webhook_view("OpenCollective")
@typed_endpoint
def api_opencollective_webhook(
    request: HttpRequest,
    user_profile: UserProfile,
    *,
    payload: JsonBodyPayload[WildValue],
) -> HttpResponse:
    name = get_name(payload)
    amount = get_amount(payload)

    # construct the body of the message
    body = ""

    if name == "Incognito":  # Incognito donation
        body = f"An **Incognito** member donated **{amount}**! :tada:"
    else:  # non-Incognito donation
        body = f"@_**{name}** donated **{amount}**! :tada:"

    topic_name = "New Member"

    # send the message
    check_send_webhook_message(request, user_profile, topic_name, body)

    return json_success(request)


def get_name(payload: WildValue) -> str:
    return MEMBER_NAME_TEMPLATE.format(
        name=payload["data"]["member"]["memberCollective"]["name"].tame(check_string)
    )


def get_amount(payload: WildValue) -> str:
    return AMOUNT_TEMPLATE.format(
        amount=payload["data"]["order"]["formattedAmount"].tame(check_string)
    )
