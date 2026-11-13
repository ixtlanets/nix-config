#!/usr/bin/python3
"""TEST FIXTURE ONLY. Synthetic answers; every actual socket is loopback-only."""
import json
import os
import socket
import struct
import sys
import threading
import time


def exact(stream, count):
    data = b""
    while len(data) < count:
        part = stream.recv(count - len(data))
        if not part:
            raise EOFError
        data += part
    return data


def serve(control):
    with control:
        control.settimeout(4)
        try:
            if exact(control, 3) != b"\x05\x01\x00":
                return
            control.sendall(b"\x05\x00")
            header = exact(control, 4)
            if header != b"\x05\x03\x00\x01":
                return
            exact(control, 6)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.bind(("127.0.0.1", 0))
                udp.settimeout(4)
                control.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01" +
                                struct.pack("!H", udp.getsockname()[1]))
                packet, peer = udp.recvfrom(4096)
                # Verify that the TCP association is still open at query time.
                control.settimeout(0.02)
                try:
                    if control.recv(1, socket.MSG_PEEK) == b"":
                        return
                except TimeoutError:
                    pass
                query = packet[10:]
                answer = (query[:2] + b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" +
                          query[12:] + b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04\xc0\x00\x02\x50")
                udp.sendto(packet[:10] + answer, peer)
        except (OSError, EOFError):
            pass


def fake_curl():
    args = sys.argv[1:]
    proxy = args[args.index("--proxy") + 1]
    assert proxy.startswith("socks5h://127.0.0.1:")
    try:
        with socket.create_connection(("127.0.0.1", int(proxy.rsplit(":", 1)[1])), timeout=1) as stream:
            stream.sendall(b"\x05\x01\x00")
            assert exact(stream, 2) == b"\x05\x00"
    except OSError:
        print("000 0 0.001")
        return 7
    url = args[-1]
    if "api.ipify.org" in url:
        data = b'{"ip":"192.0.2.7"}'
    elif "cdn-cgi/trace" in url:
        data = b"ip=192.0.2.7\ntls=TLSv1.3\nh2=1\nloc=NOT-RETAINED\n"
    elif "speed.cloudflare.com" in url:
        data = b"x" * 1048576
    else:
        data = b"synthetic HTTPS response; no TLS or external request in fixture"
    with open(args[args.index("--output") + 1], "wb") as stream:
        stream.write(data)
    print("200", len(data), "0.001")
    return 0


def main():
    if "--disable" in sys.argv:
        return fake_curl()
    config = json.load(open(sys.argv[sys.argv.index("-c") + 1], encoding="utf-8"))
    assert config["inbounds"][0]["listen"] == "127.0.0.1"
    assert len(config["outbounds"]) == 1
    if sys.argv[1] == "check":
        return 0
    if sys.argv[1] == "run":
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", config["inbounds"][0]["listen_port"]))
            listener.listen(8)
            while True:
                control, _ = listener.accept()
                threading.Thread(target=serve, args=(control,), daemon=True).start()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
