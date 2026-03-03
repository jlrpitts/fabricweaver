# fabricweaver/ui/layout.py
# Tkinter layout (Devices / Topology / Raw Data + Options)
# FIXES:
# - Removes broken alias FabricWeaverApp = FabricWeaverUI
# - Removes fake "auto chain" links
# - Parses more L2/L3 details (trunks/access/routed, port-channels, routes, routing protocols)
# - Builds links from REAL evidence (interface/port-channel descriptions + mutual matching)
# - Topology supports: drag nodes, L2/L3 toggles, edge labels show interfaces

from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ui.theme import apply_dark_theme, ThemeColors


# -----------------------------
# Data models (UI-facing)
# -----------------------------
@dataclass
class InterfaceIP:
    name: str
    ip: str


@dataclass
class VlanInfo:
    vid: str
    name: str


@dataclass
class RouteInfo:
    vrf: str
    prefix: str
    nexthop: str


@dataclass
class InterfaceInfo:
    name: str
    description: str = ""
    is_switchport: Optional[bool] = None  # True/False/None
    mode: str = ""  # access/trunk/routed/unknown
    access_vlan: str = ""
    trunk_vlans: str = ""
    channel_group: str = ""  # port-channel ID
    ip: str = ""


@dataclass
class PortChannelInfo:
    pc_id: str
    name: str  # "port-channel10"
    description: str = ""
    members: List[str] = field(default_factory=list)
    is_switchport: Optional[bool] = None
    mode: str = ""  # access/trunk/routed/unknown
    access_vlan: str = ""
    trunk_vlans: str = ""
    vpc: str = ""          # NX-OS
    mlag: str = ""         # Arista
    vlt: str = ""          # Dell


@dataclass
class DeviceSummary:
    hostname: str = "—"
    vendor: str = "—"
    mgmt_ip: str = "—"
    model: str = "—"
    os_ver: str = "—"

    # L2/L3 features
    vpc_domain: str = ""
    vpc_role: str = ""
    mlag: str = ""
    vlt_domain: str = ""

    # Parsed objects
    vlans: List[VlanInfo] = field(default_factory=list)
    l3_interfaces: List[InterfaceIP] = field(default_factory=list)
    interfaces: Dict[str, InterfaceInfo] = field(default_factory=dict)
    port_channels: Dict[str, PortChannelInfo] = field(default_factory=dict)

    routing_protocols: List[str] = field(default_factory=list)  # ospf/bgp/etc
    static_routes: List[RouteInfo] = field(default_factory=list)

    raw_text: str = ""


@dataclass
class Link:
    a: str
    b: str
    a_intf: str
    b_intf: str
    kind: str = "L2"      # "L2" or "L3"
    label: str = ""       # shown in topology
    confidence: str = "high"  # high/medium/low


@dataclass
class TopologyData:
    devices: Dict[str, DeviceSummary] = field(default_factory=dict)
    links: List[Link] = field(default_factory=list)


# -----------------------------
# Parsing helpers
# -----------------------------
HOST_RE = re.compile(r"^\s*hostname\s+(\S+)", re.IGNORECASE | re.MULTILINE)

# VLAN blocks vary; keep simple and safe
VLAN_RE = re.compile(r"^\s*vlan\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
VLAN_NAME_RE = re.compile(r"^\s*name\s+(.+)$", re.IGNORECASE | re.MULTILINE)

INT_RE = re.compile(r"^\s*interface\s+(\S+)", re.IGNORECASE | re.MULTILINE)
DESC_RE = re.compile(r"^\s*description\s+(.+)$", re.IGNORECASE | re.MULTILINE)

# NX-OS: ip address 10.0.0.1/31
IP_CIDR_RE = re.compile(r"^\s*ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\/(\d+)", re.IGNORECASE | re.MULTILINE)
# IOS/Dell sometimes: ip address A.B.C.D W.X.Y.Z
IP_MASK_RE = re.compile(r"^\s*ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", re.IGNORECASE | re.MULTILINE)

NO_SW_RE = re.compile(r"^\s*no\s+switchport\s*$", re.IGNORECASE | re.MULTILINE)
SW_MODE_RE = re.compile(r"^\s*switchport\s+mode\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
ACC_VLAN_RE = re.compile(r"^\s*switchport\s+access\s+vlan\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
TRUNK_VLANS_RE = re.compile(r"^\s*switchport\s+trunk\s+allowed\s+vlan\s+(.+)$", re.IGNORECASE | re.MULTILINE)
CHANNEL_GROUP_RE = re.compile(r"^\s*channel-group\s+(\d+)\s+mode\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)

# Port-channel indicators across vendors
PC_NAME_RE = re.compile(r"^(?:port-channel|Port-channel|Port-Channel|Po)(\d+)$", re.IGNORECASE)

# Routing / static route
ROUTER_OSPF_RE = re.compile(r"^\s*router\s+ospf\b", re.IGNORECASE | re.MULTILINE)
ROUTER_BGP_RE = re.compile(r"^\s*router\s+bgp\b", re.IGNORECASE | re.MULTILINE)
FEATURE_OSPF_RE = re.compile(r"^\s*feature\s+ospf\b", re.IGNORECASE | re.MULTILINE)
FEATURE_BGP_RE = re.compile(r"^\s*feature\s+bgp\b", re.IGNORECASE | re.MULTILINE)

# Static routes: NX-OS + IOS + Dell
# NX-OS: ip route 0.0.0.0/0 10.1.1.1
IP_ROUTE_CIDR_RE = re.compile(r"^\s*ip\s+route(?:\s+vrf\s+(\S+))?\s+(\d+\.\d+\.\d+\.\d+\/\d+)\s+(\d+\.\d+\.\d+\.\d+)", re.IGNORECASE | re.MULTILINE)
# IOS: ip route A.B.C.D W.X.Y.Z N.N.N.N
IP_ROUTE_MASK_RE = re.compile(r"^\s*ip\s+route(?:\s+vrf\s+(\S+))?\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", re.IGNORECASE | re.MULTILINE)

# vPC / MLAG / VLT
VPC_DOMAIN_RE = re.compile(r"^\s*vpc\s+domain\s+(\d+)", re.IGNORECASE | re.MULTILINE)
VPC_RE = re.compile(r"^\s*vpc\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
MLAG_RE = re.compile(r"^\s*mlag\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
VLT_DOMAIN_RE = re.compile(r"^\s*vlt\s+domain\s+(\d+)", re.IGNORECASE | re.MULTILINE)

NXOS_VENDOR_HINT = re.compile(r"nxos|nexus|feature\s+vpc|vpc\s+domain", re.IGNORECASE)
IOS_VENDOR_HINT = re.compile(r"catalyst|ios|spanning-tree|switchport", re.IGNORECASE)
ARISTA_HINT = re.compile(r"arista|eos|daemon\s+terminattr|mlag", re.IGNORECASE)
DELL_OS10_HINT = re.compile(r"os10|dell|vlt\s+domain|port-group", re.IGNORECASE)


def _guess_vendor(text: str) -> str:
    t = text.lower()
    if DELL_OS10_HINT.search(t):
        return "Dell OS10"
    if ARISTA_HINT.search(t):
        return "Arista EOS"
    if NXOS_VENDOR_HINT.search(t):
        return "Cisco Nexus (NX-OS)"
    if IOS_VENDOR_HINT.search(t):
        return "Cisco Catalyst (IOS/IOS-XE)"
    return "AUTODETECT"


def _mask_to_prefix(mask: str) -> int:
    parts = [int(p) for p in mask.split(".")]
    bits = "".join(f"{p:08b}" for p in parts)
    return bits.count("1")


def _norm_intf(name: str) -> str:
    n = name.strip()
    # normalize Port-Channel variants
    n = re.sub(r"^Po(\d+)$", r"port-channel\1", n, flags=re.IGNORECASE)
    n = n.replace("Port-Channel", "port-channel").replace("Port-channel", "port-channel")
    return n


def _parse_vlans(text: str) -> List[VlanInfo]:
    vlans: List[VlanInfo] = []
    for m in VLAN_RE.finditer(text):
        vid = m.group(1)
        start = m.end()
        window = text[start:start + 250]
        nm = VLAN_NAME_RE.search(window)
        name = nm.group(1).strip() if nm else "—"
        vlans.append(VlanInfo(vid=vid, name=name))

    seen = set()
    out: List[VlanInfo] = []
    for v in vlans:
        if v.vid not in seen:
            seen.add(v.vid)
            out.append(v)
    return out


def _iter_interface_blocks(text: str) -> List[Tuple[str, str]]:
    """
    Return list of (ifname, block_text).
    Works for NX-OS/EOS/Dell/IOS where interface stanza continues until next 'interface' line.
    """
    blocks: List[Tuple[str, str]] = []
    matches = list(INT_RE.finditer(text))
    for i, m in enumerate(matches):
        ifname = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        blocks.append((_norm_intf(ifname), block))
    return blocks


def _parse_interfaces_and_portchannels(d: DeviceSummary, text: str) -> None:
    for ifname, block in _iter_interface_blocks(text):
        iface = d.interfaces.get(ifname) or InterfaceInfo(name=ifname)

        dm = DESC_RE.search(block)
        if dm:
            iface.description = dm.group(1).strip().strip('"')

        if NO_SW_RE.search(block):
            iface.is_switchport = False
            iface.mode = "routed"
        else:
            # if we see any switchport statements, treat as switchport
            if re.search(r"^\s*switchport\b", block, re.IGNORECASE | re.MULTILINE):
                iface.is_switchport = True

        mm = SW_MODE_RE.search(block)
        if mm:
            iface.mode = mm.group(1).strip().lower()

        am = ACC_VLAN_RE.search(block)
        if am:
            iface.access_vlan = am.group(1).strip()

        tm = TRUNK_VLANS_RE.search(block)
        if tm:
            iface.trunk_vlans = tm.group(1).strip()

        cm = CHANNEL_GROUP_RE.search(block)
        if cm:
            iface.channel_group = cm.group(1).strip()

        # IP address parsing
        ip = ""
        ipm = IP_CIDR_RE.search(block)
        if ipm:
            ip = f"{ipm.group(1)}/{ipm.group(2)}"
        else:
            ipm2 = IP_MASK_RE.search(block)
            if ipm2:
                ip = f"{ipm2.group(1)}/{_mask_to_prefix(ipm2.group(2))}"
        iface.ip = ip
        if ip and iface.mode != "routed" and iface.is_switchport is False:
            iface.mode = "routed"

        d.interfaces[ifname] = iface

        # Build L3 interface list for summary
        if ip:
            d.l3_interfaces.append(InterfaceIP(name=ifname, ip=ip))

        # Port-channel record
        pcm = PC_NAME_RE.match(ifname)
        if pcm:
            pc_id = pcm.group(1)
            pc = d.port_channels.get(pc_id) or PortChannelInfo(pc_id=pc_id, name=f"port-channel{pc_id}")
            pc.description = iface.description or pc.description
            pc.is_switchport = iface.is_switchport
            pc.mode = iface.mode
            pc.access_vlan = iface.access_vlan
            pc.trunk_vlans = iface.trunk_vlans

            # NX-OS: "vpc 10"
            vpc_m = VPC_RE.search(block)
            if vpc_m:
                pc.vpc = vpc_m.group(1)

            # Arista: "mlag 10"
            mlag_m = MLAG_RE.search(block)
            if mlag_m:
                pc.mlag = mlag_m.group(1)

            d.port_channels[pc_id] = pc

    # Map member interfaces into port-channels
    for ifname, iface in d.interfaces.items():
        if iface.channel_group:
            pc = d.port_channels.get(iface.channel_group)
            if pc and ifname not in pc.members:
                pc.members.append(ifname)


def _parse_routing_and_routes(d: DeviceSummary, text: str) -> None:
    prots: List[str] = []
    if ROUTER_OSPF_RE.search(text) or FEATURE_OSPF_RE.search(text):
        prots.append("OSPF")
    if ROUTER_BGP_RE.search(text) or FEATURE_BGP_RE.search(text):
        prots.append("BGP")
    if re.search(r"^\s*router\s+eigrp\b", text, re.IGNORECASE | re.MULTILINE):
        prots.append("EIGRP")
    if re.search(r"^\s*router\s+isis\b", text, re.IGNORECASE | re.MULTILINE):
        prots.append("ISIS")
    d.routing_protocols = sorted(set(prots))

    # Static routes
    routes: List[RouteInfo] = []

    for m in IP_ROUTE_CIDR_RE.finditer(text):
        vrf = m.group(1) or "default"
        routes.append(RouteInfo(vrf=vrf, prefix=m.group(2), nexthop=m.group(3)))

    for m in IP_ROUTE_MASK_RE.finditer(text):
        vrf = m.group(1) or "default"
        prefix = f"{m.group(2)}/{_mask_to_prefix(m.group(3))}"
        routes.append(RouteInfo(vrf=vrf, prefix=prefix, nexthop=m.group(4)))

    # de-dupe
    seen = set()
    out: List[RouteInfo] = []
    for r in routes:
        k = (r.vrf, r.prefix, r.nexthop)
        if k not in seen:
            seen.add(k)
            out.append(r)
    d.static_routes = out


def _parse_vpc_mlag_vlt(d: DeviceSummary, text: str) -> None:
    vpcd = VPC_DOMAIN_RE.search(text)
    if vpcd:
        d.vpc_domain = vpcd.group(1)

    # Dell OS10 VLT domain
    vltd = VLT_DOMAIN_RE.search(text)
    if vltd:
        d.vlt_domain = vltd.group(1)


# -----------------------------
# Link inference (REAL links only)
# -----------------------------
# Example matches:
# "USATL04-AL19-Eth1/53"
# "USATL04-AL12_eth1/100"
# "UPLINK to C9500-Hun1/0/21"
REMOTE_HINT_RE = re.compile(
    r"(?P<dev>[A-Za-z0-9_.-]+)\s*[-_/ ]+\s*(?P<intf>(?:Eth|Ethernet|Gi|Gig|Te|Ten|Hu|Hundred|Fo|Forty|Po|Port-Channel|port-channel)\S+)",
    re.IGNORECASE,
)


def _extract_remote_from_desc(desc: str) -> Tuple[Optional[str], Optional[str]]:
    if not desc:
        return None, None
    s = desc.strip().strip('"')
    m = REMOTE_HINT_RE.search(s)
    if not m:
        return None, None
    dev = m.group("dev").strip()
    intf = _norm_intf(m.group("intf").strip())
    return dev, intf


def _link_kind_for_intf(d: DeviceSummary, ifname: str) -> str:
    iface = d.interfaces.get(ifname)
    if not iface:
        return "L2"
    # if routed or has ip, treat L3
    if iface.mode == "routed" or (iface.ip and iface.is_switchport is False):
        return "L3"
    return "L2"


def _build_links(topo: TopologyData) -> List[Link]:
    """
    Build links ONLY when we have evidence.
    Primary: mutual description match between two known devices.
    Secondary: one-sided match if target exists AND target has that interface stanza present
              (still medium confidence).
    """
    devices = topo.devices
    known = set(devices.keys())

    # Build hint map: A -> list of (B, A_if, B_if_hint)
    hints: Dict[str, List[Tuple[str, str, Optional[str]]]] = {k: [] for k in known}
    for a, d in devices.items():
        for ifname, iface in d.interfaces.items():
            b, b_if = _extract_remote_from_desc(iface.description)
            if b and b in known:
                hints[a].append((b, ifname, b_if))

        # also port-channel descriptions
        for pc_id, pc in d.port_channels.items():
            b, b_if = _extract_remote_from_desc(pc.description)
            if b and b in known:
                hints[a].append((b, f"port-channel{pc_id}", b_if))

    # Helper: does B have a hint back to A?
    def reverse_candidates(b: str, a: str) -> List[Tuple[str, str, Optional[str]]]:
        return [t for t in hints.get(b, []) if t[0] == a]

    links: List[Link] = []
    seen = set()

    # Mutual matches = HIGH confidence
    for a in known:
        for (b, a_if, b_if_hint) in hints[a]:
            revs = reverse_candidates(b, a)
            if not revs:
                continue

            # pick best reverse (prefer one that names our interface)
            chosen_b_if = revs[0][1]
            if b_if_hint:
                for (_a2, b_if, a_hint) in revs:
                    if a_hint and _norm_intf(a_hint) == _norm_intf(a_if):
                        chosen_b_if = b_if
                        break

            kind = _link_kind_for_intf(devices[a], a_if)
            if kind == "L2":
                # if either side appears routed, mark L3
                if _link_kind_for_intf(devices[b], chosen_b_if) == "L3":
                    kind = "L3"

            key = tuple(sorted([f"{a}:{a_if}", f"{b}:{chosen_b_if}", kind]))
            if key in seen:
                continue
            seen.add(key)

            links.append(
                Link(
                    a=a, b=b,
                    a_intf=a_if, b_intf=chosen_b_if,
                    kind=kind,
                    label=f"{a_if} ↔ {chosen_b_if}",
                    confidence="high",
                )
            )

    # One-sided matches = MEDIUM confidence (only if peer has that interface defined)
    for a in known:
        for (b, a_if, b_if_hint) in hints[a]:
            if any((l.a == a and l.b == b and l.a_intf == a_if) or (l.a == b and l.b == a and l.b_intf == a_if) for l in links):
                continue

            if not b_if_hint:
                continue
            if b_if_hint not in devices[b].interfaces and not PC_NAME_RE.match(b_if_hint):
                continue

            kind = _link_kind_for_intf(devices[a], a_if)
            if kind == "L2" and _link_kind_for_intf(devices[b], b_if_hint) == "L3":
                kind = "L3"

            key = tuple(sorted([f"{a}:{a_if}", f"{b}:{b_if_hint}", kind]))
            if key in seen:
                continue
            seen.add(key)

            links.append(
                Link(
                    a=a, b=b,
                    a_intf=a_if, b_intf=b_if_hint,
                    kind=kind,
                    label=f"{a_if} ↔ {b_if_hint}",
                    confidence="medium",
                )
            )

    return links


# -----------------------------
# Parse entrypoint used by UI
# -----------------------------
def parse_configs(paths: List[str]) -> TopologyData:
    topo = TopologyData()

    for p in paths:
        try:
            text = open(p, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue

        hostm = HOST_RE.search(text)
        hostname = hostm.group(1) if hostm else os.path.splitext(os.path.basename(p))[0]

        d = DeviceSummary(
            hostname=hostname,
            vendor=_guess_vendor(text),
            mgmt_ip="—",
            raw_text=text,
        )

        d.vlans = _parse_vlans(text)
        _parse_interfaces_and_portchannels(d, text)
        _parse_routing_and_routes(d, text)
        _parse_vpc_mlag_vlt(d, text)

        topo.devices[hostname] = d

    topo.links = _build_links(topo)
    return topo


# -----------------------------
# UI
# -----------------------------
class FabricWeaverApp(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master)

        self.colors: ThemeColors = apply_dark_theme(master)
        self._topo: TopologyData = TopologyData()
        self._active_device: Optional[str] = None

        self._show_interface_labels = tk.BooleanVar(value=True)
        self._show_vlan_ids = tk.BooleanVar(value=True)
        self._show_l2 = tk.BooleanVar(value=True)
        self._show_l3 = tk.BooleanVar(value=True)
        self._show_medium_conf = tk.BooleanVar(value=True)

        # topology manual layout
        self._node_pos: Dict[str, Tuple[int, int]] = {}
        self._dragging: Optional[str] = None
        self._drag_start: Tuple[int, int] = (0, 0)

        self._build_shell()
        self._build_tabs()
        self._build_statusbar()
        self._set_status("Ready")

    # ---- Shell / Tabs ----
    def _build_shell(self) -> None:
        self.configure(style="TFrame")
        self.pack(fill="both", expand=True)

        header = ttk.Frame(self, style="Panel.TFrame")
        header.pack(fill="x", padx=10, pady=(10, 0))

        title = ttk.Label(header, text="FabricWeaver", style="Header.TLabel")
        title.pack(side="left", padx=(12, 10), pady=10)

        self.scan_state = ttk.Label(header, text="●  Loaded: 0", style="Panel.TLabel")
        self.scan_state.pack(side="left", padx=8)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=(8, 0))

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_tabs(self) -> None:
        self.tab_devices = ttk.Frame(self.nb, style="TFrame")
        self.tab_topology = ttk.Frame(self.nb, style="TFrame")
        self.tab_raw = ttk.Frame(self.nb, style="TFrame")

        self.nb.add(self.tab_devices, text="Devices")
        self.nb.add(self.tab_topology, text="Topology")
        self.nb.add(self.tab_raw, text="Raw Data")

        self._build_devices_tab()
        self._build_topology_tab()
        self._build_raw_tab()

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self, style="Panel.TFrame")
        bar.pack(fill="x", padx=10, pady=(0, 10))

        self.status = ttk.Label(bar, text="", style="Panel.TLabel")
        self.status.pack(side="left", padx=12, pady=8)

        ttk.Button(bar, text="Options", command=self._open_options).pack(side="right", padx=12, pady=8)

    def _set_status(self, text: str) -> None:
        self.status.config(text=text)

    # ---- Devices tab ----
    def _build_devices_tab(self) -> None:
        root = self.tab_devices

        top = ttk.Frame(root, style="TFrame")
        top.pack(fill="x", pady=(0, 10))

        ttk.Button(top, text="Load Configs", style="Primary.TButton", command=self._load_configs).pack(side="left")
        ttk.Button(top, text="Export JSON", command=self._export_json).pack(side="left", padx=8)
        ttk.Button(top, text="Clear", command=self._clear_all).pack(side="left", padx=8)

        body = ttk.Frame(root, style="TFrame")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, style="Panel.TFrame")
        left.pack(side="left", fill="y", padx=(0, 10))

        ttk.Label(left, text="Devices", style="Header.TLabel").pack(anchor="w", padx=12, pady=(10, 8))

        self.device_list = tk.Listbox(
            left,
            bg=self.colors.panel,
            fg=self.colors.text,
            highlightthickness=1,
            highlightbackground=self.colors.border,
            selectbackground="#1f2a44",
            selectforeground=self.colors.text,
            relief="flat",
            width=26,
            height=22,
        )
        self.device_list.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.device_list.bind("<<ListboxSelect>>", self._on_device_select)

        right = ttk.Frame(body, style="Panel.TFrame")
        right.pack(side="left", fill="both", expand=True)

        self.detail_title = ttk.Label(right, text="Device Summary", style="Header.TLabel")
        self.detail_title.pack(anchor="w", padx=12, pady=(10, 8))

        self.detail_text = tk.Text(
            right,
            bg=self.colors.panel,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors.border,
            wrap="word",
        )
        self.detail_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.detail_text.config(state="disabled")

    def _render_device_summary(self, d: DeviceSummary) -> str:
        lines: List[str] = []
        lines.append("")
        lines.append("DEVICE")
        lines.append(f"Hostname : {d.hostname}")
        lines.append(f"Vendor   : {d.vendor}")
        lines.append(f"Mgmt IP  : {d.mgmt_ip}")
        if d.vpc_domain:
            lines.append(f"vPC Dom  : {d.vpc_domain}")
        if d.vlt_domain:
            lines.append(f"VLT Dom  : {d.vlt_domain}")
        lines.append("")

        # Routing / routes
        lines.append("L3: Routing")
        lines.append(f"Protocols: {', '.join(d.routing_protocols) if d.routing_protocols else '—'}")
        if d.static_routes:
            for r in d.static_routes[:30]:
                lines.append(f"Route    : vrf {r.vrf} {r.prefix} -> {r.nexthop}")
        else:
            lines.append("Routes   : —")
        lines.append("")

        # Port-channels
        lines.append("L2: Port-Channels")
        if d.port_channels:
            for pc_id in sorted(d.port_channels.keys(), key=lambda x: int(x) if x.isdigit() else 9999):
                pc = d.port_channels[pc_id]
                mem = ", ".join(pc.members[:10]) + ("…" if len(pc.members) > 10 else "")
                lines.append(f"{pc.name:<14} members: {mem or '—'}")
                if pc.trunk_vlans:
                    lines.append(f"  trunk vlans: {pc.trunk_vlans}")
                if pc.access_vlan:
                    lines.append(f"  access vlan: {pc.access_vlan}")
                if pc.description:
                    lines.append(f"  desc      : {pc.description}")
        else:
            lines.append("—")
        lines.append("")

        # VLANs
        lines.append("L2: VLANs")
        if d.vlans:
            for v in d.vlans[:80]:
                lines.append(f"VLAN {v.vid:<5} name: {v.name}")
        else:
            lines.append("—")
        lines.append("")

        # L3 interfaces
        lines.append("L3: Interfaces (with IP)")
        if d.l3_interfaces:
            for i in d.l3_interfaces[:80]:
                lines.append(f"{i.name:<18} {i.ip}")
        else:
            lines.append("—")
        lines.append("")

        # Interfaces (show key L2 info)
        lines.append("Interfaces (L2 details)")
        shown = 0
        for ifname in sorted(d.interfaces.keys()):
            iface = d.interfaces[ifname]
            if iface.mode in ("access", "trunk") or iface.trunk_vlans or iface.access_vlan:
                lines.append(f"{ifname:<18} mode={iface.mode or '—'} access={iface.access_vlan or '—'} trunk={iface.trunk_vlans or '—'}")
                if iface.description:
                    lines.append(f"  desc: {iface.description}")
                shown += 1
            if shown >= 60:
                lines.append("…")
                break
        if shown == 0:
            lines.append("—")

        lines.append("")
        return "\n".join(lines)

    def _on_device_select(self, _evt=None) -> None:
        sel = self.device_list.curselection()
        if not sel:
            return
        name = self.device_list.get(sel[0])
        self._active_device = name

        d = self._topo.devices.get(name)
        if not d:
            return

        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", self._render_device_summary(d))
        self.detail_text.config(state="disabled")

        self._render_raw(d)
        self._draw_topology()

    # ---- Topology tab ----
    def _build_topology_tab(self) -> None:
        root = self.tab_topology

        top = ttk.Frame(root, style="TFrame")
        top.pack(fill="x", pady=(0, 10))

        ttk.Button(top, text="Load Configs", style="Primary.TButton", command=self._load_configs).pack(side="left")
        ttk.Button(top, text="Re-Layout", command=self._auto_layout).pack(side="left", padx=8)

        ttk.Checkbutton(top, text="Show L2", variable=self._show_l2, command=self._draw_topology).pack(side="left", padx=(16, 0))
        ttk.Checkbutton(top, text="Show L3", variable=self._show_l3, command=self._draw_topology).pack(side="left", padx=8)
        ttk.Checkbutton(top, text="Show Medium", variable=self._show_medium_conf, command=self._draw_topology).pack(side="left", padx=8)
        ttk.Checkbutton(top, text="Edge Labels", variable=self._show_interface_labels, command=self._draw_topology).pack(side="left", padx=8)

        body = ttk.Frame(root, style="Panel.TFrame")
        body.pack(fill="both", expand=True)

        self.topo_canvas = tk.Canvas(
            body,
            bg=self.colors.panel2,
            highlightthickness=1,
            highlightbackground=self.colors.border,
            relief="flat",
        )
        self.topo_canvas.pack(fill="both", expand=True, padx=12, pady=12)

        # Drag support
        self.topo_canvas.bind("<ButtonPress-1>", self._on_canvas_down)
        self.topo_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.topo_canvas.bind("<ButtonRelease-1>", self._on_canvas_up)

        self.topo_canvas.bind("<Configure>", lambda e: self._draw_topology())

    def _auto_layout(self) -> None:
        """Simple grid layout (stable). Preserves manual drags if already positioned."""
        if not self._topo.devices:
            return
        c = self.topo_canvas
        w = max(600, c.winfo_width())
        h = max(400, c.winfo_height())

        names = sorted(self._topo.devices.keys())
        cols = max(2, int((w / 180)))
        x0, y0 = 120, 90
        dx, dy = 180, 120

        for idx, name in enumerate(names):
            if name in self._node_pos:
                continue
            r = idx // cols
            col = idx % cols
            self._node_pos[name] = (x0 + col * dx, y0 + r * dy)

        self._draw_topology()

    def _draw_topology(self) -> None:
        c = self.topo_canvas
        c.delete("all")

        if not self._topo.devices:
            c.create_text(
                20, 20, anchor="nw",
                fill=self.colors.muted,
                text="Load configs to build a topology view.",
                font=("Segoe UI", 11),
            )
            return

        # Ensure positions
        for name in self._topo.devices.keys():
            if name not in self._node_pos:
                self._auto_layout()
                break

        # Draw links first
        for link in self._topo.links:
            if link.kind == "L2" and not self._show_l2.get():
                continue
            if link.kind == "L3" and not self._show_l3.get():
                continue
            if link.confidence == "medium" and not self._show_medium_conf.get():
                continue

            if link.a not in self._node_pos or link.b not in self._node_pos:
                continue

            ax, ay = self._node_pos[link.a]
            bx, by = self._node_pos[link.b]

            color = self.colors.l2 if link.kind == "L2" else self.colors.l3
            width = 3 if link.kind == "L2" else 2
            dash = () if link.kind == "L2" else (6, 4)

            c.create_line(ax, ay, bx, by, fill=color, width=width, dash=dash)

            if self._show_interface_labels.get():
                mx, my = (ax + bx) // 2, (ay + by) // 2
                lbl = link.label or f"{link.a_intf} ↔ {link.b_intf}"
                if link.confidence == "medium":
                    lbl = f"{lbl} (med)"
                c.create_text(mx, my - 10, text=lbl, fill=self.colors.muted, font=("Segoe UI", 9))

        # Draw nodes
        for name in sorted(self._topo.devices.keys()):
            x, y = self._node_pos.get(name, (150, 150))
            is_active = (name == self._active_device)

            node_w, node_h = 140, 60
            x0, y0 = x - node_w // 2, y - node_h // 2
            x1, y1 = x + node_w // 2, y + node_h // 2

            fill = "#1b2232" if not is_active else "#223050"
            outline = self.colors.border if not is_active else self.colors.accent2

            # tag everything with the device name so we can drag it
            tag = f"node:{name}"

            c.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=2, tags=(tag,))
            c.create_text(x, y - 8, text=name, fill=self.colors.text, font=("Segoe UI", 10, "bold"), tags=(tag,))
            vendor = self._topo.devices[name].vendor
            c.create_text(x, y + 12, text=vendor, fill=self.colors.muted, font=("Segoe UI", 8), tags=(tag,))

    def _hit_test_node(self, x: int, y: int) -> Optional[str]:
        items = self.topo_canvas.find_overlapping(x, y, x, y)
        for it in items:
            tags = self.topo_canvas.gettags(it)
            for t in tags:
                if t.startswith("node:"):
                    return t.split("node:", 1)[1]
        return None

    def _on_canvas_down(self, evt) -> None:
        name = self._hit_test_node(evt.x, evt.y)
        if not name:
            self._dragging = None
            return
        self._dragging = name
        self._drag_start = (evt.x, evt.y)

        # select device when clicked
        self._active_device = name
        self._sync_device_list_selection(name)
        self._draw_topology()

    def _on_canvas_drag(self, evt) -> None:
        if not self._dragging:
            return
        dx = evt.x - self._drag_start[0]
        dy = evt.y - self._drag_start[1]
        x, y = self._node_pos.get(self._dragging, (evt.x, evt.y))
        self._node_pos[self._dragging] = (x + dx, y + dy)
        self._drag_start = (evt.x, evt.y)
        self._draw_topology()

    def _on_canvas_up(self, _evt) -> None:
        self._dragging = None

    def _sync_device_list_selection(self, name: str) -> None:
        # highlight listbox selection when clicking on canvas
        items = self.device_list.get(0, "end")
        for i, v in enumerate(items):
            if v == name:
                self.device_list.selection_clear(0, "end")
                self.device_list.selection_set(i)
                self.device_list.see(i)
                break

    # ---- Raw tab ----
    def _build_raw_tab(self) -> None:
        root = self.tab_raw

        top = ttk.Frame(root, style="TFrame")
        top.pack(fill="x", pady=(0, 10))

        ttk.Button(top, text="Load Configs", style="Primary.TButton", command=self._load_configs).pack(side="left")
        ttk.Button(top, text="Copy", command=self._copy_raw).pack(side="left", padx=8)

        body = ttk.Frame(root, style="Panel.TFrame")
        body.pack(fill="both", expand=True)

        self.raw_title = ttk.Label(body, text="Raw Config — (select a device)", style="Header.TLabel")
        self.raw_title.pack(anchor="w", padx=12, pady=(10, 8))

        self.raw_text = tk.Text(
            body,
            bg=self.colors.panel,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors.border,
            wrap="none",
        )
        self.raw_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.raw_text.config(state="disabled")

    def _render_raw(self, d: DeviceSummary) -> None:
        self.raw_title.config(text=f"Raw Config — {d.hostname}")
        self.raw_text.config(state="normal")
        self.raw_text.delete("1.0", "end")
        self.raw_text.insert("1.0", d.raw_text or "")
        self.raw_text.config(state="disabled")

    def _copy_raw(self) -> None:
        if not self._active_device:
            return
        d = self._topo.devices.get(self._active_device)
        if not d:
            return
        self.clipboard_clear()
        self.clipboard_append(d.raw_text or "")
        self._set_status(f"Copied raw config for {d.hostname}")

    # ---- Options dialog ----
    def _open_options(self) -> None:
        win = tk.Toplevel(self)
        win.title("Options")
        win.configure(bg=self.colors.bg)
        win.resizable(False, False)

        apply_dark_theme(win, self.colors)

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=12, pady=12)

        tab_general = ttk.Frame(nb, style="Panel.TFrame")
        nb.add(tab_general, text="Display")

        ttk.Label(tab_general, text="Topology Display", style="Header.TLabel").pack(anchor="w", padx=12, pady=(12, 8))

        display = ttk.Frame(tab_general, style="Panel.TFrame")
        display.pack(fill="x", padx=12, pady=(0, 12))

        ttk.Checkbutton(display, text="Show L2 Links", variable=self._show_l2, command=self._draw_topology).pack(anchor="w", pady=4)
        ttk.Checkbutton(display, text="Show L3 Links", variable=self._show_l3, command=self._draw_topology).pack(anchor="w", pady=4)
        ttk.Checkbutton(display, text="Show Medium Confidence Links", variable=self._show_medium_conf, command=self._draw_topology).pack(anchor="w", pady=4)
        ttk.Checkbutton(display, text="Show Edge Labels", variable=self._show_interface_labels, command=self._draw_topology).pack(anchor="w", pady=4)

        btns = ttk.Frame(win, style="TFrame")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btns, text="Close", style="Primary.TButton", command=win.destroy).pack(side="right")

        win.grab_set()
        win.transient(self.winfo_toplevel())

    # ---- Actions ----
    def _load_configs(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select device configs",
            filetypes=[("Config / Text", "*.txt *.log *.cfg *.*")],
        )
        if not paths:
            return

        self._set_status("Parsing configs…")
        self.update_idletasks()

        topo = parse_configs(list(paths))
        self._topo = topo

        self.device_list.delete(0, "end")
        for name in sorted(self._topo.devices.keys()):
            self.device_list.insert("end", name)

        self._active_device = None
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", "\n\nSelect a device on the left to view details.")
        self.detail_text.config(state="disabled")

        self.raw_text.config(state="normal")
        self.raw_text.delete("1.0", "end")
        self.raw_text.insert("1.0", "")
        self.raw_text.config(state="disabled")
        self.raw_title.config(text="Raw Config — (select a device)")

        self.scan_state.config(text=f"●  Loaded: {len(self._topo.devices)}")
        self._auto_layout()
        self._set_status(f"Loaded {len(self._topo.devices)} config(s) — Links: {len(self._topo.links)}")

    def _clear_all(self) -> None:
        self._topo = TopologyData()
        self._active_device = None
        self._node_pos.clear()

        self.device_list.delete(0, "end")

        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.config(state="disabled")

        self.raw_text.config(state="normal")
        self.raw_text.delete("1.0", "end")
        self.raw_text.config(state="disabled")
        self.raw_title.config(text="Raw Config — (select a device)")

        self.scan_state.config(text="●  Loaded: 0")
        self._draw_topology()
        self._set_status("Cleared")

    def _export_json(self) -> None:
        if not self._topo.devices:
            messagebox.showwarning("Export", "No topology loaded.")
            return

        out = {
            "devices": {},
            "links": [],
        }
        for hn, d in self._topo.devices.items():
            out["devices"][hn] = {
                "hostname": d.hostname,
                "vendor": d.vendor,
                "mgmt_ip": d.mgmt_ip,
                "vpc_domain": d.vpc_domain,
                "vlt_domain": d.vlt_domain,
                "routing_protocols": d.routing_protocols,
                "static_routes": [r.__dict__ for r in d.static_routes],
                "vlans": [v.__dict__ for v in d.vlans],
                "interfaces": {k: v.__dict__ for k, v in d.interfaces.items()},
                "port_channels": {k: v.__dict__ for k, v in d.port_channels.items()},
                "positions": {"x": self._node_pos.get(hn, (0, 0))[0], "y": self._node_pos.get(hn, (0, 0))[1]},
            }

        for l in self._topo.links:
            out["links"].append(l.__dict__)

        save_path = filedialog.asksaveasfilename(
            title="Export topology JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not save_path:
            return

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)

        self._set_status(f"Exported JSON: {os.path.basename(save_path)}")
        messagebox.showinfo("Export", f"Exported:\n{save_path}")


# (IMPORTANT) Do NOT add broken aliases here.
# The entrypoint imports FabricWeaverApp from ui.layout, so this is the only public class.