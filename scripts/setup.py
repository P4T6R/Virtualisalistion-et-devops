#!/usr/bin/env python3
"""Generate local secrets, never overwrite existing configuration."""
import os
from pathlib import Path
import secrets
root = Path(__file__).resolve().parents[1]
content = (root / '.env.exemple').read_text()
content += ''.join(f'{name}={secrets.token_hex(32)}\n' for name in
                   ('DB_PASSWORD', 'REPLICATION_PASSWORD', 'REDIS_PASSWORD'))
try:
    fd = os.open(root / '.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('Existing .env preserved.')
else:
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
    print('Created .env with private permissions. Do not commit or share it.')
