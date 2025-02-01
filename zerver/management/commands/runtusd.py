import os
from typing import Any
from urllib.parse import SplitResult

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from typing_extensions import override


class Command(BaseCommand):
    help = """Starts the tusd server"""

    @override
    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "listen", help="[Port, or address:port, to bind HTTP server to]", type=str
        )
        parser.add_argument(
            "hooks_http",
            help="[An HTTP endpoint to which hook events will be sent to]",
            default="http://127.0.0.1/api/internal/tusd",
            nargs="?",
        )

    @override
    def handle(self, *args: Any, **options: Any) -> None:
        listen = options["listen"]
        if listen.isdigit():
            addr, port = "127.0.0.1", int(listen)
        else:
            r = SplitResult("", listen, "", "", "")
            if r.port is None:
                raise CommandError(f"{listen!r} does not have a valid port number.")
            addr, port = r.hostname or "127.0.0.1", r.port

        hooks_http = options["hooks_http"]

        # https://tus.github.io/tusd/getting-started/configuration/
        # We do not set a maximum upload size, as the pre-create hooks
        # will set the max size that they want, based on the intended
        # use of the uploaded file.
        tusd_args = [
            "tusd",
            "-base-path=/api/v1/tus/",
            f"-port={port}",
            f"-host={addr}",
            "-behind-proxy",
            f"-hooks-http={hooks_http}",
            "-hooks-http-forward-headers=Cookie,Authorization",
            "--hooks-enabled-events=pre-create,pre-finish",
            "-disable-download",
        ]
        env_vars = os.environ.copy()
        if settings.LOCAL_UPLOADS_DIR is not None:
            assert settings.LOCAL_FILES_DIR is not None
            tusd_args.append(f"-upload-dir={settings.LOCAL_FILES_DIR}")
        else:
            tusd_args.append(f"-s3-bucket={settings.S3_AUTH_UPLOADS_BUCKET}")
            if settings.S3_ENDPOINT_URL is not None:
                tusd_args.append(f"-s3-endpoint={settings.S3_ENDPOINT_URL}")
            assert settings.S3_KEY is not None
            assert settings.S3_SECRET_KEY is not None
            assert settings.S3_REGION is not None
            env_vars["AWS_ACCESS_KEY_ID"] = settings.S3_KEY
            env_vars["AWS_SECRET_ACCESS_KEY"] = settings.S3_SECRET_KEY
            env_vars["AWS_REGION"] = settings.S3_REGION
        os.execvpe("tusd", tusd_args, env_vars)
