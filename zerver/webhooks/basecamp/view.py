import re
import string

from django.http import HttpRequest, HttpResponse

from zerver.decorator import webhook_view
from zerver.lib.exceptions import UnsupportedWebhookEventTypeError
from zerver.lib.response import json_success
from zerver.lib.typed_endpoint import JsonBodyPayload, typed_endpoint
from zerver.lib.validator import WildValue, check_string
from zerver.lib.webhooks.common import check_send_webhook_message
from zerver.models import UserProfile

from .support_event import SUPPORT_EVENTS

DOCUMENT_TEMPLATE = "{user_name} {verb} the document [{title}]({url})"
QUESTION_TEMPLATE = "{user_name} {verb} the question [{title}]({url})"
QUESTIONS_ANSWER_TEMPLATE = (
    "{user_name} {verb} the [answer]({answer_url})"
    " of the question [{question_title}]({question_url})"
)
COMMENT_TEMPLATE = (
    "{user_name} {verb} the [comment]({answer_url}) of the task [{task_title}]({task_url})"
)
MESSAGE_TEMPLATE = "{user_name} {verb} the message [{title}]({url})"
TODO_LIST_TEMPLATE = "{user_name} {verb} the todo list [{title}]({url})"
TODO_TEMPLATE = "{user_name} {verb} the todo task [{title}]({url})"

ALL_EVENT_TYPES = [
    "document",
    "question_answer",
    "question",
    "message",
    "todolist",
    "todo",
    "comment",
]


@webhook_view("Basecamp", all_event_types=ALL_EVENT_TYPES)
@typed_endpoint
def api_basecamp_webhook(
    request: HttpRequest,
    user_profile: UserProfile,
    *,
    payload: JsonBodyPayload[WildValue],
) -> HttpResponse:
    event = get_event_type(payload)

    if event not in SUPPORT_EVENTS:
        raise UnsupportedWebhookEventTypeError(event)

    topic_name = get_project_name(payload)
    if event.startswith("document_"):
        body = get_document_body(event, payload)
        event = "document"
    elif event.startswith("question_answer_"):
        body = get_questions_answer_body(event, payload)
        event = "question_answer"
    elif event.startswith("question_"):
        body = get_questions_body(event, payload)
        event = "question"
    elif event.startswith("message_"):
        body = get_message_body(event, payload)
        event = "message"
    elif event.startswith("todolist_"):
        body = get_todo_list_body(event, payload)
        event = "todolist"
    elif event.startswith("todo_"):
        body = get_todo_body(event, payload)
        event = "todo"
    elif event.startswith("comment_"):
        body = get_comment_body(event, payload)
        event = "comment"
    else:
        raise UnsupportedWebhookEventTypeError(event)

    check_send_webhook_message(request, user_profile, topic_name, body, event)
    return json_success(request)


def get_project_name(payload: WildValue) -> str:
    return payload["recording"]["bucket"]["name"].tame(check_string)


def get_event_type(payload: WildValue) -> str:
    return payload["kind"].tame(check_string)


def get_event_creator(payload: WildValue) -> str:
    return payload["creator"]["name"].tame(check_string)


def get_topic_url(payload: WildValue) -> str:
    return payload["recording"]["app_url"].tame(check_string)


def get_topic_title(payload: WildValue) -> str:
    return payload["recording"]["title"].tame(check_string)


def get_verb(event: str, prefix: str) -> str:
    verb = event.replace(prefix, "")
    if verb == "active":
        return "activated"

    matched = re.match(r"(?P<subject>[A-z]*)_changed", verb)
    if matched:
        return "changed {} of".format(matched.group("subject"))
    return verb


def add_punctuation_if_necessary(body: str, title: str) -> str:
    if title[-1] not in string.punctuation:
        body = f"{body}."
    return body


def get_document_body(event: str, payload: WildValue) -> str:
    return get_generic_body(event, payload, "document_", DOCUMENT_TEMPLATE)


def get_questions_answer_body(event: str, payload: WildValue) -> str:
    verb = get_verb(event, "question_answer_")
    question = payload["recording"]["parent"]
    title = question["title"].tame(check_string)
    template = add_punctuation_if_necessary(QUESTIONS_ANSWER_TEMPLATE, title)

    return template.format(
        user_name=get_event_creator(payload),
        verb=verb,
        answer_url=get_topic_url(payload),
        question_title=title,
        question_url=question["app_url"].tame(check_string),
    )


def get_comment_body(event: str, payload: WildValue) -> str:
    verb = get_verb(event, "comment_")
    task = payload["recording"]["parent"]
    template = add_punctuation_if_necessary(COMMENT_TEMPLATE, task["title"].tame(check_string))

    return template.format(
        user_name=get_event_creator(payload),
        verb=verb,
        answer_url=get_topic_url(payload),
        task_title=task["title"].tame(check_string),
        task_url=task["app_url"].tame(check_string),
    )


def get_questions_body(event: str, payload: WildValue) -> str:
    return get_generic_body(event, payload, "question_", QUESTION_TEMPLATE)


def get_message_body(event: str, payload: WildValue) -> str:
    return get_generic_body(event, payload, "message_", MESSAGE_TEMPLATE)


def get_todo_list_body(event: str, payload: WildValue) -> str:
    return get_generic_body(event, payload, "todolist_", TODO_LIST_TEMPLATE)


def get_todo_body(event: str, payload: WildValue) -> str:
    return get_generic_body(event, payload, "todo_", TODO_TEMPLATE)


def get_generic_body(event: str, payload: WildValue, prefix: str, template: str) -> str:
    verb = get_verb(event, prefix)
    title = get_topic_title(payload)
    template = add_punctuation_if_necessary(template, title)

    return template.format(
        user_name=get_event_creator(payload),
        verb=verb,
        title=get_topic_title(payload),
        url=get_topic_url(payload),
    )
