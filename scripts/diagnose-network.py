#!/usr/bin/env python3
"""Read-only check for duplicate database IP/MAC mappings."""
import json

from ops import remote, save


DB_CODE = r'''
import json
from pathlib import Path
print(json.dumps({
    'private_ip': next(line.split()[2].split('/')[0] for line in
                       __import__('subprocess').check_output(
                           ['ip', '-brief', 'address', 'show', 'eth1'], text=True
                       ).splitlines()),
    'private_mac': Path('/sys/class/net/eth1/address').read_text().strip()
}))
'''

APP_CODE = r'''
import json, socket, subprocess
hosts = ('192.168.56.31', '192.168.56.32')
for host in hosts:
    try:
        with socket.create_connection((host, 5432), timeout=2):
            pass
    except OSError:
        pass
print(json.dumps({host: subprocess.check_output(
    ['ip', 'neighbor', 'show', 'to', host], text=True).strip()
    for host in hosts}))
'''


if __name__ == '__main__':
    report = {
        'bdd1': json.loads(remote('bdd1', DB_CODE)),
        'bdd2': json.loads(remote('bdd2', DB_CODE)),
        'app3_sees': json.loads(remote('app3', APP_CODE)),
        'app4_sees': json.loads(remote('app4', APP_CODE)),
    }
    print(json.dumps(report, indent=2))
    save('network-neighbors', report)
