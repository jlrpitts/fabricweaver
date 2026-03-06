#!/usr/bin/env python
"""Test if the recent changes break basic functionality"""

import sys
sys.path.insert(0, '.')

from fabricweaver import (
    DeviceSummary, TopologyData, Link, 
    _norm_intf, _calc_link_evidence_score, _describe_link_evidence,
    build_topology, _infer_vpc_pairs
)

print("="*70)
print("Testing normalization and scoring functions...")
print("="*70)

# Test normalization
test_names = [
    "Gi0/1", "gi0/1",
    "Ethernet1/1", "eth1/1",
    "port-channel1", "Po1", "PortChannel1",
    "TenGigabitEthernet0/0/1", "Te0/0/1",
    "Loopback0", "Lo0",
]

print("\nInterface Normalization Tests:")
for name in test_names:
    norm = _norm_intf(name)
    print(f"  {name:25s} → {norm}")

# Test evidence scoring
print("\n\nEvidence Scoring Tests:")
test_evidence = [
    {"cdp"},
    {"description"},
    {"subnet"},
    {"cdp", "description"},
    {"description", "subnet"},
    {"vpc-peerlink"},
    set(),
]

for evidence in test_evidence:
    conf, score = _calc_link_evidence_score(evidence)
    desc = _describe_link_evidence(list(evidence))
    print(f"  {str(evidence):30s} → {conf:10s} ({score}) - {desc}")

# Test building topology with empty data
print("\n" + "="*70)
print("Testing topology building with minimal data...")
print("="*70)

topo = TopologyData()
d1 = DeviceSummary(
    hostname="device1",
    vendor="Cisco Nexus (NX-OS)",
    mgmt_ip="10.0.0.1"
)
d1.vpc_configured = True
d1.vpc_domain = "1"
d1.vpc_keepalive_dst = "10.0.0.2"
d1.vpc_peerlink_po = "port-channel1"

d2 = DeviceSummary(
    hostname="device2", 
    vendor="Cisco Nexus (NX-OS)",
    mgmt_ip="10.0.0.2"
)
d2.vpc_configured = True
d2.vpc_domain = "1"
d2.vpc_keepalive_dst = "10.0.0.1"
d2.vpc_peerlink_po = "port-channel1"

topo.devices["device1"] = d1
topo.devices["device2"] = d2

print(f"\nBuilding topology from {len(topo.devices)} devices...")
try:
    topo = build_topology(topo)
    print(f"Success! Generated {len(topo.links)} links and {len(topo.pairs)} pairs")
    
    for pair in topo.pairs:
        print(f"  Pair: {pair.a} ↔ {pair.b} ({pair.confidence})")
        
    for link in topo.links:
        print(f"  Link: {link.a}:{link.a_intf} ↔ {link.b}:{link.b_intf} ({link.evidence})")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("All tests completed!")
print("="*70)
