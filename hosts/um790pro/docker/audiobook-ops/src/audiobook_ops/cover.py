from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import subprocess
import tempfile
from typing import Protocol
from urllib.parse import urljoin, urlparse

from audiobook_ops.interface import OperationError


@dataclass(frozen=True)
class CoverResponse:
    status: int
    content_type: str | None
    location: str | None
    body: bytes


class CoverHTTP(Protocol):
    def fetch(
        self, url: str, maximum_bytes: int, addresses: list[str]
    ) -> CoverResponse: ...


class Resolver(Protocol):
    def resolve(self, hostname: str, port: int) -> list[str]: ...


class ImageDecoder(Protocol):
    def inspect(self, content: bytes, mime_type: str) -> tuple[int, int]: ...


class RouteGuard(Protocol):
    def require(self) -> None: ...


class SystemResolver:
    def resolve(self, hostname: str, port: int) -> list[str]:
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    hostname, port, type=socket.SOCK_STREAM
                )
            }
        except socket.gaierror as error:
            raise OperationError("cover destination cannot be resolved") from error
        if not addresses:
            raise OperationError("cover destination cannot be resolved")
        return sorted(addresses)


class PinnedHTTPSCoverHTTP:
    """HTTPS transport pinned to the already validated DNS answers."""

    def __init__(self) -> None:
        self._context = ssl.create_default_context()

    def fetch(
        self, url: str, maximum_bytes: int, addresses: list[str]
    ) -> CoverResponse:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname or not addresses:
            raise OperationError("cover destination cannot be resolved")
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        last_error: OSError | ssl.SSLError | None = None
        for address in addresses:
            connection = http.client.HTTPSConnection(hostname, 443, timeout=15)
            raw_socket: socket.socket | None = None
            try:
                raw_socket = socket.create_connection((address, 443), timeout=15)
                connection.sock = self._context.wrap_socket(
                    raw_socket, server_hostname=hostname
                )
                raw_socket = None
                connection.request(
                    "GET",
                    target,
                    headers={
                        "Accept": "image/jpeg,image/png,image/webp",
                        "Connection": "close",
                        "Host": hostname,
                        "User-Agent": "audiobook-ops-cover/1",
                    },
                )
                response = connection.getresponse()
                declared = response.getheader("Content-Length")
                if declared is not None and int(declared) > maximum_bytes:
                    raise OperationError("cover response exceeds the size limit")
                body = response.read(maximum_bytes + 1)
                return CoverResponse(
                    status=response.status,
                    content_type=response.getheader("Content-Type"),
                    location=response.getheader("Location"),
                    body=body,
                )
            except OperationError:
                raise
            except (OSError, ssl.SSLError, http.client.HTTPException) as error:
                last_error = error
            finally:
                if raw_socket is not None:
                    raw_socket.close()
                connection.close()
        raise OperationError("cover request failed") from last_error


class SubprocessImageDecoder:
    _CODECS = {
        "image/jpeg": "mjpeg",
        "image/png": "png",
        "image/webp": "webp",
    }

    def __init__(self, ffprobe_bin: str = "ffprobe", ffmpeg_bin: str = "ffmpeg") -> None:
        self._ffprobe_bin = ffprobe_bin
        self._ffmpeg_bin = ffmpeg_bin

    def inspect(self, content: bytes, mime_type: str) -> tuple[int, int]:
        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(
            mime_type
        )
        if suffix is None:
            raise OperationError("unsupported cover MIME")
        with tempfile.NamedTemporaryFile(suffix=suffix) as cover:
            cover.write(content)
            cover.flush()
            try:
                probe = subprocess.run(
                    [
                        self._ffprobe_bin,
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=codec_name,width,height",
                        "-of",
                        "json",
                        cover.name,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                decode = subprocess.run(
                    [
                        self._ffmpeg_bin,
                        "-v",
                        "error",
                        "-i",
                        cover.name,
                        "-f",
                        "null",
                        "-",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise OperationError("cover image decode failed") from error
        if probe.returncode != 0 or decode.returncode != 0:
            raise OperationError("cover image decode failed")
        try:
            payload = json.loads(probe.stdout)
            streams = payload["streams"]
            stream = streams[0]
            width = int(stream["width"])
            height = int(stream["height"])
            codec = str(stream["codec_name"])
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise OperationError("cover image decode failed") from error
        if codec != self._CODECS[mime_type]:
            raise OperationError("cover MIME does not match decoded content")
        return width, height


class CoverFetcher:
    _EXTENSIONS = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    _TAILNET = ipaddress.ip_network("100.64.0.0/10")

    def __init__(
        self,
        http: CoverHTTP,
        resolver: Resolver,
        decoder: ImageDecoder,
        route_guard: RouteGuard,
        *,
        max_bytes: int = 10 * 1024 * 1024,
        max_dimension: int = 4096,
        max_pixels: int = 16_000_000,
        max_redirects: int = 3,
    ) -> None:
        self._http = http
        self._resolver = resolver
        self._decoder = decoder
        self._route_guard = route_guard
        self._max_bytes = max_bytes
        self._max_dimension = max_dimension
        self._max_pixels = max_pixels
        self._max_redirects = max_redirects

    def fetch(self, source_url: str) -> dict[str, object]:
        current = source_url
        for redirect_count in range(self._max_redirects + 1):
            self._route_guard.require()
            addresses = self._require_safe_destination(current)
            response = self._http.fetch(current, self._max_bytes, addresses)
            if 300 <= response.status < 400:
                if redirect_count >= self._max_redirects:
                    raise OperationError("cover redirect limit exceeded")
                if not response.location:
                    raise OperationError("cover redirect is missing a destination")
                current = urljoin(current, response.location)
                continue
            if response.status != 200:
                raise OperationError("cover request failed")
            if len(response.body) > self._max_bytes:
                raise OperationError("cover response exceeds the size limit")
            mime_type = (response.content_type or "").split(";", 1)[0].strip().casefold()
            extension = self._EXTENSIONS.get(mime_type)
            if extension is None:
                raise OperationError("unsupported cover MIME")
            width, height = self._decoder.inspect(response.body, mime_type)
            if (
                width < 1
                or height < 1
                or width > self._max_dimension
                or height > self._max_dimension
                or width * height > self._max_pixels
            ):
                raise OperationError("cover dimensions exceed the safe limit")
            return {
                "source_url": source_url,
                "final_url": current,
                "checksum": hashlib.sha256(response.body).hexdigest(),
                "mime_type": mime_type,
                "filename": f"cover.{extension}",
                "width": width,
                "height": height,
                "_content_b64": base64.b64encode(response.body).decode(),
            }
        raise OperationError("cover redirect limit exceeded")

    def _require_safe_destination(self, url: str) -> list[str]:
        parsed = urlparse(url)
        try:
            port = parsed.port
        except ValueError as error:
            raise OperationError("cover URL must be HTTPS without credentials") from error
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or parsed.fragment
        ):
            raise OperationError("cover URL must be HTTPS without credentials")
        addresses = self._resolver.resolve(parsed.hostname, 443)
        if not addresses:
            raise OperationError("cover destination cannot be resolved")
        for value in addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as error:
                raise OperationError("cover destination is unsafe") from error
            if (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
                or address in self._TAILNET
            ):
                raise OperationError("cover destination is unsafe")
        return addresses
