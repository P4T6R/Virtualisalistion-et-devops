#!/usr/bin/env python3
"""Operator-run lab operations and reproducible measurements (host Python 3)."""
import argparse
import base64
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
import datetime
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
URL = 'http://127.0.0.1:8080'


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def inventory():
    return json.loads(run('ruby', 'config/topology.rb', capture=True))


def remote(node, code):
    payload = base64.b64encode(code.encode()).decode()
    return run('vagrant', 'ssh', node, '-c',
               f'''sudo python3 -c "import base64; exec(base64.b64decode('{payload}'))"''', capture=True).strip()


def request(path='/sante', host=URL):
    try:
        with urllib.request.urlopen(host + path, timeout=6) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except (OSError, TimeoutError):
        return 0, ''


def wait_health(host=URL, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if request(host=host)[0] == 200:
            return
        time.sleep(0.5)
    raise RuntimeError(f'Health check timed out: {host}')


def runtime(command):
    return remote('lb1', f'''import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
s.connect('/run/haproxy/admin.sock')
s.sendall(({command!r} + '\\n').encode())
s.shutdown(socket.SHUT_WR)
data = b''
while True:
    part = s.recv(65536)
    if not part: break
    data += part
print(data.decode())
''')


def stats():
    return list(csv.DictReader(io.StringIO(runtime('show stat').lstrip('# '))))


def backend(name):
    return next(row for row in stats() if row['pxname'] == 'apps' and row['svname'] == name)


def log_path(name, suffix='json'):
    directory = ROOT / 'results'
    directory.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    return directory / f'{stamp}-{name}.{suffix}'


def save(name, data):
    path = log_path(name)
    path.write_text(json.dumps(data, indent=2) + '\n')
    print(path.relative_to(ROOT))


def preflight():
    failed = []
    for binary in ('vagrant', 'VBoxManage', 'ruby', 'python3', 'ab'):
        found = shutil.which(binary)
        print(f'{binary}: {found or "MISSING"}')
        if not found: failed.append(binary)
    if shutil.which('VBoxManage'):
        for args in [('list', 'hostonlyifs'), ('list', 'runningvms')]:
            try:
                subprocess.run(['VBoxManage', *args], check=True, timeout=20)
            except (subprocess.SubprocessError, OSError):
                failed.append('VirtualBox access')
    if not Path('/dev/vboxdrv').exists():
        failed.append('/dev/vboxdrv inaccessible')
    print('Provisional network:', inventory()['subnet'])
    print('Check existing guest addresses in VirtualBox before starting; no automatic network reassignment.')
    if shutil.which('free'): run('free', '-h')
    if not (ROOT / '.env').exists(): failed.append('.env: run scripts/setup.py')
    if failed: raise SystemExit('Resolve before launch: ' + ', '.join(failed))


def distribution():
    rows = []
    counts = Counter()
    for _ in range(20):
        status, body = request('/info')
        rows.append({'status': status, 'body': body})
        if status != 200: raise RuntimeError(f'/info returned {status}')
        counts[json.loads(body)['hostname']] += 1
    expected = {n['name'] for n in inventory()['nodes'] if n['role'] == 'app'}
    values = [counts[n] for n in expected]
    spread = (max(values) - min(values)) / (20 / len(values))
    passed = set(counts) == expected and spread < 0.2
    save('V1', {'responses': rows, 'counts': counts, 'relative_spread': spread, 'passed': passed})
    if not passed: raise RuntimeError('V1 distribution criterion failed')


def probe(seconds, workers, path):
    start = time.monotonic()
    end = start + seconds
    def worker(_):
        rows = []
        while time.monotonic() < end:
            before = time.monotonic()
            status, _ = request(path)
            rows.append((time.time(), before - start, time.monotonic() - before, status))
            time.sleep(0.05)
        return rows
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = [row for group in pool.map(worker, range(workers)) for row in group]
    rows.sort()
    path_out = log_path('probe', 'csv')
    with path_out.open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['unix_time', 'started_seconds', 'latency_seconds', 'status'])
        writer.writerows(rows)
    errors = [r for r in rows if r[3] != 200]
    save('probe-summary', {'csv': str(path_out.relative_to(ROOT)), 'requests': len(rows),
                          'errors': len(errors), 'last_error_started_seconds': errors[-1][1] if errors else None})


def benchmark(label):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', label): raise ValueError('Invalid label')
    wait_health()
    path = log_path(label, 'txt')
    with path.open('w') as stream:
        subprocess.run(['ab', '-n', '2000', '-c', '50', URL + '/resultat?matricule=000001'],
                       stdout=stream, stderr=subprocess.STDOUT, check=True)
    print(path.relative_to(ROOT))


def promote():
    start = time.monotonic()
    status = run('vagrant', 'status', 'bdd1', '--machine-readable', capture=True)
    states = [line.split(',')[3] for line in status.splitlines()
              if len(line.split(',')) >= 4 and line.split(',')[1:3] == ['bdd1', 'state']]
    if states != ['poweroff']:
        raise RuntimeError('Fence bdd1 first: vagrant halt bdd1. A saved VM is NOT fenced.')
    remote('bdd2', '''import subprocess
value = subprocess.check_output(['runuser','-u','postgres','--','psql','-X','-At','-c',
    'SELECT CASE WHEN pg_is_in_recovery() THEN pg_promote(true, 30) ELSE true END;'],text=True)
if value.strip() != 't': raise SystemExit('Promotion failed')
print('Promotion confirmed')
''')
    (ROOT / '.runtime').mkdir(exist_ok=True)
    (ROOT / '.runtime' / 'promoted').write_text('bdd2 is primary; keep bdd1 off\n')
    topology = inventory()
    primary = next(n['ip'] for n in topology['nodes'] if n['role'] == 'primary')
    replica = next(n['ip'] for n in topology['nodes'] if n['role'] == 'replica')
    for node in topology['nodes']:
        if node['role'] != 'app':
            continue
        remote(node['name'], f'''from pathlib import Path
import subprocess
p = Path('/etc/resultats/app.env')
lines = [line for line in p.read_text().splitlines() if not line.startswith('DB_HOSTS=')]
lines.insert(0, 'DB_HOSTS={replica},{primary}')
p.write_text('\\n'.join(lines) + '\\n')
p.chmod(0o600)
subprocess.run(['systemctl','restart','resultats'],check=True)
''')
    wait_health(timeout=90)
    save('V4-promotion', {'duration_seconds': time.monotonic()-start,
                           'fenced': 'bdd1 poweroff', 'primary': 'bdd2',
                           'application_db_hosts': f'{replica},{primary}', 'health': 200})
    print('Keep bdd1 OFF. Use the documented disposable-lab rebuild before restarting it.')


def rolling(release):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,40}', release): raise ValueError('Invalid release name')
    source = base64.b64encode((ROOT / 'app/service.py').read_bytes()).decode()
    apps = [n for n in inventory()['nodes'] if n['role'] == 'app']
    started = time.monotonic()
    for node in apps:
        name = node['name']
        healthy = [n for n in apps if n['name'] != name and backend(n['name'])['status'] == 'UP']
        if not healthy: raise RuntimeError('No other healthy backend; rollout stopped')
        runtime(f'set server apps/{name} state drain')
        deadline = time.monotonic() + 30
        while int(backend(name)['scur']) != 0:
            if time.monotonic() > deadline: raise RuntimeError(f'{name}: drain timeout; left drained')
            time.sleep(0.2)
        runtime(f'set server apps/{name} state maint')
        remote(name, f'''import base64, pathlib, subprocess
p = pathlib.Path('/opt/resultats/service.py')
candidate = p.with_suffix('.candidate.py')
candidate.write_bytes(base64.b64decode({source!r}))
compile(candidate.read_text(), str(candidate), 'exec')
candidate.replace(p)
p = pathlib.Path('/etc/resultats/app.env')
lines = [line for line in p.read_text().splitlines() if not line.startswith('RELEASE=')]
lines.append('RELEASE=' + {release!r})
p.write_text('\\n'.join(lines) + '\\n')
p.chmod(0o600)
subprocess.run(['systemctl','restart','resultats'],check=True)
''')
        wait_health('http://' + node['ip'] + ':8000')
        runtime(f'set server apps/{name} state ready')
        deadline = time.monotonic() + 30
        while backend(name)['status'] != 'UP':
            if time.monotonic() > deadline: raise RuntimeError(f'{name} not UP after rollout')
            time.sleep(0.5)
    save('E4-rolling', {'release': release, 'duration_seconds': time.monotonic()-started,
                        'nodes': [n['name'] for n in apps],
                        'note': 'Run a concurrent probe to prove zero failed requests.'})


def cache_mode(enabled):
    for n in inventory()['nodes']:
        if n['role'] == 'app':
            remote(n['name'], f'''from pathlib import Path
import subprocess
p=Path('/etc/resultats/app.env')
s=[line for line in p.read_text().splitlines() if not line.startswith('CACHE_ENABLED=')]
s.append('CACHE_ENABLED={int(enabled)}')
p.write_text('\\n'.join(s)+'\\n')
p.chmod(0o600)
subprocess.run(['systemctl','restart','resultats'],check=True)
''')
    wait_health()


def purge():
    remote('lb1', '''from pathlib import Path
import redis
password=next(line.split()[1] for line in Path('/etc/redis/redis.conf').read_text().splitlines()
              if line.startswith('requirepass '))
c=redis.Redis(password=password)
for key in c.scan_iter(match='resultats:v1:*'):
    c.delete(key)
print('Result cache cleared')
''')


def replication():
    code = '''import subprocess
print(subprocess.check_output(['runuser','-u','postgres','--','psql','-X','-At','-d','resultats','-c',%r],text=True))
'''
    # Update one existing synthetic record inside a transaction; keep 50,000 rows.
    token = 'Replication probe ' + str(time.time_ns())
    remote('bdd1', code % ("UPDATE resultats SET nom='" + token + "' WHERE matricule='050000';"))
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            value = remote('bdd2', code % "SELECT nom FROM resultats WHERE matricule='050000';")
            if value == token:
                save('R5-replication', {'visible_on_bdd2': value, 'passed': True})
                return
            time.sleep(0.5)
        raise RuntimeError('Replication did not catch up within 20 seconds')
    finally:
        remote('bdd1', code % "UPDATE resultats SET nom='Candidate 50000' WHERE matricule='050000';")
        purge()


def hashes():
    result = {}
    code = '''import glob, hashlib, json
from pathlib import Path
paths = glob.glob('/etc/resultats/*') + glob.glob('/etc/postgresql/16/main/conf.d/resultats.conf')
paths += glob.glob('/etc/postgresql/16/main/pg_hba.conf') + glob.glob('/etc/haproxy/haproxy.cfg')
paths += glob.glob('/etc/systemd/system/resultats.service') + glob.glob('/etc/redis/redis.conf')
paths += glob.glob('/opt/resultats/service.py') + glob.glob('/etc/apt-cacher-ng/zz-resultats.conf')
print(json.dumps({p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(paths)}))
'''
    for n in inventory()['nodes']: result[n['name']] = json.loads(remote(n['name'], code))
    return result


def idempotence():
    before = hashes()
    run('vagrant', 'provision')
    first = hashes()
    run('vagrant', 'provision')
    second = hashes()
    # Provisioning may legitimately converge operational drift (for example a
    # cache toggle can reorder app.env). Idempotence means that applying the
    # same desired state a second time causes no further change: F(F(x))=F(x).
    passed = first == second
    save('R2-idempotence', {
        'before': before,
        'first': first,
        'second': second,
        'converged_from_drift': before != first,
        'stable_after_first_apply': first == second,
        'passed': passed,
    })
    if not passed: raise RuntimeError('Configuration changed during repeated provisioning')


def rebuild(confirm):
    if not confirm: raise RuntimeError('Use --confirm-destroy-project-vms for this destructive lab test')
    start = time.monotonic()
    run('vagrant', 'destroy', '-f')
    (ROOT / '.runtime' / 'promoted').unlink(missing_ok=True)
    run('vagrant', 'up', '--provider=virtualbox')
    wait_health(timeout=120)
    save('V5-reconstruction', {'duration_seconds': time.monotonic()-start, 'health': 200})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight','v1','probe','benchmark','promote','rolling',
                                          'cache-on','cache-off','cache-purge','replication','idempotence','rebuild'])
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--path', default='/resultat?matricule=000001')
    parser.add_argument('--label', default='benchmark')
    parser.add_argument('--release', default='2')
    parser.add_argument('--confirm-destroy-project-vms', action='store_true')
    args = parser.parse_args()
    actions = {'preflight': preflight, 'v1': distribution, 'replication': replication,
               'promote': promote, 'cache-on': lambda: cache_mode(True),
               'cache-off': lambda: cache_mode(False), 'cache-purge': purge,
               'idempotence': idempotence, 'benchmark': lambda: benchmark(args.label),
               'probe': lambda: probe(args.seconds, args.workers, args.path),
               'rolling': lambda: rolling(args.release),
               'rebuild': lambda: rebuild(args.confirm_destroy_project_vms)}
    actions[args.action]()


if __name__ == '__main__':
    main()
