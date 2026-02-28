import csv
import os
from .models import Topology


def export_topology_csv(topology: Topology, path: str):
    """
    Write topology information to two CSV files under ``path``:

    - devices.csv : hostname,mgmt_ip,vendor
    - links.csv   : a_device,a_interface,b_device,b_interface,vlan

    Args:
        topology: Topology instance to export.
        path: directory where files will be written.
    """
    os.makedirs(path, exist_ok=True)

    dev_file = os.path.join(path, "devices.csv")
    with open(dev_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["hostname", "mgmt_ip", "vendor"])
        for dev in topology.devices.values():
            writer.writerow([dev.hostname, dev.mgmt_ip or "", dev.vendor or ""])

    link_file = os.path.join(path, "links.csv")
    with open(link_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["a_device", "a_interface", "b_device", "b_interface", "vlan"])
        for l in topology.links:
            writer.writerow(
                [
                    l.a_device,
                    l.a_interface,
                    l.b_device,
                    l.b_interface,
                    l.vlan if l.vlan is not None else "",
                ]
            )
