# FabricWeaver - Desktop App (Tkinter)
# Layout B: Sidebar (devices) + Notebook (Details/Topology/Raw) + Right Inspector
#
# Single-file replacement for: fabricweaver/fabricweaver.py
#
# Goals:
# - Clean, information-rich Device Details (clear L2/L3 separation + vPC reasoning)
# - Evidence-based topology links (CDP > vPC peer-link > desc mutual > desc one-side > IP-subnet)
# - Robust parsing adapters (so orchestrator API mismatches won't crash the UI)
# - Dark earth-tone theme (uses ui.theme if available; otherwise fallback theme embedded here)
#
# Notes:
# - This file can run standalone even if parser/ and core/ are incomplete.
# - If your parser/core modules exist, this file will try to use them, but always has safe fallbacks.

from __future__ import annotations

import json
import os
import re
import ipaddress
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any, Set

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ============================================================
# Theme (prefer ui.theme; fallback if missing)
# ============================================================

@dataclass
class ThemeColors:
    bg: str = "#0f1116"
    panel: str = "#171a21"
    panel2: str = "#1c2028"
    text: str = "#e8e3d7"
    muted: str = "#a9a394"
    border: str = "#2b313c"
    accent: str = "#c47f2c"    # earth orange
    accent2: str = "#8da36b"   # sage
    l2: str = "#c47f2c"
    l3: str = "#6b8aa3"


def _apply_dark_theme_fallback(root: tk.Misc, base: Optional[ThemeColors] = None) -> ThemeColors:
    c = base or ThemeColors()
    try:
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=c.bg, foreground=c.text, bordercolor=c.border)
        style.configure("TFrame", background=c.bg)
        style.configure("Panel.TFrame", background=c.panel)
        style.configure("Card.TFrame", background=c.panel2)

        style.configure("TLabel", background=c.bg, foreground=c.text)
        style.configure("Panel.TLabel", background=c.panel, foreground=c.muted)
        style.configure("Header.TLabel", background=c.panel, foreground=c.text, font=("Segoe UI", 11, "bold"))
        style.configure("Section.TLabel", background=c.panel, foreground=c.text, font=("Segoe UI", 10, "bold"))
        style.configure("Muted.TLabel", background=c.panel, foreground=c.muted, font=("Segoe UI", 9))

        style.configure("TButton", padding=(10, 7), background=c.panel2, foreground=c.text)
        style.map("TButton", background=[("active", c.border), ("pressed", c.border)])

        # Accent button style for important actions (keeps consistent highlight)
        style.configure("Accent.TButton", padding=(8, 6), background=c.accent, foreground="#111111")
        style.map("Accent.TButton",
              background=[("active", c.accent2), ("pressed", c.accent2)],
              foreground=[("active", "#111111"), ("pressed", "#111111")])

        style.configure("Primary.TButton", padding=(10, 7), background=c.accent, foreground="#111111")
        style.map("Primary.TButton",
                  background=[("active", c.accent2), ("pressed", c.accent2)],
                  foreground=[("active", "#111111"), ("pressed", "#111111")])

        style.configure("TNotebook", background=c.bg, borderwidth=0)
        style.configure("TNotebook.Tab", background=c.panel2, foreground=c.muted, padding=(12, 8))
        style.map("TNotebook.Tab",
                  background=[("selected", c.panel), ("active", c.panel)],
                  foreground=[("selected", c.text), ("active", c.text)])

        style.configure("Treeview",
                        background=c.panel,
                        fieldbackground=c.panel,
                        foreground=c.text,
                        bordercolor=c.border,
                        rowheight=22)
        style.configure("Treeview.Heading",
                        background=c.panel2,
                        foreground=c.text,
                        bordercolor=c.border,
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview",
                  background=[("selected", "#223050")],
                  foreground=[("selected", c.text)])

        style.configure("TSeparator", background=c.border)

        # Checkbutton / Toggle visibility styling - orange accent when checked
        try:
            style.configure("Toggle.TCheckbutton", background=c.panel, foreground=c.text)
            style.map("Toggle.TCheckbutton",
                      background=[("active", c.accent), ("selected", c.accent)],
                      foreground=[("active", "#111111"), ("selected", "#111111")])
        except Exception:
            pass

        if isinstance(root, (tk.Tk, tk.Toplevel)):
            root.configure(bg=c.bg)
    except Exception:
        pass
    return c


try:
    from ui.theme import apply_dark_theme as _apply_dark_theme_real  # type: ignore
    from ui.theme import ThemeColors as _ThemeColorsReal  # type: ignore

    def apply_dark_theme(root: tk.Misc, colors: Optional[Any] = None) -> Any:
        try:
            if colors is None:
                return _apply_dark_theme_real(root)
            return _apply_dark_theme_real(root, colors)
        except TypeError:
            return _apply_dark_theme_real(root)

    ThemeColors = _ThemeColorsReal  # type: ignore

except Exception:
    def apply_dark_theme(root: tk.Misc, colors: Optional[ThemeColors] = None) -> ThemeColors:
        return _apply_dark_theme_fallback(root, colors)


# ============================================================
# Data models
# ============================================================

@dataclass
class VlanInfo:
    vid: str
    name: str = "—"


@dataclass
class RouteInfo:
    vrf: str
    prefix: str
    nexthop: str


@dataclass
class FhrpGroup:
    protocol: str  # HSRP/VRRP
    iface: str
    group: str
    vip: str = ""
    priority: str = ""


@dataclass
class InterfaceInfo:
    name: str
    description: str = ""
    is_switchport: Optional[bool] = None
    mode: str = ""  # access/trunk/routed/unknown
    access_vlan: str = ""
    trunk_vlans_raw: str = ""
    trunk_vlans_list: List[str] = field(default_factory=list)
    native_vlan: str = ""
    channel_group: str = ""
    ip: str = ""              # ip/prefix
    vrf: str = ""
    is_svi: bool = False
    svi_vlan: str = ""


@dataclass
class PortChannelInfo:
    pc_id: str
    name: str
    description: str = ""
    members: List[str] = field(default_factory=list)
    is_switchport: Optional[bool] = None
    mode: str = ""
    access_vlan: str = ""
    trunk_vlans_raw: str = ""
    trunk_vlans_list: List[str] = field(default_factory=list)
    native_vlan: str = ""
    vpc_id: str = ""
    mlag_id: str = ""
    vlt_id: str = ""
    is_peer_link: bool = False


@dataclass
class CdpAdjacency:
    local_device: str
    local_intf: str
    neighbor_device: str
    neighbor_intf: str = ""


@dataclass
class PairInference:
    kind: str  # vPC/MLAG/VLT
    a: str
    b: str
    confidence: str
    reasons: List[str] = field(default_factory=list)
    details: Dict[str, str] = field(default_factory=dict)


@dataclass
class DeviceSummary:
    hostname: str
    vendor: str = "AUTODETECT"
    model: str = "—"
    os_ver: str = "—"
    mgmt_ip: str = "—"

    vlans: List[VlanInfo] = field(default_factory=list)
    interfaces: Dict[str, InterfaceInfo] = field(default_factory=dict)
    port_channels: Dict[str, PortChannelInfo] = field(default_factory=dict)

    vrfs: Dict[str, List[str]] = field(default_factory=dict)
    routing_protocols: List[str] = field(default_factory=list)
    bgp_asn: str = ""  # Extracted from "router bgp ASN"
    static_routes: List[RouteInfo] = field(default_factory=list)
    fhrp: List[FhrpGroup] = field(default_factory=list)

    stp_mode: str = ""
    stp_priority: str = ""

    vpc_configured: bool = False
    vpc_domain: str = ""
    vpc_keepalive_dst: str = ""
    vpc_keepalive_src: str = ""
    vpc_peerlink_po: str = ""
    vpc_peerlink_members: List[str] = field(default_factory=list)

    mlag_domain: str = ""
    vlt_domain: str = ""

    cdp: List[CdpAdjacency] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class Link:
    a: str
    b: str
    a_intf: str
    b_intf: str
    kind: str = "L2"
    confidence: str = "high"
    evidence: str = "desc"
    label: str = ""


@dataclass
class TopologyData:
    devices: Dict[str, DeviceSummary] = field(default_factory=dict)
    links: List[Link] = field(default_factory=list)
    pairs: List[PairInference] = field(default_factory=list)


# ============================================================
# Embedded parsing (fallback / default)
# ============================================================

HOST_RE = re.compile(r"^\s*hostname\s+(\S+)", re.IGNORECASE | re.MULTILINE)

VLAN_RE = re.compile(r"^\s*vlan\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
VLAN_NAME_RE = re.compile(r"^\s*name\s+(.+)$", re.IGNORECASE | re.MULTILINE)

INT_RE = re.compile(r"^\s*interface\s+(\S+)", re.IGNORECASE | re.MULTILINE)
DESC_RE = re.compile(r"^\s*description\s+(.+)$", re.IGNORECASE | re.MULTILINE)

NO_SW_RE = re.compile(r"^\s*no\s+switchport\s*$", re.IGNORECASE | re.MULTILINE)
SW_MODE_RE = re.compile(r"^\s*switchport\s+mode\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
ACC_VLAN_RE = re.compile(r"^\s*switchport\s+access\s+vlan\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
TRUNK_VLANS_RE = re.compile(r"^\s*switchport\s+trunk\s+allowed\s+vlan\s+(.+)$", re.IGNORECASE | re.MULTILINE)
NATIVE_VLAN_RE = re.compile(r"^\s*switchport\s+trunk\s+native\s+vlan\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
CHANNEL_GROUP_RE = re.compile(r"^\s*channel-group\s+(\d+)\s+mode\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)

IP_CIDR_RE = re.compile(r"^\s*ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\/(\d+)", re.IGNORECASE | re.MULTILINE)
IP_MASK_RE = re.compile(r"^\s*ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", re.IGNORECASE | re.MULTILINE)

VRF_DEF_RE = re.compile(r"^\s*(?:vrf\s+definition|vrf\s+context)\s+(\S+)", re.IGNORECASE | re.MULTILINE)
VRF_FWD_RE = re.compile(r"^\s*vrf\s+forwarding\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
VRF_MEMBER_RE = re.compile(r"^\s*vrf\s+member\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)

ROUTER_OSPF_RE = re.compile(r"^\s*router\s+ospf\b", re.IGNORECASE | re.MULTILINE)
ROUTER_BGP_RE = re.compile(r"^\s*router\s+bgp\s+(\d+)", re.IGNORECASE | re.MULTILINE)
FEATURE_OSPF_RE = re.compile(r"^\s*feature\s+ospf\b", re.IGNORECASE | re.MULTILINE)
FEATURE_BGP_RE = re.compile(r"^\s*feature\s+bgp\b", re.IGNORECASE | re.MULTILINE)

IP_ROUTE_CIDR_RE = re.compile(
    r"^\s*ip\s+route(?:\s+vrf\s+(\S+))?\s+(\d+\.\d+\.\d+\.\d+\/\d+)\s+(\d+\.\d+\.\d+\.\d+)",
    re.IGNORECASE | re.MULTILINE
)
IP_ROUTE_MASK_RE = re.compile(
    r"^\s*ip\s+route(?:\s+vrf\s+(\S+))?\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)",
    re.IGNORECASE | re.MULTILINE
)

STP_MODE_RE = re.compile(r"^\s*spanning-tree\s+mode\s+(\S+)", re.IGNORECASE | re.MULTILINE)
STP_PRI_RE = re.compile(r"^\s*spanning-tree\s+vlan\s+[\d,\- ]+\s+priority\s+(\d+)", re.IGNORECASE | re.MULTILINE)
STP_PRI_GLOBAL_RE = re.compile(r"^\s*spanning-tree\s+priority\s+(\d+)", re.IGNORECASE | re.MULTILINE)

PC_NAME_RE = re.compile(r"^(?:port-channel|Port-channel|Port-Channel|Po)(\d+)$", re.IGNORECASE)

# vPC
FEATURE_VPC_RE = re.compile(r"^\s*feature\s+vpc\b", re.IGNORECASE | re.MULTILINE)
VPC_DOMAIN_RE = re.compile(r"^\s*vpc\s+domain\s+(\d+)", re.IGNORECASE | re.MULTILINE)
VPC_KEEPALIVE_RE = re.compile(
    r"^\s*peer-keepalive\s+destination\s+(\d+\.\d+\.\d+\.\d+)(?:\s+source\s+(\S+))?",
    re.IGNORECASE | re.MULTILINE
)
VPC_MEMBER_RE = re.compile(r"^\s*vpc\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
VPC_PEERLINK_CMD_RE = re.compile(r"^\s*vpc\s+peer-link\s*$", re.IGNORECASE | re.MULTILINE)

# Dell VLT / Arista MLAG (light)
VLT_DOMAIN_RE = re.compile(r"^\s*vlt\s+domain\s+(\d+)", re.IGNORECASE | re.MULTILINE)
ARISTA_MLAG_CONFIG_RE = re.compile(r"^\s*mlag\s+configuration\b", re.IGNORECASE | re.MULTILINE)
ARISTA_MLAG_ID_RE = re.compile(r"^\s*mlag\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)

# Vendor detection hints
NXOS_VENDOR_HINT = re.compile(r"nxos|nexus|feature\s+vpc|vpc\s+domain", re.IGNORECASE)
IOS_VENDOR_HINT = re.compile(r"catalyst|cisco ios|spanning-tree|switchport", re.IGNORECASE)
ARISTA_HINT = re.compile(r"arista|eos|daemon\s+terminattr|mlag\s+configuration", re.IGNORECASE)
DELL_OS10_HINT = re.compile(r"os10|dell|vlt\s+domain|port-group", re.IGNORECASE)

# show version hints (best effort)
MODEL_RE = re.compile(r"(?im)^\s*Model\s*:\s*(.+)$|^\s*Model number\s*:\s*(.+)$|^\s*cisco\s+nexus\s+(\S+)", re.MULTILINE)
NXOS_VER_RE = re.compile(r"(?im)\bNXOS:\s+version\s+(\S+)|\bsystem:\s+version\s+(\S+)", re.MULTILINE)
IOS_VER_RE = re.compile(r"(?im)\bCisco IOS.*Version\s+([\w.()]+)", re.MULTILINE)
EOS_VER_RE = re.compile(r"(?im)\bSoftware image version:\s*(\S+)|\bEOS version\s+(\S+)", re.MULTILINE)

# Description remote hints
REMOTE_HINT_RE = re.compile(
    r"(?P<dev>[A-Za-z0-9_.-]+)\s*[-_/ ]+\s*(?P<intf>(?:Eth|Ethernet|Gi|Gig|Te|Ten|Hu|Hundred|Fo|Forty|Po|Port-Channel|port-channel)\S+)",
    re.IGNORECASE,
)

# CDP parsing (detail + neighbors)
CDP_DETAIL_DEVICE_RE = re.compile(r"(?im)^\s*Device ID:\s*(\S+)\s*$")
CDP_DETAIL_LOCAL_RE = re.compile(r"(?im)^\s*Interface:\s*([^,]+),\s*Port ID\s*\(outgoing port\)\s*:\s*(.+)\s*$")
CDP_NEIGHBORS_ROW_RE = re.compile(r"(?im)^\s*(\S+)\s+(\S+)\s+\d+\s+[\w ]+\s+\S+\s+(\S+)\s*$")


def _mask_to_prefix(mask: str) -> int:
    parts = [int(p) for p in mask.split(".")]
    bits = "".join(f"{p:08b}" for p in parts)
    return bits.count("1")


def _norm_intf(name: str) -> str:
    n = (name or "").strip()
    n = re.sub(r"^Po(\d+)$", r"port-channel\1", n, flags=re.IGNORECASE)
    n = n.replace("Port-Channel", "port-channel").replace("Port-channel", "port-channel")
    return n


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


def _parse_show_version(d: DeviceSummary, text: str) -> None:
    mm = MODEL_RE.search(text)
    if mm:
        for g in mm.groups():
            if g and g.strip():
                d.model = g.strip()
                break
    vm = NXOS_VER_RE.search(text) or IOS_VER_RE.search(text) or EOS_VER_RE.search(text)
    if vm:
        for g in vm.groups():
            if g and g.strip():
                d.os_ver = g.strip()
                break


def _parse_vlans(text: str) -> List[VlanInfo]:
    vlans: List[VlanInfo] = []
    for m in VLAN_RE.finditer(text):
        vid = m.group(1)
        start = m.end()
        window = text[start:start + 300]
        nm = VLAN_NAME_RE.search(window)
        name = nm.group(1).strip().strip('"') if nm else "—"
        vlans.append(VlanInfo(vid=vid, name=name))
    # de-dupe
    out: List[VlanInfo] = []
    seen = set()
    for v in vlans:
        if v.vid not in seen:
            seen.add(v.vid)
            out.append(v)
    return out


def _iter_interface_blocks(text: str) -> List[Tuple[str, str]]:
    blocks: List[Tuple[str, str]] = []
    matches = list(INT_RE.finditer(text))
    for i, m in enumerate(matches):
        ifname = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        blocks.append((_norm_intf(ifname), block))
    return blocks


def _expand_vlan_list(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    # Strip obvious noise, keep "all" if present
    raw = raw.replace("add", "").replace("except", "").strip()
    tokens = re.split(r"[,\s]+", raw)
    out: List[str] = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        if t.lower() == "all":
            out.append("all")
            continue
        if "-" in t and re.match(r"^\d+\-\d+$", t):
            a, b = t.split("-", 1)
            try:
                aa, bb = int(a), int(b)
                if 0 < aa <= bb <= 4094 and (bb - aa) <= 4094:
                    out.extend([str(x) for x in range(aa, bb + 1)])
                    continue
            except Exception:
                pass
        out.append(t)
    # de-dupe preserve order
    seen = set()
    dedup: List[str] = []
    for v in out:
        if v not in seen:
            seen.add(v)
            dedup.append(v)
    return dedup


def _parse_interfaces_and_portchannels(d: DeviceSummary, text: str) -> None:
    # Interface parsing
    for ifname, block in _iter_interface_blocks(text):
        iface = d.interfaces.get(ifname) or InterfaceInfo(name=ifname)

        dm = DESC_RE.search(block)
        if dm:
            iface.description = dm.group(1).strip().strip('"')

        # VRF
        vfm = VRF_FWD_RE.search(block) or VRF_MEMBER_RE.search(block)
        if vfm:
            iface.vrf = vfm.group(1).strip()

        # switchport/no switchport
        if NO_SW_RE.search(block):
            iface.is_switchport = False
            iface.mode = "routed"
        else:
            if re.search(r"(?im)^\s*switchport\b", block):
                iface.is_switchport = True

        mm = SW_MODE_RE.search(block)
        if mm:
            iface.mode = mm.group(1).strip().lower()

        am = ACC_VLAN_RE.search(block)
        if am:
            iface.access_vlan = am.group(1).strip()

        tm = TRUNK_VLANS_RE.search(block)
        if tm:
            iface.trunk_vlans_raw = tm.group(1).strip()
            iface.trunk_vlans_list = _expand_vlan_list(iface.trunk_vlans_raw)

        nv = NATIVE_VLAN_RE.search(block)
        if nv:
            iface.native_vlan = nv.group(1).strip()

        cm = CHANNEL_GROUP_RE.search(block)
        if cm:
            iface.channel_group = cm.group(1).strip()

        # IP address
        ip = ""
        ipm = IP_CIDR_RE.search(block)
        if ipm:
            ip = f"{ipm.group(1)}/{ipm.group(2)}"
        else:
            ipm2 = IP_MASK_RE.search(block)
            if ipm2:
                ip = f"{ipm2.group(1)}/{_mask_to_prefix(ipm2.group(2))}"
        iface.ip = ip

        # SVI detection
        m = re.match(r"(?i)^vlan(\d+)$", ifname)
        if m:
            iface.is_svi = True
            iface.svi_vlan = m.group(1)

        d.interfaces[ifname] = iface

        # Port-channel record
        pcm = PC_NAME_RE.match(ifname)
        if pcm:
            pc_id = pcm.group(1)
            pc = d.port_channels.get(pc_id) or PortChannelInfo(pc_id=pc_id, name=f"port-channel{pc_id}")
            pc.description = iface.description or pc.description
            pc.is_switchport = iface.is_switchport
            pc.mode = iface.mode
            pc.access_vlan = iface.access_vlan
            pc.trunk_vlans_raw = iface.trunk_vlans_raw
            pc.trunk_vlans_list = list(iface.trunk_vlans_list)
            pc.native_vlan = iface.native_vlan

            # vPC member
            vpc_m = VPC_MEMBER_RE.search(block)
            if vpc_m:
                pc.vpc_id = vpc_m.group(1).strip()

            # peer-link marker
            if VPC_PEERLINK_CMD_RE.search(block) or ("peer-link" in (iface.description or "").lower()):
                pc.is_peer_link = True

            # MLAG member
            mlag_m = ARISTA_MLAG_ID_RE.search(block)
            if mlag_m:
                pc.mlag_id = mlag_m.group(1).strip()

            d.port_channels[pc_id] = pc

    # Port-channel members
    for ifname, iface in d.interfaces.items():
        if iface.channel_group:
            pc = d.port_channels.get(iface.channel_group)
            if pc and ifname not in pc.members:
                pc.members.append(ifname)

    # mgmt IP best-effort
    for ifn, iface in d.interfaces.items():
        if re.match(r"(?i)^mgmt0$", ifn) or re.match(r"(?i)^management\d+$", ifn):
            if iface.ip:
                d.mgmt_ip = iface.ip.split("/", 1)[0]
                break


def _parse_vrfs(d: DeviceSummary, text: str) -> None:
    vrfs: Set[str] = set()
    for m in VRF_DEF_RE.finditer(text):
        vrfs.add(m.group(1).strip())
    # Build membership from interface vrf fields
    membership: Dict[str, List[str]] = {v: [] for v in vrfs}
    membership.setdefault("default", [])
    for ifn, iface in d.interfaces.items():
        v = iface.vrf.strip() if iface.vrf else "default"
        membership.setdefault(v, [])
        membership[v].append(ifn)
    d.vrfs = membership


def _parse_routing_and_routes(d: DeviceSummary, text: str) -> None:
    prots: Set[str] = set()
    if ROUTER_OSPF_RE.search(text) or FEATURE_OSPF_RE.search(text):
        prots.add("OSPF")
    bgp_asn = ""
    bgpm = ROUTER_BGP_RE.search(text)
    if bgpm:
        prots.add("BGP")
        bgp_asn = bgpm.group(1).strip()
    elif FEATURE_BGP_RE.search(text):
        prots.add("BGP")

    # extra routing detectors
    if re.search(r"(?im)^\s*router\s+eigrp\b", text):
        prots.add("EIGRP")
    if re.search(r"(?im)^\s*router\s+isis\b", text):
        prots.add("ISIS")

    d.routing_protocols = sorted(prots)
    if bgp_asn:
        d.bgp_asn = bgp_asn

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


def _parse_stp(d: DeviceSummary, text: str) -> None:
    m = STP_MODE_RE.search(text)
    if m:
        d.stp_mode = m.group(1).strip()
    mp = STP_PRI_RE.search(text) or STP_PRI_GLOBAL_RE.search(text)
    if mp:
        d.stp_priority = mp.group(1).strip()


def _parse_vpc_mlag_vlt(d: DeviceSummary, text: str) -> None:
    if FEATURE_VPC_RE.search(text) or VPC_DOMAIN_RE.search(text):
        d.vpc_configured = True

    vpcd = VPC_DOMAIN_RE.search(text)
    if vpcd:
        d.vpc_domain = vpcd.group(1).strip()

    keep = VPC_KEEPALIVE_RE.search(text)
    if keep:
        d.vpc_keepalive_dst = keep.group(1).strip()
        d.vpc_keepalive_src = (keep.group(2) or "").strip()

    # Identify peer-link Po from "interface port-channelX" with "vpc peer-link"
    for pc_id, pc in d.port_channels.items():
        if pc.is_peer_link:
            d.vpc_peerlink_po = f"port-channel{pc_id}"
            d.vpc_peerlink_members = list(pc.members)
            break

    # VLT
    vltd = VLT_DOMAIN_RE.search(text)
    if vltd:
        d.vlt_domain = vltd.group(1).strip()

    # MLAG domain-ish marker
    if ARISTA_MLAG_CONFIG_RE.search(text):
        d.mlag_domain = "configured"


def _parse_cdp(d: DeviceSummary, text: str) -> None:
    # show cdp neighbors detail blocks
    # We associate blocks with the local device (d.hostname) and store adjacencies.
    adjs: List[CdpAdjacency] = []

    # If "show cdp neighbors detail" is pasted, it's typically multiple repeating sections.
    # We'll parse by finding Device ID then the Interface line following it.
    device_ids = list(CDP_DETAIL_DEVICE_RE.finditer(text))
    for i, m in enumerate(device_ids):
        neighbor = m.group(1).strip()
        start = m.end()
        end = device_ids[i + 1].start() if i + 1 < len(device_ids) else len(text)
        block = text[start:end]
        lm = CDP_DETAIL_LOCAL_RE.search(block)
        if lm:
            local_intf = _norm_intf(lm.group(1).strip())
            neigh_intf = _norm_intf(lm.group(2).strip())
            adjs.append(CdpAdjacency(local_device=d.hostname, local_intf=local_intf,
                                     neighbor_device=neighbor, neighbor_intf=neigh_intf))

    # If only "show cdp neighbors" table exists, we parse best-effort rows.
    for m in CDP_NEIGHBORS_ROW_RE.finditer(text):
        neighbor = m.group(1).strip()
        local_intf = _norm_intf(m.group(2).strip())
        port_id = _norm_intf(m.group(3).strip())
        # avoid duplicates with detail
        adjs.append(CdpAdjacency(local_device=d.hostname, local_intf=local_intf,
                                 neighbor_device=neighbor, neighbor_intf=port_id))

    # de-dupe
    seen = set()
    out: List[CdpAdjacency] = []
    for a in adjs:
        k = (a.local_device, a.local_intf, a.neighbor_device, a.neighbor_intf)
        if k not in seen:
            seen.add(k)
            out.append(a)
    d.cdp = out


def _parse_single_text(text: str, fallback_name: str) -> DeviceSummary:
    hostm = HOST_RE.search(text)
    hostname = hostm.group(1) if hostm else fallback_name

    d = DeviceSummary(hostname=hostname, vendor=_guess_vendor(text), raw_text=text)
    _parse_show_version(d, text)
    d.vlans = _parse_vlans(text)
    _parse_interfaces_and_portchannels(d, text)
    _parse_vrfs(d, text)
    _parse_routing_and_routes(d, text)
    _parse_stp(d, text)
    _parse_vpc_mlag_vlt(d, text)
    _parse_cdp(d, text)
    return d


def parse_configs_fallback(paths: List[str]) -> TopologyData:
    topo = TopologyData()
    for p in paths:
        try:
            text = open(p, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        fallback_name = os.path.splitext(os.path.basename(p))[0]
        d = _parse_single_text(text, fallback_name)
        topo.devices[d.hostname] = d
    return topo


# ============================================================
# Evidence & topology building
# ============================================================

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


def _link_kind_for_intf(dev: DeviceSummary, ifname: str) -> str:
    iface = dev.interfaces.get(ifname)
    if not iface:
        return "L2"
    if iface.mode == "routed" or (iface.ip and iface.is_switchport is False):
        return "L3"
    if iface.is_svi and iface.ip:
        return "L3"
    return "L2"


def _build_links_from_cdp(topo: TopologyData) -> List[Link]:
    links: List[Link] = []
    known = set(topo.devices.keys())
    seen = set()

    for a_name, a_dev in topo.devices.items():
        for adj in a_dev.cdp:
            b = adj.neighbor_device
            if b not in known:
                continue
            a_if = adj.local_intf
            b_if = adj.neighbor_intf or ""
            kind = _link_kind_for_intf(a_dev, a_if)
            if b_if:
                kind_b = _link_kind_for_intf(topo.devices[b], b_if)
                if kind == "L2" and kind_b == "L3":
                    kind = "L3"
            # de-dupe undirected
            key = tuple(sorted([f"{a_name}:{a_if}", f"{b}:{b_if}", f"{kind}:cdp"]))
            if key in seen:
                continue
            seen.add(key)
            links.append(Link(
                a=a_name, b=b,
                a_intf=a_if, b_intf=b_if or "—",
                kind=kind, confidence="high", evidence="cdp",
                label=f"{a_if} ↔ {b_if or '—'} (cdp)"
            ))
    return links


def _infer_vpc_pairs(topo: TopologyData) -> List[PairInference]:
    # vPC pair detection using keepalive destination matching peer mgmt or SVI IP + matching domain
    pairs: List[PairInference] = []
    devs = topo.devices

    # Precompute IPs per device: mgmt + all interface IPs
    ips: Dict[str, Set[str]] = {}
    ip_to_iface: Dict[str, Tuple[str, str]] = {}
    for hn, d in devs.items():
        s = set()
        if d.mgmt_ip and d.mgmt_ip != "—":
            s.add(d.mgmt_ip)
            ip_to_iface[d.mgmt_ip] = (hn, "mgmt")
        for ifname, iface in d.interfaces.items():
            if iface.ip:
                ipaddr = iface.ip.split("/", 1)[0]
                s.add(ipaddr)
                ip_to_iface[ipaddr] = (hn, ifname)
        ips[hn] = s

    considered = set()
    for a, da in devs.items():
        if not da.vpc_configured or not da.vpc_keepalive_dst:
            continue
        for b, db in devs.items():
            if a == b:
                continue
            if not db.vpc_configured:
                continue
            key = tuple(sorted([a, b]))
            if key in considered:
                continue

            reasons: List[str] = []
            confidence = "low"

            # keepalive match: be explicit whether it matches mgmt or a particular interface (SVI)
            if da.vpc_keepalive_dst and da.vpc_keepalive_dst in ips.get(b, set()):
                target = ip_to_iface.get(da.vpc_keepalive_dst)
                if target and target[0] == b:
                    if target[1] == "mgmt":
                        reasons.append(f"Keepalive dest {da.vpc_keepalive_dst} matches {b} mgmt IP")
                    else:
                        # indicate the interface name and if it's an SVI
                        iface_obj = devs[b].interfaces.get(target[1])
                        if iface_obj and iface_obj.is_svi:
                            reasons.append(f"Keepalive dest {da.vpc_keepalive_dst} matches {b} SVI {target[1]}")
                        else:
                            reasons.append(f"Keepalive dest {da.vpc_keepalive_dst} matches {b} interface {target[1]}")
                    confidence = "high"

            # domain match
            if da.vpc_domain and db.vpc_domain and da.vpc_domain == db.vpc_domain:
                reasons.append(f"Both devices have vPC domain {da.vpc_domain}")
                if confidence == "low":
                    confidence = "medium"

            # peer-link presence on both
            if da.vpc_peerlink_po and db.vpc_peerlink_po:
                reasons.append(f"Peer-link configured on both ({da.vpc_peerlink_po} / {db.vpc_peerlink_po})")
                if confidence == "low":
                    confidence = "medium"

            # If we have at least 2 signals, elevate
            if len(reasons) >= 2 and confidence != "high":
                confidence = "high"

            if reasons:
                considered.add(key)
                pairs.append(PairInference(
                    kind="vPC", a=a, b=b, confidence=confidence,
                    reasons=reasons,
                    details={
                        "a_domain": da.vpc_domain,
                        "b_domain": db.vpc_domain,
                        "a_keepalive": da.vpc_keepalive_dst,
                        "b_keepalive": db.vpc_keepalive_dst,
                        "a_peerlink": da.vpc_peerlink_po,
                        "b_peerlink": db.vpc_peerlink_po,
                    }
                ))
    return pairs


def _build_links_from_vpc_peerlink(topo: TopologyData, pairs: List[PairInference]) -> List[Link]:
    # Create explicit peer-link edges between inferred vPC peers if peer-link Po exists
    links: List[Link] = []
    seen = set()
    for p in pairs:
        if p.kind != "vPC":
            continue
        a = p.a
        b = p.b
        da = topo.devices[a]
        db = topo.devices[b]
        if not da.vpc_peerlink_po or not db.vpc_peerlink_po:
            continue

        a_if = da.vpc_peerlink_po
        b_if = db.vpc_peerlink_po

        key = tuple(sorted([f"{a}:{a_if}", f"{b}:{b_if}", "L2:vpc"]))
        if key in seen:
            continue
        seen.add(key)
        links.append(Link(
            a=a, b=b,
            a_intf=a_if, b_intf=b_if,
            kind="L2", confidence="high", evidence="vpc",
            label=f"{a_if} ↔ {b_if} (vPC peer-link)"
        ))
    return links


def _build_links_from_descriptions(topo: TopologyData) -> List[Link]:
    devs = topo.devices
    known = set(devs.keys())
    hints: Dict[str, List[Tuple[str, str, Optional[str]]]] = {k: [] for k in known}

    for a, d in devs.items():
        for ifname, iface in d.interfaces.items():
            b, b_if = _extract_remote_from_desc(iface.description)
            if b and b in known:
                hints[a].append((b, ifname, b_if))
        for pc_id, pc in d.port_channels.items():
            b, b_if = _extract_remote_from_desc(pc.description)
            if b and b in known:
                hints[a].append((b, f"port-channel{pc_id}", b_if))

    def reverse_candidates(b: str, a: str) -> List[Tuple[str, str, Optional[str]]]:
        return [t for t in hints.get(b, []) if t[0] == a]

    links: List[Link] = []
    seen = set()

    # mutual = high
    for a in known:
        for (b, a_if, b_if_hint) in hints[a]:
            revs = reverse_candidates(b, a)
            if not revs:
                continue

            chosen_b_if = revs[0][1]
            # Prefer reverse that explicitly names our interface (if available)
            if b_if_hint:
                for (_a2, b_if, a_hint) in revs:
                    if a_hint and _norm_intf(a_hint) == _norm_intf(a_if):
                        chosen_b_if = b_if
                        break

            kind = _link_kind_for_intf(devs[a], a_if)
            if kind == "L2" and _link_kind_for_intf(devs[b], chosen_b_if) == "L3":
                kind = "L3"

            key = tuple(sorted([f"{a}:{a_if}", f"{b}:{chosen_b_if}", f"{kind}:mut"]))
            if key in seen:
                continue
            seen.add(key)

            links.append(Link(
                a=a, b=b,
                a_intf=a_if, b_intf=chosen_b_if,
                kind=kind, confidence="high", evidence="desc-mutual",
                label=f"{a_if} ↔ {chosen_b_if} (desc)"
            ))

    # one-sided = medium (only if peer interface exists)
    for a in known:
        for (b, a_if, b_if_hint) in hints[a]:
            if not b_if_hint:
                continue
            if b_if_hint not in devs[b].interfaces and not PC_NAME_RE.match(b_if_hint):
                continue

            kind = _link_kind_for_intf(devs[a], a_if)
            if kind == "L2" and _link_kind_for_intf(devs[b], b_if_hint) == "L3":
                kind = "L3"

            key = tuple(sorted([f"{a}:{a_if}", f"{b}:{b_if_hint}", f"{kind}:one"]))
            if key in seen:
                continue
            # Avoid duplicates if mutual already created
            if any((l.a == a and l.b == b and l.a_intf == a_if and l.b_intf == b_if_hint) or
                   (l.a == b and l.b == a and l.a_intf == b_if_hint and l.b_intf == a_if)
                   for l in links):
                continue

            seen.add(key)
            links.append(Link(
                a=a, b=b,
                a_intf=a_if, b_intf=b_if_hint,
                kind=kind, confidence="medium", evidence="desc-one-side",
                label=f"{a_if} ↔ {b_if_hint} (desc, med)"
            ))
    return links


def _build_links_from_ip_subnet(topo: TopologyData) -> List[Link]:
    # Evidence: two interfaces in same L3 subnet (common for /31 P2P, /30, etc.)
    # Only create edges when:
    # - both sides have routed interface (or SVI) with IP
    # - same network
    # - network is "small-ish" (prefixlen >= 29) OR point-to-point /31
    devs = topo.devices
    ip_map: List[Tuple[str, str, ipaddress.IPv4Interface]] = []
    for hn, d in devs.items():
        for ifn, iface in d.interfaces.items():
            if not iface.ip:
                continue
            try:
                ipi = ipaddress.ip_interface(iface.ip)
                if isinstance(ipi, ipaddress.IPv6Interface):
                    continue
                # must look like L3 (routed/SVI/has ip and not switchport)
                if iface.mode == "routed" or iface.is_svi or iface.is_switchport is False:
                    ip_map.append((hn, ifn, ipi))  # type: ignore
            except Exception:
                continue

    links: List[Link] = []
    seen = set()
    # Compare pairs
    for i in range(len(ip_map)):
        a, a_if, a_ip = ip_map[i]
        for j in range(i + 1, len(ip_map)):
            b, b_if, b_ip = ip_map[j]
            if a == b:
                continue
            if a_ip.network != b_ip.network:
                continue

            # avoid huge shared VLAN subnets (unless /31 or /30-ish)
            plen = a_ip.network.prefixlen
            if plen < 29 and plen != 31:
                continue

            key = tuple(sorted([f"{a}:{a_if}", f"{b}:{b_if}", f"L3:ip:{a_ip.network}"]))
            if key in seen:
                continue
            seen.add(key)

            links.append(Link(
                a=a, b=b,
                a_intf=a_if, b_intf=b_if,
                kind="L3", confidence="medium", evidence="ip-subnet",
                label=f"{a_if} ↔ {b_if} ({a_ip.network})"
            ))
    return links


def build_topology(topo: TopologyData) -> TopologyData:
    pairs = _infer_vpc_pairs(topo)
    topo.pairs = pairs

    links: List[Link] = []
    # precedence: CDP, vPC peer-link, description, IP subnet
    links.extend(_build_links_from_cdp(topo))
    links.extend(_build_links_from_vpc_peerlink(topo, pairs))
    links.extend(_build_links_from_descriptions(topo))
    links.extend(_build_links_from_ip_subnet(topo))

    # De-dupe final links (undirected)
    seen = set()
    final: List[Link] = []
    for l in links:
        key = tuple(sorted([f"{l.a}:{l.a_intf}", f"{l.b}:{l.b_intf}", f"{l.kind}:{l.evidence}"]))
        if key in seen:
            continue
        seen.add(key)
        # If label empty, populate
        if not l.label:
            l.label = f"{l.a_intf} ↔ {l.b_intf}"
        final.append(l)

    topo.links = final
    return topo


# ============================================================
# Adapters: attempt to use repo modules if present
# ============================================================

def parse_with_adapters(paths: List[str]) -> TopologyData:
    """
    Tries:
      1) parser.orchestrator.parse_paths(paths)
      2) parser.orchestrator.parse_configs(paths)
      3) parser.orchestrator.parse_files(paths)
      4) fallback parser in this file
    Then always runs build_topology() (unless the orchestrator already returns links),
    but we won't destroy existing links— we merge evidence-based extras.
    """
    topo: Optional[TopologyData] = None
    used_external = False

    try:
        from parser import orchestrator  # type: ignore

        for fn_name in ("parse_paths", "parse_configs", "parse_files", "parse"):
            fn = getattr(orchestrator, fn_name, None)
            if callable(fn):
                try:
                    result = fn(list(paths))
                    # If external returns dict-like, convert best-effort
                    topo = _coerce_topology(result)
                    used_external = True
                    break
                except Exception:
                    continue
    except Exception:
        topo = None

    if topo is None:
        topo = parse_configs_fallback(paths)

    # If external already built links, keep them but also add missing evidence links.
    # We'll treat external links as evidence="external".
    if used_external and topo.links:
        ext_links = topo.links
        topo.links = []
        topo = build_topology(topo)
        # merge
        merged = topo.links[:]
        seen = set(tuple(sorted([f"{l.a}:{l.a_intf}", f"{l.b}:{l.b_intf}", l.kind])) for l in merged)
        for l in ext_links:
            key = tuple(sorted([f"{l.a}:{l.a_intf}", f"{l.b}:{l.b_intf}", l.kind]))
            if key in seen:
                continue
            l.evidence = getattr(l, "evidence", "external") or "external"
            l.confidence = getattr(l, "confidence", "medium") or "medium"
            if not l.label:
                l.label = f"{l.a_intf} ↔ {l.b_intf} (external)"
            merged.append(l)
            seen.add(key)
        topo.links = merged
    else:
        topo = build_topology(topo)

    return topo


def _coerce_topology(result: Any) -> TopologyData:
    # If it's already our TopologyData
    if isinstance(result, TopologyData):
        return result

    topo = TopologyData()

    # If dict-like
    if isinstance(result, dict):
        # devices
        devices = result.get("devices") or result.get("Devices") or {}
        if isinstance(devices, dict):
            for hn, d in devices.items():
                topo.devices[str(hn)] = _coerce_device(str(hn), d)
        # links
        links = result.get("links") or result.get("Links") or []
        if isinstance(links, list):
            for l in links:
                try:
                    topo.links.append(_coerce_link(l))
                except Exception:
                    continue
        return topo

    # If list of devices
    if isinstance(result, list):
        for item in result:
            try:
                d = _coerce_device(getattr(item, "hostname", "device"), item)
                topo.devices[d.hostname] = d
            except Exception:
                continue
        return topo

    return topo


def _coerce_device(fallback_hn: str, obj: Any) -> DeviceSummary:
    if isinstance(obj, DeviceSummary):
        return obj

    d = DeviceSummary(hostname=fallback_hn)

    # dict-like
    if isinstance(obj, dict):
        d.hostname = str(obj.get("hostname") or obj.get("name") or fallback_hn)
        d.vendor = str(obj.get("vendor") or d.vendor)
        d.model = str(obj.get("model") or d.model)
        d.os_ver = str(obj.get("os_version") or obj.get("os_ver") or d.os_ver)
        d.mgmt_ip = str(obj.get("mgmt_ip") or d.mgmt_ip)
        d.raw_text = str(obj.get("raw_text") or obj.get("raw") or "")

        # attempt to pull vPC fields
        d.vpc_domain = str(obj.get("vpc_domain") or "")
        d.vpc_keepalive_dst = str(obj.get("vpc_keepalive_dst") or "")
        d.vpc_peerlink_po = str(obj.get("vpc_peerlink_po") or "")
        d.vpc_configured = bool(obj.get("vpc_configured") or d.vpc_domain or d.vpc_keepalive_dst)

        # VLANs
        vl = obj.get("vlans") or []
        if isinstance(vl, list):
            for v in vl:
                if isinstance(v, dict):
                    d.vlans.append(VlanInfo(vid=str(v.get("vid") or v.get("vlan_id") or ""), name=str(v.get("name") or "—")))
        # Interfaces
        ifaces = obj.get("interfaces") or {}
        if isinstance(ifaces, dict):
            for ifn, iv in ifaces.items():
                if isinstance(iv, dict):
                    ii = InterfaceInfo(name=str(ifn))
                    ii.description = str(iv.get("description") or "")
                    ii.mode = str(iv.get("mode") or "")
                    ii.access_vlan = str(iv.get("access_vlan") or "")
                    ii.trunk_vlans_raw = str(iv.get("trunk_vlans") or iv.get("trunk_vlans_raw") or "")
                    ii.trunk_vlans_list = _expand_vlan_list(ii.trunk_vlans_raw)
                    ii.channel_group = str(iv.get("channel_group") or "")
                    ii.ip = str(iv.get("ip") or "")
                    ii.vrf = str(iv.get("vrf") or "")
                    d.interfaces[ii.name] = ii
        # Port-channels
        pcs = obj.get("port_channels") or {}
        if isinstance(pcs, dict):
            for pc_id, pv in pcs.items():
                if isinstance(pv, dict):
                    pc = PortChannelInfo(pc_id=str(pc_id), name=str(pv.get("name") or f"port-channel{pc_id}"))
                    pc.description = str(pv.get("description") or "")
                    pc.members = list(pv.get("members") or [])
                    pc.mode = str(pv.get("mode") or "")
                    pc.trunk_vlans_raw = str(pv.get("trunk_vlans") or pv.get("trunk_vlans_raw") or "")
                    pc.trunk_vlans_list = _expand_vlan_list(pc.trunk_vlans_raw)
                    pc.access_vlan = str(pv.get("access_vlan") or "")
                    pc.vpc_id = str(pv.get("vpc") or pv.get("vpc_id") or "")
                    d.port_channels[pc.pc_id] = pc

    return d


def _coerce_link(obj: Any) -> Link:
    if isinstance(obj, Link):
        return obj
    if isinstance(obj, dict):
        return Link(
            a=str(obj.get("a") or obj.get("src") or ""),
            b=str(obj.get("b") or obj.get("dst") or ""),
            a_intf=str(obj.get("a_intf") or obj.get("src_intf") or obj.get("src_port") or ""),
            b_intf=str(obj.get("b_intf") or obj.get("dst_intf") or obj.get("dst_port") or ""),
            kind=str(obj.get("kind") or "L2"),
            confidence=str(obj.get("confidence") or "medium"),
            evidence=str(obj.get("evidence") or "external"),
            label=str(obj.get("label") or ""),
        )
    raise ValueError("Unsupported link")


# ============================================================
# UI helpers: scrollable frame + collapsible sections
# ============================================================

class ScrollableFrame(ttk.Frame):
    def __init__(self, master, colors: Any, panel_style: str = "Panel.TFrame"):
        super().__init__(master, style=panel_style)
        self.colors = colors

        self.canvas = tk.Canvas(self, bg=self.colors.panel, highlightthickness=0, relief="flat")
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.inner = ttk.Frame(self.canvas, style=panel_style)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # mousewheel
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_configure(self, _evt=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, evt):
        # keep inner width synced to canvas width
        self.canvas.itemconfigure(self.inner_id, width=evt.width)

    def _on_mousewheel(self, evt):
        try:
            self.canvas.yview_scroll(int(-1 * (evt.delta / 120)), "units")
        except Exception:
            pass


class CollapsibleSection(ttk.Frame):
    def __init__(self, master, title: str, colors: Any, build_fn):
        super().__init__(master, style="Panel.TFrame")
        self.colors = colors
        self.title = title
        self.build_fn = build_fn
        self._built = False
        self._open = tk.BooleanVar(value=False)

        hdr = ttk.Frame(self, style="Panel.TFrame")
        hdr.pack(fill="x", padx=10, pady=(8, 0))

        self.btn = ttk.Button(hdr, text="▸", width=3, command=self.toggle)
        self.btn.pack(side="left")

        ttk.Label(hdr, text=title, style="Section.TLabel").pack(side="left", padx=(6, 0))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=(6, 0))

        self.body = ttk.Frame(self, style="Panel.TFrame")

    def toggle(self):
        self._open.set(not self._open.get())
        if self._open.get():
            self.btn.configure(text="▾")
            if not self._built:
                self.build_fn(self.body)
                self._built = True
            self.body.pack(fill="x", padx=10, pady=(6, 8))
        else:
            self.btn.configure(text="▸")
            self.body.pack_forget()


# ============================================================
# Main App (Layout B)
# ============================================================

class FabricWeaverApp(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, style="TFrame")
        self.master = master
        self.pack(fill="both", expand=True)

        self.colors = apply_dark_theme(master)

        # state
        self._topo: TopologyData = TopologyData()
        self._active_device: Optional[str] = None
        self._device_order: List[str] = []
        self._node_pos: Dict[str, Tuple[int, int]] = {}
        self._dragging: Optional[str] = None
        self._drag_start: Tuple[int, int] = (0, 0)

        # filters/toggles
        self.var_show_l2 = tk.BooleanVar(value=True)
        self.var_show_l3 = tk.BooleanVar(value=True)
        self.var_show_medium = tk.BooleanVar(value=True)
        self.var_show_labels = tk.BooleanVar(value=True)
        self.var_show_grid = tk.BooleanVar(value=False)

        # Zoom and pan state
        self.zoom_level = 1.0
        self.zoom_min = 0.3
        self.zoom_max = 3.0
        self.pan_x = 0
        self.pan_y = 0

        # ensure changes to these variables always redraw topology
        # Debounce rapid changes to avoid excessive redraws (150ms for performance)
        self._toggle_timer = None
        def _on_toggle(*args):
            if self._toggle_timer:
                try:
                    self.after_cancel(self._toggle_timer)
                except (tk.TclError, AttributeError):
                    pass
            self._toggle_timer = self.after(150, self.draw_topology)

        try:
            # Try modern trace_add first (Tk 8.6.11+)
            self.var_show_l2.trace_add("write", _on_toggle)
            self.var_show_l3.trace_add("write", _on_toggle)
            self.var_show_medium.trace_add("write", _on_toggle)
            self.var_show_labels.trace_add("write", _on_toggle)
        except AttributeError:
            # Fall back to older trace method
            self.var_show_l2.trace("w", _on_toggle)
            self.var_show_l3.trace("w", _on_toggle)
            self.var_show_medium.trace("w", _on_toggle)
            self.var_show_labels.trace("w", _on_toggle)

        self._cached_detail_text: Dict[str, str] = {}
        self._cached_device_json: Dict[str, str] = {}
        self._cached_pair_text: Dict[str, str] = {}
        self._cache_limit = 400  # Clear caches if device count exceeds this

        self._build_layout()

    # ---------------- UI build ----------------

    def _build_layout(self):
        # Use a resizable PanedWindow so panes (sidebar / main / inspector) can be adjusted by the user.
        # Left: sidebar, Center: a nested PanedWindow with main + inspector (inspector will be added/removed
        # depending on active tab to keep the inspector visible only on the Topology tab).
        self.rowconfigure(0, weight=1)

        self.paned = tk.PanedWindow(self, orient="horizontal", sashrelief="raised", bg=self.colors.bg)
        self.paned.pack(fill="both", expand=True)

        # Sidebar
        self.sidebar = ttk.Frame(self.paned, style="Panel.TFrame", width=280)
        self.sidebar.pack_propagate(False)
        self.paned.add(self.sidebar, minsize=120)

        # Center area: nested PanedWindow to hold main and (optionally) inspector
        self.center_paned = tk.PanedWindow(self.paned, orient="horizontal", sashrelief="raised", bg=self.colors.bg)
        self.paned.add(self.center_paned, minsize=400)

        # Main (notebook)
        self.main = ttk.Frame(self.center_paned, style="TFrame")
        self.main.rowconfigure(0, weight=1)
        self.main.columnconfigure(0, weight=1)
        self.center_paned.add(self.main)

        # Inspector frame (created but not added to paned until Topology tab active)
        self.inspector = ttk.Frame(self.center_paned, style="Panel.TFrame", width=360)
        self.inspector.pack_propagate(False)

        # Build UI pieces
        self._build_sidebar()
        self._build_main()
        self._build_inspector()

        # Notebook tab change handler: show inspector only on Topology tab
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_sidebar(self):
        # Small title (no top banner)
        top = ttk.Frame(self.sidebar, style="Panel.TFrame")
        top.pack(fill="x", padx=10, pady=(10, 6))

        ttk.Label(top, text="FabricWeaver", style="Header.TLabel").pack(anchor="w")
        self.lbl_loaded = ttk.Label(top, text="Loaded: 0", style="Muted.TLabel")
        self.lbl_loaded.pack(anchor="w", pady=(2, 0))

        ttk.Separator(self.sidebar, orient="horizontal").pack(fill="x", padx=10, pady=(6, 8))

        ttk.Label(self.sidebar, text="Devices", style="Section.TLabel").pack(anchor="w", padx=10)

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            self.sidebar,
            textvariable=self.search_var,
            bg=self.colors.panel2,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors.border
        )
        self.search_entry.pack(fill="x", padx=10, pady=(6, 8))
        self.search_entry.bind("<KeyRelease>", lambda _e: self._refresh_device_list())

        self.device_list = tk.Listbox(
            self.sidebar,
            bg=self.colors.panel,
            fg=self.colors.text,
            highlightthickness=1,
            highlightbackground=self.colors.border,
            selectbackground="#223050",
            selectforeground=self.colors.text,
            relief="flat",
            height=20
        )
        self.device_list.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.device_list.bind("<<ListboxSelect>>", self._on_select_device)

        btns = ttk.Frame(self.sidebar, style="Panel.TFrame")
        btns.pack(fill="x", padx=10, pady=(6, 10))

        ttk.Button(btns, text="Load Files", style="Primary.TButton", command=self.load_files).pack(fill="x", pady=(0, 6))
        ttk.Button(btns, text="Export", command=self.export_menu).pack(fill="x", pady=(0, 6))
        ttk.Button(btns, text="Clear", command=self.clear_all).pack(fill="x")

    def _build_main(self):
        self.nb = ttk.Notebook(self.main)
        self.nb.grid(row=0, column=0, sticky="nsew")

        self.tab_details = ttk.Frame(self.nb, style="Panel.TFrame")
        self.tab_topology = ttk.Frame(self.nb, style="Panel.TFrame")
        self.tab_raw = ttk.Frame(self.nb, style="Panel.TFrame")

        self.nb.add(self.tab_details, text="Details")
        self.nb.add(self.tab_topology, text="Topology")
        self.nb.add(self.tab_raw, text="Raw")

        self._build_details_tab()
        self._build_topology_tab()
        self._build_raw_tab()

    def _build_inspector(self):
        ttk.Label(self.inspector, text="Inspector", style="Header.TLabel").pack(anchor="w", padx=10, pady=(10, 6))
        ttk.Separator(self.inspector, orient="horizontal").pack(fill="x", padx=10, pady=(0, 8))

        self.ins_text = tk.Text(
            self.inspector,
            bg=self.colors.panel,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors.border,
            wrap="word",
            height=28
        )
        self.ins_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.ins_text.configure(state="disabled")

    def _on_tab_changed(self, _evt=None):
        try:
            sel = self.nb.select()
            # Compare widget ids; self.tab_topology is the frame associated with topology
            if sel == str(self.tab_topology):
                # ensure inspector is present in center_paned
                panes = self.center_paned.panes()
                if str(self.inspector) not in panes:
                    self.center_paned.add(self.inspector, minsize=200)
            else:
                # remove inspector pane if present
                try:
                    panes = self.center_paned.panes()
                    if str(self.inspector) in panes:
                        self.center_paned.forget(self.inspector)
                except Exception:
                    pass
        except Exception:
            pass

    def _build_details_tab(self):
        self.details_scroll = ScrollableFrame(self.tab_details, self.colors, panel_style="Panel.TFrame")
        self.details_scroll.pack(fill="both", expand=True, padx=6, pady=6)

        # sections (lazy built)
        self.sec_identity = CollapsibleSection(self.details_scroll.inner, "Identity", self.colors, self._build_sec_identity)
        self.sec_pairing = CollapsibleSection(self.details_scroll.inner, "Clustering / Pairing", self.colors, self._build_sec_pairing)
        self.sec_l2 = CollapsibleSection(self.details_scroll.inner, "Layer 2 Summary", self.colors, self._build_sec_l2)
        self.sec_l3 = CollapsibleSection(self.details_scroll.inner, "Layer 3 Summary", self.colors, self._build_sec_l3)
        self.sec_int = CollapsibleSection(self.details_scroll.inner, "Interfaces", self.colors, self._build_sec_interfaces)

        for s in (self.sec_identity, self.sec_pairing, self.sec_l2, self.sec_l3, self.sec_int):
            s.pack(fill="x", pady=(0, 2))

        # Default open a couple sections
        self.sec_identity.toggle()
        self.sec_pairing.toggle()

    def _build_topology_tab(self):
        # Compact topology toolbar (no metrics area) — focused on topology interaction
        top = ttk.Frame(self.tab_topology, style="Panel.TFrame")
        top.pack(fill="x", padx=10, pady=(10, 6))

        # Main action buttons
        ttk.Button(top, text="Auto-layout", style="Accent.TButton", command=self.auto_layout).pack(side="left")
        ttk.Button(top, text="Export PNG", style="Accent.TButton", command=self.export_png).pack(side="left", padx=(6, 0))

        # Zoom controls
        ttk.Label(top, text=" | ", style="Panel.TLabel").pack(side="left", padx=8)
        ttk.Button(top, text="Zoom +", command=self._zoom_in).pack(side="left", padx=(0, 2))
        ttk.Button(top, text="Zoom -", command=self._zoom_out).pack(side="left", padx=2)
        ttk.Button(top, text="Reset", command=self._zoom_reset).pack(side="left", padx=(2, 6))
        ttk.Button(top, text="Fit All", command=self._zoom_fit_all).pack(side="left", padx=2)

        # Visibility toggles
        ttk.Label(top, text=" | ", style="Panel.TLabel").pack(side="left", padx=8)
        ttk.Checkbutton(top, text="Show L2", style="Toggle.TCheckbutton", variable=self.var_show_l2).pack(side="left")
        ttk.Checkbutton(top, text="Show L3", style="Toggle.TCheckbutton", variable=self.var_show_l3).pack(side="left", padx=8)
        ttk.Checkbutton(top, text="Show Medium", style="Toggle.TCheckbutton", variable=self.var_show_medium).pack(side="left", padx=8)
        ttk.Checkbutton(top, text="Edge Labels", style="Toggle.TCheckbutton", variable=self.var_show_labels).pack(side="left", padx=8)
        ttk.Checkbutton(top, text="Grid", style="Toggle.TCheckbutton", variable=self.var_show_grid).pack(side="left", padx=8)

        # Topology canvas (main interactive area)
        self.canvas = tk.Canvas(
            self.tab_topology,
            bg=self.colors.panel2,
            highlightthickness=1,
            highlightbackground=self.colors.border,
            relief="flat"
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.canvas.bind("<ButtonPress-1>", self._on_canvas_down)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_up)
        self.canvas.bind("<Configure>", lambda _e: self.draw_topology())
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Button-4>", self._on_mouse_wheel)  # Linux scroll up
        self.canvas.bind("<Button-5>", self._on_mouse_wheel)  # Linux scroll down

    def _build_raw_tab(self):
        self.tab_raw.columnconfigure(0, weight=1)
        self.tab_raw.columnconfigure(1, weight=1)
        self.tab_raw.rowconfigure(1, weight=1)

        bar = ttk.Frame(self.tab_raw, style="Panel.TFrame")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))
        ttk.Button(bar, text="Copy Raw", command=self.copy_raw).pack(side="left")
        ttk.Button(bar, text="Copy Parsed JSON", command=self.copy_json).pack(side="left", padx=(6, 0))

        self.raw_text = tk.Text(
            self.tab_raw,
            bg=self.colors.panel,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors.border,
            wrap="none"
        )
        self.raw_text.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=(0, 10))
        self.raw_text.configure(state="disabled")

        # horizontal scrollbar for raw text
        self.raw_xscroll = ttk.Scrollbar(self.tab_raw, orient="horizontal", command=self.raw_text.xview)
        self.raw_xscroll.grid(row=2, column=0, sticky="ew", padx=(10, 6))
        self.raw_text.configure(xscrollcommand=self.raw_xscroll.set)

        self.json_text = tk.Text(
            self.tab_raw,
            bg=self.colors.panel,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors.border,
            wrap="none"
        )
        self.json_text.grid(row=1, column=1, sticky="nsew", padx=(6, 10), pady=(0, 10))
        self.json_text.configure(state="disabled")

        # horizontal scrollbar for json text
        self.json_xscroll = ttk.Scrollbar(self.tab_raw, orient="horizontal", command=self.json_text.xview)
        self.json_xscroll.grid(row=2, column=1, sticky="ew", padx=(6, 10))
        self.json_text.configure(xscrollcommand=self.json_xscroll.set)

    # ---------------- Section builders ----------------

    def _build_sec_identity(self, body: ttk.Frame):
        self.identity_text = tk.Text(
            body, bg=self.colors.panel, fg=self.colors.text,
            insertbackground=self.colors.text, relief="flat",
            highlightthickness=1, highlightbackground=self.colors.border,
            wrap="word", height=7
        )
        self.identity_text.pack(fill="x", pady=(0, 6))
        self.identity_text.configure(state="disabled")

    def _build_sec_pairing(self, body: ttk.Frame):
        self.pair_text = tk.Text(
            body, bg=self.colors.panel, fg=self.colors.text,
            insertbackground=self.colors.text, relief="flat",
            highlightthickness=1, highlightbackground=self.colors.border,
            wrap="word", height=10
        )
        self.pair_text.pack(fill="x", pady=(0, 6))
        self.pair_text.configure(state="disabled")

    def _build_sec_l2(self, body: ttk.Frame):
        # Summary text + VLAN / Port-channel trees
        self.l2_text = tk.Text(
            body, bg=self.colors.panel, fg=self.colors.text,
            insertbackground=self.colors.text, relief="flat",
            highlightthickness=1, highlightbackground=self.colors.border,
            wrap="word", height=6
        )
        self.l2_text.pack(fill="x", pady=(0, 6))
        self.l2_text.configure(state="disabled")

        ttk.Label(body, text="VLANs", style="Muted.TLabel").pack(anchor="w", pady=(4, 2))
        self.vlan_tree = ttk.Treeview(body, columns=("vid", "name"), show="headings", height=6)
        self.vlan_tree.heading("vid", text="VLAN")
        self.vlan_tree.heading("name", text="Name")
        self.vlan_tree.column("vid", width=70, anchor="w")
        self.vlan_tree.column("name", width=320, anchor="w")
        self.vlan_tree.pack(fill="x", pady=(0, 8))

        ttk.Label(body, text="Port-channels", style="Muted.TLabel").pack(anchor="w", pady=(4, 2))
        self.pc_tree = ttk.Treeview(body, columns=("po", "members", "mode", "trunk", "vpc", "peer"),
                                    show="headings", height=7)
        for c, t, w in [
            ("po", "Po", 90),
            ("members", "Members", 200),
            ("mode", "Mode", 80),
            ("trunk", "Trunk VLANs", 160),
            ("vpc", "vPC", 60),
            ("peer", "Peer-link", 80),
        ]:
            self.pc_tree.heading(c, text=t)
            self.pc_tree.column(c, width=w, anchor="w")
        self.pc_tree.pack(fill="x", pady=(0, 6))

    def _build_sec_l3(self, body: ttk.Frame):
        self.l3_text = tk.Text(
            body, bg=self.colors.panel, fg=self.colors.text,
            insertbackground=self.colors.text, relief="flat",
            highlightthickness=1, highlightbackground=self.colors.border,
            wrap="word", height=7
        )
        self.l3_text.pack(fill="x", pady=(0, 6))
        self.l3_text.configure(state="disabled")

        ttk.Label(body, text="SVIs / Routed Interfaces (IP)", style="Muted.TLabel").pack(anchor="w", pady=(4, 2))
        self.ip_tree = ttk.Treeview(body, columns=("iface", "ip", "vrf"), show="headings", height=7)
        for c, t, w in [("iface", "Interface", 140), ("ip", "IP/Prefix", 160), ("vrf", "VRF", 120)]:
            self.ip_tree.heading(c, text=t)
            self.ip_tree.column(c, width=w, anchor="w")
        self.ip_tree.pack(fill="x", pady=(0, 8))

        ttk.Label(body, text="Static Routes (top 20)", style="Muted.TLabel").pack(anchor="w", pady=(4, 2))
        self.route_tree = ttk.Treeview(body, columns=("vrf", "prefix", "nh"), show="headings", height=6)
        for c, t, w in [("vrf", "VRF", 120), ("prefix", "Prefix", 170), ("nh", "Next-hop", 150)]:
            self.route_tree.heading(c, text=t)
            self.route_tree.column(c, width=w, anchor="w")
        self.route_tree.pack(fill="x", pady=(0, 6))

    def _build_sec_interfaces(self, body: ttk.Frame):
        # Filter row
        f = ttk.Frame(body, style="Panel.TFrame")
        f.pack(fill="x", pady=(0, 6))

        self.if_filter_var = tk.StringVar(value="all")
        for key, label in [("all", "All"), ("access", "Access"), ("trunk", "Trunk"), ("routed", "Routed"), ("pc", "In Po")]:
            rb = ttk.Radiobutton(f, text=label, value=key, variable=self.if_filter_var, command=self._render_interfaces_table)
            rb.pack(side="left", padx=(0, 10))

        self.if_tree = ttk.Treeview(
            body,
            columns=("iface", "mode", "access", "trunk", "native", "po", "ip", "vrf", "desc"),
            show="headings",
            height=14
        )
        cols = [
            ("iface", "Interface", 130),
            ("mode", "Mode", 70),
            ("access", "Access", 70),
            ("trunk", "Trunk VLANs", 140),
            ("native", "Native", 70),
            ("po", "Po", 60),
            ("ip", "IP", 140),
            ("vrf", "VRF", 90),
            ("desc", "Description", 260),
        ]
        for c, t, w in cols:
            self.if_tree.heading(c, text=t)
            self.if_tree.column(c, width=w, anchor="w")
        self.if_tree.pack(fill="both", expand=True)

    # ---------------- Actions ----------------

    def load_files(self):
        paths = filedialog.askopenfilenames(
            title="Select device configs / runbooks",
            filetypes=[("Text / Config", "*.txt *.log *.cfg *.conf *.*")]
        )
        if not paths:
            return

        try:
            topo = parse_with_adapters(list(paths))
        except Exception as e:
            messagebox.showerror("Parse Error", f"Failed to parse files:\n{e}")
            return

        self._topo = topo
        self._cached_detail_text.clear()
        self._cached_device_json.clear()
        self._cached_pair_text.clear()

        self._device_order = sorted(self._topo.devices.keys())
        self.lbl_loaded.configure(text=f"Loaded: {len(self._device_order)}")
        self._refresh_device_list()

        self._active_device = None
        self._node_pos.clear()
        self.auto_layout()

        # auto select first device
        if self._device_order:
            self._select_device(self._device_order[0])

    def clear_all(self):
        self._topo = TopologyData()
        self._active_device = None
        self._device_order = []
        self._node_pos.clear()
        self._cached_detail_text.clear()
        self._cached_device_json.clear()
        self._cached_pair_text.clear()

        self.lbl_loaded.configure(text="Loaded: 0")
        self.device_list.delete(0, "end")
        self._set_inspector_text("")

        self._set_text(self.raw_text, "")
        self._set_text(self.json_text, "")

        # clear details widgets if built
        for wname in ("identity_text", "pair_text", "l2_text", "l3_text"):
            if hasattr(self, wname):
                self._set_text(getattr(self, wname), "")

        for tname in ("vlan_tree", "pc_tree", "ip_tree", "route_tree", "if_tree"):
            if hasattr(self, tname):
                tree = getattr(self, tname)
                for item in tree.get_children():
                    tree.delete(item)

        self.draw_topology()

    def export_menu(self):
        if not self._topo.devices:
            messagebox.showwarning("Export", "Nothing loaded.")
            return

        win = tk.Toplevel(self)
        win.title("Export")
        win.configure(bg=self.colors.bg)
        win.resizable(False, False)
        apply_dark_theme(win, self.colors)

        box = ttk.Frame(win, style="Panel.TFrame")
        box.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(box, text="Export options", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Button(box, text="Export Topology JSON", style="Primary.TButton", command=lambda: (win.destroy(), self.export_json())).pack(fill="x", pady=(0, 8))
        ttk.Button(box, text="Export Topology PNG", command=lambda: (win.destroy(), self.export_png())).pack(fill="x", pady=(0, 8))
        ttk.Button(box, text="Export Topology PDF", command=lambda: (win.destroy(), self.export_pdf())).pack(fill="x", pady=(0, 8))
        ttk.Button(box, text="Export Summary TXT", command=lambda: (win.destroy(), self.export_summary_txt())).pack(fill="x")

        ttk.Button(box, text="Close", command=win.destroy).pack(anchor="e", pady=(12, 0))
        win.grab_set()
        win.transient(self.master)

    def export_json(self):
        save_path = filedialog.asksaveasfilename(
            title="Export topology JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")]
        )
        if not save_path:
            return

        out = {
            "devices": {hn: _device_to_export_dict(d) for hn, d in self._topo.devices.items()},
            "links": [asdict(l) for l in self._topo.links],
            "pairs": [asdict(p) for p in self._topo.pairs],
            "positions": {hn: {"x": self._node_pos.get(hn, (0, 0))[0], "y": self._node_pos.get(hn, (0, 0))[1]} for hn in self._topo.devices}
        }
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)

        messagebox.showinfo("Export", f"Exported:\n{save_path}")

    def export_summary_txt(self):
        save_path = filedialog.asksaveasfilename(
            title="Export summary TXT",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")]
        )
        if not save_path:
            return

        lines: List[str] = []
        lines.append("FabricWeaver Summary Report")
        lines.append("=" * 60)
        lines.append(f"Devices: {len(self._topo.devices)}   Links: {len(self._topo.links)}   Pairs: {len(self._topo.pairs)}")
        lines.append("")

        if self._topo.pairs:
            lines.append("PAIR INFERENCE")
            for p in self._topo.pairs:
                lines.append(f"- {p.kind}: {p.a} <-> {p.b}  ({p.confidence})")
                for r in p.reasons:
                    lines.append(f"    • {r}")
            lines.append("")

        for hn in sorted(self._topo.devices.keys()):
            d = self._topo.devices[hn]
            lines.append(f"DEVICE: {d.hostname}")
            lines.append(f"  Vendor: {d.vendor}   Model: {d.model}   OS: {d.os_ver}   Mgmt: {d.mgmt_ip}")
            lines.append(f"  VLANs: {len(d.vlans)}   Port-channels: {len(d.port_channels)}   Interfaces: {len(d.interfaces)}")
            lines.append(f"  Routing: {', '.join(d.routing_protocols) if d.routing_protocols else '—'}   Static routes: {len(d.static_routes)}")
            if d.vpc_configured:
                lines.append(f"  vPC domain: {d.vpc_domain or '—'}  keepalive: {d.vpc_keepalive_dst or '—'}  peer-link: {d.vpc_peerlink_po or '—'}")
            lines.append("")

        with open(save_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        messagebox.showinfo("Export", f"Exported:\n{save_path}")

    def export_png(self):
        if not self._topo.devices:
            messagebox.showwarning("Export", "Nothing loaded.")
            return

        save_path = filedialog.asksaveasfilename(
            title="Export topology PNG",
            defaultextension=".png",
            filetypes=[("PNG", "*.png")]
        )
        if not save_path:
            return

        # Tkinter canvas can export PostScript. We'll convert to PNG if Pillow is installed.
        ps_path = save_path[:-4] + ".ps"
        try:
            self.canvas.postscript(file=ps_path, colormode="color")
        except Exception as e:
            messagebox.showerror("Export", f"Failed to export PostScript:\n{e}")
            return

        try:
            from PIL import Image  # type: ignore
            img = Image.open(ps_path)
            img.save(save_path, "png")
            try:
                os.remove(ps_path)
            except Exception:
                pass
            messagebox.showinfo("Export", f"Exported:\n{save_path}")
        except Exception:
            messagebox.showinfo(
                "Export",
                "Exported PostScript successfully, but PNG conversion requires Pillow.\n\n"
                f"Saved:\n{ps_path}\n\nInstall Pillow:\n  pip install pillow"
            )

    def export_pdf(self):
        if not self._topo.devices:
            messagebox.showwarning("Export", "Nothing loaded.")
            return

        save_path = filedialog.asksaveasfilename(
            title="Export topology PDF",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")]
        )
        if not save_path:
            return

        ps_path = save_path[:-4] + ".ps"
        try:
            self.canvas.postscript(file=ps_path, colormode="color")
        except Exception as e:
            messagebox.showerror("Export", f"Failed to export PostScript:\n{e}")
            return

        try:
            from PIL import Image  # type: ignore
            img = Image.open(ps_path)
            # Convert and save as PDF
            img.convert("RGB").save(save_path, "PDF")
            try:
                os.remove(ps_path)
            except Exception:
                pass
            messagebox.showinfo("Export", f"Exported:\n{save_path}")
        except Exception:
            messagebox.showinfo(
                "Export",
                "Exported PostScript successfully, but PDF conversion requires Pillow.\n\n"
                f"Saved:\n{ps_path}\n\nInstall Pillow:\n  pip install pillow"
            )

    # ---------------- Device selection / rendering ----------------

    def _refresh_device_list(self):
        q = (self.search_var.get() or "").strip().lower()
        self.device_list.delete(0, "end")
        for hn in self._device_order:
            d = self._topo.devices.get(hn)
            if not d:
                continue
            label = f"{hn}   •   {d.vendor}"
            if q and q not in hn.lower() and q not in (d.vendor or "").lower():
                continue
            self.device_list.insert("end", label)

    def _on_select_device(self, _evt=None):
        sel = self.device_list.curselection()
        if not sel:
            return
        label = self.device_list.get(sel[0])
        hn = label.split("   •   ", 1)[0].strip()
        if hn in self._topo.devices:
            self._select_device(hn)

    def _select_device(self, hostname: str):
        self._active_device = hostname
        d = self._topo.devices.get(hostname)
        if not d:
            return

        # sync list selection
        for i in range(self.device_list.size()):
            label = self.device_list.get(i)
            hn = label.split("   •   ", 1)[0].strip()
            if hn == hostname:
                self.device_list.selection_clear(0, "end")
                self.device_list.selection_set(i)
                self.device_list.see(i)
                break

        # render details + inspector + raw
        self._render_details(d)
        self._render_inspector(d)
        self._render_raw(d)
        self.draw_topology()

    def _render_details(self, d: DeviceSummary):
        # Identity
        if hasattr(self, "identity_text"):
            self._set_text(self.identity_text, self._identity_block(d))

        # Pairing
        if hasattr(self, "pair_text"):
            self._set_text(self.pair_text, self._pairing_block(d))

        # L2
        if hasattr(self, "l2_text"):
            self._set_text(self.l2_text, self._l2_block(d))

        if hasattr(self, "vlan_tree"):
            for item in self.vlan_tree.get_children():
                self.vlan_tree.delete(item)
            for v in sorted(d.vlans, key=lambda x: int(x.vid) if x.vid.isdigit() else 9999)[:200]:
                self.vlan_tree.insert("", "end", values=(v.vid, v.name))

        if hasattr(self, "pc_tree"):
            for item in self.pc_tree.get_children():
                self.pc_tree.delete(item)
            for pc_id in sorted(d.port_channels.keys(), key=lambda x: int(x) if x.isdigit() else 9999):
                pc = d.port_channels[pc_id]
                mem = ", ".join(pc.members[:6]) + ("…" if len(pc.members) > 6 else "")
                self.pc_tree.insert(
                    "", "end",
                    values=(pc.name, mem, pc.mode or "—", pc.trunk_vlans_raw or "—", pc.vpc_id or "—", "yes" if pc.is_peer_link else "—")
                )

        # L3
        if hasattr(self, "l3_text"):
            self._set_text(self.l3_text, self._l3_block(d))

        if hasattr(self, "ip_tree"):
            for item in self.ip_tree.get_children():
                self.ip_tree.delete(item)
            ip_rows: List[Tuple[str, str, str]] = []
            for ifn, iface in d.interfaces.items():
                if iface.ip and (iface.mode == "routed" or iface.is_svi or iface.is_switchport is False):
                    ip_rows.append((ifn, iface.ip, iface.vrf or "default"))
            for ifn, ip, vrf in sorted(ip_rows, key=lambda x: x[0].lower())[:200]:
                self.ip_tree.insert("", "end", values=(ifn, ip, vrf))

        if hasattr(self, "route_tree"):
            for item in self.route_tree.get_children():
                self.route_tree.delete(item)
            for r in d.static_routes[:20]:
                self.route_tree.insert("", "end", values=(r.vrf, r.prefix, r.nexthop))

        # Interfaces table
        self._render_interfaces_table()

    def _render_interfaces_table(self):
        if not self._active_device or not hasattr(self, "if_tree"):
            return
        d = self._topo.devices.get(self._active_device)
        if not d:
            return

        for item in self.if_tree.get_children():
            self.if_tree.delete(item)

        mode_filter = self.if_filter_var.get() if hasattr(self, "if_filter_var") else "all"

        rows = []
        for ifn, iface in d.interfaces.items():
            po = iface.channel_group or ""
            mode = iface.mode or ("routed" if iface.is_switchport is False else "—")
            if mode_filter == "access" and mode != "access":
                continue
            if mode_filter == "trunk" and mode != "trunk":
                continue
            if mode_filter == "routed" and not (mode == "routed" or iface.ip):
                continue
            if mode_filter == "pc" and not po:
                continue

            rows.append((
                ifn,
                mode or "—",
                iface.access_vlan or "—",
                iface.trunk_vlans_raw or "—",
                iface.native_vlan or "—",
                po or "—",
                iface.ip or "—",
                iface.vrf or "default",
                iface.description or "—"
            ))

        for r in sorted(rows, key=lambda x: x[0].lower())[:800]:
            self.if_tree.insert("", "end", values=r)

    def _render_raw(self, d: DeviceSummary):
        self._set_text(self.raw_text, d.raw_text or "")

        if d.hostname not in self._cached_device_json:
            self._cached_device_json[d.hostname] = json.dumps(_device_to_export_dict(d), indent=2)
        self._set_text(self.json_text, self._cached_device_json[d.hostname])

    def _render_inspector(self, d: DeviceSummary):
        lines: List[str] = []
        lines.append(f"{d.hostname}")
        lines.append(f"{d.vendor}")
        lines.append("")
        lines.append("Quick facts")
        lines.append(f"  Model: {d.model}")
        lines.append(f"  OS   : {d.os_ver}")
        lines.append(f"  Mgmt : {d.mgmt_ip}")
        lines.append("")
        lines.append("L2")
        lines.append(f"  VLANs        : {len(d.vlans)}")
        lines.append(f"  Port-channels: {len(d.port_channels)}")
        lines.append(f"  STP          : {d.stp_mode or '—'}  priority {d.stp_priority or '—'}")
        lines.append("")
        lines.append("L3")
        lines.append(f"  Routing      : {', '.join(d.routing_protocols) if d.routing_protocols else '—'}")
        lines.append(f"  Static routes: {len(d.static_routes)}")
        lines.append(f"  VRFs         : {', '.join(sorted(d.vrfs.keys())) if d.vrfs else 'default'}")
        lines.append("")
        lines.append("Evidence")
        lines.append(f"  CDP adjacencies: {len(d.cdp)}")
        lines.append(f"  Links involving this device: {self._count_links_for(d.hostname)}")
        lines.append("")
        lines.append("Pairing")
        lines.append(self._pairing_inline_summary(d))

        self._set_inspector_text("\n".join(lines))

    def _count_links_for(self, hostname: str) -> int:
        c = 0
        for l in self._topo.links:
            if l.a == hostname or l.b == hostname:
                c += 1
        return c

    # ---------------- Text blocks ----------------

    def _identity_block(self, d: DeviceSummary) -> str:
        return "\n".join([
            "Identity",
            f"  Hostname : {d.hostname}",
            f"  Vendor   : {d.vendor}",
            f"  Model    : {d.model}",
            f"  OS       : {d.os_ver}",
            f"  Mgmt IP  : {d.mgmt_ip}",
        ])

    def _pairing_inline_summary(self, d: DeviceSummary) -> str:
        # show most relevant pair line for this device
        for p in self._topo.pairs:
            if p.a == d.hostname or p.b == d.hostname:
                other = p.b if p.a == d.hostname else p.a
                return f"  {p.kind}: likely peer {other} ({p.confidence})"
        if d.vpc_configured:
            return "  vPC: configured (peer not confidently inferred yet)"
        if d.vlt_domain:
            return f"  VLT: domain {d.vlt_domain}"
        if d.mlag_domain:
            return "  MLAG: configured"
        return "  —"

    def _pairing_block(self, d: DeviceSummary) -> str:
        lines: List[str] = []
        lines.append("Clustering / Pairing")

        if d.vpc_configured:
            lines.append("vPC (NX-OS)")
            lines.append(f"  Domain     : {d.vpc_domain or '—'}")
            lines.append(f"  Keepalive  : dest {d.vpc_keepalive_dst or '—'}  source {d.vpc_keepalive_src or '—'}")
            lines.append(f"  Peer-link  : {d.vpc_peerlink_po or '—'}")
            if d.vpc_peerlink_members:
                lines.append(f"  Peer-link members: {', '.join(d.vpc_peerlink_members)}")

            # reasoning lines from inferred pair
            for p in self._topo.pairs:
                if p.kind == "vPC" and (p.a == d.hostname or p.b == d.hostname):
                    other = p.b if p.a == d.hostname else p.a
                    lines.append("")
                    lines.append(f"Likely vPC peer: {other} ({p.confidence})")
                    for r in p.reasons:
                        lines.append(f"  • {r}")
                    break

        if d.vlt_domain:
            lines.append("")
            lines.append("VLT (Dell OS10)")
            lines.append(f"  Domain: {d.vlt_domain}")

        if d.mlag_domain:
            lines.append("")
            lines.append("MLAG (Arista EOS)")
            lines.append("  Configured: yes")

        if not (d.vpc_configured or d.vlt_domain or d.mlag_domain):
            lines.append("—")

        return "\n".join(lines)

    def _l2_block(self, d: DeviceSummary) -> str:
        trunks = 0
        access = 0
        routed = 0
        for iface in d.interfaces.values():
            if iface.mode == "trunk":
                trunks += 1
            elif iface.mode == "access":
                access += 1
            elif iface.mode == "routed" or (iface.ip and iface.is_switchport is False):
                routed += 1

        peer_pos = [pc for pc in d.port_channels.values() if pc.is_peer_link]
        lines = [
            "Layer 2 Summary",
            f"  VLANs         : {len(d.vlans)}",
            f"  Port-channels : {len(d.port_channels)}",
            f"  Access ports  : {access}",
            f"  Trunk ports   : {trunks}",
            f"  Routed ports  : {routed}",
            f"  STP           : {d.stp_mode or '—'}  priority {d.stp_priority or '—'}",
            f"  Peer-link Po  : {peer_pos[0].name if peer_pos else (d.vpc_peerlink_po or '—')}",
        ]
        # Add clustering info
        if d.vpc_configured:
            lines.append(f"  vPC domain    : {d.vpc_domain or '—'}")
            lines.append(f"  vPC keepalive : {d.vpc_keepalive_dst or '—'}")
        if d.vlt_domain:
            lines.append(f"  VLT domain    : {d.vlt_domain}")
        if d.mlag_domain:
            lines.append(f"  MLAG domain   : {d.mlag_domain}")
        return "\n".join(lines)

    def _l3_block(self, d: DeviceSummary) -> str:
        ip_count = 0
        svi_count = 0
        for iface in d.interfaces.values():
            if iface.ip:
                ip_count += 1
            if iface.is_svi and iface.ip:
                svi_count += 1

        vrfs = sorted(d.vrfs.keys()) if d.vrfs else ["default"]
        # Count BGP neighbors from topology links
        bgp_neighbors = 0
        for link in self._topo.links:
            if link.kind == "L3" and (link.a == d.hostname or link.b == d.hostname):
                if link.evidence in ("ip-subnet", "external"):
                    bgp_neighbors += 1
        
        lines = [
            "Layer 3 Summary",
            f"  IP interfaces : {ip_count}",
            f"  SVIs          : {svi_count}",
            f"  VRFs          : {', '.join(vrfs)}",
            f"  Routing protos: {', '.join(d.routing_protocols) if d.routing_protocols else '—'}",
            f"  Static routes : {len(d.static_routes)}",
            f"  BGP neighbors : {bgp_neighbors}",
            f"  CDP neighbors : {len(d.cdp)}",
        ]
        return "\n".join(lines)

    # ---------------- Raw copy ----------------

    def copy_raw(self):
        if not self._active_device:
            return
        d = self._topo.devices.get(self._active_device)
        if not d:
            return
        self.clipboard_clear()
        self.clipboard_append(d.raw_text or "")

    def copy_json(self):
        if not self._active_device:
            return
        txt = self._cached_device_json.get(self._active_device)
        if not txt:
            return
        self.clipboard_clear()
        self.clipboard_append(txt)

    # ---------------- Canvas / topology ----------------

    def auto_layout(self):
        if not self._topo.devices:
            self.draw_topology()
            return
        w = max(700, self.canvas.winfo_width() if hasattr(self, "canvas") else 900)
        names = sorted(self._topo.devices.keys())

        # Larger spacing for larger nodes (420x200)
        cols = max(1, int(w / 480))
        x0, y0 = 280, 180
        dx, dy = 480, 260
        for idx, name in enumerate(names):
            if name in self._node_pos:
                continue
            r = idx // cols
            c = idx % cols
            self._node_pos[name] = (x0 + c * dx, y0 + r * dy)

        self.draw_topology()

    def _zoom_in(self):
        """Increase zoom level."""
        self.zoom_level = min(self.zoom_level * 1.2, self.zoom_max)
        self.draw_topology()

    def _zoom_out(self):
        """Decrease zoom level."""
        self.zoom_level = max(self.zoom_level / 1.2, self.zoom_min)
        self.draw_topology()

    def _zoom_reset(self):
        """Reset zoom to 100% and pan to origin."""
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.draw_topology()

    def _zoom_fit_all(self):
        """Auto-scale to fit all devices in view."""
        if not self._topo.devices or not self._node_pos:
            return
        
        # Get bounding box of all nodes
        xs = [x for x, y in self._node_pos.values()]
        ys = [y for x, y in self._node_pos.values()]
        if not xs or not ys:
            return
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        # Add padding
        padding = 100
        min_x -= padding
        max_x += padding
        min_y -= padding
        max_y += padding
        
        # Calculate zoom to fit
        canvas_w = self.canvas.winfo_width() or 900
        canvas_h = self.canvas.winfo_height() or 600
        
        bbox_w = max_x - min_x
        bbox_h = max_y - min_y
        
        if bbox_w > 0 and bbox_h > 0:
            zoom_x = (canvas_w * 0.8) / bbox_w
            zoom_y = (canvas_h * 0.8) / bbox_h
            self.zoom_level = min(zoom_x, zoom_y, self.zoom_max)
            
            # Center view on bbox
            self.pan_x = (canvas_w / 2) - ((min_x + max_x) / 2) * self.zoom_level
            self.pan_y = (canvas_h / 2) - ((min_y + max_y) / 2) * self.zoom_level
        
        self.draw_topology()

    def _on_mouse_wheel(self, evt):
        """Handle mouse wheel zoom (Ctrl required on some platforms)."""
        # Get wheel delta
        delta = 0
        if evt.num == 5 or evt.delta < 0:
            delta = -1  # scroll down / away
        elif evt.num == 4 or evt.delta > 0:
            delta = 1   # scroll up / toward
        
        if delta == 0:
            return
        
        # Only zoom if Ctrl is pressed OR if it's a scroll event (num 4/5)
        if evt.num in (4, 5) or (evt.state & 0x4):  # 0x4 is Ctrl mask
            old_zoom = self.zoom_level
            self.zoom_level *= (1.2 if delta > 0 else (1.0 / 1.2))
            self.zoom_level = max(self.zoom_min, min(self.zoom_level, self.zoom_max))
            
            # Zoom centered on cursor
            canvas_w = self.canvas.winfo_width() or 900
            canvas_h = self.canvas.winfo_height() or 600
            cursor_x = evt.x - self.pan_x
            cursor_y = evt.y - self.pan_y
            
            # Adjust pan to keep cursor position fixed
            zoom_ratio = self.zoom_level / old_zoom
            self.pan_x = evt.x - cursor_x * zoom_ratio
            self.pan_y = evt.y - cursor_y * zoom_ratio
            
            self.draw_topology()

    def _draw_grid(self, canvas, xform):
        """Draw subtle grid lines scaled with zoom."""
        canvas_w = canvas.winfo_width() or 900
        canvas_h = canvas.winfo_height() or 600
        
        grid_spacing = 100  # Base spacing in world units
        grid_color = "#2a3038"  # Subtle dark color
        
        # Calculate grid density based on zoom
        screen_spacing = grid_spacing * self.zoom_level
        if screen_spacing < 10:
            grid_spacing *= 5  # Skip more lines when zoomed out
        elif screen_spacing > 100:
            grid_spacing //= 2  # Add more lines when zoomed in
        
        # Draw vertical lines
        x = -self.pan_x / self.zoom_level if self.zoom_level > 0 else 0
        while x < canvas_w / self.zoom_level:
            x_world = int(x)
            if x_world % grid_spacing == 0:
                x_screen, _ = xform(x_world, 0)
                canvas.create_line(x_screen, 0, x_screen, canvas_h, fill=grid_color, dash=(2, 4))
            x += 10
        
        # Draw horizontal lines
        y = -self.pan_y / self.zoom_level if self.zoom_level > 0 else 0
        while y < canvas_h / self.zoom_level:
            y_world = int(y)
            if y_world % grid_spacing == 0:
                _, y_screen = xform(0, y_world)
                canvas.create_line(0, y_screen, canvas_w, y_screen, fill=grid_color, dash=(2, 4))
            y += 10

    def _draw_edge_labels(self, canvas, link_labels):
        """Draw edge labels with improved contrast and collision avoidance."""
        if not link_labels:
            return
        
        # Sort by position to process top-to-bottom, left-to-right
        link_labels.sort(key=lambda l: (l["y1"] + l["y2"], l["x1"] + l["x2"]))
        
        used_regions = []  # Track label positions to avoid collisions
        
        for label_data in link_labels:
            x1, y1 = label_data["x1"], label_data["y1"]
            x2, y2 = label_data["x2"], label_data["y2"]
            
            # Mid-point of edge
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2
            
            # Perpendicular offset for readability
            dx = x2 - x1
            dy = y2 - y1
            dist = (dx**2 + dy**2)**0.5
            
            if dist > 0:
                # Unit perpendicular vector
                perp_x = -dy / dist
                perp_y = dx / dist
                
                # Try offsets: original, offset +, offset -
                offsets = [0, 20, -20]
                placed = False
                
                for offset in offsets:
                    label_x = mx + perp_x * offset
                    label_y = my + perp_y * offset
                    
                    # Check collision
                    collision = False
                    for region in used_regions:
                        if abs(label_x - region[0]) < 80 and abs(label_y - region[1]) < 30:
                            collision = True
                            break
                    
                    if not collision:
                        # Draw label with dark rounded background (simulated with rectangle)
                        label_text = label_data["text"]
                        
                        # Create dark background
                        canvas.create_rectangle(
                            label_x - 60, label_y - 12,
                            label_x + 60, label_y + 12,
                            fill=self.colors.panel2, outline=self.colors.border, width=1
                        )
                        
                        # Draw text with high contrast
                        canvas.create_text(
                            label_x, label_y,
                            text=label_text, fill="#e8e3d7",
                            font=("Segoe UI", 7, "bold"),
                            justify="center"
                        )
                        
                        used_regions.append((label_x, label_y))
                        placed = True
                        break
                
                # Fallback: just place it if no good location found
                if not placed and link_labels.index(label_data) < 5:  # Only fallback for first few
                    canvas.create_rectangle(
                        mx - 60, my - 12,
                        mx + 60, my + 12,
                        fill=self.colors.panel2, outline=self.colors.border, width=1
                    )
                    canvas.create_text(
                        mx, my,
                        text=label_data["text"], fill="#e8e3d7",
                        font=("Segoe UI", 7, "bold"),
                        justify="center"
                    )

    def _format_node_info(self, d: DeviceSummary) -> List[str]:
        """Format device info for display inside topology node."""
        lines = []
        
        # Header: hostname + vendor/model/os
        lines.append(d.hostname)
        model_str = f"{d.vendor} {d.model}" if d.model != "—" else d.vendor
        lines.append(f"{model_str} | {d.os_ver}")
        
        # Redundancy section if applicable
        if d.vpc_configured:
            lines.append(f"vPC domain {d.vpc_domain} (peer-link {d.vpc_peerlink_po or '—'})")
        elif d.vlt_domain:
            lines.append(f"VLT domain {d.vlt_domain}")
        elif d.mlag_domain:
            lines.append(f"MLAG domain {d.mlag_domain}")
        
        # L2 summary
        trunks = sum(1 for i in d.interfaces.values() if i.mode == "trunk")
        access = sum(1 for i in d.interfaces.values() if i.mode == "access")
        svi_count = sum(1 for i in d.interfaces.values() if i.is_svi and i.ip)
        
        lines.append(f"L2: {len(d.vlans)} VLANs | {trunks} Trunks | {access} Access | {len(d.port_channels)} PCs")
        
        # L3 summary
        vrf_count = len(d.vrfs) if d.vrfs else 1
        bgp_asn = d.bgp_asn or "—"
        bgp_neighbors = 0
        
        # Count BGP neighbors from topology links
        for link in self._topo.links:
            if link.kind == "L3" and (link.a == d.hostname or link.b == d.hostname):
                bgp_neighbors += 1
        
        lines.append(f"L3: {svi_count} SVIs | {vrf_count} VRFs | BGP {bgp_asn} ({bgp_neighbors} peers)")
        
        # Topology connections summary
        neighbors = set()
        for link in self._topo.links:
            if link.a == d.hostname:
                neighbors.add(link.b)
            elif link.b == d.hostname:
                neighbors.add(link.a)
        
        if neighbors:
            lines.append(f"Connected to: {', '.join(sorted(neighbors))}")
        
        return lines

    def draw_topology(self):
        if not hasattr(self, "canvas"):
            return
        c = self.canvas
        c.delete("all")

        if not self._topo.devices:
            c.create_text(20, 20, anchor="nw", fill=self.colors.muted,
                          text="Load files to build a topology view.", font=("Segoe UI", 11))
            return

        # ensure positions
        for name in self._topo.devices.keys():
            if name not in self._node_pos:
                self.auto_layout()
                break

        # Helper to transform coordinates with zoom and pan
        def xform(x: int, y: int) -> tuple:
            """Apply zoom and pan transformation."""
            return (x * self.zoom_level + self.pan_x, y * self.zoom_level + self.pan_y)

        # Draw grid if enabled
        if self.var_show_grid.get():
            self._draw_grid(c, xform)

        # links with improved labels
        link_labels = []  # Collect labels for post-processing
        for link in self._topo.links:
            if link.kind == "L2" and not self.var_show_l2.get():
                continue
            if link.kind == "L3" and not self.var_show_l3.get():
                continue
            if link.confidence == "medium" and not self.var_show_medium.get():
                continue

            if link.a not in self._node_pos or link.b not in self._node_pos:
                continue

            ax, ay = self._node_pos[link.a]
            bx, by = self._node_pos[link.b]

            # Transform endpoints
            ax_zoom, ay_zoom = xform(ax, ay)
            bx_zoom, by_zoom = xform(bx, by)

            color = self.colors.l2 if link.kind == "L2" else self.colors.l3
            width = max(1, int(3 * self.zoom_level)) if link.kind == "L2" else max(1, int(2 * self.zoom_level))
            dash = () if link.kind == "L2" else (6, 4)

            c.create_line(ax_zoom, ay_zoom, bx_zoom, by_zoom, fill=color, width=width, dash=dash)

            if self.var_show_labels.get():
                # Prepare label data (process later for collision avoidance)
                label_text = f"{link.a}:{link.a_intf} ↔ {link.b}:{link.b_intf}\n({link.evidence})"
                link_labels.append({
                    "text": label_text,
                    "x1": ax_zoom,
                    "y1": ay_zoom,
                    "x2": bx_zoom,
                    "y2": by_zoom,
                    "link": link
                })
        
        # Draw edge labels with improved contrast
        self._draw_edge_labels(c, link_labels)

        # nodes with embedded detail information
        for name in sorted(self._topo.devices.keys()):
            d = self._topo.devices[name]
            x, y = self._node_pos.get(name, (180, 140))
            is_active = (name == self._active_device)

            # Larger node to accommodate detail
            node_w, node_h = 420, 200
            x0 = x - node_w // 2
            y0 = y - node_h // 2
            x1 = x + node_w // 2
            y1 = y + node_h // 2

            # Transform node corners
            x0_zoom, y0_zoom = xform(x0, y0)
            x1_zoom, y1_zoom = xform(x1, y1)

            fill = "#1b2232" if not is_active else "#223050"
            outline = self.colors.border if not is_active else self.colors.accent
            line_width = max(1, int(2 * self.zoom_level)) if not is_active else max(1, int(3 * self.zoom_level))

            tag = f"node:{name}"
            c.create_rectangle(x0_zoom, y0_zoom, x1_zoom, y1_zoom, fill=fill, outline=outline, width=line_width, tags=(tag,))

            # Format and draw multi-line node info
            info_lines = self._format_node_info(d)
            line_height = max(10, int(14 * self.zoom_level))
            start_y = y0_zoom + max(5, int(10 * self.zoom_level))
            
            for idx, line in enumerate(info_lines):
                y_pos = start_y + (idx * line_height)
                if y_pos > y1_zoom - 10:
                    break
                # Use smaller font for compact display (scale with zoom)
                font_size = max(7, int((9 if idx == 0 else 8) * (self.zoom_level ** 0.5)))
                font_weight = "bold" if idx == 0 else "normal"
                text_color = self.colors.text if idx == 0 else self.colors.muted
                c.create_text(x0_zoom + max(5, int(8 * self.zoom_level)), y_pos, anchor="nw", text=line, fill=text_color,
                             font=("Segoe UI", font_size, font_weight), tags=(tag,))

    def _hit_test_node(self, x: int, y: int) -> Optional[str]:
        items = self.canvas.find_overlapping(x, y, x, y)
        for it in items:
            tags = self.canvas.gettags(it)
            for t in tags:
                if t.startswith("node:"):
                    return t.split("node:", 1)[1]
        return None

    def _on_canvas_down(self, evt):
        name = self._hit_test_node(evt.x, evt.y)
        if not name:
            self._dragging = None
            return
        self._dragging = name
        self._drag_start = (evt.x, evt.y)
        self._select_device(name)

    def _on_canvas_drag(self, evt):
        if not self._dragging:
            return
        dx = (evt.x - self._drag_start[0]) / self.zoom_level if self.zoom_level > 0 else 0
        dy = (evt.y - self._drag_start[1]) / self.zoom_level if self.zoom_level > 0 else 0
        x, y = self._node_pos.get(self._dragging, (evt.x, evt.y))
        self._node_pos[self._dragging] = (x + dx, y + dy)
        self._drag_start = (evt.x, evt.y)
        self.draw_topology()

    def _on_canvas_up(self, _evt):
        self._dragging = None



    # ---------------- small helpers ----------------

    def _set_text(self, widget: tk.Text, text: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _set_inspector_text(self, text: str):
        self.ins_text.configure(state="normal")
        self.ins_text.delete("1.0", "end")
        self.ins_text.insert("1.0", text)
        self.ins_text.configure(state="disabled")


def _device_to_export_dict(d: DeviceSummary) -> Dict[str, Any]:
    return {
        "hostname": d.hostname,
        "vendor": d.vendor,
        "model": d.model,
        "os_ver": d.os_ver,
        "mgmt_ip": d.mgmt_ip,
        "stp_mode": d.stp_mode,
        "stp_priority": d.stp_priority,
        "vpc": {
            "configured": d.vpc_configured,
            "domain": d.vpc_domain,
            "keepalive_dst": d.vpc_keepalive_dst,
            "keepalive_src": d.vpc_keepalive_src,
            "peerlink_po": d.vpc_peerlink_po,
            "peerlink_members": d.vpc_peerlink_members,
        },
        "vlt_domain": d.vlt_domain,
        "mlag": {"configured": bool(d.mlag_domain)},
        "routing_protocols": d.routing_protocols,
        "static_routes": [asdict(r) for r in d.static_routes],
        "vrfs": d.vrfs,
        "vlans": [asdict(v) for v in d.vlans],
        "interfaces": {k: asdict(v) for k, v in d.interfaces.items()},
        "port_channels": {k: asdict(v) for k, v in d.port_channels.items()},
        "cdp": [asdict(c) for c in d.cdp],
    }


# ============================================================
# Entrypoint
# ============================================================

def main():
    root = tk.Tk()
    root.title("FabricWeaver")
    root.geometry("1400x820")
    apply_dark_theme(root)

    app = FabricWeaverApp(root)
    app.pack(fill="both", expand=True)

    root.mainloop()


if __name__ == "__main__":
    main()