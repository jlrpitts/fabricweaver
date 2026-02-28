# Show commands per vendor
"""
FabricWeaver - Canonical Command Registry

Organized by:
- Vendor
- Layer
- Critical vs Extended

Used by:
ssh/live_collect.py
"""

COMMAND_REGISTRY = {

    "cisco_ios": {

        "critical": [
            "show lldp neighbors detail",
            "show ip interface brief",
            "show ip route",
            "show mac address-table",
            "show etherchannel summary",
            "show spanning-tree",
            "show ip ospf neighbor",
            "show ip bgp summary",
            "show vrf"
        ],

        "l2": [
            "show cdp neighbors detail",
            "show interfaces status",
            "show interface trunk",
            "show vlan brief",
            "show spanning-tree root",
            "show spanning-tree interface",
            "show interfaces port-channel",
            "show mac address-table dynamic",
            "show storm-control",
            "show interfaces switchport",
            "show port-security",
            "show vtp status",
            "show vtp counters",
            "show platform stack-manager all",
            "show switch",
            "show power inline"
        ],

        "l3": [
            "show ip route summary",
            "show ip arp",
            "show ip ospf database",
            "show ip eigrp neighbors",
            "show standby brief"
        ]
    },

    "cisco_nxos": {

        "critical": [
            "show lldp neighbors detail",
            "show ip interface brief",
            "show ip route vrf all",
            "show mac address-table",
            "show port-channel summary",
            "show spanning-tree",
            "show ip ospf neighbor",
            "show bgp ipv4 unicast summary",
            "show vrf"
        ],

        "l2": [
            "show cdp neighbors detail",
            "show interface brief",
            "show interface trunk",
            "show vlan brief",
            "show spanning-tree root",
            "show port-channel traffic",
            "show vpc",
            "show vpc brief",
            "show vpc consistency-parameters",
            "show mac address-table dynamic",
            "show system internal l2fwder mac",
            "show interface switchport",
            "show feature",
            "show fex",
            "show interface transceiver",
            "show hardware forwarding"
        ],

        "l3": [
            "show ip arp",
            "show ip ospf database",
            "show bgp l2vpn evpn summary",
            "show hsrp brief"
        ]
    },

    "arista_eos": {

        "critical": [
            "show lldp neighbors detail",
            "show ip interface brief",
            "show ip route",
            "show mac address-table",
            "show port-channel summary",
            "show spanning-tree",
            "show ip ospf neighbor",
            "show ip bgp summary",
            "show vrf"
        ],

        "l2": [
            "show interfaces status",
            "show interfaces trunk",
            "show vlan",
            "show spanning-tree root",
            "show mlag",
            "show mlag interfaces",
            "show mac address-table dynamic",
            "show interfaces switchport",
            "show interfaces transceiver",
            "show running-config section vlan",
            "show running-config section interface",
            "show l2protocol",
            "show storm-control",
            "show vlan internal usage",
            "show platform fap",
            "show version"
        ],

        "l3": [
            "show ip route vrf all",
            "show ip arp",
            "show ip ospf database",
            "show ip bgp neighbors",
            "show vrrp"
        ]
    },

    "dell_os10": {

        "critical": [
            "show lldp neighbors detail",
            "show ip interface brief",
            "show ip route vrf all",
            "show mac address-table",
            "show port-channel summary",
            "show spanning-tree",
            "show ip ospf neighbor",
            "show ip bgp summary",
            "show vrf"
        ],

        "l2": [
            "show interfaces status",
            "show interfaces switchport",
            "show vlan",
            "show spanning-tree root",
            "show mac address-table dynamic",
            "show running-configuration interface",
            "show running-configuration vlan",
            "show mlag",
            "show mlag interfaces",
            "show interface transceiver",
            "show storm-control",
            "show bridge",
            "show bridge address-table",
            "show system",
            "show hardware",
            "show environment"
        ],

        "l3": [
            "show ip route",
            "show ip arp",
            "show ip ospf database",
            "show ip bgp neighbors",
            "show vrrp"
        ]
    }
}