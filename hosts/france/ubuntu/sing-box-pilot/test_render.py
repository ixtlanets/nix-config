import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from render import render


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.state = {
            'nodes': [
                {'id': 'france', 'host': '194.87.166.59', 'port': 443,
                 'enabled': True, 'server_name': 'www.google.com',
                 'public_key': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
                 'short_id': 'abcd'},
                {'id': 'frankfurt', 'host': '31.58.85.163', 'port': 34443,
                 'enabled': True, 'server_name': 'www.google.com',
                 'public_key': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
                 'short_id': 'ef01'},
                {'id': 'poland', 'host': '193.124.205.153', 'port': 34443,
                 'enabled': True, 'server_name': 'www.google.com',
                 'public_key': 'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBA',
                 'short_id': '1234'},
                {'id': 'italy', 'host': '81.29.155.74', 'port': 34443,
                 'enabled': True, 'server_name': 'www.google.com',
                 'public_key': 'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCA',
                 'short_id': '5678'}],
            'devices': [
                {'id': 'first', 'enabled': True,
                 'credentials': {
                     'france': {'uuid': '11111111-1111-4111-8111-111111111111'},
                     'frankfurt': {'uuid': '22222222-2222-4222-8222-222222222222'},
                     'poland': {'uuid': '44444444-4444-4444-8444-444444444444'},
                     'italy': {'uuid': '55555555-5555-4555-8555-555555555555'}}},
                {'id': 'disabled', 'enabled': False, 'credentials': {}}]}
        self.keys = {
            node['id']: {'private_key': node['public_key'],
                         'public_key': node['public_key']}
            for node in self.state['nodes']}

    def test_exact_identity_and_disabled_device(self):
        for node in ['france', 'frankfurt', 'poland', 'italy']:
            with self.subTest(node=node):
                inbound = render(self.state, self.keys, node)['inbounds'][0]
                expected = next(n for n in self.state['nodes'] if n['id'] == node)
                self.assertEqual((inbound['listen'], inbound['listen_port']),
                                 (expected['host'], expected['port']))
                self.assertEqual(inbound['users'], [{
                    'name': 'first',
                    'uuid': self.state['devices'][0]['credentials'][node]['uuid'],
                    'flow': 'xtls-rprx-vision'}])
                self.assertEqual(inbound['tls']['reality']['private_key'],
                                 self.keys[node]['private_key'])
                rules = render(self.state, self.keys, node)['route']['rules']
                self.assertEqual(rules[0]['action'], 'resolve')
                self.assertEqual(rules[1], {'ip_is_private': True, 'action': 'reject'})
                self.assertEqual(rules[2]['ip_cidr'],
                                 ['100.64.0.0/10', '224.0.0.0/4',
                                  '240.0.0.0/4', 'ff00::/8'])

    def test_reject_endpoint_drift_and_mismatched_keys(self):
        drift = copy.deepcopy(self.state)
        drift['nodes'][0]['port'] = 24443
        with self.assertRaises(ValueError):
            render(drift, self.keys, 'france')
        keys = copy.deepcopy(self.keys)
        keys['france']['public_key'] = 'mismatch'
        with self.assertRaises(ValueError):
            render(self.state, keys, 'france')

    def test_new_node_rejects_endpoint_and_key_drift(self):
        for node in ('poland', 'italy'):
            for field, value in (('host', '203.0.113.1'), ('port', 443)):
                with self.subTest(node=node, field=field):
                    state = copy.deepcopy(self.state)
                    next(n for n in state['nodes'] if n['id'] == node)[field] = value
                    with self.assertRaises(ValueError):
                        render(state, self.keys, node)
            keys = copy.deepcopy(self.keys)
            keys[node]['public_key'] = 'mismatch'
            with self.assertRaises(ValueError):
                render(self.state, keys, node)
        state = copy.deepcopy(self.state)
        state['nodes'].append(dict(state['nodes'][0], id='unknown'))
        with self.assertRaises(KeyError):
            render(state, self.keys, 'unknown')

    def test_cli_new_nodes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            state, keys = directory / 'state.json', directory / 'keys.json'
            state.write_text(json.dumps(self.state))
            keys.write_text(json.dumps(self.keys))
            for node in ('poland', 'italy'):
                output = directory / (node + '.json')
                command = ['python3', str(Path(__file__).with_name('render.py')),
                           '--state', str(state), '--keys', str(keys),
                           '--node', node, '--output', str(output)]
                result = subprocess.run(command, capture_output=True)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(json.loads(output.read_text()),
                                 render(self.state, self.keys, node))
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
                self.assertEqual(json.loads(output.read_text()),
                                 render(self.state, self.keys, node))

    def test_canary_distinct_and_domain_resolution_precedes_rejection(self):
        config = render(self.state, self.keys, 'france',
                        '33333333-3333-4333-8333-333333333333')
        self.assertEqual(len(config['inbounds'][0]['users']), 2)
        self.assertEqual(config['route']['rules'][0]['action'], 'resolve')
        self.assertEqual(config['route']['rules'][1],
                         {'ip_is_private': True, 'action': 'reject'})
        self.assertIn('100.64.0.0/10', config['route']['rules'][2]['ip_cidr'])
        with self.assertRaises(ValueError):
            render(self.state, self.keys, 'france',
                   self.state['devices'][0]['credentials']['france']['uuid'])

    @unittest.skipUnless(os.environ.get('SING_BOX_BIN'), 'Set SING_BOX_BIN for native validation')
    def test_real_core_accepts_all_sites(self):
        with tempfile.TemporaryDirectory() as directory:
            for node in ['france', 'frankfurt', 'poland', 'italy']:
                path = Path(directory) / (node + '.json')
                path.write_text(json.dumps(render(self.state, self.keys, node)))
                path.chmod(0o600)
                result = subprocess.run([os.environ['SING_BOX_BIN'], 'check', '-c', str(path)],
                                        capture_output=True)
                self.assertEqual(result.returncode, 0, 'Core rejected synthetic server config')


if __name__ == '__main__':
    unittest.main()
