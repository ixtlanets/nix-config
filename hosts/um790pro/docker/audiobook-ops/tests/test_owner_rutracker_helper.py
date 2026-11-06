"""Synthetic helper boundary tests; never contact a provider or Docker."""
import importlib.util
import io
from pathlib import Path
import sys
import struct
import tempfile
import hashlib
import zlib
import base64
from unittest.mock import patch
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'scripts' / 'owner_rutracker_helper.py'


def png_chunk(kind, data):
    return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)


PNG = b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('!IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) + png_chunk(b'IDAT', zlib.compress(b'\x00\x00\x00\x00\xff')) + png_chunk(b'IEND', b'')


def helper(test):
    if not HELPER.is_file():
        test.fail('Missing framed helper channel behavior')
    spec = importlib.util.spec_from_file_location('owner_rutracker_helper', HELPER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ChannelTests(unittest.TestCase):
    def test_frame_round_trip_keeps_synthetic_credentials_off_other_streams(self):
        h = helper(self)
        stream = io.BytesIO()
        outgoing = {'kind': 'login', 'username': 'fixture', 'password': 'synthetic-only', 'captcha': ''}
        h.write_frame(stream, outgoing)
        self.assertGreater(len(stream.getvalue()), 4)
        stream.seek(0)
        self.assertEqual(h.read_frame(stream), outgoing)

    def test_malformed_frames_fail_with_fixed_protocol_code(self):
        h = helper(self)
        cases = [b'', b'\x00', struct.pack('!I', h.MAX_FRAME + 1),
                 struct.pack('!I', 6) + b'{}', struct.pack('!I', 1) + b'!',
                 struct.pack('!I', 2) + b'[]', struct.pack('!I', 13) + b'{"x":1,"x":2}']
        for data in cases:
            with self.subTest(data_size=len(data)):
                outcome = 'accepted'
                try:
                    h.read_frame(io.BytesIO(data))
                except h.SafeError as exc:
                    outcome = exc.code
                except Exception:
                    outcome = 'unbounded_exception'
                self.assertEqual(outcome, 'protocol')

    def test_oversized_write_does_not_emit_partial_frame(self):
        h = helper(self)
        stream = io.BytesIO()
        outcome = 'accepted'
        try:
            h.write_frame(stream, {'kind': 'login', 'password': 'x' * h.MAX_FRAME})
        except h.SafeError as exc:
            outcome = exc.code
        self.assertEqual(outcome, 'protocol')
        self.assertEqual(stream.getvalue(), b'')


class SyntheticBrowser:
    def __init__(self):
        self.events = []
        self.login_html = '<form method="post" action="login.php"><input name="login_username"><input name="login_password" type="password"></form>'
        self.index_html = '<span id="logged-in-username">fixture</span>'
        self.final_url = 'https://rutracker.org/forum/index.php'
        self.cookie_rows = [{'name': 'bb_session', 'value': 'rotated-fixture', 'domain': 'rutracker.org', 'path': '/forum/', 'secure': True, 'expiry': 4102444800}]

    def open_login(self):
        self.events.append('login')
        return 'https://rutracker.org/forum/login.php', self.login_html, PNG

    def submit_login(self, fields):
        self.events.append(('submit', fields.copy()))

    def verify_index(self):
        self.events.append('verify')
        return self.final_url, self.index_html

    def cookies(self):
        self.events.append('cookies')
        return self.cookie_rows

    def close(self):
        self.events.append('close')


class SyntheticChannel:
    def __init__(self):
        self.messages = []
        self.reply = {'kind': 'login', 'username': 'fixture', 'password': 'synthetic-password', 'captcha': ''}

    def send(self, message):
        self.messages.append(message)

    def receive(self):
        return self.reply


class RefreshTests(unittest.TestCase):
    def test_same_browser_direct_verification_precedes_rotated_cookie_and_cleanup(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'run', None)), 'Missing retained-browser refresh behavior')
        browser = SyntheticBrowser()
        channel = SyntheticChannel()
        h.run(browser, channel)
        self.assertEqual(browser.events[0], 'login')
        self.assertEqual(browser.events[1][0], 'submit')
        self.assertEqual(browser.events[1][1]['login_username'], 'fixture')
        self.assertEqual(browser.events[1][1]['login_password'], 'synthetic-password')
        self.assertEqual(browser.events[2:], ['verify', 'cookies', 'close'])
        self.assertEqual(channel.messages[0]['kind'], 'captcha')
        self.assertFalse(channel.messages[0]['cap_required'])
        self.assertEqual(channel.messages[1], {'kind': 'verified', 'cookies': {'bb_session': 'rotated-fixture'}})

    def test_strict_hidden_captcha_challenge_is_submitted_in_same_browser(self):
        h = helper(self)
        browser, channel = SyntheticBrowser(), SyntheticChannel()
        browser.login_html = '<form method="post" action="https://rutracker.org/forum/login.php"><input name="login_username"><input name="login_password"><input type="hidden" name="cap_sid" value="fixture123"><input name="cap_code_fixture123"></form>'
        channel.reply['captcha'] = 'fixture-answer'
        h.run(browser, channel)
        self.assertTrue(channel.messages[0]['cap_required'])
        self.assertEqual(browser.events[1][1]['cap_sid'], 'fixture123')
        self.assertEqual(browser.events[1][1]['cap_code_fixture123'], 'fixture-answer')

    def test_untrusted_form_and_malformed_challenge_are_rejected_before_prompt(self):
        h = helper(self)
        forms = [
            '<form method="post" action="https://other.invalid/login.php"><input name="login_username"><input name="login_password"></form>',
            '<form method="post" action="login.php"><input type="hidden" name="cap_sid" value="x"><input name="cap_code_x"></form>',
            '<form method="post" action="login.php"><input name="login_username"><input name="login_password"><input name="cap_sid" value="x"><input name="cap_code_x"></form>',
            '<form method="post" action="login.php"><input name="login_username"><input name="login_password"><input type="hidden" name="cap_sid" value="x"><input name="cap_code_x"><input name="cap_code_y"></form>',
            '<form method="post" action="login.php" action="https://other.invalid/"><input name="login_username"><input name="login_password"></form>',
        ]
        for html in forms:
            with self.subTest(form_index=forms.index(html)):
                browser, channel = SyntheticBrowser(), SyntheticChannel()
                browser.login_html = html
                outcome = 'accepted'
                try:
                    h.run(browser, channel)
                except h.SafeError as exc:
                    outcome = exc.code
                self.assertIn(outcome, {'target', 'challenge'})
                self.assertEqual(channel.messages, [])
                self.assertEqual(browser.events, ['login', 'close'])

    def test_authentication_requires_one_active_marker_with_matching_principal(self):
        h = helper(self)
        bad = ['', '<!-- <span id="logged-in-username">fixture</span> -->',
               '<script><span id="logged-in-username">fixture</span></script>',
               '<template><span id="logged-in-username">fixture</span></template>',
               '<span id="other" id="logged-in-username">fixture</span>',
               '<span id="logged-in-username" id="other">fixture</span>',
               '<span id="logged-in-username">other</span>',
               '<span id="logged-in-username">fixture</span><span id="logged-in-username">fixture</span>',
               '<div hidden><span id="logged-in-username">fixture</span></div>']
        for html in bad:
            with self.subTest(case=bad.index(html)):
                browser, channel = SyntheticBrowser(), SyntheticChannel()
                browser.index_html = html
                outcome = 'accepted'
                try:
                    h.run(browser, channel)
                except h.SafeError as exc:
                    outcome = exc.code
                self.assertEqual(outcome, 'authentication')
                self.assertNotIn('cookies', browser.events)
                self.assertEqual(browser.events[-1], 'close')
                self.assertFalse(any(m['kind'] == 'verified' for m in channel.messages))

    def test_wrong_final_target_cannot_publish_authenticated_fixture(self):
        h = helper(self)
        for url in ['https://other.invalid/forum/index.php', 'http://rutracker.org/forum/index.php', 'https://rutracker.org/forum/index.php?x=1']:
            browser, channel = SyntheticBrowser(), SyntheticChannel()
            browser.final_url = url
            outcome = 'accepted'
            try:
                h.run(browser, channel)
            except h.SafeError as exc:
                outcome = exc.code
            self.assertEqual(outcome, 'target')
            self.assertNotIn('cookies', browser.events)

    def test_cookie_scope_expiry_and_duplicate_ambiguity_cannot_be_published(self):
        h = helper(self)
        variants = [
            {'domain': 'other.invalid'}, {'domain': '.org'}, {'domain': 'sub.rutracker.org'},
            {'path': '/elsewhere/'}, {'path': '/forum/index.php'}, {'path': '//forum/'},
            {'expiry': 1}, {'expiry': True}, {'value': ''}, {'value': 'line\nbreak'},
            {'name': 'not_whitelisted'}, {'secure': False},
        ]
        base = SyntheticBrowser().cookie_rows[0]
        cases = [[dict(base, **delta)] for delta in variants]
        cases.append([base, dict(base, value='ambiguous')])
        for index, rows in enumerate(cases):
            with self.subTest(case=index):
                browser, channel = SyntheticBrowser(), SyntheticChannel()
                browser.cookie_rows = rows
                outcome = 'accepted'
                try:
                    h.run(browser, channel)
                except h.SafeError as exc:
                    outcome = exc.code
                self.assertEqual(outcome, 'cookies')
                self.assertEqual(browser.events[-1], 'close')
                self.assertFalse(any(m['kind'] == 'verified' for m in channel.messages))

    def test_malformed_login_reply_is_rejected_without_submission(self):
        h = helper(self)
        replies = [{'kind': 'login', 'username': 'fixture', 'password': 'x', 'captcha': '', 'extra': 'x'},
                   {'kind': 'wrong', 'username': 'fixture', 'password': 'x', 'captcha': ''},
                   {'kind': 'login', 'username': 'fixture', 'password': 'x\n', 'captcha': ''},
                   {'kind': 'login', 'username': '', 'password': 'x', 'captcha': ''}]
        for reply in replies:
            browser, channel = SyntheticBrowser(), SyntheticChannel()
            channel.reply = reply
            outcome = 'accepted'
            try:
                h.run(browser, channel)
            except h.SafeError as exc:
                outcome = exc.code
            self.assertEqual(outcome, 'protocol')
            self.assertEqual(browser.events, ['login', 'close'])

    def test_browser_channel_and_cleanup_exception_text_never_escapes(self):
        h = helper(self)
        for boundary in ('open_login', 'submit_login', 'verify_index', 'cookies', 'close', 'send', 'receive'):
            with self.subTest(boundary=boundary):
                browser, channel = SyntheticBrowser(), SyntheticChannel()
                def fail(*args):
                    raise RuntimeError('SYNTHETIC_SECRET_MUST_NOT_ESCAPE')
                setattr(channel if boundary in {'send', 'receive'} else browser, boundary, fail)
                outcome = None
                try:
                    h.run(browser, channel)
                except BaseException as exc:
                    outcome = exc
                self.assertIsInstance(outcome, h.SafeError)
                self.assertNotIn('SYNTHETIC_SECRET', str(outcome))
                self.assertFalse(any(m['kind'] == 'verified' for m in channel.messages))
                if boundary != 'close':
                    self.assertEqual(browser.events[-1], 'close')

    def test_invalid_or_oversized_screenshot_never_prompts_for_credentials(self):
        h = helper(self)
        for png in (b'', b'not-a-PNG', b'\x89PNG\r\n\x1a\n' + b'x' * 1048576):
            browser, channel = SyntheticBrowser(), SyntheticChannel()
            original = browser.open_login
            browser.open_login = lambda: (*original()[:2], png)
            outcome = 'accepted'
            try:
                h.run(browser, channel)
            except h.SafeError as exc:
                outcome = exc.code
            self.assertEqual(outcome, 'challenge')
            self.assertEqual(channel.messages, [])
            self.assertEqual(browser.events, ['login', 'close'])

    def test_captcha_field_suffix_is_independent_of_hidden_sid_and_login_value_is_fixed(self):
        h = helper(self)
        browser, channel = SyntheticBrowser(), SyntheticChannel()
        browser.login_html = '<form method="post" action="login.php"><input name="login_username"><input name="login_password"><input type="hidden" name="cap_sid" value="session-one"><input name="cap_code_challenge-two"></form>'
        channel.reply['captcha'] = 'answer'
        outcome = 'accepted'
        try:
            h.run(browser, channel)
        except h.SafeError as exc:
            outcome = exc.code
        self.assertEqual(outcome, 'accepted')
        fields = browser.events[1][1]
        self.assertEqual(fields['cap_sid'], 'session-one')
        self.assertEqual(fields['cap_code_challenge-two'], 'answer')
        self.assertEqual(fields['login'], 'вход')

    def test_webdriver_action_keycodes_are_refused_before_browser_input(self):
        h = helper(self)
        for key in ('\ue007', '\ue008', '\ue00c', '\ue050', '\ue0ff'):
            for field in ('username', 'password', 'captcha'):
                with self.subTest(key=ord(key), field=field):
                    browser, channel = SyntheticBrowser(), SyntheticChannel()
                    channel.reply[field] = 'prefix' + key + 'suffix'
                    outcome = 'accepted'
                    try: h.run(browser, channel)
                    except h.SafeError as exc: outcome = exc.code
                    self.assertEqual(outcome, 'protocol')
                    self.assertFalse(any(isinstance(event, tuple) for event in browser.events))
        reply = {'kind': 'login', 'username': 'владелец', 'password': '<&"пароль', 'captcha': 'ответ'}
        h.validate_login(reply, True)


class RequestPolicyTests(unittest.TestCase):
    def test_request_gate_blocks_unexpected_redirect_before_forwarding_post(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'RequestPolicy', None)), 'Missing pre-request destination policy')
        policy = h.RequestPolicy()
        request = lambda url, method='GET', kind='Document': {'request': {'url': url, 'method': method}, 'resourceType': kind}
        self.assertTrue(policy.permits(request(h.LOGIN_URL)))
        self.assertFalse(policy.permits(request(h.LOGIN_URL, 'POST')))
        self.assertFalse(policy.permits(request('https://other.invalid/forum/login.php', 'POST')))
        policy.enable_submission()
        self.assertTrue(policy.permits(request(h.LOGIN_URL, 'POST')))
        self.assertTrue(policy.permits(request(h.INDEX_URL)))
        self.assertFalse(policy.permits(request(h.INDEX_URL, 'POST')))
        self.assertFalse(policy.permits(request(h.LOGIN_URL + '?redirect=bad')))
        image = 'https://rutracker.org/forum/captcha-fixture.php?challenge=fixture'
        policy.set_image(image)
        self.assertTrue(policy.permits(request(image, kind='Image')))
        self.assertFalse(policy.permits(request(image, kind='Script')))
        self.assertFalse(policy.permits(request(image + '&other=1', kind='Image')))

    def test_parsed_captcha_resource_is_one_active_constrained_actual_image(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'captcha_image', None)), 'Missing constrained parsed captcha image selection')
        base = '<form method="post" action="login.php"><input name="login_username"><input name="login_password"><input type="hidden" name="cap_sid" value="x"><input name="cap_code_y">%s</form>'
        self.assertEqual(h.captcha_image(base % '<img src="captcha-fixture.php?x=1">'), 'https://rutracker.org/forum/captcha-fixture.php?x=1')
        for markup in ('', '<img src="https://other.invalid/x">', '<img src="//other.invalid/x">', '<img src="../../x">', '<img src="x"><img src="y">', '<template><img src="x"></template>'):
            outcome = 'accepted'
            try:
                h.captcha_image(base % markup)
            except h.SafeError as exc:
                outcome = exc.code
            self.assertEqual(outcome, 'challenge')


class PinnedAdapterTests(unittest.TestCase):
    def test_adapter_uses_native_same_origin_fields_and_named_submit(self):
        h = helper(self)
        events = []
        class Guard:
            policy = h.RequestPolicy()
            def check(self): pass
            def close(self): events.append('guard-close')
        class Field:
            tag_name = 'input'
            def __init__(self, name, kind='text', value=''):
                self.name, self.kind, self.value = name, kind, value
            def get_attribute(self, name): return {'name': self.name, 'type': self.kind, 'value': self.value}.get(name)
            def get_property(self, name): return form if name == 'form' else None
            def clear(self): self.value = ''
            def send_keys(self, value): self.value += value; events.append(('typed', self.name))
            def click(self): events.append(('clicked', self.name))
        fields = {'login_username': Field('login_username'), 'login_password': Field('login_password', 'password'), 'redirect': Field('redirect', 'hidden', 'index.php'), 'login': Field('login', 'submit', 'вход')}
        class Form:
            def get_attribute(self, name): return {'action': h.LOGIN_URL, 'method': 'post'}.get(name)
            def find_elements(self, by, name): return [fields[name]] if name in fields else []
        form = Form()
        class Driver:
            window_handles = ['only']
            current_url = h.LOGIN_URL
            page_source = SyntheticBrowser().login_html
            def execute_script(self, script, *args): return True
            def get(self, target): events.append(target)
            def find_elements(self, by, name): return [form] if name == 'form' else []
            def get_screenshot_as_base64(self): return base64.b64encode(PNG).decode('ascii')
            def get_cookies(self): return SyntheticBrowser().cookie_rows
            def quit(self): events.append('quit')
        browser = h.PinnedBrowser(Driver(), Guard())
        browser.open_login()
        browser.submit_login({'login_username': 'fixture', 'login_password': '<&"synthetic', 'login': 'вход', 'redirect': 'index.php'})
        self.assertEqual(events[1:4], [('typed', 'login_username'), ('typed', 'login_password'), ('clicked', 'login')])
        self.assertEqual(fields['login_password'].value, '<&"synthetic')
        self.assertFalse(any(isinstance(item, str) and item.startswith('data:') for item in events))
        browser.verify_index()
        self.assertEqual(events[4], h.INDEX_URL)
        browser.close()
        self.assertEqual(events[-2:], ['quit', 'guard-close'])


    def test_native_submit_overrides_are_refused_before_any_browser_input(self):
        import types
        h = helper(self)
        for attr, value in [('formaction', 'https://external.invalid/'), ('formtarget', '_blank'),
                            ('formmethod', 'get'), ('formenctype', 'text/plain'), ('form', 'other')]:
            with self.subTest(attr=attr):
                events = []
                class Field:
                    tag_name = 'input'
                    def __init__(self, name): self.name = name
                    def get_attribute(self, key):
                        return {'type': 'submit' if self.name == 'login' else ('hidden' if self.name == 'redirect' else ('password' if self.name == 'login_password' else 'text')), 'value': 'вход' if self.name == 'login' else 'index.php', attr: value if self.name == 'login' else None}.get(key)
                    def get_dom_attribute(self, key): return value if self.name == 'login' and key == attr else None
                    def get_property(self, key): return form if key == 'form' else None
                    def clear(self): events.append('clear')
                    def send_keys(self, value): events.append('typed')
                    def click(self): events.append('clicked')
                class Form:
                    def get_attribute(self, key): return {'action': h.LOGIN_URL, 'method': 'post', 'target': '', 'enctype': 'application/x-www-form-urlencoded'}.get(key)
                    def find_elements(self, by, name): return [Field(name)]
                form = Form()
                class Driver:
                    current_url = h.LOGIN_URL
                    current_window_handle = 'only'
                    window_handles = ['only']
                    page_source = SyntheticBrowser().login_html
                    def execute_script(self, script, *args): return False
                    def find_elements(self, by, name): return [form] if name == 'form' else [Field('login')]
                guard = types.SimpleNamespace(check=lambda: None, policy=h.RequestPolicy())
                browser = h.PinnedBrowser(Driver(), guard)
                outcome = 'accepted'
                try: browser.submit_login({'login_username': 'fixture', 'login_password': 'fixture-password'})
                except h.SafeError as exc: outcome = exc.code
                self.assertEqual((outcome, events), ('target', []))
    def test_rotating_login_challenge_retries_image_in_same_rendered_document(self):
        h = helper(self)
        events = []
        class Guard:
            policy = h.RequestPolicy()
            def check(self): pass
        class Image:
            loaded = False
            def __init__(self, source): self.source = source
            def get_attribute(self, name): return self.source if name == 'src' else None
            def is_displayed(self): return True
            def get_property(self, name): return self.loaded if name == 'complete' else (1 if self.loaded else 0)
        class Form:
            def find_elements(self, by, name):
                kinds = {'login_username': 'text', 'login_password': 'password', 'redirect': 'hidden', 'login': 'submit', 'cap_sid': 'hidden', driver.code: 'text'}
                if name not in kinds: return []
                class Field:
                    tag_name = 'input'
                    def get_property(self, key): return form if key == 'form' else None
                    def get_attribute(self, key):
                        return {'type': kinds[name], 'value': {'redirect': 'index.php', 'login': 'вход', 'cap_sid': driver.sid}.get(name, '')}.get(key)
                return [Field()]
        form = Form()
        class Driver:
            window_handles = ['only']
            current_url = h.LOGIN_URL
            gets = 0
            def get(self, target):
                self.gets += 1
                sid = 'session-' + str(self.gets)
                code = 'cap_code_independent-' + str(self.gets)
                self.sid, self.code = sid, code
                image = 'https://rutracker.org/forum/fixture-' + str(self.gets) + '.png'
                self.page_source = '<form method="post" action="login.php"><input name="login_username"><input name="login_password" type="password"><input type="hidden" name="cap_sid" value="' + sid + '"><input name="' + code + '"><input name="redirect" type="hidden" value="index.php"><input name="login" type="submit" value="вход"><img src="' + image + '"></form>'
                self.image = Image(image)
            def find_elements(self, by, name): return [self.image] if name == 'img' else ([form] if name == 'form' else [])
            def execute_script(self, script, element, image, *args):
                if script != h.RETRY_CAPTCHA_IMAGE_SCRIPT: return True
                events.append(('retry', element.source, image))
                self.image.loaded = True
                return True
            def get_screenshot_as_base64(self): return base64.b64encode(PNG).decode('ascii')
        driver = Driver()
        browser = h.PinnedBrowser(driver, Guard())
        outcome = 'accepted'
        result = None
        try: result = browser.open_login()
        except h.SafeError as exc: outcome = exc.code
        self.assertEqual(outcome, 'accepted')
        self.assertEqual(driver.gets, 1)
        self.assertEqual(h.parse_challenge(result[1]), ('session-1', 'cap_code_independent-1'))
        self.assertEqual(browser.challenge, ('session-1', 'cap_code_independent-1'))
        self.assertEqual(events, [('retry', 'https://rutracker.org/forum/fixture-1.png', 'https://rutracker.org/forum/fixture-1.png')])


class NativeInputBoundaryTests(unittest.TestCase):
    """Model Selenium elements; exact native DOM branding is tested by runtime fixtures."""

    def fixture(self, h, replacement=None, role='login', wrong_owner=False, captcha=False):
        events = []
        class Field:
            tag_name = 'input'
            def __init__(self, name, kind, value=''):
                self.name, self.kind, self.value = name, kind, value
            def get_attribute(self, key):
                return {'name': self.name, 'type': self.kind, 'value': self.value}.get(key)
            def get_property(self, key):
                return (None if wrong_owner and self.name == role else form) if key == 'form' else None
            def clear(self): events.append(('clear', self.name)); self.value = ''
            def send_keys(self, value): events.append(('typed', self.name)); self.value += value
            def click(self):
                events.append(('clicked', self.name))
                if self.tag_name != 'input': driver.window_handles.append('new-context')
        fields = {name: Field(name, kind, value) for name, kind, value in (
            ('login_username', 'text', ''), ('login_password', 'password', ''),
            ('redirect', 'hidden', 'index.php'), ('login', 'submit', 'вход'),
            ('cap_sid', 'hidden', 'fixture-sid'), ('cap_code_other', 'text', ''))}
        if replacement: fields[role].tag_name = replacement
        class Form:
            tag_name = 'form'
            def get_attribute(self, key): return {'action': h.LOGIN_URL, 'method': 'post'}.get(key)
            def find_elements(self, by, name): return [fields[name]] if name in fields else []
        form = Form()
        markup = '<form action="login.php" method="post"><input name="login_username" type="text"><input name="login_password" type="password"><input name="redirect" type="hidden" value="index.php"><input name="login" type="submit" value="вход"></form>'
        if role == 'login' and replacement == 'a':
            markup = markup.replace('<input name="login" type="submit" value="вход">', '<a name="login" type="submit" value="вход" href="https://forbidden.invalid/escape" target="new-context">enter</a>')
        if role == 'login' and replacement == 'button':
            markup = markup.replace('<input name="login" type="submit" value="вход">', '<button name="login" type="submit" value="вход"><a href="https://forbidden.invalid/escape" target="new-context">enter</a></button>')
        if captcha:
            markup = markup.replace('</form>', '<input name="cap_sid" type="hidden" value="fixture-sid"><input name="cap_code_other" type="text"><img src="/forum/captcha.png"></form>')
        class Image:
            def get_attribute(self, key): return 'https://rutracker.org/forum/captcha.png' if key == 'src' else None
            def is_displayed(self): return True
            def get_property(self, key): return True if key == 'complete' else 1
        image = Image()
        class Driver:
            window_handles = ['only']
            current_url = h.LOGIN_URL
            page_source = markup
            def get(self, url):
                self.current_url = url
                if url == h.INDEX_URL: self.page_source = SyntheticBrowser().index_html
            def find_elements(self, by, name): return [form] if name == 'form' else ([image] if name == 'img' else [])
            def execute_script(self, script, *args): return True
            def get_screenshot_as_base64(self):
                events.append('screenshot'); return base64.b64encode(PNG).decode('ascii')
            def get_cookies(self): return SyntheticBrowser().cookie_rows
            def quit(self): events.append('quit')
        driver = Driver()
        class Guard:
            policy = h.RequestPolicy()
            def check(self): pass
            def close(self): pass
        return h.PinnedBrowser(driver, Guard()), driver, fields, events

    def refused_before_input(self, replacement, role='login', wrong_owner=False, captcha=False):
        h = helper(self)
        browser, driver, fields, events = self.fixture(h, replacement, role, wrong_owner, captcha)
        channel = SyntheticChannel()
        outcome = 'accepted'
        try: h.run(browser, channel)
        except h.SafeError as exc: outcome = exc.code
        self.assertEqual((outcome, channel.messages, events, driver.window_handles),
                         ('target', [], ['quit'], ['only']))

    def test_named_anchor_submit_is_refused_before_screenshot_or_credentials(self):
        self.refused_before_input('a')

    def test_button_with_link_is_refused_before_screenshot_or_credentials(self):
        self.refused_before_input('button')

    def test_native_input_form_preserves_literal_credentials_and_native_submit(self):
        h = helper(self)
        browser, driver, fields, events = self.fixture(h)
        channel = SyntheticChannel()
        channel.reply['password'] = '<&"literal synthetic password'
        h.run(browser, channel)
        self.assertEqual(fields['login_password'].value, channel.reply['password'])
        self.assertEqual([e for e in events if isinstance(e, tuple)],
                         [('clear', 'login_username'), ('typed', 'login_username'),
                          ('clear', 'login_password'), ('typed', 'login_password'), ('clicked', 'login')])
        self.assertEqual([m['kind'] for m in channel.messages], ['captcha', 'verified'])
        self.assertEqual(driver.window_handles, ['only'])

    def test_field_tag_spoofs_and_wrong_native_owner_are_refused_before_input(self):
        for role in ('login_username', 'login_password', 'redirect', 'login'):
            for replacement, wrong_owner in [('a', False), ('custom-input', False), (None, True)]:
                with self.subTest(role=role, replacement=replacement, wrong_owner=wrong_owner):
                    self.refused_before_input(replacement, role, wrong_owner)

    def test_captcha_and_hidden_sid_require_native_inputs_with_canonical_owner(self):
        for role in ('cap_sid', 'cap_code_other'):
            for replacement, wrong_owner in [('a', False), ('custom-input', False), (None, True)]:
                with self.subTest(role=role, replacement=replacement, wrong_owner=wrong_owner):
                    self.refused_before_input(replacement, role, wrong_owner, captcha=True)

    def test_native_captcha_input_preserves_independent_sid_and_answer(self):
        h = helper(self)
        browser, driver, fields, events = self.fixture(h, captcha=True)
        channel = SyntheticChannel()
        channel.reply['captcha'] = 'synthetic literal <&" answer'
        h.run(browser, channel)
        self.assertEqual(fields['cap_sid'].value, 'fixture-sid')
        self.assertEqual(fields['cap_code_other'].value, channel.reply['captcha'])
        self.assertEqual([e for e in events if isinstance(e, tuple) and e[0] == 'typed'],
                         [('typed', 'login_username'), ('typed', 'login_password'), ('typed', 'cap_code_other')])
        self.assertEqual([m['kind'] for m in channel.messages], ['captcha', 'verified'])
        self.assertTrue(channel.messages[0]['cap_required'])
        self.assertEqual(driver.window_handles, ['only'])

    def test_shape_is_rechecked_before_typing_and_before_click(self):
        h = helper(self)
        for when in ('receive', 'typed'):
            with self.subTest(when=when):
                browser, driver, fields, events = self.fixture(h)
                channel = SyntheticChannel()
                if when == 'receive':
                    def receive():
                        fields['login'].tag_name = 'button'
                        return channel.reply
                    channel.receive = receive
                else:
                    original = fields['login_password'].send_keys
                    def send_keys(value):
                        original(value)
                        fields['login'].tag_name = 'button'
                    fields['login_password'].send_keys = send_keys
                outcome = 'accepted'
                try: h.run(browser, channel)
                except h.SafeError as exc: outcome = exc.code
                self.assertEqual(outcome, 'target')
                self.assertFalse(any(isinstance(e, tuple) and e[0] == 'clicked' for e in events))
                if when == 'receive': self.assertFalse(any(isinstance(e, tuple) and e[0] == 'typed' for e in events))
                self.assertEqual(driver.window_handles, ['only'])


class CDPGuardTests(unittest.TestCase):
    def test_persistent_wire_enables_gate_and_denies_unexpected_document(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'CDPGuard', None)), 'Missing persistent CDP Fetch request gate')
        import asyncio
        import json
        import threading
        sent, finished = [], threading.Event()
        class Connection:
            def __init__(self):
                self.messages = [json.dumps({'id': 1, 'result': {}}), json.dumps({'id': 2, 'result': {}}), json.dumps({'id': 3, 'result': {}}), json.dumps({'id': 4, 'result': {}}), json.dumps({'method': 'Fetch.requestPaused', 'params': {'requestId': 'allow', 'resourceType': 'Document', 'request': {'url': h.LOGIN_URL, 'method': 'GET'}}}), json.dumps({'method': 'Fetch.requestPaused', 'params': {'requestId': 'deny', 'resourceType': 'Document', 'request': {'url': 'https://other.invalid/', 'method': 'POST'}}})]
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def send(self, data):
                sent.append(json.loads(data))
                if len(sent) == 6: finished.set()
            async def recv(self):
                if self.messages: return self.messages.pop(0)
                await asyncio.sleep(0.01)
                raise asyncio.TimeoutError()
        class Guard(h.CDPGuard):
            def _connect(self): return Connection()
        guard = Guard('ws://127.0.0.1:12345/devtools/page/fixture', h.RequestPolicy(), lambda: None)
        try:
            guard.start()
            self.assertTrue(finished.wait(2))
            self.assertEqual([row['method'] for row in sent], ['Emulation.setScriptExecutionDisabled', 'Network.setCacheDisabled', 'Network.setBypassServiceWorker', 'Fetch.enable', 'Fetch.continueRequest', 'Fetch.failRequest'])
            self.assertEqual(sent[0]['params'], {'value': True})
            self.assertEqual(sent[1]['params'], {'cacheDisabled': True})
            self.assertEqual(sent[2]['params'], {'bypass': True})
            outcome = 'accepted'
            try: guard.check()
            except h.SafeError as exc: outcome = exc.code
            self.assertEqual(outcome, 'target')
        finally:
            guard.close()
        self.assertFalse(guard.thread.is_alive())

    def test_wire_failure_aborts_owned_browser_before_releasing_interception(self):
        h = helper(self)
        import json
        import threading
        events, done = [], threading.Event()
        class Connection:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): events.append('context-exit'); done.set()
            async def send(self, data): pass
            async def recv(self): raise RuntimeError('SYNTHETIC_SECRET_WIRE_FAILURE')
        class Guard(h.CDPGuard):
            def _connect(self): return Connection()
        guard = Guard('ws://127.0.0.1:1234/devtools/page/fixture', h.RequestPolicy(), lambda: events.append('abort'))
        try:
            guard.start()
        except h.SafeError:
            pass
        self.assertTrue(done.wait(2))
        guard.close()
        self.assertEqual(events, ['abort', 'context-exit'])



class FactoryTests(unittest.TestCase):
    def test_pinned_file_check_rejects_malformed_or_changed_hashes(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'read_pinned', None)), 'Missing pinned input verification')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'fixture'
            source.write_bytes(b'public-fixture')
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(h.read_pinned(source, {digest}), b'public-fixture')
            for pin in ('0' * 63, 'g' * 64, '0' * 64):
                outcome = 'accepted'
                try: h.read_pinned(source, {pin})
                except h.SafeError as exc: outcome = exc.code
                self.assertEqual(outcome, 'identity')
            source.chmod(0o666)
            with self.assertRaises(h.SafeError): h.read_pinned(source, {digest})

    def test_factory_copies_pinned_driver_and_package_before_browser_patch(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'build_browser', None)), 'Missing private pinned-browser factory')
        import types
        import os
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'INHERITED_SYNTHETIC_SENTINEL': 'must-not-reach-browser'}, clear=True), patch.object(tempfile, 'tempdir', tempfile.tempdir):
            root = Path(directory)
            original = root / 'original-driver'
            original.write_bytes(b'fixture-driver')
            original.chmod(0o755)
            owned = root / 'private'
            owned.mkdir(mode=0o700)
            class Options:
                def __init__(self): self.arguments = []; self.capabilities = {}
                def add_argument(self, arg): self.arguments.append(arg)
                def set_capability(self, key, value): self.capabilities[key] = value
            class Driver:
                browser_pid = 99999999
                service = types.SimpleNamespace(process=None)
                def __init__(self, **kwargs):
                    self.kwargs = kwargs
                    Path(kwargs['driver_executable_path']).write_bytes(b'privately-patched')
                    self.env = dict(os.environ)
                def set_page_load_timeout(self, timeout): pass
                def set_script_timeout(self, timeout): pass
            class Guard:
                def __init__(self, wsurl, policy, abort): self.policy = policy
                def start(self): pass
            fake_uc = types.SimpleNamespace(ChromeOptions=Options, Chrome=Driver)
            fake_patcher = types.SimpleNamespace(Patcher=type('Patcher', (), {}))
            with patch.dict(sys.modules, {'undetected_chromedriver': fake_uc, 'undetected_chromedriver.patcher': fake_patcher}), patch.object(h, 'DRIVER_PATH', original), patch.object(h, 'DRIVER_PINS', {hashlib.sha256(original.read_bytes()).hexdigest()}), patch.object(h, 'copy_pinned_package'), patch.object(h, 'debugger_websocket', return_value='ws://127.0.0.1:1234/devtools/page/fixture'):
                browser = h.build_browser(owned, guard_type=Guard)
            self.assertEqual(original.read_bytes(), b'fixture-driver')
            self.assertEqual(Path(browser.driver.kwargs['driver_executable_path']).parent, owned)
            self.assertNotIn('INHERITED_SYNTHETIC_SENTINEL', browser.driver.env)
            self.assertFalse(browser.driver.kwargs['options'].capabilities['acceptInsecureCerts'])
            self.assertTrue(browser.driver.kwargs['use_subprocess'])


class SupervisorTests(unittest.TestCase):
    def test_supervisor_defers_verified_until_owned_child_group_and_directory_are_gone(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'supervise', None)), 'Missing owned process supervisor')
        import os
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / 'owned'
            private.mkdir(mode=0o700)
            host_read, host_write = os.pipe()
            out_read, out_write = os.pipe()
            observed = []
            def peer():
                with os.fdopen(os.dup(out_read), 'rb', buffering=0) as stream:
                    observed.append(h.read_frame(stream))
                with os.fdopen(os.dup(host_write), 'wb', buffering=0) as stream:
                    h.write_frame(stream, {'kind': 'login', 'username': 'fixture', 'password': 'x', 'captcha': ''})
            peer_pid = os.fork()
            if peer_pid == 0:
                peer()
                os._exit(0)
            def worker(channel):
                child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], env={'PATH': '/usr/bin:/bin', 'HOME': tempfile.gettempdir(), 'TMPDIR': tempfile.gettempdir()})
                (private / 'child-pid').write_text(str(child.pid))
                channel.send({'kind': 'captcha', 'png': '', 'cap_required': False})
                channel.receive()
                channel.send({'kind': 'verified', 'cookies': {'bb_session': 'synthetic'}, 'child_pid': child.pid})
            try:
                result = h.supervise(worker, private, host_read, out_write, seconds=5)
                self.assertEqual(result['kind'], 'verified')
                self.assertFalse(private.exists())
                _, peer_status = os.waitpid(peer_pid, 0)
                self.assertEqual(peer_status, 0)
                child_stat = Path('/proc') / str(result['child_pid']) / 'stat'
                self.assertTrue(not child_stat.exists() or child_stat.read_text().rsplit(')', 1)[1].split()[0] == 'Z')
                # supervise returns candidate only after cleanup; caller publishes it.
            finally:
                for fd in (host_read, host_write, out_read, out_write): os.close(fd)

    def test_eof_aborts_owned_worker_before_browser_block_completes(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'supervise', None)), 'Missing EOF supervision behavior')
        import os
        import time
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / 'owned'
            private.mkdir(mode=0o700)
            host_read, host_write = os.pipe()
            out_read, out_write = os.pipe()
            os.close(host_write)
            def worker(channel): time.sleep(60)
            started = time.monotonic()
            try:
                with self.assertRaises(h.SafeError):
                    h.supervise(worker, private, host_read, out_write, seconds=5)
                self.assertLess(time.monotonic() - started, 4)
                self.assertFalse(private.exists())
            finally:
                for fd in (host_read, out_read, out_write): os.close(fd)

    def test_termination_signal_still_reaps_owned_worker_and_private_directory(self):
        h = helper(self)
        import os
        import signal
        import time
        import json
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / 'owned'
            private.mkdir(mode=0o700)
            identity_path = Path(directory) / 'worker-identity.json'
            host_read, host_write = os.pipe()
            out_read, out_write = os.pipe()
            supervisor = os.fork()
            if supervisor == 0:
                def worker(channel):
                    pid = os.getpid()
                    fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
                    identity_path.write_text(json.dumps({'pid': pid, 'start': fields[19]}))
                    (private / 'started').touch()
                    time.sleep(60)
                try:
                    h.supervise(worker, private, host_read, out_write, seconds=5)
                except h.SafeError:
                    os._exit(0 if not private.exists() else 2)
                os._exit(3)
            reaped = False
            try:
                deadline = time.monotonic() + 3
                while not (private / 'started').exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((private / 'started').exists())
                os.kill(supervisor, signal.SIGTERM)
                status = os.waitpid(supervisor, 0)[1]
                reaped = True
                self.assertEqual(status, 0)
                self.assertFalse(private.exists())
            finally:
                if not reaped:
                    os.kill(supervisor, signal.SIGKILL)
                    os.waitpid(supervisor, 0)
                # Even the historical broken supervisor cannot leave this fixture
                # running: use its retained PID+starttime and private session only.
                if identity_path.exists():
                    identity = json.loads(identity_path.read_text())
                    process = Path('/proc') / str(identity['pid'])
                    try:
                        fields = (process / 'stat').read_text().rsplit(')', 1)[1].split()
                        if fields[19] == identity['start'] and int(fields[2]) == identity['pid'] and int(fields[3]) == identity['pid'] and process.stat().st_uid == os.getuid():
                            os.killpg(identity['pid'], signal.SIGKILL)
                    except (FileNotFoundError, ProcessLookupError):
                        pass
                for fd in (host_read, host_write, out_read, out_write):
                    os.close(fd)


class BootstrapTests(unittest.TestCase):
    def test_runtime_storage_requires_fixed_executable_tmpfs_mount(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'executable_tmpfs', None)), 'Missing executable tmpfs gate')
        valid = '38 30 0:25 / /dev rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755\n'
        self.assertTrue(h.executable_tmpfs(valid, '/dev'))
        self.assertFalse(h.executable_tmpfs(valid.replace('rw,nosuid', 'rw,nosuid,noexec'), '/dev'))
        self.assertFalse(h.executable_tmpfs(valid.replace('tmpfs tmpfs', 'ext4 /dev/sda'), '/dev'))
        self.assertFalse(h.executable_tmpfs(valid, '/tmp'))
        self.assertFalse(h.executable_tmpfs(valid + valid, '/dev'))

    def test_worker_has_only_private_protocol_fds_and_null_standard_streams(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'supervise', None)), 'Missing private worker stream boundary')
        import os
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / 'owned'
            private.mkdir(mode=0o700)
            host_read, host_write = os.pipe()
            out_read, out_write = os.pipe()
            peer_pid = os.fork()
            if peer_pid == 0:
                with os.fdopen(os.dup(out_read), 'rb', buffering=0) as stream: h.read_frame(stream)
                with os.fdopen(os.dup(host_write), 'wb', buffering=0) as stream: h.write_frame(stream, {'kind': 'login', 'username': 'fixture', 'password': 'x', 'captcha': ''})
                os._exit(0)
            def worker(channel):
                import resource
                safe = all(os.readlink('/proc/self/fd/' + str(fd)) == '/dev/null' for fd in (0, 1, 2))
                safe = safe and not os.get_inheritable(channel.source.fileno()) and not os.get_inheritable(channel.sink.fileno()) and resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
                channel.send({'kind': 'captcha', 'png': '', 'cap_required': False})
                channel.receive()
                channel.send({'kind': 'verified', 'cookies': {'bb_session': 'synthetic'}, 'safe': safe})
            try:
                result = h.supervise(worker, private, host_read, out_write, seconds=5)
                self.assertTrue(result['safe'])
                self.assertEqual(os.waitpid(peer_pid, 0)[1], 0)
            finally:
                for fd in (host_read, host_write, out_read, out_write): os.close(fd)


class MarkupIsolationTests(unittest.TestCase):
    def test_hidden_form_never_prompts_but_inert_marker_copies_do_not_replace_active_principal(self):
        h = helper(self)
        browser, channel = SyntheticBrowser(), SyntheticChannel()
        browser.login_html = '<div hidden>' + browser.login_html + '</div>'
        outcome = 'accepted'
        try: h.run(browser, channel)
        except h.SafeError as exc: outcome = exc.code
        self.assertEqual(outcome, 'challenge')
        self.assertEqual(channel.messages, [])
        browser, channel = SyntheticBrowser(), SyntheticChannel()
        browser.index_html = '<template><span id="logged-in-username">other</span></template><span id="logged-in-username">fixture</span>'
        outcome = 'accepted'
        try: h.run(browser, channel)
        except h.SafeError as exc: outcome = exc.code
        self.assertEqual(outcome, 'accepted')


class MainBoundaryTests(unittest.TestCase):
    def test_production_worker_drops_privilege_before_browser_import_boundary(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'restrict_worker', None)), 'Missing complete irreversible worker restrictions')
        import os
        import types
        events = []
        browser = SyntheticBrowser()
        channel = SyntheticChannel()
        def restrict():
            events.extend([('groups', []), ('gid', 1000), ('uid', 1000)])
        with patch.object(h, 'restrict_worker', side_effect=restrict), patch.object(h, 'build_browser', side_effect=lambda root: events.append(('browser', root)) or browser), patch.object(h, 'verify_current_inputs'):
            h.production_worker(Path('/fixture-owned'), channel)
        self.assertEqual(events[:3], [('groups', []), ('gid', 1000), ('uid', 1000)])
        self.assertEqual(events[3][0], 'browser')
        self.assertEqual(channel.messages[-1]['kind'], 'verified')

    def test_root_bootstrap_refuses_nonroot_before_creating_storage(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'prepare_private', None)), 'Missing fixed root storage bootstrap')
        with patch.object(h.os, 'geteuid', return_value=1000):
            outcome = 'accepted'
            try: h.prepare_private()
            except h.SafeError as exc: outcome = exc.code
        self.assertEqual(outcome, 'privacy')

    def test_main_keeps_protocol_private_and_sanitizes_bootstrap_failure(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'main', None)), 'Missing private helper process entrypoint')
        import os
        import resource
        import shutil
        for fails in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                private = Path(directory) / 'owned'
                private.mkdir(mode=0o700)
                out_read, out_write = os.pipe()
                error_read, error_write = os.pipe()
                pid = os.fork()
                if pid == 0:
                    os.dup2(out_write, 1)
                    os.dup2(error_write, 2)
                    def fake_supervise(worker, root, source_fd, sink_fd):
                        safe = not os.get_inheritable(source_fd) and not os.get_inheritable(sink_fd) and all(os.readlink('/proc/self/fd/' + str(fd)) == '/dev/null' for fd in (0, 1, 2)) and resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
                        shutil.rmtree(root)
                        return {'kind': 'verified', 'cookies': {'bb_session': 'synthetic'}, 'safe': safe}
                    def fake_prepare():
                        if fails: raise RuntimeError('SYNTHETIC_SECRET_BOOTSTRAP')
                        return private
                    with patch.object(h, 'prepare_private', side_effect=fake_prepare), patch.object(h, 'supervise', side_effect=fake_supervise), patch.object(sys, 'argv', ['helper']):
                        os._exit(h.main())
                os.close(out_write)
                os.close(error_write)
                status = os.waitpid(pid, 0)[1]
                with os.fdopen(out_read, 'rb', buffering=0) as stream: message = h.read_frame(stream)
                with os.fdopen(error_read, 'rb', buffering=0) as stream: self.assertEqual(stream.read(), b'')
                self.assertNotIn('SYNTHETIC_SECRET', str(message))
                if fails:
                    self.assertEqual(message, {'kind': 'error', 'code': 'browser'})
                    self.assertNotEqual(status, 0)
                else:
                    self.assertEqual(status, 0)
                    self.assertTrue(message['safe'])
                    self.assertFalse(private.exists())

    def test_root_capability_gate_requires_owned_cleanup_and_privilege_drop_capabilities(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'require_root_caps', None)), 'Missing effective root capability preflight')
        required = (1 << 0) | (1 << 1) | (1 << 5) | (1 << 6) | (1 << 7)
        h.require_root_caps('CapEff:\t%016x\n' % required)
        for bit in (0, 1, 5, 6, 7):
            with self.assertRaises(h.SafeError):
                h.require_root_caps('CapEff:\t%016x\n' % (required & ~(1 << bit)))

    def test_fixed_no_new_privileges_syscall_is_verified_in_isolated_subprocess(self):
        h = helper(self)
        self.assertTrue(callable(getattr(h, 'set_no_new_privileges', None)), 'Missing no-new-privileges enforcement')
        import subprocess
        code = "import importlib.util; s=importlib.util.spec_from_file_location('h', " + repr(str(HELPER)) + "); h=importlib.util.module_from_spec(s); s.loader.exec_module(h); h.set_no_new_privileges(); print('NNP_OK')"
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code], env={'PATH': '/usr/bin:/bin', 'HOME': tempfile.gettempdir(), 'TMPDIR': tempfile.gettempdir()}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'NNP_OK\n')
        self.assertEqual(result.stderr, b'')


class PNGTests(unittest.TestCase):
    def test_corrupt_or_incomplete_png_is_rejected_before_credential_prompt(self):
        h = helper(self)
        bad = [PNG[:-1], PNG + b'trailing', PNG[:40] + bytes([PNG[40] ^ 1]) + PNG[41:], b'\x89PNG\r\n\x1a\nfixture', b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('!IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) + png_chunk(b'IEND', b'')]
        for index, png in enumerate(bad):
            with self.subTest(case=index):
                browser, channel = SyntheticBrowser(), SyntheticChannel()
                original = browser.open_login
                browser.open_login = lambda: (*original()[:2], png)
                outcome = 'accepted'
                try: h.run(browser, channel)
                except h.SafeError as exc: outcome = exc.code
                self.assertEqual(outcome, 'challenge')
                self.assertEqual(channel.messages, [])


class BrowserMarkupSemanticsTests(unittest.TestCase):
    def test_raw_text_and_ignored_self_closing_slashes_cannot_forge_principal(self):
        h = helper(self)
        marker = '<span id="logged-in-username">fixture</span>'
        for tag in ('xmp', 'noembed', 'noframes', 'plaintext', 'script/', 'template/'):
            with self.subTest(tag=tag):
                html = '<' + tag + '>' + marker
                if tag == 'plaintext': html = '<plaintext></plaintext>' + marker
                outcome = 'accepted'
                try: h.verify_principal(html, 'fixture')
                except h.SafeError as exc: outcome = exc.code
                self.assertEqual(outcome, 'authentication')
        for tag in ('xmp', 'noembed', 'noframes', 'script/', 'template/'):
            closing = tag.rstrip('/')
            h.verify_principal('<' + tag + '>inert</' + closing + '>' + marker, 'fixture')

    def test_raw_text_and_ignored_self_closing_slashes_cannot_own_login_form(self):
        h = helper(self)
        form = SyntheticBrowser().login_html
        for tag in ('xmp', 'noembed', 'noframes', 'plaintext', 'script/', 'template/'):
            with self.subTest(tag=tag):
                html = '<' + tag + '>' + form
                if tag == 'plaintext': html = '<plaintext></plaintext>' + form
                outcome = 'accepted'
                try: h.parse_challenge(html)
                except h.SafeError as exc: outcome = exc.code
                self.assertEqual(outcome, 'challenge')
        for tag in ('xmp', 'noembed', 'noframes', 'script/', 'template/'):
            self.assertIsNone(h.parse_challenge('<' + tag + '>inert</' + tag.rstrip('/') + '>' + form))

    def test_raw_text_inside_real_form_cannot_supply_challenge_fields_or_images(self):
        h = helper(self)
        form = SyntheticBrowser().login_html
        fake = '<input type="hidden" name="cap_sid" value="fake"><input name="cap_code_fake">'
        for tag in ('xmp', 'noembed', 'noframes'):
            self.assertIsNone(h.parse_challenge(form.replace('</form>', '<' + tag + '>' + fake + '</' + tag + '></form>')))
        actual = form.replace('</form>', '<input type="hidden" name="cap_sid" value="one"><input name="cap_code_two"><img src="actual-fixture.png"><xmp><img src="fake-fixture.png"></xmp></form>')
        self.assertEqual(h.captcha_image(actual), 'https://rutracker.org/forum/actual-fixture.png')


if __name__ == '__main__':
    unittest.main()
