from typing import Union, List, Dict, Any

from .models import Topology, Device, Interface, Link


def build_topology_from_snapshot(snapshots: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Topology:
    """
    Build a Topology object from one or more device snapshot dictionaries.
    Each snapshot is expected to follow the structure returned by
    ``ssh.live_collect.build_device_snapshot`` and augmented by the
    parser.orchestrator routines.

    Args:
        snapshots: single snapshot or list of snapshots.

    Returns:
        Topology populated with Device, Interface and Link instances.
    """
    if not isinstance(snapshots, list):
        snapshots = [snapshots]

    topology = Topology()

    for snap in snapshots:
        dev = snap.get("device", {})
        hostname = dev.get("hostname") or dev.get("mgmt_ip") or "unknown"
        device = Device(
            hostname=hostname,
            mgmt_ip=dev.get("mgmt_ip"),
            vendor=dev.get("vendor"),
        )

        # interfaces saved under l3.interfaces
        for i in snap.get("l3", {}).get("interfaces", []):
            device.interfaces.append(
                Interface(
                    name=i.get("name"),
                    description=i.get("description"),
                    ip=i.get("ip"),
                    vlan=i.get("vlan"),
                    mac=i.get("mac"),
                )
            )

        topology.add_device(device)

        # look for neighbour information and convert to Link objects
        for nbr in snap.get("l2", {}).get("neighbors", []):
            a_int = nbr.get("interface")
            b_dev = nbr.get("neighbor_device")
            b_int = nbr.get("neighbor_interface")
            vlan = nbr.get("vlan")
            if a_int and b_dev and b_int:
                topology.add_link(
                    Link(
                        a_device=hostname,
                        a_interface=a_int,
                        b_device=b_dev,
                        b_interface=b_int,
                        vlan=vlan,
                    )
                )

    return topology
