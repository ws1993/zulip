from typing import Annotated

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from pydantic import StringConstraints

from zerver.actions.saved_snippets import (
    do_create_saved_snippet,
    do_delete_saved_snippet,
    do_get_saved_snippets,
)
from zerver.lib.response import json_success
from zerver.lib.typed_endpoint import typed_endpoint
from zerver.models import SavedSnippet, UserProfile


def get_saved_snippets(
    request: HttpRequest,
    user_profile: UserProfile,
) -> HttpResponse:
    return json_success(request, data={"saved_snippets": do_get_saved_snippets(user_profile)})


@typed_endpoint
def create_saved_snippet(
    request: HttpRequest,
    user_profile: UserProfile,
    *,
    title: Annotated[
        str,
        StringConstraints(
            min_length=1, max_length=SavedSnippet.MAX_TITLE_LENGTH, strip_whitespace=True
        ),
    ],
    content: Annotated[
        str,
        StringConstraints(
            min_length=1, max_length=settings.MAX_MESSAGE_LENGTH, strip_whitespace=True
        ),
    ],
) -> HttpResponse:
    title = title.strip()
    content = content.strip()
    saved_snippet = do_create_saved_snippet(title, content, user_profile)
    return json_success(request, data={"saved_snippet_id": saved_snippet.id})


def delete_saved_snippet(
    request: HttpRequest,
    user_profile: UserProfile,
    *,
    saved_snippet_id: int,
) -> HttpResponse:
    do_delete_saved_snippet(saved_snippet_id, user_profile)
    return json_success(request)
