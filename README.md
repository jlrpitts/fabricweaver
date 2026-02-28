# Network Topology Mapper

An enterprise-grade multi-vendor network discovery, parsing, and topology generation platform.

This application supports both:

- **Static Build Mode** – Upload configuration files
- **Dynamic Build Mode** – SSH into live devices and collect topology data

Supported Vendors:

- Cisco Catalyst (IOS / IOS-XE)
- Cisco Nexus (NX-OS)
- Dell OS10
- Arista EOS

The system extracts Layer 2 and Layer 3 constructs and generates structured topology data and connectivity diagrams.

---

## Architecture Modes

### 1️⃣ Static Build Mode
- Upload multiple device configuration files
- Parse full running-config
- Build logical L2/L3 adjacency maps
- Ideal for migrations, audits, offline design review

### 2️⃣ Dynamic Build Mode
- SSH into live devices (Netmiko-based collection)
- Execute vendor-specific show commands
- Collect neighbor, port-channel, VLAN, routing, and interface data
- Build real-time topology map
- No credential storage (session-only)

---

## Supported Protocol Parsing

### Layer 2
- VLAN database
- Access / Trunk ports
- Port-Channels (LACP)
- Cisco vPC
- Dell VLT
- Arista MLAG
- Spanning Tree
- LLDP / CDP neighbors

### Layer 3
- SVIs
- Routed interfaces
- Static routes
- OSPF
- BGP
- VRFs
- HSRP / VRRP

---

## Core Capabilities

- Multi-device ingestion
- Vendor detection engine
- Normalized interface modeling
- Topology graph builder
- Peer-link and uplink inference
- L2/L3 adjacency correlation
- Dark mode UI
- JSON export
- Diagram export (PNG / PDF)

---

## Design Philosophy

- Vendor-specific parsing modules
- Unified normalized data model
- Separation of:
  - Collection (SSH)
  - Parsing
  - Topology modeling
  - Visualization

Built to scale from:
- Small campus environments
- To large multi-site data centers

---

## Target Use Cases

- Data center migrations
- Pre-change validation
- L2/L3 discovery and documentation
- Multi-vendor consolidation projects
- Architecture design validation
- Change control risk analysis

---

## Roadmap

- EVPN/VXLAN fabric support
- NetFlow correlation
- Configuration generation engine (build configs from topology model)
- Compliance validation engine
- AI-assisted anomaly detection
- Role-based access control
- API integration

---

## Security Model

- No credential persistence
- Session-based SSH authentication
- Read-only command execution
- Designed for jump-host integration (future)

---

## Author

Built for enterprise data center architecture, migration engineering, and multi-vendor operational workflows.