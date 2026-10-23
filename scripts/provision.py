#!/usr/bin/env python3
"""Idempotent guest provisioning. Run only inside a project VM as root."""
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import sys


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def write(path, text, mode=0o644, owner=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    changed = not path.exists() or path.read_text() != text
    if changed:
        temp = path.with_suffix(path.suffix + '.new')
        temp.write_text(text)
        temp.chmod(mode)
        temp.replace(path)
    path.chmod(mode)
    if owner:
        account = pwd.getpwnam(owner)
        os.chown(path, account.pw_uid, account.pw_gid)
    return changed


def sql(statement, database='postgres'):
    return run('runuser', '-u', 'postgres', '--', 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
               '-At', '-d', database, input=statement, capture_output=True).stdout.strip()


def reload_postgresql_access_rules():
    """Reconcile PostgreSQL's in-memory HBA rules with the generated file.

    A previous provisioning run may have written pg_hba.conf and then been
    interrupted before PostgreSQL reloaded it. Reload unconditionally so an
    unchanged file cannot leave stale access rules active.
    """
    run('systemctl', 'reload', 'postgresql@16-main')
    errors = sql('SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;')
    if errors != '0':
        raise SystemExit('PostgreSQL rejected one or more generated access rules.')


def haproxy_config(nodes):
    servers = '\n'.join(f"    server {n['name']} {n['ip']}:8000 check inter 1s fastinter 500ms fall 2 rise 2"
                        for n in nodes if n['role'] == 'app')
    return '''global
    log /dev/log local0
    user haproxy
    group haproxy
    daemon
    stats socket /run/haproxy/admin.sock mode 600 level admin
    maxconn 1024

defaults
    log global
    mode http
    timeout connect 1s
    timeout client 10s
    timeout server 10s
    timeout check 1s

frontend public
    bind 0.0.0.0:80
    # Without any healthy server, answer like the application does: JSON 503.
    http-request return status 503 content-type application/json string '{"error":"service_unavailable"}' if { nbsrv(apps) eq 0 }
    default_backend apps

backend apps
    balance roundrobin
    option http-server-close
    option httpchk GET /sante
    http-check expect status 200
''' + servers + '\n'


def main():
    if os.geteuid() != 0:
        raise SystemExit('Guest root privileges required.')
    upload = Path('/home/vagrant/resultats-upload')
    topology = json.loads((upload / 'inventory.json').read_text())
    secrets = json.loads((upload / 'secrets.json').read_text())
    nodes = topology['nodes']
    node = next(n for n in nodes if n['name'] == sys.argv[1])
    role = node['role']
    expected = {'primary': ['DB_PASSWORD', 'REPLICATION_PASSWORD'],
                'replica': ['REPLICATION_PASSWORD'], 'app': ['DB_PASSWORD', 'REDIS_PASSWORD'],
                'lb': ['REDIS_PASSWORD']}[role]
    if any(not re.fullmatch('[0-9a-f]{32,}', secrets.get(k, '')) for k in expected):
        raise SystemExit('Missing secrets: run scripts/setup.py on the host first.')
    primary = next(n['ip'] for n in nodes if n['role'] == 'primary')
    replica = next(n['ip'] for n in nodes if n['role'] == 'replica')
    lb = next(n['ip'] for n in nodes if n['role'] == 'lb')
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    # Reuse downloaded packages through the primary, with direct fallback if fenced.
    proxy = Path('/etc/apt/apt.conf.d/02resultats-proxy')
    if role != 'primary':
        try:
            with socket.create_connection((primary, 3142), timeout=1):
                pass
            write(proxy, f'Acquire::http::Proxy "http://{primary}:3142";\n')
        except OSError:
            proxy.unlink(missing_ok=True)
    packages = {'primary': ['postgresql-16', 'apt-cacher-ng'],
                'replica': ['postgresql-16'],
                'app': ['python3-flask', 'python3-psycopg2', 'python3-redis', 'gunicorn'],
                'lb': ['haproxy', 'redis-server', 'python3-redis']}[role]
    missing = [p for p in packages if subprocess.run(
        ['dpkg-query', '-W', '-f=${Status}', p], capture_output=True, text=True).stdout != 'install ok installed']
    if missing:
        run('apt-get', 'update', '-o', 'Acquire::Retries=3')
        run('apt-get', 'install', '-y', '--no-install-recommends', *missing)
    write('/etc/resultats/inventory.json', json.dumps(topology, indent=2) + '\n')
    if role == 'primary':
        changed = write('/etc/apt-cacher-ng/zz-resultats.conf',
                        f'BindAddress: 127.0.0.1 {primary}\nPort: 3142\n')
        run('systemctl', 'enable', '--now', 'apt-cacher-ng')
        if changed:
            run('systemctl', 'restart', 'apt-cacher-ng')
    if role in ('primary', 'replica'):
        conf = '/etc/postgresql/16/main'
        changed = write(conf + '/conf.d/resultats.conf', f"""listen_addresses = '127.0.0.1,{node['ip']}'
wal_level = replica
max_wal_senders = 5
max_replication_slots = 5
wal_keep_size = '128MB'
max_slot_wal_keep_size = '256MB'
shared_buffers = '128MB'
max_connections = 100
hot_standby = on
password_encryption = 'scram-sha-256'
""")
        hba = 'local all postgres peer\nlocal all all peer\n'
        hba += 'host all all 127.0.0.1/32 scram-sha-256\n'
        hba += f'host replication replicator {replica}/32 scram-sha-256\n'
        hba += ''.join(f"host resultats resultats_app {n['ip']}/32 scram-sha-256\n"
                       for n in nodes if n['role'] == 'app')
        changed = write(conf + '/pg_hba.conf', hba, 0o640, 'postgres') or changed
        if role == 'primary':
            run('systemctl', 'enable', '--now', 'postgresql')
            run('systemctl', 'start', 'postgresql@16-main')
            if changed:
                run('systemctl', 'restart', 'postgresql@16-main')
            if sql('SELECT pg_is_in_recovery();') != 'f':
                raise SystemExit('Refusing to seed a standby.')
            for name, attribute, key in [('resultats_app', 'LOGIN', 'DB_PASSWORD'),
                                         ('replicator', 'LOGIN REPLICATION', 'REPLICATION_PASSWORD')]:
                sql(f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{name}') "
                    f"THEN CREATE ROLE {name} {attribute} PASSWORD '{secrets[key]}'; END IF; END $$;")
            if sql("SELECT 1 FROM pg_database WHERE datname='resultats';") != '1':
                run('runuser', '-u', 'postgres', '--', 'createdb', 'resultats')
            sql('''CREATE TABLE IF NOT EXISTS resultats (
                matricule text PRIMARY KEY, nom text NOT NULL, serie text NOT NULL,
                moyenne numeric(4,2) NOT NULL, admis boolean NOT NULL);
                INSERT INTO resultats
                SELECT lpad(g::text,6,'0'), 'Candidate ' || g,
                       (ARRAY['A','C','D'])[1+(g%3)], (g%2001)/100.0, g%2001>=1000
                FROM generate_series(1,50000) g ON CONFLICT (matricule) DO NOTHING;
                GRANT CONNECT ON DATABASE resultats TO resultats_app;
                GRANT USAGE ON SCHEMA public TO resultats_app;
                GRANT SELECT ON resultats TO resultats_app;''', 'resultats')
            if sql("SELECT 1 FROM pg_replication_slots WHERE slot_name='bdd2_slot';") != '1':
                sql("SELECT pg_create_physical_replication_slot('bdd2_slot');")
        else:
            write('/var/lib/postgresql/.pgpass',
                  f"{primary}:5432:replication:replicator:{secrets['REPLICATION_PASSWORD']}\n", 0o600, 'postgres')
            marker = Path('/var/lib/postgresql/resultats-replica-initialized')
            data = Path('/var/lib/postgresql/16/main')
            if not marker.exists():
                # Archive the original distribution-created cluster; never erase an existing project DB.
                if (data / 'standby.signal').exists():
                    raise SystemExit('Standby exists without marker; inspect before retrying.')
                run('systemctl', 'stop', 'postgresql@16-main')
                staging = Path('/var/lib/postgresql/16/resultats-basebackup')
                if staging.exists():
                    shutil.rmtree(staging)
                run('runuser', '-u', 'postgres', '--', 'env', 'PGPASSFILE=/var/lib/postgresql/.pgpass',
                    'pg_basebackup', '-d', f'host={primary} user=replicator passfile=/var/lib/postgresql/.pgpass',
                    '-D', str(staging), '-R', '-X', 'stream', '-S', 'bdd2_slot', '-w')
                if data.exists():
                    data.rename(data.with_name('distribution-cluster'))
                staging.rename(data)
                write(marker, 'initialized\n', 0o600, 'postgres')
                changed = True
            # A promoted replica is preserved by subsequent provisioning.
            run('systemctl', 'enable', '--now', 'postgresql')
            run('systemctl', 'start', 'postgresql@16-main')
            if changed:
                run('systemctl', 'restart', 'postgresql@16-main')
        reload_postgresql_access_rules()
    elif role == 'app':
        if subprocess.run(['id', '-u', 'resultats'], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode:
            run('useradd', '--system', '--home', '/opt/resultats', '--shell', '/usr/sbin/nologin', 'resultats')
        changed = write('/opt/resultats/service.py', (upload / 'service.py').read_text())
        env = {'DB_HOSTS': f'{primary},{replica}', 'DB_PASSWORD': secrets['DB_PASSWORD'],
               'REDIS_HOST': lb, 'REDIS_PASSWORD': secrets['REDIS_PASSWORD'],
               'CACHE_ENABLED': str(int(topology['cache_enabled'])), 'RELEASE': '1'}
        # Keep a release set by the rolling deployment script.
        old = Path('/etc/resultats/app.env')
        if old.exists():
            for line in old.read_text().splitlines():
                if line.startswith('RELEASE='):
                    env['RELEASE'] = line.split('=', 1)[1]
        changed = write(old, ''.join(f'{k}={v}\n' for k, v in env.items()), 0o600) or changed
        changed = write('/etc/systemd/system/resultats.service', '''[Unit]
Description=RESULTATS-BF API
After=network-online.target
Wants=network-online.target
[Service]
User=resultats
Group=resultats
WorkingDirectory=/opt/resultats
EnvironmentFile=/etc/resultats/app.env
ExecStart=/usr/bin/gunicorn --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 15 service:app
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
''') or changed
        run('systemctl', 'daemon-reload')
        run('systemctl', 'enable', '--now', 'resultats')
        if changed:
            run('systemctl', 'restart', 'resultats')
    else:
        changed = write('/etc/redis/redis.conf', f'''bind 127.0.0.1 {lb}
protected-mode yes
port 6379
requirepass {secrets['REDIS_PASSWORD']}
supervised systemd
daemonize no
logfile ""
dir /var/lib/redis
save ""
appendonly no
maxmemory 64mb
maxmemory-policy allkeys-lru
''', 0o640, 'redis')
        run('systemctl', 'enable', '--now', 'redis-server')
        if changed:
            run('systemctl', 'restart', 'redis-server')
        config = haproxy_config(nodes)
        candidate = '/etc/haproxy/resultats-candidate.cfg'
        write(candidate, config)
        run('haproxy', '-c', '-f', candidate)
        changed = write('/etc/haproxy/haproxy.cfg', config)
        Path(candidate).unlink()
        run('systemctl', 'enable', '--now', 'haproxy')
        if changed:
            run('systemctl', 'reload', 'haproxy')
    (upload / 'secrets.json').unlink(missing_ok=True)
    print(f"Configured {node['name']} ({role}).")


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        # Captured SQL can include secrets. Never print command inputs or stderr.
        print(f'Provisioning failed (exit {error.returncode}); inspect the relevant guest service.', file=sys.stderr)
        raise SystemExit(1)
