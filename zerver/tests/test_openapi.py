import os
from collections.abc import Callable, Mapping
from typing import Any
from unittest.mock import MagicMock, patch

import yaml
from django.http import HttpResponse
from django.urls import URLPattern
from django.utils import regex_helper
from pydantic import TypeAdapter

from zerver.lib.request import arguments_map
from zerver.lib.rest import rest_dispatch
from zerver.lib.test_classes import ZulipTestCase
from zerver.lib.typed_endpoint import parse_view_func_signature
from zerver.lib.utils import assert_is_not_none
from zerver.openapi.markdown_extension import generate_curl_example, render_curl_example
from zerver.openapi.openapi import (
    OPENAPI_SPEC_PATH,
    OpenAPISpec,
    Parameter,
    SchemaError,
    find_openapi_endpoint,
    get_openapi_fixture,
    get_openapi_parameters,
    get_openapi_paths,
    openapi_spec,
    validate_against_openapi_schema,
    validate_request,
    validate_schema,
)
from zerver.tornado.views import get_events, get_events_backend

TEST_ENDPOINT = "/messages/{message_id}"
TEST_METHOD = "patch"
TEST_RESPONSE_BAD_REQ = "400"
TEST_RESPONSE_SUCCESS = "200"

VARMAP = {
    "integer": int,
    "string": str,
    "boolean": bool,
    "object": dict,
    "NoneType": type(None),
    "number": float,
}


def schema_type(schema: dict[str, Any], defs: Mapping[str, Any] = {}) -> type | tuple[type, object]:
    if "oneOf" in schema:
        # Hack: Just use the type of the first value
        # Ideally, we'd turn this into a Union type.
        return schema_type(schema["oneOf"][0], defs)
    elif "anyOf" in schema:
        return schema_type(schema["anyOf"][0], defs)
    elif schema.get("contentMediaType") == "application/json":
        return schema_type(schema["contentSchema"], defs)
    elif "$ref" in schema:
        return schema_type(defs[schema["$ref"]], defs)
    elif schema["type"] == "array":
        return (list, schema_type(schema["items"], defs))
    else:
        return VARMAP[schema["type"]]


class OpenAPIToolsTest(ZulipTestCase):
    """Make sure that the tools we use to handle our OpenAPI specification
    (located in zerver/openapi/openapi.py) work as expected.

    These tools are mostly dedicated to fetching parts of the -already parsed-
    specification, and comparing them to objects returned by our REST API.
    """

    def test_get_openapi_fixture(self) -> None:
        actual = get_openapi_fixture(TEST_ENDPOINT, TEST_METHOD, TEST_RESPONSE_BAD_REQ)[0]["value"]
        expected = {
            "code": "BAD_REQUEST",
            "msg": "You don't have permission to edit this message",
            "result": "error",
        }
        self.assertEqual(actual, expected)

    def test_get_openapi_parameters(self) -> None:
        actual = get_openapi_parameters(TEST_ENDPOINT, TEST_METHOD)
        expected_item = Parameter(
            kind="path",
            name="message_id",
            description="The target message's ID.\n",
            json_encoded=False,
            value_schema={"type": "integer"},
            example=43,
            required=True,
            deprecated=False,
        )
        assert expected_item in actual

    def test_validate_against_openapi_schema(self) -> None:
        with self.assertRaisesRegex(
            SchemaError, r"Additional properties are not allowed \('foo' was unexpected\)"
        ):
            bad_content: dict[str, object] = {
                "msg": "",
                "result": "success",
                "foo": "bar",
            }
            validate_against_openapi_schema(
                bad_content, TEST_ENDPOINT, TEST_METHOD, TEST_RESPONSE_SUCCESS
            )

        with self.assertRaisesRegex(SchemaError, r"42 is not of type 'string'"):
            bad_content = {
                "msg": 42,
                "result": "success",
            }
            validate_against_openapi_schema(
                bad_content, TEST_ENDPOINT, TEST_METHOD, TEST_RESPONSE_SUCCESS
            )

        with self.assertRaisesRegex(SchemaError, r"'msg' is a required property"):
            bad_content = {
                "result": "success",
            }
            validate_against_openapi_schema(
                bad_content, TEST_ENDPOINT, TEST_METHOD, TEST_RESPONSE_SUCCESS
            )

        # No exceptions should be raised here.
        good_content = {
            "msg": "",
            "result": "success",
        }
        validate_against_openapi_schema(
            good_content, TEST_ENDPOINT, TEST_METHOD, TEST_RESPONSE_SUCCESS
        )

        # Overwrite the exception list with a mocked one
        test_dict: dict[str, Any] = {}

        # Check that validate_against_openapi_schema correctly
        # descends into 'deep' objects and arrays.  Test 1 should
        # pass, Test 2 has a 'deep' extraneous key and Test 3 has a
        # 'deep' opaque object. Also the parameters are a heterogeneous
        # mix of arrays and objects to verify that our descent logic
        # correctly gets to the deeply nested objects.
        test_filename = os.path.join(os.path.dirname(OPENAPI_SPEC_PATH), "testing.yaml")
        with open(test_filename) as test_file:
            test_dict = yaml.safe_load(test_file)
        with patch("zerver.openapi.openapi.openapi_spec", OpenAPISpec(test_filename)):
            validate_against_openapi_schema(
                {
                    "top_array": [
                        {"obj": {"str3": "test"}},
                        [{"str1": "success", "str2": "success"}],
                    ],
                },
                "/test1",
                "get",
                "200",
            )
            with self.assertRaisesRegex(
                SchemaError,
                r"\{'obj': \{'str3': 'test', 'str4': 'extraneous'\}\} is not valid under any of the given schemas",
            ):
                validate_against_openapi_schema(
                    {
                        "top_array": [
                            {"obj": {"str3": "test", "str4": "extraneous"}},
                            [{"str1": "success", "str2": "success"}],
                        ],
                    },
                    "/test2",
                    "get",
                    "200",
                )
            with self.assertRaisesRegex(
                SchemaError,
                r"additionalProperties needs to be defined for objects to make sure they have no additional properties left to be documented\.",
            ):
                # Checks for opaque objects
                validate_schema(
                    test_dict["paths"]["/test3"]["get"]["responses"]["200"]["content"][
                        "application/json"
                    ]["schema"]
                )

    def test_live_reload(self) -> None:
        # Force the reload by making the last update date < the file's last
        # modified date
        openapi_spec.mtime = 0
        get_openapi_fixture(TEST_ENDPOINT, TEST_METHOD)

        # Check that the file has been reloaded by verifying that the last
        # update date isn't zero anymore
        self.assertNotEqual(openapi_spec.mtime, 0)

        # Now verify calling it again doesn't call reload
        old_openapi = openapi_spec.openapi()
        get_openapi_fixture(TEST_ENDPOINT, TEST_METHOD)
        new_openapi = openapi_spec.openapi()
        self.assertIs(old_openapi, new_openapi)


class OpenAPIArgumentsTest(ZulipTestCase):
    # This will be filled during test_openapi_arguments:
    checked_endpoints: set[str] = set()
    pending_endpoints = {
        #### TODO: These endpoints are a priority to document:
        # These are a priority to document but don't match our normal URL schemes
        # and thus may be complicated to document with our current tooling.
        # (No /api/v1/ or /json prefix).
        "/avatar/{email_or_id}",
        ## This one is in zulip.yaml, but not the actual docs.
        # "/api/v1/user_uploads/{realm_id_str}/{filename}",
        ## And this one isn't, and isn't really representable
        # "/user_uploads/{realm_id_str}/{filename}",
        #### These realm administration settings are valuable to document:
        # Delete a data export.
        "/export/realm/{export_id}",
        # Manage default streams and default stream groups
        "/default_stream_groups/create",
        "/default_stream_groups/{group_id}",
        "/default_stream_groups/{group_id}/streams",
        # Single-stream settings alternative to the bulk endpoint
        # users/me/subscriptions/properties; probably should just be a
        # section of the same page.
        "/users/me/subscriptions/{stream_id}",
        #### Mobile-app only endpoints; important for mobile developers.
        # Mobile interface for development environment login
        "/dev_list_users",
        #### These personal settings endpoints have modest value to document:
        "/users/me/avatar",
        "/users/me/api_key/regenerate",
        # Much more valuable would be an org admin bulk-upload feature.
        "/users/me/profile_data",
        #### Should be documented as part of interactive bots documentation
        "/bot_storage",
        "/submessage",
        "/zcommand",
        #### These "organization settings" endpoint have modest value to document:
        "/realm",
        "/realm/domains",
        "/realm/domains/{domain}",
        "/bots",
        "/bots/{bot_id}",
        "/bots/{bot_id}/api_key/regenerate",
        #### These "organization settings" endpoints have low value to document:
        "/realm/profile_fields/{field_id}",
        "/realm/icon",
        "/realm/logo",
        "/realm/deactivate",
        "/realm/subdomain/{subdomain}",
        # API for Zoom video calls.  Unclear if this can support other apps.
        "/calls/zoom/create",
        #### The following are fake endpoints that live in our zulip.yaml
        #### for tooling convenience reasons, and should eventually be moved.
        # Real-time-events endpoint
        "/real-time",
        # Rest error handling endpoint
        "/rest-error-handling",
        # Zulip outgoing webhook payload
        "/zulip-outgoing-webhook",
        "/jwt/fetch_api_key",
    }

    # Endpoints in the API documentation that don't use rest_dispatch
    # and only use the POST method; used in test_openapi_arguments.
    documented_post_only_endpoints = {
        "fetch_api_key",
        "dev_fetch_api_key",
    }

    # Endpoints where the documentation is currently failing our
    # consistency tests.  We aim to keep this list empty.
    buggy_documentation_endpoints: set[str] = set()

    def ensure_no_documentation_if_intentionally_undocumented(
        self, url_pattern: str, method: str, msg: str | None = None
    ) -> None:
        try:
            get_openapi_parameters(url_pattern, method)
            if not msg:  # nocoverage
                msg = f"""
We found some OpenAPI documentation for {method} {url_pattern},
so maybe we shouldn't mark it as intentionally undocumented in the URLs.
"""
            raise AssertionError(msg)  # nocoverage
        except KeyError:
            return

    def check_for_non_existent_openapi_endpoints(self) -> None:
        """Here, we check to see if every endpoint documented in the OpenAPI
        documentation actually exists in urls.py and thus in actual code.
        Note: We define this as a helper called at the end of
        test_openapi_arguments instead of as a separate test to ensure that
        this test is only executed after test_openapi_arguments so that it's
        results can be used here in the set operations."""
        openapi_paths = set(get_openapi_paths())
        undocumented_paths = openapi_paths - self.checked_endpoints
        undocumented_paths -= self.buggy_documentation_endpoints
        undocumented_paths -= self.pending_endpoints
        try:
            self.assert_length(undocumented_paths, 0)
        except AssertionError:  # nocoverage
            msg = "The following endpoints have been documented but can't be found in urls.py:"
            for undocumented_path in undocumented_paths:
                msg += f"\n + {undocumented_path}"
            raise AssertionError(msg)

    def render_openapi_type_exception(
        self,
        function: Callable[..., HttpResponse],
        openapi_params: set[tuple[str, type | tuple[type, object]]],
        function_params: set[tuple[str, type | tuple[type, object]]],
        diff: set[tuple[str, type | tuple[type, object]]],
    ) -> None:  # nocoverage
        """Print a *VERY* clear and verbose error message for when the types
        (between the OpenAPI documentation and the function declaration) don't match."""

        msg = f"""
The types for the request parameters in zerver/openapi/zulip.yaml
do not match the types declared in the implementation of {function.__name__}.\n"""
        msg += "=" * 65 + "\n"
        msg += "{:<10}{:^30}{:>10}\n".format(
            "parameter", "OpenAPI type", "function declaration type"
        )
        msg += "=" * 65 + "\n"
        opvtype = None
        fdvtype = None
        for element in diff:
            vname = element[0]
            for element in openapi_params:
                if element[0] == vname:
                    opvtype = element[1]
                    break
            for element in function_params:
                if element[0] == vname:
                    fdvtype = element[1]
                    break
        msg += f"{vname:<10}{opvtype!s:^30}{fdvtype!s:>10}\n"
        raise AssertionError(msg)

    def validate_json_schema(
        self, function: Callable[..., HttpResponse], openapi_parameters: list[Parameter]
    ) -> None:
        """Validate against the Pydantic generated JSON schema against our OpenAPI definitions"""
        USE_JSON_CONTENT_TYPE_HINT = f"""
    The view function {{param_name}} should accept JSON input.
    Consider wrapping the type annotation of the parameter in Json.
    For example:

    from pydantic import Json
    ...
    @typed_endpoint
    def {function.__name__}(
        request: HttpRequest,
        *,
        {{param_name}}: Json[{{param_type}}] = ...,
    ) -> ...:
"""
        # The set of tuples containing the var name and type pairs extracted
        # from the function signature.
        function_params = set()
        # The set of tuples containing the var name and type pairs extracted
        # from OpenAPI.
        openapi_params = set()
        # The names of request variables that should have a content type of
        # application/json according to our OpenAPI definitions.
        json_request_var_names = set()
        for openapi_parameter in openapi_parameters:
            # We differentiate JSON and non-JSON parameters here. Because
            # application/json is the only content type to be verify in the API,
            # we assume that as long as "content" is present in the OpenAPI
            # spec, the content type should be JSON.
            expected_request_var_name = openapi_parameter.name
            if openapi_parameter.json_encoded:
                json_request_var_names.add(expected_request_var_name)

            openapi_params.add(
                (expected_request_var_name, schema_type(openapi_parameter.value_schema))
            )

        for actual_param in parse_view_func_signature(function).parameters:
            actual_param_schema = TypeAdapter(actual_param.param_type).json_schema(
                ref_template="{model}"
            )
            defs_mapping = actual_param_schema.get("$defs", {})
            # The content type of the JSON schema generated from the
            # function parameter type annotation should have content type
            # matching that of our OpenAPI spec. If not so, hint that the
            # Json[T] wrapper might be missing from the type annotation.
            if actual_param.request_var_name in json_request_var_names:
                # skipping this check for send_message_backend 'to' parameter because it is a
                # special case where the content type of the parameter is application/json but the
                # parameter may or may not be JSON encoded since previously we also accepted a raw
                # string and some ad-hoc bot might still depend on sending a raw string.
                if (
                    function.__name__ != "send_message_backend"
                    or actual_param.param_name != "req_to"
                ):
                    self.assertEqual(
                        actual_param_schema.get("contentMediaType"),
                        "application/json",
                        USE_JSON_CONTENT_TYPE_HINT.format(
                            param_name=actual_param.param_name,
                            param_type=actual_param.param_type,
                        ),
                    )
                    # actual_param_schema is a json_schema. Reference:
                    # https://docs.pydantic.dev/latest/api/json_schema/#pydantic.json_schema.GenerateJsonSchema.json_schema
                    actual_param_schema = actual_param_schema["contentSchema"]
            elif "contentMediaType" in actual_param_schema:
                function_schema_type = schema_type(actual_param_schema, defs_mapping)
                # We do not specify that the content type of int or bool
                # parameters should be JSON encoded, while our code does expect
                # that. In this case, we exempt this parameter from the content
                # type check.
                self.assertIn(
                    function_schema_type,
                    (int, bool),
                    f"\nUnexpected content type {actual_param_schema['contentMediaType']} on function parameter {actual_param.param_name}, which does not match the OpenAPI definition.",
                )
            function_params.add(
                (actual_param.request_var_name, schema_type(actual_param_schema, defs_mapping))
            )

        diff = openapi_params - function_params
        if diff:  # nocoverage
            self.render_openapi_type_exception(function, openapi_params, function_params, diff)

    def check_argument_types(
        self, function: Callable[..., HttpResponse], openapi_parameters: list[Parameter]
    ) -> None:
        """We construct for both the OpenAPI data and the function's definition a set of
        tuples of the form (var_name, type) and then compare those sets to see if the
        OpenAPI data defines a different type than that actually accepted by the function.
        Otherwise, we print out the exact differences for convenient debugging and raise an
        AssertionError."""
        # Iterate through the decorators to find the original
        # function, wrapped by typed_endpoint, so we can parse its
        # arguments.
        while (wrapped := getattr(function, "__wrapped__", None)) is not None:
            function = wrapped

        if len(openapi_parameters) > 0:
            return self.validate_json_schema(function, openapi_parameters)

    def check_openapi_arguments_for_view(
        self,
        pattern: URLPattern,
        function_name: str,
        function: Callable[..., HttpResponse],
        method: str,
        tags: set[str],
    ) -> None:
        # Our accounting logic in the `typed_endpoint`
        # code means we have the list of all arguments
        # accepted by every view function in arguments_map.
        accepted_arguments = set(arguments_map[function_name])

        regex_pattern = pattern.pattern.regex.pattern
        for url_format, url_params in regex_helper.normalize(regex_pattern):
            url_pattern = "/" + url_format % {param: f"{{{param}}}" for param in url_params}

            if "intentionally_undocumented" in tags:
                self.ensure_no_documentation_if_intentionally_undocumented(url_pattern, method)
                continue

            if url_pattern in self.pending_endpoints:
                # HACK: After all pending_endpoints have been resolved, we should remove
                # this segment and the "msg" part of the `ensure_no_...` method.
                msg = f"""
We found some OpenAPI documentation for {method} {url_pattern},
so maybe we shouldn't include it in pending_endpoints.
"""
                self.ensure_no_documentation_if_intentionally_undocumented(url_pattern, method, msg)
                continue

            try:
                # Don't include OpenAPI parameters that live in
                # the path; these are not extracted by typed_endpoint.
                openapi_parameters = get_openapi_parameters(
                    url_pattern, method, include_url_parameters=False
                )
            except Exception:  # nocoverage
                raise AssertionError(f"Could not find OpenAPI docs for {method} {url_pattern}")

            # We now have everything we need to understand the
            # function as defined in our urls.py:
            #
            # * method is the HTTP method, e.g. GET, POST, or PATCH
            #
            # * p.pattern.regex.pattern is the URL pattern; might require
            #   some processing to match with OpenAPI rules
            #
            # * accepted_arguments is the full set of arguments
            #   this method accepts.
            #
            # * The documented parameters for the endpoint as recorded in our
            #   OpenAPI data in zerver/openapi/zulip.yaml.
            #
            # We now compare these to confirm that the documented
            # argument list matches what actually appears in the
            # codebase.

            openapi_parameter_names = {parameter.name for parameter in openapi_parameters}

            if len(accepted_arguments - openapi_parameter_names) > 0:  # nocoverage
                print("Undocumented parameters for", url_pattern, method, function_name)
                print(" +", openapi_parameter_names)
                print(" -", accepted_arguments)
                assert url_pattern in self.buggy_documentation_endpoints
            elif len(openapi_parameter_names - accepted_arguments) > 0:  # nocoverage
                print(
                    "Documented invalid parameters for",
                    url_pattern,
                    method,
                    function_name,
                )
                print(" -", openapi_parameter_names)
                print(" +", accepted_arguments)
                assert url_pattern in self.buggy_documentation_endpoints
            else:
                self.assertEqual(openapi_parameter_names, accepted_arguments)
                self.check_argument_types(function, openapi_parameters)
                self.checked_endpoints.add(url_pattern)

    def test_openapi_arguments(self) -> None:
        """This end-to-end API documentation test compares the arguments
        defined in the actual code using @typed_endpoint,
        with the arguments declared in our API documentation
        for every API endpoint in Zulip.

        First, we import the fancy-Django version of zproject/urls.py
        by doing this, each typed_endpoint wrapper around each
        imported view function gets called to generate the wrapped
        view function and thus filling the global arguments_map variable.
        Basically, we're exploiting code execution during import.

            Then we need to import some view modules not already imported in
        urls.py. We use this different syntax because of the linters complaining
        of an unused import (which is correct, but we do this for triggering the
        typed_endpoint decorator).

            At the end, we perform a reverse mapping test that verifies that
        every URL pattern defined in the OpenAPI documentation actually exists
        in code.
        """

        from zproject import urls as urlconf

        # We loop through all the API patterns, looking in particular
        # for those using the rest_dispatch decorator; we then parse
        # its mapping of (HTTP_METHOD -> FUNCTION).
        for p in urlconf.v1_api_and_json_patterns + urlconf.v1_api_mobile_patterns:
            methods_endpoints: dict[str, Any] = {}
            if p.callback is not rest_dispatch:
                # Endpoints not using rest_dispatch don't have extra data.
                if str(p.pattern) in self.documented_post_only_endpoints:
                    methods_endpoints = dict(POST=p.callback)
                else:
                    methods_endpoints = dict(GET=p.callback)
            else:
                methods_endpoints = assert_is_not_none(p.default_args)

            # since the module was already imported and is now residing in
            # memory, we won't actually face any performance penalties here.
            for method, value in methods_endpoints.items():
                if callable(value):
                    function: Callable[..., HttpResponse] = value
                    tags: set[str] = set()
                else:
                    function, tags = value

                if function is get_events:
                    # Work around the fact that the registered
                    # get_events view function isn't where we do
                    # @typed_endpoint.
                    #
                    # TODO: Make this configurable via an optional argument
                    # to typed_endpoint, e.g.
                    # @typed_endpoint(view_func_name="zerver.tornado.views.get_events")
                    function = get_events_backend

                function_name = f"{function.__module__}.{function.__name__}"

                with self.subTest(function_name):
                    self.check_openapi_arguments_for_view(p, function_name, function, method, tags)

        self.check_for_non_existent_openapi_endpoints()


class TestCurlExampleGeneration(ZulipTestCase):
    spec_mock_without_examples = {
        "security": [{"basicAuth": []}],
        "paths": {
            "/mark_stream_as_read": {
                "post": {
                    "description": "Mark all the unread messages in a stream as read.",
                    "parameters": [
                        {
                            "name": "stream_id",
                            "in": "query",
                            "description": "The ID of the stream whose messages should be marked as read.",
                            "schema": {
                                "type": "integer",
                            },
                            "required": True,
                        },
                        {
                            "name": "bool_param",
                            "in": "query",
                            "description": "Just a boolean parameter.",
                            "schema": {
                                "type": "boolean",
                            },
                            "required": True,
                        },
                    ],
                },
            },
        },
    }

    spec_mock_with_invalid_method: dict[str, object] = {
        "security": [{"basicAuth": []}],
        "paths": {
            "/endpoint": {
                "brew": {},  # the data is irrelevant as is should be rejected.
            },
        },
    }

    spec_mock_using_object = {
        "security": [{"basicAuth": []}],
        "paths": {
            "/endpoint": {
                "get": {
                    "description": "Get some info.",
                    "parameters": [
                        {
                            "name": "param1",
                            "in": "query",
                            "description": "An object",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"},
                                    "example": {
                                        "key": "value",
                                    },
                                }
                            },
                            "required": True,
                        },
                    ],
                },
            },
        },
    }

    spec_mock_using_param_in_path = {
        "security": [{"basicAuth": []}],
        "paths": {
            "/endpoint/{param1}": {
                "get": {
                    "description": "Get some info.",
                    "parameters": [
                        {
                            "name": "param1",
                            "in": "path",
                            "description": "Param in path",
                            "schema": {
                                "type": "integer",
                            },
                            "example": 35,
                            "required": True,
                        },
                        {
                            "name": "param2",
                            "in": "query",
                            "description": "An object",
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"},
                                    "example": {
                                        "key": "value",
                                    },
                                }
                            },
                        },
                    ],
                },
            },
        },
    }

    spec_mock_using_object_without_example = {
        "security": [{"basicAuth": []}],
        "paths": {
            "/endpoint": {
                "get": {
                    "description": "Get some info.",
                    "parameters": [
                        {
                            "name": "param1",
                            "in": "query",
                            "description": "An object",
                            "schema": {
                                "type": "object",
                            },
                            "required": True,
                        },
                    ],
                },
            },
        },
    }

    spec_mock_using_array_without_example = {
        "security": [{"basicAuth": []}],
        "paths": {
            "/endpoint": {
                "get": {
                    "description": "Get some info.",
                    "parameters": [
                        {
                            "name": "param1",
                            "in": "query",
                            "description": "An array",
                            "schema": {
                                "type": "array",
                            },
                            "required": True,
                        },
                    ],
                },
            },
        },
    }

    def curl_example(self, endpoint: str, method: str, *args: Any, **kwargs: Any) -> list[str]:
        return generate_curl_example(endpoint, method, "http://localhost:9991/api", *args, **kwargs)

    def test_generate_and_render_curl_example(self) -> None:
        generated_curl_example = self.curl_example("/get_stream_id", "GET")
        expected_curl_example = [
            "```curl",
            "curl -sSX GET -G http://localhost:9991/api/v1/get_stream_id \\",
            "    -u BOT_EMAIL_ADDRESS:BOT_API_KEY \\",
            "    --data-urlencode stream=Denmark",
            "```",
        ]
        self.assertEqual(generated_curl_example, expected_curl_example)

    def test_generate_and_render_curl_example_with_nonexistent_endpoints(self) -> None:
        with self.assertRaises(KeyError):
            self.curl_example("/mark_this_stream_as_read", "POST")
        with self.assertRaises(KeyError):
            self.curl_example("/mark_stream_as_read", "GET")

    def test_generate_and_render_curl_without_auth(self) -> None:
        generated_curl_example = self.curl_example("/dev_fetch_api_key", "POST")
        expected_curl_example = [
            "```curl",
            "curl -sSX POST http://localhost:9991/api/v1/dev_fetch_api_key \\",
            "    --data-urlencode username=iago@zulip.com",
            "```",
        ]
        self.assertEqual(generated_curl_example, expected_curl_example)

    @patch("zerver.openapi.openapi.OpenAPISpec.openapi")
    def test_generate_and_render_curl_with_default_examples(self, spec_mock: MagicMock) -> None:
        spec_mock.return_value = self.spec_mock_without_examples
        generated_curl_example = self.curl_example("/mark_stream_as_read", "POST")
        expected_curl_example = [
            "```curl",
            "curl -sSX POST http://localhost:9991/api/v1/mark_stream_as_read \\",
            "    -u BOT_EMAIL_ADDRESS:BOT_API_KEY \\",
            "    --data-urlencode stream_id=1 \\",
            "    --data-urlencode bool_param=false",
            "```",
        ]
        self.assertEqual(generated_curl_example, expected_curl_example)

    @patch("zerver.openapi.openapi.OpenAPISpec.openapi")
    def test_generate_and_render_curl_with_invalid_method(self, spec_mock: MagicMock) -> None:
        spec_mock.return_value = self.spec_mock_with_invalid_method
        with self.assertRaises(ValueError):
            self.curl_example("/endpoint", "BREW")  # see: HTCPCP

    def test_generate_and_render_curl_with_array_example(self) -> None:
        generated_curl_example = self.curl_example(
            "/messages",
            "GET",
            exclude=["use_first_unread_anchor", "message_ids", "allow_empty_topic_name"],
        )
        expected_curl_example = [
            "```curl",
            "curl -sSX GET -G http://localhost:9991/api/v1/messages \\",
            "    -u BOT_EMAIL_ADDRESS:BOT_API_KEY \\",
            "    --data-urlencode anchor=43 \\",
            "    --data-urlencode include_anchor=false \\",
            "    --data-urlencode num_before=4 \\",
            "    --data-urlencode num_after=8 \\",
            '    --data-urlencode \'narrow=[{"operand": "Denmark", "operator": "channel"}]\' \\',
            "    --data-urlencode client_gravatar=false \\",
            "    --data-urlencode apply_markdown=false",
            "```",
        ]
        self.assertEqual(generated_curl_example, expected_curl_example)

    @patch("zerver.openapi.openapi.OpenAPISpec.openapi")
    def test_generate_and_render_curl_with_object(self, spec_mock: MagicMock) -> None:
        spec_mock.return_value = self.spec_mock_using_object
        generated_curl_example = self.curl_example("/endpoint", "GET")
        expected_curl_example = [
            "```curl",
            "curl -sSX GET -G http://localhost:9991/api/v1/endpoint \\",
            "    -u BOT_EMAIL_ADDRESS:BOT_API_KEY \\",
            '    --data-urlencode \'param1={"key": "value"}\'',
            "```",
        ]
        self.assertEqual(generated_curl_example, expected_curl_example)

    @patch("zerver.openapi.openapi.OpenAPISpec.openapi")
    def test_generate_and_render_curl_with_object_without_example(
        self, spec_mock: MagicMock
    ) -> None:
        spec_mock.return_value = self.spec_mock_using_object_without_example
        with self.assertRaises(ValueError):
            self.curl_example("/endpoint", "GET")

    @patch("zerver.openapi.openapi.OpenAPISpec.openapi")
    def test_generate_and_render_curl_with_array_without_example(
        self, spec_mock: MagicMock
    ) -> None:
        spec_mock.return_value = self.spec_mock_using_array_without_example
        with self.assertRaises(ValueError):
            self.curl_example("/endpoint", "GET")

    @patch("zerver.openapi.openapi.OpenAPISpec.openapi")
    def test_generate_and_render_curl_with_param_in_path(self, spec_mock: MagicMock) -> None:
        spec_mock.return_value = self.spec_mock_using_param_in_path
        generated_curl_example = self.curl_example("/endpoint/{param1}", "GET")
        expected_curl_example = [
            "```curl",
            "curl -sSX GET -G http://localhost:9991/api/v1/endpoint/35 \\",
            "    -u BOT_EMAIL_ADDRESS:BOT_API_KEY \\",
            '    --data-urlencode \'param2={"key": "value"}\'',
            "```",
        ]
        self.assertEqual(generated_curl_example, expected_curl_example)

    def test_generate_and_render_curl_wrapper(self) -> None:
        generated_curl_example = render_curl_example(
            "/get_stream_id:GET:email:key", api_url="https://zulip.example.com/api"
        )
        expected_curl_example = [
            "```curl",
            "curl -sSX GET -G https://zulip.example.com/api/v1/get_stream_id \\",
            "    -u email:key \\",
            "    --data-urlencode stream=Denmark",
            "```",
        ]
        self.assertEqual(generated_curl_example, expected_curl_example)

    def test_generate_and_render_curl_example_with_excludes(self) -> None:
        generated_curl_example = self.curl_example(
            "/messages",
            "GET",
            exclude=[
                "client_gravatar",
                "apply_markdown",
                "use_first_unread_anchor",
                "message_ids",
                "allow_empty_topic_name",
            ],
        )
        expected_curl_example = [
            "```curl",
            "curl -sSX GET -G http://localhost:9991/api/v1/messages \\",
            "    -u BOT_EMAIL_ADDRESS:BOT_API_KEY \\",
            "    --data-urlencode anchor=43 \\",
            "    --data-urlencode include_anchor=false \\",
            "    --data-urlencode num_before=4 \\",
            "    --data-urlencode num_after=8 \\",
            '    --data-urlencode \'narrow=[{"operand": "Denmark", "operator": "channel"}]\'',
            "```",
        ]
        self.assertEqual(generated_curl_example, expected_curl_example)


class OpenAPIAttributesTest(ZulipTestCase):
    def test_attributes(self) -> None:
        """
        Checks:
        * All endpoints have `operationId` and `tag` attributes.
        * All example responses match their schema.
        * All example events in `/get-events` match an event schema.
        * That no opaque object exists.
        """
        EXCLUDE = ["/real-time"]
        VALID_TAGS = [
            "users",
            "server_and_organizations",
            "authentication",
            "real_time_events",
            "channels",
            "messages",
            "drafts",
            "webhooks",
            "scheduled_messages",
            "mobile",
            "invites",
        ]
        paths = OpenAPISpec(OPENAPI_SPEC_PATH).openapi()["paths"]
        for path, path_item in paths.items():
            if path in EXCLUDE:
                continue
            for method, operation in path_item.items():
                assert "operationId" in operation
                assert "tags" in operation
                tag = operation["tags"][0]
                assert tag in VALID_TAGS
                for status_code, response in operation["responses"].items():
                    schema = response["content"]["application/json"]["schema"]
                    # Validate the documented examples for each event type
                    # in api/get-events for the documented event schemas.
                    if path == "/events" and method == "get" and status_code == "200":
                        for event_type in schema["properties"]["events"]["items"]["oneOf"]:
                            event_array = [event_type["example"]]
                            content = {
                                "queue_id": "fb67bf8a-c031-47cc-84cf-ed80accacda8",
                                "events": event_array,
                                "msg": "",
                                "result": "success",
                            }
                            assert validate_against_openapi_schema(
                                content, path, method, status_code
                            )
                    if "oneOf" in schema:
                        for subschema in schema["oneOf"]:
                            validate_schema(subschema)
                            assert validate_against_openapi_schema(
                                subschema["example"],
                                path,
                                method,
                                status_code,
                            )
                        continue
                    validate_schema(schema)
                    if "example" not in schema:
                        assert "examples" in response["content"]["application/json"]
                        examples = response["content"]["application/json"]["examples"]
                        for example in examples:
                            assert validate_against_openapi_schema(
                                examples[example]["value"], path, method, status_code
                            )
                    else:
                        assert validate_against_openapi_schema(
                            schema["example"], path, method, status_code
                        )


class OpenAPIRegexTest(ZulipTestCase):
    def test_regex(self) -> None:
        """
        Calls a few documented  and undocumented endpoints and checks whether they
        find a match or not.
        """
        # Some of the undocumented endpoints which are very similar to
        # some of the documented endpoints.
        assert find_openapi_endpoint("/users/me/presence") is None
        assert find_openapi_endpoint("/users/me/subscriptions/23") is None
        assert find_openapi_endpoint("/users/iago/subscriptions/23") is None
        assert find_openapi_endpoint("/messages/matches_narrow") is None
        # Making sure documented endpoints are matched correctly.
        assert (
            find_openapi_endpoint("/users/23/subscriptions/21")
            == "/users/{user_id}/subscriptions/{stream_id}"
        )
        assert (
            find_openapi_endpoint("/users/iago@zulip.com/presence")
            == "/users/{user_id_or_email}/presence"
        )
        assert find_openapi_endpoint("/users/iago@zulip.com") == "/users/{email}"
        assert find_openapi_endpoint("/messages/23") == "/messages/{message_id}"
        assert find_openapi_endpoint("/realm/emoji/realm_emoji_1") == "/realm/emoji/{emoji_name}"


class OpenAPIRequestValidatorTest(ZulipTestCase):
    def test_validator(self) -> None:
        """
        Test to make sure the request validator works properly
        The tests cover both cases such as catching valid requests marked
        as invalid and making sure invalid requests are marked properly
        """
        # `/users/me/subscriptions` doesn't require any parameters
        validate_request("/users/me/subscriptions", "get", {}, {}, False, "200")
        with self.assertRaises(SchemaError):
            # `/messages` POST does not work on an empty response
            validate_request("/messages", "post", {}, {}, False, "200")
        # 400 responses are allowed to fail validation.
        validate_request("/messages", "post", {}, {}, False, "400")
        # `intentionally_undocumented` allows validation errors on
        # 200 responses.
        validate_request(
            "/dev_fetch_api_key", "post", {}, {}, False, "200", intentionally_undocumented=True
        )


class APIDocsSidebarTest(ZulipTestCase):
    def test_link_in_sidebar(self) -> None:
        """
        Test to make sure that links of API documentation pages exist
        in the sidebar and have the same label as the summary of the endpoint.
        """
        # These endpoints are in zulip.yaml, but not the actual docs.
        exempted_docs = {
            # (No /api/v1/ or /json prefix).
            "get-file-temporary-url",
            # This one is not used by any clients and is likely to get
            # deprecated.
            "update-subscriptions",
            # This is rendered on the "Outgoing webhooks" page and hence is not
            # linked in the sidebar.
            "zulip-outgoing-webhooks",
        }
        sidebar_path = "api_docs/sidebar_index.md"
        rest_endpoints_path = "api_docs/include/rest-endpoints.md"
        with open(sidebar_path) as fp:
            sidebar_content = fp.readlines()
        with open(rest_endpoints_path) as fp:
            sidebar_content += fp.readlines()

        sidebar_content_set = set(sidebar_content)
        paths = openapi_spec.openapi()["paths"]
        for endpoint in paths:
            for method in paths[endpoint]:
                operationId = paths[endpoint][method].get("operationId")
                summary = paths[endpoint][method].get("summary")
                if operationId and operationId not in exempted_docs:
                    link = f"* [{summary}](/api/{operationId})\n"
                    assert link in sidebar_content_set
