#!/usr/bin/env python
"""Quick test to check file loading"""

import os
import glob
from fabricweaver import parse_configs_fallback

# Find all .txt, .cfg, .log files in current directory
config_files = []
for ext in ['*.txt', '*.cfg', '*.log', '*.conf']:
    config_files.extend(glob.glob(ext))

if not config_files:
    print("No config files found in current directory")
    print("Looking for: *.txt, *.cfg, *.log, *.conf")
else:
    print(f"Found {len(config_files)} potential config file(s):")
    for f in config_files:
        size = os.path.getsize(f)
        print(f"  - {f} ({size} bytes)")
    
    print("\nParsing...")
    topo, errors = parse_configs_fallback(config_files)
    
    print(f"\nResults:")
    print(f"  Devices loaded: {len(topo.devices)}")
    print(f"  Files with errors: {len(errors)}")
    
    if topo.devices:
        print("\nDevices:")
        for hostname, dev in topo.devices.items():
            print(f"  - {hostname} ({dev.vendor})")
            if dev.parse_errors:
                print(f"    Warnings: {len(dev.parse_errors)}")
    
    if errors:
        print("\nFile Errors:")
        for fname, err in errors.items():
            print(f"  - {fname}: {err}")
