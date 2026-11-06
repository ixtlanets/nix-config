"""Private owner refresh boundaries. Importing this module starts no browser."""
from __future__ import annotations

import json
import struct
import os
import hashlib
import stat
import sys
from pathlib import Path
from typing import BinaryIO, Protocol
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
import re

MAX_FRAME = 2 * 1024 * 1024
ERROR_CODES = frozenset({'protocol', 'browser', 'challenge', 'target', 'authentication', 'cookies', 'privacy', 'identity', 'timeout', 'cleanup'})


class SafeError(Exception):
    """A fixed diagnostic which can safely cross the private protocol."""

    def __init__(self, code: str):
        self.code = code if code in ERROR_CODES else 'browser'
        super().__init__(self.code)


def write_frame(stream: BinaryIO, value: dict) -> None:
    try:
        if type(value) is not dict:
            raise SafeError('protocol')
        payload = json.dumps(value, ensure_ascii=True, allow_nan=False,
                             separators=(',', ':')).encode('ascii')
        if not 0 < len(payload) <= MAX_FRAME:
            raise SafeError('protocol')
        frame = struct.pack('!I', len(payload)) + payload
        offset = 0
        while offset < len(frame):
            written = stream.write(frame[offset:])
            if type(written) is not int or written <= 0:
                raise SafeError('protocol')
            offset += written
        stream.flush()
    except Exception:
        raise SafeError('protocol') from None


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        part = stream.read(size - len(chunks))
        if not isinstance(part, bytes) or not part:
            raise SafeError('protocol')
        chunks.extend(part)
    return bytes(chunks)


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SafeError('protocol')
        result[key] = value
    return result


def read_frame(stream: BinaryIO) -> dict:
    try:
        size = struct.unpack('!I', _read_exact(stream, 4))[0]
        if not 0 < size <= MAX_FRAME:
            raise SafeError('protocol')
        value = json.loads(_read_exact(stream, size), object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(SafeError('protocol')))
        if type(value) is not dict:
            raise SafeError('protocol')
        return value
    except Exception:
        raise SafeError('protocol') from None


LOGIN_URL = 'https://rutracker.org/forum/login.php'
INDEX_URL = 'https://rutracker.org/forum/index.php'
INERT_TAGS = frozenset({'script', 'style', 'template', 'noscript', 'iframe', 'object', 'textarea', 'title', 'svg', 'math', 'select', 'option', 'xmp', 'noembed', 'noframes', 'plaintext'})
VOID_TAGS = frozenset({'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'})


class BrowserHTMLParser(HTMLParser):
    """Use browser raw-text and slash semantics on pinned Python 3.11 too."""

    CDATA_CONTENT_ELEMENTS = ('script', 'style', 'xmp', 'iframe', 'noembed',
                              'noframes', 'noscript', 'textarea', 'title', 'plaintext')

    def set_cdata_mode(self, elem, **_kwargs):
        super().set_cdata_mode(elem)
        if elem.lower() == 'plaintext':
            # HTML plaintext consumes the remainder, including apparent end tags.
            self.interesting = re.compile(r'(?!)')

    def handle_startendtag(self, tag, attrs):
        # In HTML, a trailing slash does not close a non-void element. Inert
        # foreign content is conservatively retained rather than interpreted.
        self.handle_starttag(tag, attrs)
        if tag in self.CDATA_CONTENT_ELEMENTS or tag == 'plaintext':
            self.set_cdata_mode(tag)


class LoginFormParser(BrowserHTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        hidden = bool(self.stack and self.stack[-1][1]) or tag in INERT_TAGS or 'hidden' in values or 'inert' in values or values.get('aria-hidden', '').lower() == 'true' or bool(re.search(r'(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:;|$)', values.get('style', ''), re.I))
        if tag not in VOID_TAGS:
            self.stack.append((tag, hidden))
        if hidden or tag not in {'form', 'input', 'img'}:
            return
        values = _unique_object(attrs)
        if tag == 'form':
            if self.current is not None:
                raise SafeError('challenge')
            self.current = (values, [])
            self.forms.append(self.current)
        elif self.current is not None:
            self.current[1].append({'_image_src': values.get('src')} if tag == 'img' else values)

    def handle_endtag(self, tag):
        hidden = bool(self.stack and self.stack[-1][1])
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if tag == 'form' and not hidden:
            self.current = None


def parse_challenge(html: str) -> tuple[str, str] | None:
    try:
        if type(html) is not str or len(html) > MAX_FRAME:
            raise SafeError('challenge')
        parser = LoginFormParser()
        parser.feed(html)
        matching = []
        for attrs, inputs in parser.forms:
            names = [item.get('name') for item in inputs]
            if 'login_username' in names and 'login_password' in names:
                matching.append((attrs, inputs))
        if len(matching) != 1:
            raise SafeError('challenge')
        attrs, inputs = matching[0]
        if attrs.get('method', '').lower() != 'post' or urljoin(LOGIN_URL, attrs.get('action', '')) != LOGIN_URL:
            raise SafeError('target')
        by_name = {}
        for item in inputs:
            name = item.get('name')
            if name in by_name:
                raise SafeError('challenge')
            if name:
                by_name[name] = item
        cap_names = [name for name in by_name if name.startswith('cap_code_')]
        if not cap_names and 'cap_sid' not in by_name:
            return None
        sid = by_name.get('cap_sid', {})
        value = sid.get('value', '')
        if sid.get('type', '').lower() != 'hidden' or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) or len(cap_names) != 1 or not re.fullmatch(r'cap_code_[A-Za-z0-9_-]{1,128}', cap_names[0]):
            raise SafeError('challenge')
        return value, cap_names[0]
    except SafeError as exc:
        raise SafeError('target' if exc.code == 'target' else 'challenge') from None
    except Exception:
        raise SafeError('challenge') from None


class PrincipalParser(BrowserHTMLParser):
    """Recognize only a single visible canonical element, never inert markup."""

    VOID = VOID_TAGS

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.markers = []
        self.invalid = False

    def handle_starttag(self, tag, attrs):
        keys = [key for key, _ in attrs]
        values = dict(attrs)
        duplicate = len(keys) != len(set(keys))
        hidden = bool(self.stack and self.stack[-1][1]) or tag in INERT_TAGS or 'hidden' in values or 'inert' in values or values.get('aria-hidden', '').lower() == 'true' or bool(re.search(r'(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:;|$)', values.get('style', ''), re.I))
        marker = self.stack[-1][2] if self.stack else None
        if not hidden and any(key == 'id' and value == 'logged-in-username' for key, value in attrs):
            if duplicate or tag not in {'a', 'b', 'span', 'strong'}:
                self.invalid = True
            else:
                marker = len(self.markers)
                self.markers.append([])
        if tag not in self.VOID:
            self.stack.append((tag, hidden, marker))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and not self.stack[-1][1] and self.stack[-1][2] is not None:
            self.markers[self.stack[-1][2]].append(data)


def verify_principal(html: str, username: str) -> None:
    try:
        if type(html) is not str or len(html) > MAX_FRAME:
            raise SafeError('authentication')
        parser = PrincipalParser()
        parser.feed(html)
        parser.close()
        if parser.invalid or len(parser.markers) != 1 or ''.join(parser.markers[0]).strip() != username:
            raise SafeError('authentication')
    except Exception:
        raise SafeError('authentication') from None


COOKIE_NAMES = frozenset({'bb_session', 'bb_data', 'bb_t', 'bb_ssl'})


def validate_cookies(rows: list[dict]) -> dict[str, str]:
    import time
    try:
        if type(rows) is not list or not 1 <= len(rows) <= 16:
            raise SafeError('cookies')
        result = {}
        for row in rows:
            if type(row) is not dict:
                raise SafeError('cookies')
            name, value = row.get('name'), row.get('value')
            if name not in COOKIE_NAMES or name in result or type(value) is not str or not 1 <= len(value) <= 4096 or any(ord(char) < 33 or ord(char) > 126 or char in ';,"\\' for char in value):
                raise SafeError('cookies')
            if row.get('domain') not in {'rutracker.org', '.rutracker.org'} or row.get('path') not in {'/', '/forum', '/forum/'} or row.get('secure') is not True:
                raise SafeError('cookies')
            if 'expiry' in row and (type(row['expiry']) is not int or not time.time() < row['expiry'] <= 253402300799):
                raise SafeError('cookies')
            for field in ('httpOnly',):
                if field in row and type(row[field]) is not bool:
                    raise SafeError('cookies')
            if 'sameSite' in row and row['sameSite'] not in {'Strict', 'Lax', 'None'}:
                raise SafeError('cookies')
            result[name] = value
        if not result.get('bb_session') or sum(len(k) + len(v) for k, v in result.items()) > 16384:
            raise SafeError('cookies')
        return result
    except Exception:
        raise SafeError('cookies') from None


def validate_login(reply: dict, cap_required: bool) -> None:
    if type(reply) is not dict or set(reply) != {'kind', 'username', 'password', 'captcha'} or reply['kind'] != 'login':
        raise SafeError('protocol')
    for name, limit in (('username', 128), ('password', 1024), ('captcha', 128)):
        value = reply[name]
        if type(value) is not str or len(value) > limit or any(ord(char) < 32 or ord(char) == 127 or 0xE000 <= ord(char) <= 0xE0FF for char in value) or (not value and (name != 'captcha' or cap_required)):
            raise SafeError('protocol')


class Browser(Protocol):
    """A retained browser; implementations enforce request policy before navigation."""

    def open_login(self) -> tuple[str, str, bytes]: ...
    def submit_login(self, fields: dict[str, str]) -> None: ...
    def verify_index(self) -> tuple[str, str]: ...
    def cookies(self) -> list[dict]: ...
    def close(self) -> None: ...


class Channel(Protocol):
    def send(self, message: dict) -> None: ...
    def receive(self) -> dict: ...


def run(browser: Browser, channel: Channel) -> None:
    """Execute one login; only publish the candidate after browser cleanup."""
    import base64
    try:
        url, html, png = browser.open_login()
        if url != LOGIN_URL:
            raise SafeError('target')
        challenge = parse_challenge(html)
        validate_png(png)
        channel.send({'kind': 'captcha', 'png': base64.b64encode(png).decode('ascii'), 'cap_required': challenge is not None})
        reply = channel.receive()
        validate_login(reply, challenge is not None)
        fields = {'login_username': reply['username'], 'login_password': reply['password'], 'login': 'вход', 'redirect': 'index.php'}
        if challenge is not None:
            fields['cap_sid'] = challenge[0]
            fields[challenge[1]] = reply['captcha']
        browser.submit_login(fields)
        final_url, index_html = browser.verify_index()
        if final_url != INDEX_URL:
            raise SafeError('target')
        verify_principal(index_html, reply['username'])
        cookies = validate_cookies(browser.cookies())
    except SafeError:
        raise
    except BaseException:
        raise SafeError('browser') from None
    finally:
        try:
            browser.close()
        except BaseException:
            raise SafeError('cleanup') from None
    try:
        channel.send({'kind': 'verified', 'cookies': cookies})
    except BaseException:
        raise SafeError('protocol') from None


class RequestPolicy:
    """Deny every paused request outside the fixed login flow and one image."""

    def __init__(self):
        self.submission = False
        self.image = None

    def enable_submission(self) -> None:
        self.submission = True

    def set_image(self, url: str) -> None:
        self.image = url

    def permits(self, paused: dict) -> bool:
        request = paused.get('request', {})
        url, method = request.get('url'), request.get('method')
        kind = paused.get('resourceType')
        if kind == 'Document' and method == 'GET' and url == LOGIN_URL:
            return True
        if self.submission and kind == 'Document' and ((url == LOGIN_URL and method == 'POST') or (url == INDEX_URL and method == 'GET')):
            return True
        return self.image is not None and url == self.image and method == 'GET' and kind == 'Image'


def captcha_image(html: str) -> str:
    if parse_challenge(html) is None:
        raise SafeError('challenge')
    parser = LoginFormParser()
    parser.feed(html)
    images = []
    for attrs, inputs in parser.forms:
        if {'login_username', 'login_password'}.issubset({item.get('name') for item in inputs}):
            images = [item['_image_src'] for item in inputs if '_image_src' in item]
    if len(images) != 1 or type(images[0]) is not str:
        raise SafeError('challenge')
    url = urljoin(LOGIN_URL, images[0])
    parsed, origin = urlsplit(url), urlsplit(LOGIN_URL)
    if len(url) > 2048 or any(ord(char) < 33 or ord(char) > 126 for char in url) or (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc) or parsed.fragment or not parsed.path.startswith('/forum/') or '%' in parsed.path or '\\' in url:
        raise SafeError('challenge')
    return url


RETRY_CAPTCHA_IMAGE_SCRIPT = """
const image = arguments[0];
const url = arguments[1];
if (image.ownerDocument !== document || image.tagName !== 'IMG' ||
    !image.isConnected || image.src !== url) return false;
image.removeAttribute('src');
image.setAttribute('src', url);
return true;
"""


STATIC_FORM_SCRIPT = """
const form = arguments[0];
if (!(form instanceof HTMLFormElement) || form.tagName !== 'FORM' ||
    form.namespaceURI !== 'http://www.w3.org/1999/xhtml' ||
    window.top !== window || window.length !== 0 ||
    document.forms.length !== 1 || document.forms[0] !== form ||
    !form.isConnected || form.ownerDocument !== document ||
    form.action !== arguments[1] || form.method !== 'post' ||
    !['', '_self'].includes(form.target) ||
    form.enctype !== 'application/x-www-form-urlencoded') return false;
if (document.querySelector('[form], [formaction], [formtarget], [formmethod], [formenctype], base[target], iframe, frame, object, embed')) return false;
const members = Array.from(form.elements);
return members.every(element => element.form === form) &&
    arguments[2].every(element => element instanceof HTMLInputElement &&
        element.tagName === 'INPUT' &&
        element.namespaceURI === 'http://www.w3.org/1999/xhtml' &&
        element.ownerDocument === document && element.isConnected &&
        element.form === form && members.includes(element));
"""


class PinnedBrowser:
    """Adapter for the pinned Selenium/UC APIs; its guard starts before use."""

    def __init__(self, driver, guard):
        self.driver = driver
        self.guard = guard
        self.challenge = None

    def static_form(self):
        # Page scripts are disabled by the acknowledged guard before navigation.
        # Only genuine native inputs are supported, including the submit control.
        if len(self.driver.window_handles) != 1:
            raise SafeError('target')
        forms = self.driver.find_elements('tag name', 'form')
        if len(forms) != 1:
            raise SafeError('target')
        form = forms[0]
        expected = [('login_username', 'text', None), ('login_password', 'password', None),
                    ('login', 'submit', 'вход'), ('redirect', 'hidden', 'index.php')]
        if self.challenge is not None:
            expected += [('cap_sid', 'hidden', self.challenge[0]), (self.challenge[1], 'text', None)]
        controls = {}
        for name, kind, value in expected:
            matches = form.find_elements('name', name)
            if len(matches) != 1:
                raise SafeError('target')
            element = matches[0]
            if (element.tag_name != 'input' or element.get_property('form') != form
                    or element.get_attribute('type') != kind
                    or (value is not None and element.get_attribute('value') != value)):
                raise SafeError('target')
            controls[name] = element
        # Check native DOM brands and actual form.elements membership, not attributes.
        if self.driver.execute_script(STATIC_FORM_SCRIPT, form, LOGIN_URL, list(controls.values())) is not True:
            raise SafeError('target')
        return form, controls

    def open_login(self) -> tuple[str, str, bytes]:
        import base64
        import time
        self.guard.check()
        self.driver.get(LOGIN_URL)
        self.guard.check()
        if self.driver.current_url != LOGIN_URL:
            raise SafeError('target')
        html = self.driver.page_source
        original_challenge = parse_challenge(html)
        if original_challenge is not None:
            image = captcha_image(html)
            matches = [element for element in self.driver.find_elements('tag name', 'img') if element.get_attribute('src') == image]
            if len(matches) != 1:
                raise SafeError('challenge')
            self.guard.policy.set_image(image)
            if self.driver.execute_script(RETRY_CAPTCHA_IMAGE_SCRIPT, matches[0], image) is not True:
                raise SafeError('challenge')
            self.guard.check()
            deadline = time.monotonic() + 10
            while True:
                matches = [element for element in self.driver.find_elements('tag name', 'img') if element.get_attribute('src') == image]
                if len(matches) == 1 and matches[0].is_displayed() and matches[0].get_property('complete') is True and type(matches[0].get_property('naturalWidth')) is int and matches[0].get_property('naturalWidth') > 0:
                    break
                self.guard.check()
                if time.monotonic() >= deadline:
                    raise SafeError('challenge')
                time.sleep(0.1)
            html = self.driver.page_source
            if self.driver.current_url != LOGIN_URL or parse_challenge(html) != original_challenge or captcha_image(html) != image:
                raise SafeError('challenge')
        self.challenge = parse_challenge(html)
        self.static_form()
        png = base64.b64decode(self.driver.get_screenshot_as_base64(), validate=True)
        self.guard.check()
        return self.driver.current_url, html, png

    def submit_login(self, fields: dict[str, str]) -> None:
        self.guard.check()
        if self.driver.current_url != LOGIN_URL or parse_challenge(self.driver.page_source) != self.challenge:
            raise SafeError('challenge')
        form, selected = self.static_form()
        names = ['login_username', 'login_password']
        if self.challenge is not None:
            if fields.get('cap_sid') != self.challenge[0]:
                raise SafeError('challenge')
            names.append(self.challenge[1])
        controls = [(name, selected[name]) for name in names]
        for name, element in controls:
            element.clear()
            element.send_keys(fields[name])
        self.guard.check()
        if form.get_attribute('action') != LOGIN_URL or self.driver.current_url != LOGIN_URL or parse_challenge(self.driver.page_source) != self.challenge:
            raise SafeError('challenge')
        if self.static_form() != (form, selected):
            raise SafeError('target')
        self.guard.policy.enable_submission()
        selected['login'].click()
        self.guard.check()

    def verify_index(self) -> tuple[str, str]:
        self.guard.check()
        self.driver.get(INDEX_URL)
        self.guard.check()
        return self.driver.current_url, self.driver.page_source

    def cookies(self) -> list[dict]:
        self.guard.check()
        return self.driver.get_cookies()

    def close(self) -> None:
        if hasattr(self.guard, 'expect_shutdown'):
            self.guard.expect_shutdown()
        try:
            self.driver.quit()
        finally:
            self.guard.close()


class CDPGuard:
    """One live page websocket pauses requests before Chromium forwards them."""

    def __init__(self, wsurl: str, policy: RequestPolicy, abort):
        import threading
        parsed = urlsplit(wsurl)
        if parsed.scheme != 'ws' or parsed.hostname != '127.0.0.1' or not parsed.port or not parsed.path.startswith('/devtools/page/') or parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise SafeError('privacy')
        self.wsurl, self.policy, self.abort = wsurl, policy, abort
        self.ready, self.stop = threading.Event(), threading.Event()
        self.failed = False
        self.denied_document = False
        self.closing = False
        self.thread = threading.Thread(target=self._thread_main, daemon=True)

    def _connect(self):
        import websockets
        return websockets.connect(self.wsurl, open_timeout=5, close_timeout=2, max_size=MAX_FRAME, proxy=None)

    def _decision(self, paused: dict) -> tuple[str, dict]:
        params = {'requestId': paused['requestId']}
        if self.policy.permits(paused):
            return 'Fetch.continueRequest', params
        if paused.get('resourceType') == 'Document':
            self.denied_document = True
        params['errorReason'] = 'BlockedByClient'
        return 'Fetch.failRequest', params

    async def _serve(self):
        import asyncio
        async with self._connect() as ws:
            try:
                commands = [('Emulation.setScriptExecutionDisabled', {'value': True}), ('Network.setCacheDisabled', {'cacheDisabled': True}), ('Network.setBypassServiceWorker', {'bypass': True}), ('Fetch.enable', {'patterns': [{'urlPattern': '*', 'requestStage': 'Request'}]})]
                for command_id, (method, params) in enumerate(commands, 1):
                    await ws.send(json.dumps({'id': command_id, 'method': method, 'params': params}))
                pending = {1, 2, 3, 4}
                sequence = 4
                while not self.stop.is_set():
                    try:
                        message = json.loads(await asyncio.wait_for(ws.recv(), 0.25))
                    except asyncio.TimeoutError:
                        continue
                    if 'error' in message:
                        raise SafeError('browser')
                    pending.discard(message.get('id'))
                    if not pending:
                        self.ready.set()
                    if message.get('method') == 'Fetch.requestPaused':
                        method, params = self._decision(message['params'])
                        sequence += 1
                        await ws.send(json.dumps({'id': sequence, 'method': method, 'params': params}))
            except BaseException:
                if not self.closing:
                    self.failed = True
                    try:
                        self.abort()
                    except BaseException:
                        pass
                raise

    def _thread_main(self):
        import asyncio
        try:
            asyncio.run(self._serve())
        except BaseException:
            if not self.closing:
                self.failed = True
        finally:
            self.ready.set()

    def start(self) -> None:
        self.thread.start()
        if not self.ready.wait(10) or self.failed:
            raise SafeError('browser')

    def check(self) -> None:
        if self.failed or not self.thread.is_alive():
            raise SafeError('browser')
        if self.denied_document:
            raise SafeError('target')

    def expect_shutdown(self) -> None:
        self.closing = True

    def close(self) -> None:
        self.closing = True
        self.stop.set()
        self.thread.join(3)
        if self.thread.is_alive():
            raise SafeError('cleanup')


SOURCE_PINS = {'bottle_plugins/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'bottle_plugins/error_plugin.py': 'bfe4e3f04eb9976e0a1628afe466d4ef1c56e0993323522a4667f785c76640f9',
 'bottle_plugins/logger_plugin.py': '4bc8ad04ac72e5ded5e5c8dbf9f51068afc6022122de60c28792c0cfacbbf2c2',
 'bottle_plugins/prometheus_plugin.py': '31cf5f5a0eb943afdbb48ec3d151b4b9b957de800d4aecc58b90b98312fe3752',
 'build_package.py': '42ecf4446fe11cb9a7354356b69e3f3201f55ac78ed7103df089adae391b8087',
 'dtos.py': 'aee10d73a8449c43ae2c5e454416625d3ff7a70662b9c5f0ccea8fc056c55f69',
 'flaresolverr.py': 'b26652d4cbde4bf8fa6ec3e773ddc7afb5a9d6ca298d3bab8f5137387836c0bf',
 'flaresolverr_service.py': 'aeb870a59eb6ac868af5eec54f4ce9d0652a9b50b1c832507555cf62d04caecb',
 'metrics.py': 'cfb4216c308cf30b249c7e1e4ca9e17bc9838934eb7ca9f08f9ce0d32bf4a6ca',
 'sessions.py': '2bb7b5cc932df8edef838afa0b0efb8c0226be63665f88664fcc3cafb0c1d3c6',
 'tests.py': '2291ad5d3ba1a1c5f7ebcc866943abe61157c9819a7ab85f16f8923570167ad6',
 'tests_sites.py': '5ad6b8d0f8cb8bda8dab6a003006a724ac3fec34a8fbf59d6af23641fae3dcc0',
 'undetected_chromedriver/__init__.py': '7c2ebaa66f65b040434d398d2982a9e133e663ee81911c30ab97afbc48a03a44',
 'undetected_chromedriver/cdp.py': 'cdd6c097b41f07b97ebb3571de48c658b21d9e2a6dc909e9dacd46c96752b902',
 'undetected_chromedriver/devtool.py': 'c6513fe0e427a59473304a91596c9e06d4f0bce395883522b617e479c50c8468',
 'undetected_chromedriver/dprocess.py': 'd53a7223fabdf6885ca316c8687a1337cdb536f8375f42f18fc7e2660bfee039',
 'undetected_chromedriver/options.py': '13249f8e29580ce8bd032ee6a8fa1490492ef5f8f601558ff766cfd0f25ec94a',
 'undetected_chromedriver/patcher.py': '5d993d8bb629576d733b390027d6aa4bbc99293bb5955e6279acb76fc3d4c8ee',
 'undetected_chromedriver/reactor.py': '8bc607a5d59880954c6aba7c7d7cb3ad00197162c40459e678b51200a137add3',
 'undetected_chromedriver/webelement.py': 'd425ad23bb7c33d978647e6b2d1efce56dd938f03d726d7452beea132cbde8cb',
 'utils.py': 'c7ab204e32ec4e6ea51d47827073ac4f983a70b6bb790228c8b58626be9a0c87'}
DRIVER_PINS = {'96959755da2c4ea28b888076c3a164806b11e2ff5692b0af936f4c1d47dee088', '19283fd89652a5c8c68d518febd9f7d12b91400ed8ad97b69b21179721101034'}
DRIVER_PATH = Path('/app/chromedriver')


def read_pinned(path: Path, allowed: set[str]) -> bytes:
    try:
        if not allowed or any(not re.fullmatch(r'[0-9a-f]{64}', pin) for pin in allowed):
            raise SafeError('identity')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_nlink != 1 or info.st_size > 64 * 1024 * 1024:
                raise SafeError('identity')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                data = stream.read(64 * 1024 * 1024 + 1)
            if hashlib.sha256(data).hexdigest() not in allowed:
                raise SafeError('identity')
            return data
        finally:
            os.close(fd)
    except Exception:
        raise SafeError('identity') from None


def copy_pinned_package(root: Path) -> None:
    imports = root / 'imports'
    imports.mkdir(mode=0o700)
    package = imports / 'undetected_chromedriver'
    package.mkdir(mode=0o700)
    for name, pin in SOURCE_PINS.items():
        data = read_pinned(Path('/app') / name, {pin})
        if name.startswith('undetected_chromedriver/'):
            target = package / Path(name).name
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
    sys.path.insert(0, str(imports))


def debugger_websocket(driver) -> str:
    from urllib.request import ProxyHandler, build_opener
    addr = driver.options.debugger_address
    host, separator, port = addr.rpartition(':')
    if separator != ':' or host != '127.0.0.1' or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise SafeError('privacy')
    opener = build_opener(ProxyHandler({}))
    with opener.open('http://' + addr + '/json/protocol', timeout=5) as response:
        protocol = json.loads(response.read(8 * MAX_FRAME + 1))
    network = [domain for domain in protocol.get('domains', []) if domain.get('domain') == 'Network']
    if len(network) != 1:
        raise SafeError('browser')
    commands = {command['name']: {parameter['name'] for parameter in command.get('parameters', [])} for command in network[0].get('commands', [])}
    if 'cacheDisabled' not in commands.get('setCacheDisabled', set()) or 'bypass' not in commands.get('setBypassServiceWorker', set()):
        raise SafeError('browser')
    with opener.open('http://' + addr + '/json/list', timeout=5) as response:
        pages = json.loads(response.read(MAX_FRAME + 1))
    pages = [row for row in pages if row.get('type') == 'page']
    if len(pages) != 1 or not pages[0]['webSocketDebuggerUrl'].startswith('ws://' + addr + '/devtools/page/'):
        raise SafeError('privacy')
    return pages[0]['webSocketDebuggerUrl']


def build_browser(private_root: Path, guard_type=CDPGuard) -> PinnedBrowser:
    """Trusted library seam; production callers supply no policy or target overrides."""
    import tempfile
    tempfile.tempdir = str(private_root)
    sys.dont_write_bytecode = True
    os.environ.clear()
    os.environ.update(PATH='/usr/local/bin:/usr/bin:/bin', LANG='C.UTF-8', HOME=str(private_root), TMPDIR=str(private_root), XDG_CACHE_HOME=str(private_root / 'cache'), XDG_CONFIG_HOME=str(private_root / 'config'))
    copy_pinned_package(private_root)
    driver_bytes = read_pinned(DRIVER_PATH, DRIVER_PINS)
    private_driver = private_root / 'chromedriver'
    fd = os.open(private_driver, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(driver_bytes)
    import undetected_chromedriver as uc
    from undetected_chromedriver.patcher import Patcher
    Patcher.data_path = str(private_root / 'patcher')
    Path(Patcher.data_path).mkdir(mode=0o700)
    options = uc.ChromeOptions()
    for arg in ('--disable-background-networking', '--disable-default-apps', '--disable-sync', '--disable-breakpad', '--disable-crash-reporter', '--no-first-run', '--no-default-browser-check', '--no-proxy-server', '--disable-search-engine-choice-screen', '--disk-cache-dir=' + str(private_root / 'cache')):
        options.add_argument(arg)
    options.set_capability('acceptInsecureCerts', False)
    driver = uc.Chrome(options=options, browser_executable_path='/usr/bin/chromium', driver_executable_path=str(private_driver), user_data_dir=str(private_root / 'profile'), headless=True, use_subprocess=True, no_sandbox=True, enable_cdp_events=False, debug=False, log_level=3)
    driver.set_page_load_timeout(20)
    driver.set_script_timeout(10)
    def abort():
        # The outer helper always creates a fresh session before this factory.
        # Never signal a caller's/shared group from a direct library invocation.
        if os.getsid(0) == os.getpid() and os.getpgrp() == os.getpid():
            import signal
            os.killpg(os.getpid(), signal.SIGKILL)
    guard = guard_type(debugger_websocket(driver), RequestPolicy(), abort)
    guard.start()
    return PinnedBrowser(driver, guard)


class PipeChannel:
    def __init__(self, source, sink):
        self.source, self.sink = source, sink

    def send(self, message: dict) -> None:
        write_frame(self.sink, message)

    def receive(self) -> dict:
        return read_frame(self.source)


def _quiet_stdio() -> None:
    null = os.open('/dev/null', os.O_RDWR | os.O_CLOEXEC)
    try:
        for fd in (0, 1, 2):
            os.dup2(null, fd)
    finally:
        if null > 2:
            os.close(null)


def _child_entry(worker, source_fd: int, sink_fd: int) -> None:
    import resource
    os.setsid()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    _quiet_stdio()
    for entry in Path('/proc/self/fd').iterdir():
        fd = int(entry.name)
        if fd > 2 and fd not in (source_fd, sink_fd):
            try:
                os.close(fd)
            except OSError:
                pass
    os.set_inheritable(source_fd, False)
    os.set_inheritable(sink_fd, False)
    with os.fdopen(source_fd, 'rb', buffering=0) as source, os.fdopen(sink_fd, 'wb', buffering=0) as sink:
        channel = PipeChannel(source, sink)
        try:
            worker(channel)
        except BaseException as exc:
            code = exc.code if isinstance(exc, SafeError) else 'browser'
            try:
                channel.send({'kind': 'error', 'code': code})
            except BaseException:
                pass
            os._exit(1)
    os._exit(0)


def _group_live(group: int) -> bool:
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == group and fields[0] not in {'Z', 'X'}:
                return True
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return False


def _terminate_owned(pid: int) -> None:
    import signal
    import time
    # Do not reap the leader until the group is killed: its reserved PID prevents
    # reuse while we signal this freshly acquired private session.
    try:
        grouped = os.getpgid(pid) == pid and os.getsid(pid) == pid
    except ProcessLookupError:
        grouped = False
    def send(sig):
        try:
            if grouped:
                os.killpg(pid, sig)
            else:
                os.kill(pid, sig)
        except ProcessLookupError:
            pass
    send(signal.SIGTERM)
    if grouped:
        deadline = time.monotonic() + 0.5
        while _group_live(pid) and time.monotonic() < deadline:
            time.sleep(0.025)
    send(signal.SIGKILL)
    deadline = time.monotonic() + 2
    while grouped and _group_live(pid):
        if time.monotonic() >= deadline:
            raise SafeError('cleanup')
        time.sleep(0.025)
    os.waitpid(pid, 0)


def supervise(worker, private_root: Path, source_fd: int, sink_fd: int, seconds: int = 480) -> dict:
    """Proxy one private exchange while supervising EOF and owned descendants."""
    import select
    import signal
    import shutil
    import time
    child_read, parent_write = os.pipe()
    parent_read, child_write = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            _child_entry(worker, child_read, child_write)
        except BaseException:
            os._exit(1)
    os.close(child_read)
    os.close(child_write)
    watched_signals = (signal.SIGALRM, signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    prior_signals = {sig: signal.getsignal(sig) for sig in watched_signals}
    def expired(*_args):
        raise SafeError('timeout')
    signal.signal(signal.SIGALRM, expired)
    def interrupted(*_args):
        raise SafeError('protocol')
    for sig in watched_signals[1:]:
        signal.signal(sig, interrupted)
    signal.alarm(seconds)
    pending = None
    state = 'starting'
    try:
        with os.fdopen(parent_read, 'rb', buffering=0) as incoming, os.fdopen(parent_write, 'wb', buffering=0) as outgoing, os.fdopen(os.dup(source_fd), 'rb', buffering=0) as host_source, os.fdopen(os.dup(sink_fd), 'wb', buffering=0) as host_sink:
            while True:
                watches = [source_fd] + ([parent_read] if pending is None else [])
                ready, _, _ = select.select(watches, [], [], 0.05)
                if source_fd in ready:
                    if state != 'awaiting-login':
                        # Reading one byte distinguishes EOF from unexpected data;
                        # both abort without forwarding another credential frame.
                        os.read(source_fd, 1)
                        raise SafeError('protocol')
                    reply = read_frame(host_source)
                    validate_login(reply, False)
                    write_frame(outgoing, reply)
                    state = 'awaiting-result'
                if parent_read in ready:
                    message = read_frame(incoming)
                    if message.get('kind') == 'captcha' and state == 'starting':
                        write_frame(host_sink, message)
                        state = 'awaiting-login'
                    elif message.get('kind') == 'verified' and state == 'awaiting-result':
                        pending = message
                    elif message.get('kind') == 'error' and message.get('code') in ERROR_CODES:
                        raise SafeError(message['code'])
                    else:
                        raise SafeError('protocol')
                status = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if status is not None:
                    if pending is None or status.si_code != os.CLD_EXITED or status.si_status != 0:
                        raise SafeError('browser')
                    break
        return pending
    except SafeError:
        raise
    except BaseException:
        raise SafeError('browser') from None
    finally:
        signal.alarm(0)
        for sig in watched_signals:
            signal.signal(sig, signal.SIG_IGN)
        try:
            try:
                _terminate_owned(pid)
            finally:
                shutil.rmtree(private_root)
        finally:
            for sig, previous in prior_signals.items():
                signal.signal(sig, previous)


def executable_tmpfs(mountinfo: str, target: str) -> bool:
    matches = []
    for line in mountinfo.splitlines():
        before, sep, after = line.partition(' - ')
        fields, filesystem = before.split(), after.split()
        if sep and len(fields) >= 6 and fields[4] == target:
            matches.append(filesystem and filesystem[0] == 'tmpfs' and 'noexec' not in fields[5].split(',') and len(filesystem) >= 3 and 'noexec' not in filesystem[2].split(','))
    return len(matches) == 1 and bool(matches[0])


def validate_png(png: bytes) -> None:
    import zlib
    try:
        if type(png) is not bytes or not 57 <= len(png) <= 1048576 or not png.startswith(b'\x89PNG\r\n\x1a\n'):
            raise SafeError('challenge')
        offset, count, image_data, ended = 8, 0, False, False
        while offset < len(png):
            if offset + 12 > len(png):
                raise SafeError('challenge')
            size = struct.unpack('!I', png[offset:offset + 4])[0]
            kind = png[offset + 4:offset + 8]
            end = offset + 12 + size
            if end > len(png) or not re.fullmatch(b'[A-Za-z]{4}', kind):
                raise SafeError('challenge')
            data = png[offset + 8:offset + 8 + size]
            crc = struct.unpack('!I', png[end - 4:end])[0]
            if zlib.crc32(kind + data) & 0xffffffff != crc:
                raise SafeError('challenge')
            if count == 0 and kind != b'IHDR':
                raise SafeError('challenge')
            if kind == b'IHDR':
                if count or size != 13:
                    raise SafeError('challenge')
                width, height, depth, color, compression, filtering, interlace = struct.unpack('!IIBBBBB', data)
                depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
                if not 1 <= width <= 8192 or not 1 <= height <= 8192 or width * height > 16777216 or depth not in depths.get(color, set()) or compression or filtering or interlace not in (0, 1):
                    raise SafeError('challenge')
            elif kind == b'IDAT':
                image_data = image_data or bool(size)
            elif kind == b'IEND':
                if size or not image_data or end != len(png):
                    raise SafeError('challenge')
                ended = True
            elif kind[0] < 97 and kind != b'PLTE':
                raise SafeError('challenge')
            offset, count = end, count + 1
        if not ended:
            raise SafeError('challenge')
    except Exception:
        raise SafeError('challenge') from None


BROWSER_UID = 1000
BROWSER_GID = 1000


def verify_current_inputs() -> None:
    for name, pin in SOURCE_PINS.items():
        read_pinned(Path('/app') / name, {pin})
    read_pinned(DRIVER_PATH, DRIVER_PINS)


def production_worker(private_root: Path, channel: Channel) -> None:
    restrict_worker()
    browser = build_browser(private_root)
    run(browser, channel)
    verify_current_inputs()


def prepare_private() -> Path:
    import pwd
    import tempfile
    if os.geteuid() != 0:
        raise SafeError('privacy')
    require_root_caps(Path('/proc/self/status').read_text())
    account = pwd.getpwnam('flaresolverr')
    if (account.pw_uid, account.pw_gid) != (BROWSER_UID, BROWSER_GID):
        raise SafeError('identity')
    info = os.lstat('/dev')
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o755 or not executable_tmpfs(Path('/proc/self/mountinfo').read_text(), '/dev'):
        raise SafeError('privacy')
    private = Path(tempfile.mkdtemp(prefix='owner-rutracker-', dir='/dev'))
    try:
        os.chmod(private, 0o700)
        os.chown(private, BROWSER_UID, BROWSER_GID)
        return private
    except BaseException:
        private.rmdir()
        raise SafeError('privacy') from None


def main() -> int:
    import resource
    import shutil
    source_fd, sink_fd = os.dup(0), os.dup(1)
    os.set_inheritable(source_fd, False)
    os.set_inheritable(sink_fd, False)
    _quiet_stdio()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    sys.dont_write_bytecode = True
    private = None
    try:
        if len(sys.argv) != 1:
            raise SafeError('protocol')
        private = prepare_private()
        def worker(channel):
            production_worker(private, channel)
        result = supervise(worker, private, source_fd, sink_fd)
        with os.fdopen(os.dup(sink_fd), 'wb', buffering=0) as sink:
            write_frame(sink, result)
        return 0
    except BaseException as exc:
        code = exc.code if isinstance(exc, SafeError) else 'browser'
        try:
            with os.fdopen(os.dup(sink_fd), 'wb', buffering=0) as sink:
                write_frame(sink, {'kind': 'error', 'code': code})
        except BaseException:
            pass
        return 1
    finally:
        if private is not None and private.exists():
            try:
                shutil.rmtree(private)
            except BaseException:
                pass
        os.close(source_fd)
        os.close(sink_fd)


def _status_field(status: str, name: str) -> str:
    values = [line.split(':', 1)[1].strip() for line in status.splitlines() if line.startswith(name + ':')]
    if len(values) != 1:
        raise SafeError('privacy')
    return values[0]


def require_root_caps(status: str) -> None:
    value = _status_field(status, 'CapEff')
    required = (1 << 0) | (1 << 1) | (1 << 5) | (1 << 6) | (1 << 7)
    if not re.fullmatch(r'[0-9a-fA-F]{16}', value) or int(value, 16) & required != required:
        raise SafeError('privacy')


def set_no_new_privileges() -> None:
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(38, 1, 0, 0, 0) != 0 or _status_field(Path('/proc/self/status').read_text(), 'NoNewPrivs') != '1':
        raise SafeError('privacy')


def restrict_worker() -> None:
    os.setgroups([])
    os.setgid(BROWSER_GID)
    os.setuid(BROWSER_UID)
    set_no_new_privileges()
    status = Path('/proc/self/status').read_text()
    if os.getresuid() != (BROWSER_UID,) * 3 or os.getresgid() != (BROWSER_GID,) * 3 or os.getgroups() or _status_field(status, 'CapEff') != '0000000000000000' or _status_field(status, 'NoNewPrivs') != '1':
        raise SafeError('privacy')


if __name__ == '__main__':
    raise SystemExit(main())
