from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class Interface:
	name: str
	description: Optional[str] = None
	ip: Optional[str] = None
	vlan: Optional[int] = None
	mac: Optional[str] = None


@dataclass
class Device:
	hostname: str
	mgmt_ip: Optional[str] = None
	vendor: Optional[str] = None
	interfaces: List[Interface] = field(default_factory=list)


@dataclass
class Link:
	a_device: str
	a_interface: str
	b_device: str
	b_interface: str
	vlan: Optional[int] = None


@dataclass
class Topology:
	devices: Dict[str, Device] = field(default_factory=dict)
	links: List[Link] = field(default_factory=list)

	def add_device(self, device: Device):
		self.devices[device.hostname] = device

	def add_link(self, link: Link):
		self.links.append(link)
