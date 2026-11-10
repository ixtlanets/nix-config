#!/usr/bin/env python3
"""Exercise native PVE HTTPS/login and optionally a VM's noVNC WebSocket.

Run from an approved admin client. Credentials stay in process memory; output
never includes the API response body, ticket, CSRF token or password.
"""
import argparse
import base64
import hashlib
import http.client
import json
import secrets
import socket
import ssl
import struct
import subprocess
import urllib.parse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='pve.nikcode.xyz')
    parser.add_argument('--connect-address', help='Optional IP override; TLS still verifies --host')
    parser.add_argument('--port', type=int, default=443)
    parser.add_argument('--node', default='pve-um790')
    parser.add_argument('--vmid', type=int, help='Running VM for a real noVNC WebSocket check')
    parser.add_argument('--pass-name', default='machines/um790pro/proxmox')
    args = parser.parse_args()
    context = ssl.create_default_context()
    address = args.connect_address or args.host

    def tls_connect():
        raw = socket.create_connection((address, args.port), timeout=12)
        try:
            return context.wrap_socket(raw, server_hostname=args.host)
        except Exception:
            raw.close()
            raise

    with tls_connect() as connection:
        cert = connection.getpeercert()
        print('TLS: verified chain and hostname; expires', cert['notAfter'])

    def request(method, path, data=None, headers=None):
        conn = http.client.HTTPSConnection(args.host, args.port, context=context, timeout=12)
        conn.sock = tls_connect()
        payload = urllib.parse.urlencode(data) if data is not None else None
        merged = {'Host': args.host, **(headers or {})}
        if payload is not None:
            merged['Content-Type'] = 'application/x-www-form-urlencoded'
        try:
            conn.request(method, path, body=payload, headers=merged)
            response = conn.getresponse()
            body = response.read()
            if response.status != 200:
                raise RuntimeError(f'{method} {path.split("?")[0]}: HTTP {response.status}')
            return body
        finally:
            conn.close()

    assert b'Proxmox' in request('GET', '/'), 'Unexpected landing page'
    print('UI: HTTP 200')
    password = subprocess.check_output(['pass', 'show', args.pass_name], text=True).splitlines()[0]
    auth = json.loads(request('POST', '/api2/json/access/ticket', {
        'username': 'root@pam', 'password': password,
    }))['data']
    del password
    headers = {'Cookie': 'PVEAuthCookie=' + auth['ticket'],
               'CSRFPreventionToken': auth['CSRFPreventionToken']}
    status = json.loads(request('GET', f'/api2/json/nodes/{args.node}/status', headers=headers))['data']
    assert status['uptime'] > 0
    print('Login/API: authenticated node status OK')
    if args.vmid is None:
        return
    path = f'/api2/json/nodes/{args.node}/qemu/{args.vmid}'
    proxy = json.loads(request('POST', path + '/vncproxy', {'websocket': 1}, headers))['data']
    query = urllib.parse.urlencode({'port': proxy['port'], 'vncticket': proxy['ticket']})
    key = base64.b64encode(secrets.token_bytes(16)).decode()
    ws_headers = {
        'Host': args.host, 'Origin': 'https://' + args.host,
        'Upgrade': 'websocket', 'Connection': 'Upgrade',
        'Sec-WebSocket-Key': key, 'Sec-WebSocket-Version': '13',
        'Sec-WebSocket-Protocol': 'binary', 'Cookie': headers['Cookie'],
    }
    with tls_connect() as ws:
        wire = f'GET {path}/vncwebsocket?{query} HTTP/1.1\r\n'
        wire += ''.join(f'{k}: {v}\r\n' for k, v in ws_headers.items()) + '\r\n'
        ws.sendall(wire.encode('ascii'))
        reader = ws.makefile('rb')
        try:
            assert reader.readline().startswith(b'HTTP/1.1 101 '), 'WebSocket upgrade rejected'
            response_headers = {}
            while True:
                line = reader.readline()
                if line == b'\r\n':
                    break
                if not line:
                    raise RuntimeError('WebSocket headers incomplete')
                name, value = line.decode('ascii').split(':', 1)
                response_headers[name.lower()] = value.strip()
            expected = base64.b64encode(hashlib.sha1(
                (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            assert response_headers.get('sec-websocket-accept') == expected

            def read_exact(count):
                data = reader.read(count)
                if len(data) != count:
                    raise RuntimeError('Incomplete WebSocket frame')
                return data

            first, second = read_exact(2)
            assert first & 0x0f in (1, 2), 'Expected console data frame'
            assert not second & 0x80, 'Unexpected masked server frame'
            length = second & 0x7f
            if length == 126:
                length = struct.unpack('!H', read_exact(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', read_exact(8))[0]
            assert length <= 65536, 'Unexpected console banner size'
            banner = read_exact(length)
            assert banner.startswith(b'RFB '), 'Expected native VNC protocol greeting'
            print(f'noVNC: authenticated WebSocket 101 and RFB greeting OK (VM{args.vmid})')
        finally:
            reader.close()


if __name__ == '__main__':
    main()
