#!/usr/bin/env python3
"""Operator-run, read-only database connectivity comparison; credentials are redacted."""
import json
from ops import remote, save

CODE = r'''
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

if __name__ == '__main__':
    report = {}
    for node in ('app3', 'app4'):
        report[node] = json.loads(remote(node, CODE))
    print(json.dumps(report, indent=2))
    save('database-connectivity', report)
