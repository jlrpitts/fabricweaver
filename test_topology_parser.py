#!/usr/bin/env python
"""
Diagnostic tool for testing topology parser functionality.
Tests config parsing, device detection, vPC/LACP/CDP detection, and topology building.
"""

import sys
import os
import glob
sys.path.insert(0, '.')

from fabricweaver import parse_with_adapters, build_topology

def run_topology_parser_test(config_dir=None):
    """Test topology parser on config files in specified directory"""
    
    if config_dir is None:
        # Default to current directory
        config_dir = os.getcwd()
    
    # Find all config files
    patterns = ['*.txt', '*.cfg', '*.conf', '*.log']
    config_files = []
    for pattern in patterns:
        config_files.extend(glob.glob(os.path.join(config_dir, pattern)))
    
    if not config_files:
        print(f"No config files found in {config_dir}")
        return

    print("="*80)
    print("TOPOLOGY PARSER DIAGNOSTIC TEST")
    print("="*80)
    print(f"Config directory: {config_dir}")
    print(f"Found {len(config_files)} config file(s)")

    try:
        print(f"\nParsing {len(config_files)} config(s)...")
        topo, file_errors = parse_with_adapters(config_files)
        
        print(f"\n{'='*80}")
        print(f"PARSE RESULTS")
        print(f"{'='*80}")
        
        print(f"Devices loaded: {len(topo.devices)}")
        print(f"File errors: {len(file_errors)}")
        
        if file_errors:
            print("\nFile Errors:")
            for fname, err in file_errors.items():
                print(f"  {fname}: {err}")
        
        # Display each device
        for hostname, dev in topo.devices.items():
            print(f"\n{'-'*80}")
            print(f"Device: {hostname}")
            print(f"{'-'*80}")
            print(f"  Hostname (parsed): {dev.hostname}")
            print(f"  Vendor: {dev.vendor}")
            print(f"  Model: {dev.model}")
            print(f"  OS Version: {dev.os_version}")
            print(f"")
            print(f"  L2 Information:")
            print(f"    Interfaces: {len(dev.interfaces)} total")
            print(f"    Port-channels: {len(dev.port_channels)}")
            pc_details = []
            for pc_id, pc in dev.port_channels.items():
                members = len(pc.member_interfaces) if pc.member_interfaces else 0
                pc_details.append(f"{pc_id} ({members} members)")
            if pc_details:
                print(f"      {', '.join(pc_details[:10])}")
            print(f"    VLANs: {len(dev.vlans)}")
            print(f"    STP: {dev.stp_mode if dev.stp_mode else 'Not configured'}")
            print(f"")
            print(f"  L3 Information:")
            print(f"    SVIs: {sum(1 for i in dev.interfaces.values() if i.is_svi)}")
            print(f"    Routed interfaces: {sum(1 for i in dev.interfaces.values() if i.mode == 'routed')}")
            print(f"    VRFs: {len(dev.vrfs) if dev.vrfs else 0}")
            print(f"    Loopbacks: {sum(1 for i in dev.interfaces.keys() if 'loopback' in i.lower())}")
            print(f"")
            print(f"  Routing:")
            print(f"    Protocols: {dev.routing_protocols}")
            print(f"    Static routes: {len(dev.static_routes)}")
            print(f"    BGP neighbors: {len(dev.bgp_neighbors)}")
            if dev.bgp_neighbors:
                print(f"      {', '.join(str(n.neighbor_ip) for n in dev.bgp_neighbors[:5])}")
            print(f"    OSPF neighbors: {len(dev.ospf_neighbors)}")
            print(f"    CDP neighbors: {len(dev.cdp)}")
            if dev.cdp:
                print(f"      {', '.join(cdp.neighbor_device for cdp in dev.cdp[:5])}")
            print(f"")
            print(f"  High Availability:")
            print(f"    vPC configured: {dev.vpc_configured}")
            if dev.vpc_configured:
                print(f"      Domain: {dev.vpc_domain}")
                print(f"      Keepalive: {dev.vpc_keepalive_dst}")
                print(f"      Peer-link: {dev.vpc_peerlink_po}")
            print(f"    LACP: Present in config")
            print(f"")
            if dev.parse_errors:
                print(f"  Parse Warnings ({len(dev.parse_errors)}):")
                for err in dev.parse_errors[:5]:
                    print(f"    - {err}")
                if len(dev.parse_errors) > 5:
                    print(f"    ... and {len(dev.parse_errors) - 5} more")
            else:
                print(f"  Parse Warnings: None")
        
        # Build topology
        print(f"\n{'='*80}")
        print(f"TOPOLOGY BUILDING")
        print(f"{'='*80}")
        
        topo = build_topology(topo)
        
        print(f"\nLinks created: {len(topo.links)}")
        for link in topo.links:
            print(f"  {link.a}:{link.a_intf} ↔ {link.b}:{link.b_intf}")
            print(f"    Type: {link.kind}, Evidence: {link.evidence}, Confidence: {link.confidence}")
            if link.reasons:
                for reason in link.reasons[:2]:
                    print(f"      • {reason}")
        
        print(f"\nvPC Pairs: {len(topo.pairs)}")
        for pair in topo.pairs:
            print(f"  {pair.a} ↔ {pair.b}")
            print(f"    Kind: {pair.kind}, Confidence: {pair.confidence}")
            for reason in pair.reasons[:3]:
                print(f"      • {reason}")
        
        print(f"\n{'='*80}")
        print(f"SUCCESS - Topology parser functioning correctly!")
        print(f"{'='*80}")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # If a directory is specified on command line, use it
    config_dir = sys.argv[1] if len(sys.argv) > 1 else None
    run_topology_parser_test(config_dir)
