#!/usr/bin/python3
"""Exercise the real local guard with isolated state and ephemeral TCP sockets."""
import errno
import os
from pathlib import Path
import runpy
import socket
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "hosts/omarchy-vm/dsh/dsh-vm"


class LocalPortGuard(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dsh-port-guard-")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)

    def guard(self, port):
        # Same literal port substitution as the lifecycle fixture. Never bind
        # production port 3080 or inspect real processes/state in this test.
        source = ENGINE.read_text()
        self.assertEqual(source.count('("127.0.0.1", 3080)'), 1,
                         "Refuse to run the guard without redirecting its production bind")
        source = source.replace(
            '("127.0.0.1", 3080)', '("127.0.0.1", ' + str(port) + ')')
        engine = self.home / "dsh-local"
        engine.write_text(source)
        with patch.dict(os.environ, HOME=str(self.home)):
            guard = runpy.run_path(str(engine))["local_guard"]
        original_iterdir = Path.iterdir

        def isolated_iterdir(path):
            if path == Path("/proc"):
                return iter(())
            return original_iterdir(path)

        with patch.object(Path, "iterdir", isolated_iterdir):
            guard()

    def test_server_time_wait_without_listener_allows_restart(self):
        # Node uses SO_REUSEADDR. Actively close the accepted server socket
        # first, then observe EOF on both ends, leaving server-side TIME_WAIT.
        with socket.socket() as server, socket.socket() as client:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", 0))
            port = server.getsockname()[1]
            server.listen()
            client.settimeout(2)
            client.connect(("127.0.0.1", port))
            accepted, _ = server.accept()
            with accepted:
                accepted.settimeout(2)
                accepted.shutdown(socket.SHUT_WR)
                self.assertEqual(client.recv(1), b"")
                client.close()
                self.assertEqual(accepted.recv(1), b"")

        with socket.socket() as probe:
            probe.settimeout(2)
            self.assertEqual(probe.connect_ex(("127.0.0.1", port)), errno.ECONNREFUSED)
        with socket.socket() as probe:
            with self.assertRaises(OSError) as busy:
                probe.bind(("127.0.0.1", port))
            self.assertEqual(busy.exception.errno, errno.EADDRINUSE)
        with socket.socket() as restart:
            restart.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            restart.bind(("127.0.0.1", port))
            restart.listen()
        try:
            self.guard(port)
        except RuntimeError as error:
            self.fail("No listener: connect_ex=ECONNREFUSED, plain bind=EADDRINUSE, "
                      "SO_REUSEADDR restart succeeded; actual local_guard rejected: " + str(error))

    def test_free_port_is_allowed(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        self.guard(port)

    def test_live_loopback_and_wildcard_listeners_are_rejected(self):
        for host in ("127.0.0.1", "0.0.0.0"):
            for reuse in (False, True):
                with self.subTest(host=host, reuse=reuse), socket.socket() as other:
                    other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, int(reuse))
                    other.bind((host, 0))
                    other.listen()
                    port = other.getsockname()[1]
                    with self.assertRaisesRegex(RuntimeError, "Competing listener"):
                        self.guard(port)

    def test_exclusive_bound_socket_is_rejected_without_listening(self):
        for host in ("127.0.0.1", "0.0.0.0"):
            with self.subTest(host=host), socket.socket() as other:
                other.bind((host, 0))
                port = other.getsockname()[1]
                with self.assertRaisesRegex(RuntimeError, "Competing listener"):
                    self.guard(port)

    def test_other_bind_errors_are_not_reported_as_competing_listeners(self):
        for code in (errno.EACCES, errno.EADDRNOTAVAIL, errno.EMFILE):
            with self.subTest(errno=errno.errorcode[code]):
                class BindFailure(socket.socket):
                    def bind(self, address):
                        raise OSError(code, os.strerror(code))

                with patch.object(socket, "socket", BindFailure):
                    with self.assertRaises(OSError) as error:
                        self.guard(12345)
                self.assertEqual(error.exception.errno, code)


if __name__ == "__main__":
    unittest.main()
