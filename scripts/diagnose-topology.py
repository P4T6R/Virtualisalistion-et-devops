#!/usr/bin/env python3
"""Read-only guest inventory, HBA and endpoint comparison; operator-run."""
import json
from ops import remote, save

DB_CODE = r'''
import json, subprocess
from pathlib import Path

def sql(query):
    return subprocess.check_output(['runuser','-u','postgres','--','psql','-X','-At',
        '-v','ON_ERROR_STOP=1','-d','resultats','-c',query],text=True).strip()

hba_path = sql('SHOW hba_file')
report = {
    'inventory': json.loads(Path('/etc/resultats/inventory.json').read_text()),
    'hba_path': hba_path,
    'hba_content': Path(hba_path).read_text(),
    'database_identity': sql("SELECT json_build_object('started',pg_postmaster_start_time(),"
                             "'database_oid',oid,'in_recovery',pg_is_in_recovery()) "
                             "FROM pg_database WHERE datname=current_database()"),
    'hba_parse_errors': sql("SELECT line_number,error FROM pg_hba_file_rules WHERE error IS NOT NULL"),
    'network': subprocess.check_output(['ip','-brief','address'],text=True),
    'links': subprocess.check_output(['ip','-brief','link'],text=True),
    'neighbors': subprocess.check_output(['ip','neighbor','show'],text=True)
}
print(json.dumps(report))
'''
APP_CODE = r'''
import json, psycopg2, subprocess
from pathlib import Path
values = dict(line.split('=',1) for line in Path('/etc/resultats/app.env').read_text().splitlines()
              if line and not line.startswith('#'))
report = {
    'network': subprocess.check_output(['ip','-brief','address'],text=True),
    'links': subprocess.check_output(['ip','-brief','link'],text=True),
    'neighbors': subprocess.check_output(['ip','neighbor','show'],text=True),
    'endpoints': []
}
for host in values['DB_HOSTS'].split(','):
    entry = {'host': host}
    connection = None
    try:
        connection = psycopg2.connect(host=host,dbname='resultats',user='resultats_app',
            password=values['DB_PASSWORD'],connect_timeout=3, options='-c statement_timeout=1500')
        with connection.cursor() as cursor:
            cursor.execute("SELECT json_build_object('started',pg_postmaster_start_time(),"
                           "'database_oid',oid,'in_recovery',pg_is_in_recovery()) "
                           "FROM pg_database WHERE datname=current_database()")
            entry['database_identity'] = cursor.fetchone()[0]
    except psycopg2.Error as error:
        message = str(error)
        for key,value in values.items():
            if 'PASSWORD' in key and value: message = message.replace(value,'[REDACTED]')
        entry['error'] = message.strip()
    finally:
        if connection is not None: connection.close()
    report['endpoints'].append(entry)
print(json.dumps(report))
'''
if __name__ == '__main__':
    report = {}
    for node in ('bdd1','bdd2','app3','app4'):
        report[node] = json.loads(remote(node, DB_CODE if node.startswith('bdd') else APP_CODE))
    print(json.dumps(report,indent=2))
    save('topology-diagnostic',report)
