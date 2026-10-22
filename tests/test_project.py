import importlib.util
import json
import re
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'scripts'))
import service
import provision
from provision import haproxy_config, write


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.client = service.app.test_client()
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.db = patch.object(service, 'connect', return_value=self.connection)
        self.db.start()
        self.cache_patch = patch.object(service, 'cache')
        self.cache = self.cache_patch.start()
        self.cache.get.return_value = None
        self.env = patch.dict(os.environ, {'CACHE_ENABLED': '1'})
        self.env.start()
        self.addCleanup(self.db.stop)
        self.addCleanup(self.cache_patch.stop)
        self.addCleanup(self.env.stop)

    def test_info(self):
        self.assertEqual(self.client.get('/info').status_code, 200)
        self.assertIn('hostname', self.client.get('/info').json)
    
    def test_info_reports_release_used_by_e4(self):
        with patch.dict(os.environ, {'RELEASE': '2'}):
            self.assertEqual(self.client.get('/info').json['release'], '2')

    def test_unknown_route_returns_json(self):
        response = self.client.get('/inconnu')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {'error': 'not_found'})

    def test_wrong_method_returns_json(self):
        response = self.client.post('/resultat?matricule=000001')
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json, {'error': 'method_not_allowed'})


    def test_health_requires_real_query_and_closes_connection(self):
        self.assertEqual(self.client.get('/sante').status_code, 200)
        self.cursor.execute.assert_called_once_with('SELECT 1')
        self.connection.close.assert_called_once()
        self.cache.get.assert_not_called()

    def test_health_database_failure_has_no_raw_exception(self):
        service.connect.side_effect = service.psycopg2.OperationalError('secret detail')
        response = self.client.get('/sante')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', response.get_data(as_text=True))

    def test_undecodable_database_error_returns_503(self):
        service.connect.side_effect = UnicodeDecodeError('utf-8', b'\xe9', 0, 1, 'invalid')
        self.assertEqual(self.client.get('/sante').status_code, 503)
        response = self.client.get('/resultat?matricule=000001')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json, {'error': 'database_unavailable'})
    
    def test_query_error_closes_connection(self):
        self.cursor.execute.side_effect = service.psycopg2.OperationalError('bad SQL')
        self.assertEqual(self.client.get('/sante').status_code, 503)
        self.connection.close.assert_called_once()

    def test_invalid_matricule_rejected_before_database(self):
        for value in ['', '1', "000001' OR 1=1--", '1234567', 'abcdef']:
            self.assertEqual(self.client.get('/resultat', query_string={'matricule': value}).status_code, 400)
        service.connect.assert_not_called()

    def test_result_uses_parameterized_query(self):
        self.cursor.fetchone.return_value = ('000001', 'Candidate 1', 'C', 12.5, True)
        response = self.client.get('/resultat?matricule=000001')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['moyenne'], 12.5)
        self.assertEqual(self.cursor.execute.call_args.args[1], ('000001',))
        self.connection.close.assert_called_once()
        self.assertEqual(self.cache.setex.call_args.args[1], 30)

    def test_missing_candidate(self):
        self.cursor.fetchone.return_value = None
        self.assertEqual(self.client.get('/resultat?matricule=999999').status_code, 404)
        self.cache.setex.assert_not_called()

    def test_cache_hit_skips_database(self):
        self.cache.get.return_value = '{"matricule":"000001"}'
        self.assertEqual(self.client.get('/resultat?matricule=000001').status_code, 200)
        service.connect.assert_not_called()

    def test_redis_unavailable_falls_back_to_database(self):
        self.cache.get.side_effect = service.redis.RedisError('unavailable')
        self.cache.setex.side_effect = service.redis.RedisError('unavailable')
        self.cursor.fetchone.return_value = ('000001', 'Candidate 1', 'C', 12.5, True)
        self.assertEqual(self.client.get('/resultat?matricule=000001').status_code, 200)
        service.connect.assert_called_once()

    def test_cache_disabled(self):
        os.environ['CACHE_ENABLED'] = '0'
        self.cursor.fetchone.return_value = ('000001', 'Candidate 1', 'C', 12.5, True)
        self.assertEqual(self.client.get('/resultat?matricule=000001').status_code, 200)
        self.cache.get.assert_not_called()
        self.cache.setex.assert_not_called()

    def test_database_failure_on_miss(self):
        service.connect.side_effect = service.psycopg2.OperationalError('password=secret')
        response = self.client.get('/resultat?matricule=000001')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json, {'error': 'database_unavailable'})


class InfrastructureTests(unittest.TestCase):
    def topology(self, count=2, octet=56):
        env = dict(os.environ, NB_APP=str(count), NETWORK_OCTET=str(octet))
        return subprocess.run(['ruby', str(ROOT / 'config/topology.rb')], env=env,
                              capture_output=True, text=True)

    def test_base_memory_and_unique_addresses(self):
        data = json.loads(self.topology().stdout)
        self.assertEqual(len(data['nodes']), 5)
        self.assertEqual(sum(n['memory'] for n in data['nodes']), 3072)
        self.assertEqual(len({n['ip'] for n in data['nodes']}), 5)

    def test_scaling_uses_same_nodes_for_load_balancer(self):
        for count in (2, 4, 8):
            data = json.loads(self.topology(count).stdout)
            config = haproxy_config(data['nodes'])
            lines = [line for line in config.splitlines() if line.strip().startswith('server ')]
            self.assertEqual(len(lines), count)
            for node in data['nodes']:
                if node['role'] == 'app':
                    self.assertIn(f"server {node['name']} {node['ip']}:8000", config)
            self.assertIn('option httpchk GET /sante', config)
            self.assertIn('fall 2', config)
    def test_health_check_timing_evicts_server_within_five_seconds(self):
        nodes = json.loads(self.topology().stdout)['nodes']
        config = haproxy_config(nodes)
        check_timeout = float(re.search(r'timeout check (\d+)s', config).group(1))
        for line in config.splitlines():
            if line.strip().startswith('server '):
                inter = float(re.search(r'inter (\d+)s', line).group(1))
                fastinter = float(re.search(r'fastinter (\d+)ms', line).group(1)) / 1000
                fall = int(re.search(r'fall (\d+)', line).group(1))
                worst_case = inter + fall * (fastinter + check_timeout)
                self.assertLess(worst_case, 5, line)
    
    def test_invalid_network_and_count_fail(self):
        for count, octet in [(1,56),(9,56),(2,65),(2,55)]:
            self.assertNotEqual(self.topology(count,octet).returncode, 0)

    def test_configuration_write_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'config'
            self.assertTrue(write(file, 'expected\n', 0o600))
            stamp = file.stat().st_mtime_ns
            self.assertFalse(write(file, 'expected\n', 0o600))
            self.assertEqual(file.stat().st_mtime_ns, stamp)
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_service_under_100_lines(self):
        self.assertLess(len((ROOT / 'app/service.py').read_text().splitlines()), 100)

    def test_postgresql_access_rules_are_always_reloaded(self):
        with patch.object(provision, 'run') as run, \
             patch.object(provision, 'sql', return_value='0') as sql:
            provision.reload_postgresql_access_rules()
        run.assert_called_once_with('systemctl', 'reload', 'postgresql@16-main')
        sql.assert_called_once_with(
            'SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;')

    def test_invalid_postgresql_access_rules_stop_provisioning(self):
        with patch.object(provision, 'run'), \
             patch.object(provision, 'sql', return_value='1'):
            with self.assertRaisesRegex(SystemExit, 'rejected'):
                provision.reload_postgresql_access_rules()


class OperationSafetyTests(unittest.TestCase):
    def test_promotion_refuses_running_or_saved_primary(self):
        import ops
        for state in ('running', 'saved', 'not_created'):
            with patch.object(ops, 'run', return_value=f'0,bdd1,state,{state}'), \
                 patch.object(ops, 'remote') as remote:
                with self.assertRaisesRegex(RuntimeError, 'Fence bdd1 first'):
                    ops.promote()
                remote.assert_not_called()

    def test_rebuild_requires_explicit_destructive_flag(self):
        import ops
        with patch.object(ops, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'confirm-destroy'):
                ops.rebuild(False)
            run.assert_not_called()

    def test_rollout_refuses_to_remove_only_healthy_backend(self):
        import ops
        nodes = [{'name': 'app1', 'role': 'app'}, {'name': 'app2', 'role': 'app'}]
        with patch.object(ops, 'inventory', return_value={'nodes': nodes}), \
             patch.object(ops, 'backend', return_value={'status': 'DOWN'}), \
             patch.object(ops, 'runtime') as runtime:
            with self.assertRaisesRegex(RuntimeError, 'No other healthy backend'):
                ops.rolling('2')
            runtime.assert_not_called()


class AddressConflictTests(unittest.TestCase):
    NODES = [{'name': 'bdd1', 'ip': '192.168.56.31'}, {'name': 'bdd2', 'ip': '192.168.56.32'},
             {'name': 'lb1', 'ip': '192.168.56.11'}]

    def test_guest_addresses_reads_guest_additions_properties(self):
        import ops
        net = '/VirtualBox/GuestInfo/Net/'
        outputs = {
            ('list', 'runningvms'): '"old_bdd1" {aaaa-1}\n"no additions" {bbbb-2}\n',
            ('guestproperty', 'get', 'aaaa-1', net + 'Count'): 'Value: 2\n',
            ('guestproperty', 'get', 'aaaa-1', net + '0/V4/IP'): 'Value: 10.0.2.15\n',
            ('guestproperty', 'get', 'aaaa-1', net + '1/V4/IP'): 'Value: 192.168.56.31\n',
            ('guestproperty', 'get', 'bbbb-2', net + 'Count'): 'No value set!\n',
        }
        with patch.object(ops, 'run', side_effect=lambda *args, capture: outputs[args[1:]]):
            self.assertEqual(ops.guest_addresses(), {
                ('old_bdd1', 'aaaa-1'): {'10.0.2.15', '192.168.56.31'},
                ('no additions', 'bbbb-2'): set()})

    def test_only_vms_outside_project_are_conflicts(self):
        import ops
        guests = {('resultats_bdd1', 'project-1'): {'192.168.56.31'},
                  ('old_bdd2', 'stale-2'): {'10.0.2.15', '192.168.56.32'},
                  ('unrelated', 'other-3'): {'192.168.57.31'}}
        conflicts = ops.address_conflicts(self.NODES, guests, {'project-1'})
        self.assertEqual(conflicts, ['bdd2 192.168.56.32 is already used by VirtualBox VM "old_bdd2" (stale-2)'])

    def test_project_vm_ids_come_from_vagrant_state(self):
        import ops
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(ops.project_vm_ids(root), set())
            for name, uuid in (('bdd1', 'uuid-1'), ('lb1', 'uuid-2')):
                (root / '.vagrant/machines' / name / 'virtualbox').mkdir(parents=True)
                (root / '.vagrant/machines' / name / 'virtualbox/id').write_text(uuid + '\n')
            self.assertEqual(ops.project_vm_ids(root), {'uuid-1', 'uuid-2'})

    def test_preflight_stops_on_address_conflict(self):
        import ops
        with patch.object(ops.shutil, 'which', return_value='/usr/bin/tool'), \
             patch.object(ops.subprocess, 'run'), patch.object(ops, 'run'), \
             patch.object(ops, 'inventory', return_value={'nodes': self.NODES, 'subnet': '192.168.56.0/24'}), \
             patch.object(ops, 'guest_addresses', return_value={('old_bdd1', 'stale'): {'192.168.56.31'}}), \
             patch.object(ops, 'project_vm_ids', return_value=set()), \
             patch('builtins.print') as output:
            with self.assertRaisesRegex(SystemExit, 'address conflict'):
                ops.preflight()
        output.assert_any_call('Address conflict:',
                               'bdd1 192.168.56.31 is already used by VirtualBox VM "old_bdd1" (stale)')


if __name__ == '__main__':
    unittest.main()
