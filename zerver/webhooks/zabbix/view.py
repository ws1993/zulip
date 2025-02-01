from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext as _

from zerver.actions.message_send import send_rate_limited_pm_notification_to_bot_owner
from zerver.decorator import webhook_view
from zerver.lib.exceptions import JsonableError
from zerver.lib.response import json_success
from zerver.lib.send_email import FromAddress
from zerver.lib.typed_endpoint import JsonBodyPayload, typed_endpoint
from zerver.lib.validator import WildValue, check_string
from zerver.lib.webhooks.common import check_send_webhook_message
from zerver.models import UserProfile

MISCONFIGURED_PAYLOAD_ERROR_MESSAGE = """
Hi there! Your bot {bot_name} just received a Zabbix payload that is missing
some data that Zulip requires. This usually indicates a configuration issue
in your Zabbix webhook settings. Please make sure that you set the
script correctly and provide all the required parameters
when configuring the Zabbix webhook. Contact {support_email} if you
need further help!
"""

ZABBIX_TOPIC_TEMPLATE = "{hostname}"
ZABBIX_MESSAGE_TEMPLATE = """
{status} ({severity}) alert on [{hostname}]({link}):
* {trigger}
* {item}
""".strip()


@webhook_view("Zabbix")
@typed_endpoint
def api_zabbix_webhook(
    request: HttpRequest,
    user_profile: UserProfile,
    *,
    payload: JsonBodyPayload[WildValue],
) -> HttpResponse:
    try:
        body = get_body_for_http_request(payload)
        topic_name = get_topic_for_http_request(payload)
    except ValidationError:
        message = MISCONFIGURED_PAYLOAD_ERROR_MESSAGE.format(
            bot_name=user_profile.full_name,
            support_email=FromAddress.SUPPORT,
        ).strip()
        send_rate_limited_pm_notification_to_bot_owner(user_profile, user_profile.realm, message)

        raise JsonableError(_("Invalid payload"))

    check_send_webhook_message(request, user_profile, topic_name, body)
    return json_success(request)


def get_topic_for_http_request(payload: WildValue) -> str:
    return ZABBIX_TOPIC_TEMPLATE.format(hostname=payload["hostname"].tame(check_string))


def get_body_for_http_request(payload: WildValue) -> str:
    hostname = payload["hostname"].tame(check_string)
    severity = payload["severity"].tame(check_string)
    status = payload["status"].tame(check_string)
    item = payload["item"].tame(check_string)
    trigger = payload["trigger"].tame(check_string)
    link = payload["link"].tame(check_string)

    data = {
        "hostname": hostname,
        "severity": severity,
        "status": status,
        "item": item,
        "trigger": trigger,
        "link": link,
    }
    return ZABBIX_MESSAGE_TEMPLATE.format(**data)
