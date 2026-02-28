"""
Live Collection Engine
Builds structured device snapshot from SSH command outputs.
"""

def build_device_snapshot(device_ip, vendor, raw_outputs):
    """
    Constructs structured snapshot dictionary.
    """

    snapshot = {
        "device": {
            "hostname": None,
            "mgmt_ip": device_ip,
            "vendor": vendor,
            "model": None,
            "os_version": None,
            "serial": None,
            "stack_members": [],
            "vpc_role": None,
            "mlag_role": None
        },

        "l2": {
            "vlans": [],
            "interfaces": [],
            "port_channels": [],
            "mac_table": [],
            "spanning_tree": {
                "root_bridge": None,
                "per_vlan_roots": {}
            },
            "neighbors": []
        },

        "l3": {
            "interfaces": [],
            "arp_table": [],
            "routes": [],
            "ospf_neighbors": [],
            "bgp_neighbors": [],
            "hsrp": [],
            "vrrp": [],
            "vrfs": []
        },

        "raw_outputs": raw_outputs
    }

    return snapshot