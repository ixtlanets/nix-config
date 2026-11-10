"""Adapter contract tests; every compositor/process interaction is mocked."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/hex-gliff-wtype.py"
spec = importlib.util.spec_from_file_location("hex_gliff_wtype", SCRIPT)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.window = {
            "address": "0x123abc",
            "pid": 1234,
            "class": "gliff",
            "title": "omarchy-vm — Gliff",
        }
        self.run = self.enterContext(patch.object(adapter.subprocess, "run"))
        self.run.return_value = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(self.window), stderr=""
        )
        self.readlink = self.enterContext(
            patch.object(adapter.os, "readlink", return_value="/usr/bin/gliff")
        )
        self.read_bytes = self.enterContext(
            patch.object(Path, "read_bytes", return_value=b"/usr/bin/gliff\0omarchy-vm\0")
        )
        self.execv = self.enterContext(patch.object(adapter.os, "execv"))
        self.sleep = self.enterContext(patch.object(adapter.time, "sleep"))
        self.enterContext(patch.dict(os.environ, {"HEX_GLIFF_PASTE": "1"}, clear=True))

    def invoke(self, args=None):
        with patch.object(adapter.sys, "argv", ["wtype", *(adapter.HEX_ARGS if args is None else args)]):
            return adapter.main()

    def assert_fallback(self, args=None):
        original = adapter.HEX_ARGS if args is None else args
        self.assertEqual(self.invoke(args), 0)
        self.execv.assert_called_once_with("/usr/bin/wtype", ["/usr/bin/wtype", *original])
        self.sleep.assert_not_called()
        self.assertFalse(any(call.args[0][1] == "eval" for call in self.run.call_args_list))

    def test_hex_signature_is_exact_prior_adapter_sequence(self):
        expected = [part for code in range(0x2460, 0x248E) for part in ("-p", f"U{code:04X}")]
        expected += ["-M", "ctrl", "-k", "v", "-m", "ctrl", "-p", "VoidSymbol"]
        self.assertEqual(adapter.HEX_ARGS, expected)

    def test_arbitrary_and_near_match_calls_do_not_inspect_focus(self):
        variants = [[], ["hello"], ["-M", "ctrl", "-k", "v", "-m", "ctrl"],
                    adapter.HEX_ARGS[:-1], adapter.HEX_ARGS + ["extra"],
                    ["-P", *adapter.HEX_ARGS[1:]]]
        for args in variants:
            with self.subTest(args=args):
                self.execv.reset_mock()
                self.assert_fallback(args)
                self.run.assert_not_called()
                self.readlink.assert_not_called()
                self.read_bytes.assert_not_called()

    def test_feature_requires_literal_one(self):
        for value in (None, "", "0", "true", "01"):
            with self.subTest(value=value):
                if value is None:
                    os.environ.pop("HEX_GLIFF_PASTE", None)
                else:
                    os.environ["HEX_GLIFF_PASTE"] = value
                self.execv.reset_mock()
                self.assert_fallback()
                self.run.assert_not_called()

    def test_verified_focus_and_proc(self):
        self.assertEqual(adapter.focused_gliff(), self.window)
        self.run.assert_called_once_with(
            ["hyprctl", "-j", "activewindow"], capture_output=True,
            text=True, timeout=0.5, check=True,
        )
        self.readlink.assert_called_once_with(Path("/proc/1234/exe"))
        self.read_bytes.assert_called_once_with()

    def test_class_and_title_guards(self):
        for key, value in (("class", "kitty"), ("class", "gliff-other"),
                           ("class", None), ("title", "other — Gliff"),
                           ("title", "omarchy-vm — Gliff extra"), ("title", None)):
            with self.subTest(key=key, value=value):
                self.run.return_value.stdout = json.dumps(dict(self.window, **{key: value}))
                self.execv.reset_mock()
                self.assert_fallback()
                self.readlink.assert_not_called()

    def test_invalid_window_identity(self):
        for key, value in (("pid", None), ("pid", "1234"), ("pid", True),
                           ("pid", 0), ("pid", -1), ("pid", 1.5),
                           ("address", None), ("address", ""),
                           ("address", "0x0"), ("address", '0x1"; evil()')):
            with self.subTest(key=key, value=value):
                self.run.return_value.stdout = json.dumps(dict(self.window, **{key: value}))
                self.execv.reset_mock()
                self.assert_fallback()
                self.readlink.assert_not_called()

    def test_executable_guard_precedes_cmdline_read(self):
        for exe in ("/tmp/gliff", "/usr/bin/other", "/usr/bin/gliff (deleted)"):
            with self.subTest(exe=exe):
                self.readlink.return_value = exe
                self.execv.reset_mock()
                self.assert_fallback()
                self.read_bytes.assert_not_called()

    def test_endpoint_must_be_an_exact_argument_not_a_substring_or_argv_zero(self):
        for command in (b"/usr/bin/gliff\0other\0", b"/usr/bin/gliff\0other-omarchy-vm\0",
                        b"/usr/bin/gliff\0--host=omarchy-vm\0", b"omarchy-vm\0", b""):
            with self.subTest(command=command):
                self.read_bytes.return_value = command
                self.execv.reset_mock()
                self.assert_fallback()

    def test_other_arguments_are_allowed_with_exact_endpoint(self):
        self.read_bytes.return_value = b"/usr/bin/gliff\0--fullscreen\0omarchy-vm\0"
        self.assertEqual(adapter.focused_gliff(), self.window)

    def test_malformed_json_and_non_objects_fall_back(self):
        for stdout in ("not JSON", "", "null", "[]", '"gliff"', "123", "{}"):
            with self.subTest(stdout=stdout):
                self.run.return_value.stdout = stdout
                self.execv.reset_mock()
                self.assert_fallback()

    def test_missing_identity_fields_fall_back(self):
        for key in self.window:
            with self.subTest(key=key):
                window = dict(self.window)
                del window[key]
                self.run.return_value.stdout = json.dumps(window)
                self.execv.reset_mock()
                self.assert_fallback()

    def test_focus_command_failure_and_timeout_fall_back(self):
        for error in (FileNotFoundError(), subprocess.CalledProcessError(1, "hyprctl"),
                      subprocess.TimeoutExpired("hyprctl", 0.5)):
            with self.subTest(error=error):
                self.run.side_effect = error
                self.execv.reset_mock()
                self.assert_fallback()

    def test_missing_or_unreadable_proc_falls_back(self):
        for target in (self.readlink, self.read_bytes):
            for error in (FileNotFoundError(), PermissionError(), ProcessLookupError()):
                with self.subTest(target=target, error=error):
                    target.side_effect = error
                    self.execv.reset_mock()
                    self.assert_fallback()
                    target.side_effect = None

    def test_native_dispatch_revalidates_before_exact_key_sequence(self):
        self.run.side_effect = [self.run.return_value, subprocess.CompletedProcess([], 0, "ok\n", "")]
        self.assertEqual(self.invoke(), 0)
        self.execv.assert_not_called()
        self.assertEqual(self.run.call_count, 2)
        call = self.run.call_args
        self.assertEqual(call.args[0][:2], ["hyprctl", "eval"])
        self.assertEqual(call.kwargs, dict(capture_output=True, text=True, timeout=1.0, check=True))
        lua = call.args[0][2]
        first_dispatch = lua.index("hl.dispatch")
        for guard in ('hl.get_active_window()', 'window.address == "0x123abc"',
                      'window.pid == 1234', 'window.title == "omarchy-vm — Gliff"'):
            self.assertLess(lua.index(guard), first_dispatch)
        sequence = [
            'hl.dispatch(hl.dsp.send_key_state({mods="",key="Control_L",state="down"}))',
            'hl.dispatch(hl.dsp.send_key_state({mods="CTRL",key="V",state="down"}))',
            'hl.timer(function()',
            'hl.dispatch(hl.dsp.send_key_state({mods="CTRL",key="V",state="up"}))',
            'hl.dispatch(hl.dsp.send_key_state({mods="",key="Control_L",state="up"}))',
            'end,{timeout=50,type="oneshot"})',
        ]
        positions = [lua.index(part) for part in sequence]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(lua.count("hl.dispatch"), 4)
        self.sleep.assert_called_once_with(0.1)

    def test_native_failures_never_fall_back_or_retry(self):
        failures = [FileNotFoundError(), subprocess.CalledProcessError(1, "hyprctl"),
                    subprocess.TimeoutExpired("hyprctl", 1.0)]
        for failure in failures:
            with self.subTest(failure=failure):
                self.run.reset_mock()
                self.sleep.reset_mock()
                self.run.side_effect = [subprocess.CompletedProcess([], 0, json.dumps(self.window), ""), failure]
                self.assertNotEqual(self.invoke(), 0)
                self.execv.assert_not_called()
                self.assertEqual(self.run.call_count, 2)
                self.sleep.assert_called_once_with(0.1)

    def test_eval_error_text_is_failure_even_with_zero_exit_status(self):
        for stdout in ("", "Lua error: focus changed", "unknown request", "ok\nerror"):
            with self.subTest(stdout=stdout):
                self.run.side_effect = [subprocess.CompletedProcess([], 0, json.dumps(self.window), ""),
                                        subprocess.CompletedProcess([], 0, stdout, "")]
                self.assertNotEqual(self.invoke(), 0)
                self.execv.assert_not_called()


if __name__ == "__main__":
    unittest.main()
