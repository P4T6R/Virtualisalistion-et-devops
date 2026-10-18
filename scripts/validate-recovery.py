#!/usr/bin/env python3
"""Operator-run V4 database failover followed by V5 full reconstruction."""
import time

import ops


def validate_v4():
    print('[1/2] V4: halt bdd1, observe HTTP 503, then promote bdd2')
    promoted_marker = ops.ROOT / '.runtime' / 'promoted'
    resumed = promoted_marker.exists()
    if not resumed:
        ops.wait_health()
    started = time.monotonic()
    fault_unix = time.time()
    if not resumed:
        ops.run('vagrant', 'halt', 'bdd1')
        fenced_seconds = time.monotonic() - started
    else:
        fenced_seconds = None
        print('Resuming V4 with bdd1 fenced and bdd2 already promoted.')

    deadline = time.monotonic() + 20
    unavailable_status = 0
    unavailable_body = ''
    while time.monotonic() < deadline:
        unavailable_status, unavailable_body = ops.request('/sante')
        if unavailable_status == 503:
            break
        time.sleep(0.25)
    if unavailable_status != 503:
        raise RuntimeError(f'V4 expected HTTP 503 before promotion, got {unavailable_status}')

    promotion_started = time.monotonic()
    ops.promote()
    promotion_seconds = time.monotonic() - promotion_started
    recovered_status, recovered_body = ops.request('/sante')
    total_seconds = time.monotonic() - started
    passed = recovered_status == 200
    ops.save('V4-total-failover', {
        'fault_unix': fault_unix,
        'resumed_after_prior_promotion': resumed,
        'fencing_seconds': fenced_seconds,
        'status_before_promotion': unavailable_status,
        'body_before_promotion': unavailable_body,
        'promotion_and_health_seconds': promotion_seconds,
        'total_seconds_from_halt_start_to_health': total_seconds,
        'status_after_promotion': recovered_status,
        'body_after_promotion': recovered_body,
        'old_primary_fenced': True,
        'new_primary': 'bdd2',
        'passed': passed,
    })
    if not passed:
        raise RuntimeError('V4 health did not recover after promotion')


def machine_states():
    output = ops.run('vagrant', 'status', '--machine-readable', capture=True)
    states = {}
    for line in output.splitlines():
        parts = line.split(',', 3)
        if len(parts) == 4 and parts[2] == 'state':
            states[parts[1]] = parts[3]
    return states


def validate_v5():
    print('[2/2] V5: destroy and reconstruct every project VM')
    ops.rebuild(True)
    states = machine_states()
    expected = {node['name'] for node in ops.inventory()['nodes']}
    health_status, health_body = ops.request('/sante')
    passed = (set(states) == expected
              and all(state == 'running' for state in states.values())
              and health_status == 200)
    ops.save('V5-post-rebuild', {
        'machine_states': states,
        'health_status': health_status,
        'health_body': health_body,
        'passed': passed,
    })
    if not passed:
        raise RuntimeError('V5 post-rebuild state failed')

    # These checks prove that the reconstructed platform is functional without
    # any manual configuration after vagrant up.
    ops.distribution()
    ops.replication()


if __name__ == '__main__':
    validate_v4()
    validate_v5()
    print('Recovery validation completed. V4 and V5 evidence is in results/.')
