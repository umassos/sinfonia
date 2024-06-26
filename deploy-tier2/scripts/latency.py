import os
import subprocess

import geopy.distance


LIGHT_SPEED_KM_PER_MS = 299.792458
LATENCY_VARIANCE = 0.01
NETWORK_INTERFACES = ['eno1', 'kilo0']

    
client_coordinate = (
    float(os.environ['SINFONIA_TIER3_LATITUDE']),
    float(os.environ['SINFONIA_TIER3_LONGITUDE'])
    )
print("client", client_coordinate)

host_coordinate = (
    float(os.environ['SINFONIA_TIER2_LATITUDE']),
    float(os.environ['SINFONIA_TIER2_LONGITUDE']),
    )
print("host", host_coordinate)

transition_latency_ms = float(os.environ['EXPERIMENT_TRANSITION_LATENCY_MS'])
print("transition latency (ms)", transition_latency_ms)

dist_km = geopy.distance.distance(client_coordinate, host_coordinate).km
print(dist_km)
    
latency_ms = round(dist_km / LIGHT_SPEED_KM_PER_MS, 1)
latency_variance_ms = round(latency_ms * LATENCY_VARIANCE, 1)

for itf in NETWORK_INTERFACES:
    cmd = ([
        'sudo',
        'tc',
        'qdisc',
        'add',
        'dev',
        f'{itf}',
        'root',
        'netem',
        'delay',
        f'{latency_ms + transition_latency_ms}ms',
        ])
    subprocess.run(cmd)
    print(cmd)
    # time.sleep(1)
