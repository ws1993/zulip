from django.http import HttpRequest, HttpResponse

from zerver.decorator import webhook_view
from zerver.lib.response import json_success
from zerver.lib.typed_endpoint import JsonBodyPayload, typed_endpoint
from zerver.lib.validator import WildValue, check_string
from zerver.lib.webhooks.common import check_send_webhook_message
from zerver.models import UserProfile


@webhook_view("HomeAssistant")
@typed_endpoint
def api_homeassistant_webhook(
    request: HttpRequest,
    user_profile: UserProfile,
    *,
    payload: JsonBodyPayload[WildValue],
) -> HttpResponse:
    # construct the body of the message
    body = payload["message"].tame(check_string)

    # set the topic to the topic parameter, if given
    if "topic" in payload:
        topic_name = payload["topic"].tame(check_string)
    else:
        topic_name = "homeassistant"

    # send the message
    check_send_webhook_message(request, user_profile, topic_name, body)

    # return json result
    return json_success(request)
