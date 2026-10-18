#!/usr/bin/env python3
"""Operator-run V2 and E4 live-traffic validations."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import json
import threading
import time

import ops


def collect_load(seconds, workers, path, started):
    end = started + seconds

    def worker(_):
        rows = []
        while time.monotonic() < end:
            before = time.monotonic()
            status, _ = ops.request(path)
            rows.append((time.time(), before - started,
                         time.monotonic() - before, status))
            time.sleep(0.05)
        return rows

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = [row for group in pool.map(worker, range(workers)) for row in group]
    rows.sort()
    return rows


def collect_until(stop, workers, path, started):
    def worker(_):
        rows = []
        while not stop.is_set():
            before = time.monotonic()
            status, _ = ops.request(path)
            rows.append((time.time(), before - started,
                         time.monotonic() - before, status))
            time.sleep(0.05)
        return rows

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = [row for group in pool.map(worker, range(workers)) for row in group]
    rows.sort()
    return rows


def write_csv(label, rows):
    path = ops.log_path(label, 'csv')
    with path.open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['unix_time', 'started_seconds', 'latency_seconds', 'status'])
        writer.writerows(rows)
    return str(path.relative_to(ops.ROOT))


def validate_v2():
    print('[1/2] V2: stop app1 during continuous traffic')
    ops.wait_health()
    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            load = pool.submit(collect_load, 25, 8,
                               '/resultat?matricule=000001', started)
            time.sleep(2)
            fault_offset = time.monotonic() - started
            fault_unix = time.time()
            halt = pool.submit(ops.run, 'vagrant', 'halt', 'app1')
            eviction_offset = None
            deadline = started + fault_offset + 10
            while time.monotonic() < deadline:
                if ops.backend('app1')['status'] == 'DOWN':
                    eviction_offset = time.monotonic() - started
                    break
                time.sleep(0.25)
            halt.result()
            halt_completed_offset = time.monotonic() - started
            rows = load.result()

        errors = [row for row in rows if row[3] != 200 and row[1] >= fault_offset]
        failure_onset = errors[0][1] if errors else halt_completed_offset
        late_errors = [row for row in errors
                       if row[1] + row[2] > failure_onset + 5]
        eviction_seconds = (eviction_offset - failure_onset
                            if eviction_offset is not None else None)
        passed = (eviction_seconds is not None and eviction_seconds < 5
                  and not late_errors)
        ops.save('V2-app-failure', {
            'probe_csv': write_csv('V2-app-failure', rows),
            'fault_unix': fault_unix,
            'halt_command_started_seconds': fault_offset,
            'halt_command_completed_seconds': halt_completed_offset,
            'failure_onset_seconds': failure_onset,
            'requests': len(rows),
            'lost_requests': len(errors),
            'degraded_window_seconds': (
                max(row[1] + row[2] for row in errors) - failure_onset
                if errors else 0),
            'haproxy_eviction_seconds_after_failure': eviction_seconds,
            'errors_after_five_seconds': len(late_errors),
            'passed': passed,
        })
        if not passed:
            raise RuntimeError('V2 criterion failed')
    finally:
        ops.run('vagrant', 'up', 'app1')
        ops.wait_health('http://192.168.56.21:8000', timeout=120)


def validate_e4():
    print('[2/2] E4: rolling deployment during continuous traffic')
    ops.wait_health()
    started = time.monotonic()
    stop = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        load = pool.submit(collect_until, stop, 8,
                           '/resultat?matricule=000001', started)
        time.sleep(2)
        rollout_started = time.monotonic()
        try:
            ops.rolling('2')
            rollout_seconds = time.monotonic() - rollout_started
            time.sleep(5)
        finally:
            stop.set()
        rows = load.result()

    errors = [row for row in rows if row[3] != 200]
    releases = []
    for _ in range(20):
        status, body = ops.request('/info')
        if status != 200:
            raise RuntimeError(f'/info returned {status} after rollout')
        releases.append(json.loads(body))
    passed = not errors and {item['release'] for item in releases} == {'2'}
    ops.save('E4-zero-downtime', {
        'probe_csv': write_csv('E4-zero-downtime', rows),
        'requests': len(rows),
        'failed_requests': len(errors),
        'rollout_seconds': rollout_seconds,
        'probe_seconds': max(row[1] + row[2] for row in rows),
        'post_rollout_probe_seconds': 5,
        'observed_hosts': sorted({item['hostname'] for item in releases}),
        'observed_releases': sorted({item['release'] for item in releases}),
        'passed': passed,
    })
    if not passed:
        raise RuntimeError('E4 zero-downtime criterion failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=['all', 'v2', 'e4'], nargs='?', default='all')
    selected = parser.parse_args().scenario
    if selected in ('all', 'v2'):
        validate_v2()
    if selected in ('all', 'e4'):
        validate_e4()
    print(f'Live validation completed for {selected}. Evidence is in results/.')
