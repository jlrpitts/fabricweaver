"""
FabricWeaver - Clean Static Config Parser
Stable block-based parsing.

Parses:
- Hostname
- VRFs
- VLANs
- Port-Channels (vPC)
- L3 Interfaces
- Static Routes
- HSRP (correct block parser)
- OSPF
- BGP
"""

from parser import vendor_detect
from ssh.live_collect import build_device_snapshot


def parse_file(filepath):
    with open(filepath, "r", errors="ignore") as f:
        content = f.read()

    vendor = vendor_detect.detect_vendor(content)

    snapshot = build_device_snapshot(
        device_ip="STATIC_FILE",
        vendor=vendor,
        raw_outputs={"running_config": content}
    )

    parse_hostname(content, snapshot)
    parse_vrfs(content, snapshot)
    parse_vlans(content, snapshot)
    parse_port_channels(content, snapshot)
    parse_l3_interfaces(content, snapshot)
    parse_static_routes(content, snapshot)
    parse_hsrp(content, snapshot)
    parse_ospf(content, snapshot)
    parse_bgp(content, snapshot)

    return snapshot


# ---------------- HOSTNAME ----------------

def parse_hostname(config, snapshot):
    for line in config.splitlines():
        if line.lower().startswith("hostname"):
            snapshot["device"]["hostname"] = line.split()[1]
            break


# ---------------- VRF ----------------

def parse_vrfs(config, snapshot):
    for line in config.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("vrf context"):
            snapshot["l3"]["vrfs"].append(stripped.split()[2])


# ---------------- VLAN ----------------

def parse_vlans(config, snapshot):
    lines = config.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("vlan "):
            vlan_id = int(line.split()[1])
            name = None
            i += 1

            while i < len(lines):
                sub = lines[i].strip()
                if sub.startswith("name "):
                    name = sub.split(" ", 1)[1]
                if sub == "!" or sub.startswith("vlan ") or sub.startswith("interface "):
                    i -= 1
                    break
                i += 1

            snapshot["l2"]["vlans"].append({
                "vlan_id": vlan_id,
                "name": name
            })

        i += 1


# ---------------- PORT CHANNEL ----------------

def parse_port_channels(config, snapshot):
    lines = config.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if line.lower().startswith("interface port-channel"):
            po_id = line.split()[1].replace("port-channel", "")
            description = None
            peer_link = False
            vpc_id = None
            i += 1

            while i < len(lines):
                sub = lines[i].strip()

                if sub.startswith("description"):
                    description = sub.split(" ", 1)[1]

                if "vpc peer-link" in sub.lower():
                    peer_link = True
                    snapshot["device"]["vpc_role"] = "Configured"

                if sub.startswith("vpc ") and sub.split()[1].isdigit():
                    vpc_id = sub.split()[1]

                if sub == "!" or sub.startswith("interface "):
                    i -= 1
                    break

                i += 1

            snapshot["l2"]["port_channels"].append({
                "id": po_id,
                "description": description,
                "peer_link": peer_link,
                "vpc_id": vpc_id
            })

        i += 1


# ---------------- L3 INTERFACES ----------------

def parse_l3_interfaces(config, snapshot):
    lines = config.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if line.lower().startswith("interface "):
            interface = line.split()[1]
            vrf = None
            ip = None
            i += 1

            while i < len(lines):
                sub = lines[i].strip()

                if sub.startswith("vrf member"):
                    vrf = sub.split()[-1]

                if sub.startswith("ip address"):
                    ip = sub.split()[2]

                if sub == "!" or sub.startswith("interface "):
                    i -= 1
                    break

                i += 1

            if ip:
                snapshot["l3"]["interfaces"].append({
                    "name": interface,
                    "ip": ip,
                    "vrf": vrf
                })

        i += 1


# ---------------- STATIC ROUTES ----------------

def parse_static_routes(config, snapshot):
    for line in config.splitlines():
        stripped = line.strip()
        if stripped.startswith("ip route"):
            parts = stripped.split()
            if len(parts) >= 4:
                snapshot["l3"]["routes"].append({
                    "prefix": parts[2],
                    "next_hop": parts[3],
                    "protocol": "static"
                })


# ---------------- HSRP (FINAL CLEAN BLOCK PARSER) ----------------

def parse_hsrp(config, snapshot):
    lines = config.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if line.lower().startswith("interface "):
            interface = line.split()[1]
            i += 1

            while i < len(lines):
                sub = lines[i].strip()

                if sub.lower().startswith("hsrp "):
                    group = sub.split()[1]
                    vip = None
                    i += 1

                    while i < len(lines):
                        inner = lines[i].strip()

                        if inner.startswith("ip "):
                            vip = inner.split()[1]

                        if inner.startswith("hsrp ") or inner.startswith("interface ") or inner == "!":
                            i -= 1
                            break

                        i += 1

                    snapshot["l3"]["hsrp"].append({
                        "interface": interface,
                        "group": group,
                        "vip": vip
                    })

                if sub.startswith("interface ") or sub == "!":
                    i -= 1
                    break

                i += 1

        i += 1


# ---------------- OSPF ----------------

def parse_ospf(config, snapshot):
    for line in config.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("router ospf"):
            snapshot["l3"]["ospf_neighbors"].append({
                "process": stripped.split()[2]
            })


# ---------------- BGP ----------------

def parse_bgp(config, snapshot):
    lines = config.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if line.lower().startswith("router bgp"):
            i += 1
            while i < len(lines):
                sub = lines[i].strip()

                if sub.startswith("neighbor") and "remote-as" in sub:
                    parts = sub.split()
                    snapshot["l3"]["bgp_neighbors"].append({
                        "neighbor": parts[1],
                        "remote_as": parts[-1]
                    })

                if sub == "!":
                    break

                i += 1

        i += 1