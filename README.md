# Network Topology Mapper

A multi-vendor network topology parsing and visualization tool.

This application parses configuration files from:

- Cisco Catalyst (IOS / IOS-XE)
- Cisco Nexus (NX-OS)
- Dell OS10
- Arista EOS

It extracts Layer 2 and Layer 3 protocols and generates connectivity flow diagrams.

---

## Supported Protocol Parsing

### Layer 2
- VLANs
- Trunk / Access Ports
- Port-Channels (vPC / LACP / MLAG)
- Spanning Tree
- VLT / vPC / MLAG relationships

### Layer 3
- SVIs
- Static Routes
- OSPF
- BGP
- VRFs
- HSRP / VRRP

---

## Features
- Upload multiple device configurations
- Automatically identify peer links and uplinks
- Build L2/L3 adjacency map
- Generate topology flow chart
- Dark mode UI
- Export topology (PNG / PDF)

---

## Target Use Cases
- Data center migrations
- Pre-change validation
- L2/L3 discovery
- Documentation automation
- Multi-vendor environments

---

## Roadmap
- NetFlow parsing
- Live SSH pull (Netmiko)
- Fabric mode (EVPN/VXLAN support)
- Validation engine (missing config detection)

---

## Author
Built for enterprise data center architecture and migration workflows.