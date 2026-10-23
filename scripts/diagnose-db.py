#!/usr/bin/env python3
"""Operator-run, read-only database diagnosis; credentials are redacted.

Each database node is first inspected locally (service, role, replication
stream, replication slot). Each application node then reports how it reaches
the hosts listed in DB_HOSTS. Application nodes come from the shared inventory,
so the diagnosis follows NB_APP instead of naming machines in the code.
"""
import argparse
import json
import subprocess

from ops import inventory, remote, save

APP_CODE = r'''
import json
from pathlib import Path
import psycopg2
values = dict(line.split('=', 1) for line in Path('/etc/resultats/app.env').read_text().splitlines()
              if line and not line.startswith('#'))
secrets = [value for key, value in values.items() if 'PASSWORD' in key and value]
def redact(message):
    for secret in secrets:
        message = message.replace(secret, '[REDACTED]')
    return message
report = {'configured_hosts': values.get('DB_HOSTS'), 'checks': []}
for host in values['DB_HOSTS'].split(','):
    connection = None
    entry = {'host': host}
    try:
        connection = psycopg2.connect(host=host, dbname='resultats', user='resultats_app',
            password=values['DB_PASSWORD'], connect_timeout=3,
            options='-c statement_timeout=1500', target_session_attrs='read-write')
        with connection.cursor() as cursor:
            cursor.execute('SELECT inet_server_addr()::text, pg_is_in_recovery()')
            entry['server_ip'], entry['in_recovery'] = cursor.fetchone()
        entry['writable_connection'] = True
    except psycopg2.Error as error:
        entry['writable_connection'] = False
        entry['error'] = redact(str(error)).strip()
    finally:
        if connection is not None:
            connection.close()
    report['checks'].append(entry)
print(json.dumps(report))
'''

DB_CODE = r'''
import json
import subprocess
def sql(query):
    return subprocess.run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-At', '-d', 'resultats',
                           '-c', query], capture_output=True, text=True, timeout=10)
def rows(query):
    return [line for line in sql(query).stdout.splitlines() if line]
report = {'reachable': True}
report['service'] = subprocess.run(['systemctl', 'is-active', 'postgresql@16-main'],
                                   capture_output=True, text=True).stdout.strip()
role = sql('SELECT pg_is_in_recovery();')
if role.returncode != 0:
    report['error'] = role.stderr.strip()[:200]
else:
    report['in_recovery'] = role.stdout.strip() == 't'
    if report['in_recovery']:
        report['wal_receiver'] = rows('SELECT status, sender_host FROM pg_stat_wal_receiver;')
    else:
        report['replicas'] = rows('SELECT client_addr, state, replay_lag FROM pg_stat_replication;')
        report['slots'] = rows('SELECT slot_name, active, wal_status FROM pg_replication_slots;')
print(json.dumps(report))
'''


def guarded(node, code):
    """A halted VM is a diagnosis result, not a crash of the diagnostic."""
    try:
        return json.loads(remote(node, code))
    except subprocess.CalledProcessError:
        return {'reachable': False}
    except json.JSONDecodeError:
        return {'reachable': True, 'error': 'unreadable diagnostic output'}


def app_nodes(topology, requested=None):
    names = [n['name'] for n in topology['nodes'] if n['role'] == 'app']
    if not requested:
        return names
    unknown = sorted(set(requested) - set(names))
    if unknown:
        raise SystemExit('Unknown application node: ' + ', '.join(unknown))
    return list(requested)


def verdict(databases):
    writable = sorted(name for name, state in databases.items() if state.get('in_recovery') is False)
    if not writable:
        return writable, 'no writable database: /sante returns 503 until a primary is available'
    if len(writable) > 1:
        return writable, 'more than one writable database: split brain, stop one immediately'
    return writable, 'one writable database: ' + writable[0]


def diagnose(requested=None):
    topology = inventory()
    report = {'databases': {}, 'applications': {}}
    for node in topology['nodes']:
        if node['role'] in ('primary', 'replica'):
            report['databases'][node['name']] = guarded(node['name'], DB_CODE)
    for name in app_nodes(topology, requested):
        report['applications'][name] = guarded(name, APP_CODE)
    report['writable_databases'], report['verdict'] = verdict(report['databases'])
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nodes', nargs='*', help='application nodes to test (default: all of them)')
    args = parser.parse_args()
    result = diagnose(args.nodes)
    print(json.dumps(result, indent=2))
    save('database-connectivity', result)
