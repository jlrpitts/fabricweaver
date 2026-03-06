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
import logging
import logging.handlers
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any, Set

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ============================================================
# Logging Configuration
# ============================================================

def setup_logging():
    """Configure logging for troubleshooting"""
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f'fabricweaver_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    # Create logger
    logger = logging.getLogger('fabricweaver')
    logger.setLevel(logging.DEBUG)
    
    # File handler (detailed logs)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler (errors only in console)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.debug(f"=== FabricWeaver Session Started ===")
    logger.debug(f"Log file: {log_file}")
    
    return logger, log_file

logger, LOG_FILE = setup_logging()



# ============================================================
# Theme (prefer ui.theme; fallback if missing)
# ============================================================

@dataclass
class ThemeColors:
    bg: str = "#ffffff"         # Pure white background
    panel: str = "#ffffff"      # White panels
    panel2: str = "#f9f9f9"     # Almost white
    text: str = "#1a1a1a"       # Dark text for contrast
    muted: str = "#8a8a8a"      # Lighter gray for muted text
    border: str = "#e5e5e5"     # Very light border
    accent: str = "#4a9ef5"     # Bright blue
    accent2: str = "#7db8d6"    # Soft blue
    l2: str = "#eb6f5f"         # Red (L2 links)
    l3: str = "#72c472"         # Green (L3 links)


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
        style.configure("Accent.TButton", padding=(8, 6), background=c.accent, foreground="#1a1a1a")
        style.map("Accent.TButton",
              background=[("active", c.accent2), ("pressed", c.accent2)],
              foreground=[("active", "#1a1a1a"), ("pressed", "#1a1a1a")])

        style.configure("Primary.TButton", padding=(10, 7), background=c.accent, foreground="#1a1a1a")
        style.map("Primary.TButton",
                  background=[("active", c.accent2), ("pressed", c.accent2)],
                  foreground=[("active", "#1a1a1a"), ("pressed", "#1a1a1a")])

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
                  background=[("selected", "#d4e9f7")],
                  foreground=[("selected", c.text)])

        style.configure("TSeparator", background=c.border)

        # Checkbutton / Toggle visibility styling - disable all highlighting
        try:
            # Configure base style with flat relief to prevent 3D effects
            style.configure("Toggle.TCheckbutton", 
                          background=c.panel, 
                          foreground=c.text,
                          relief="flat",
                          borderwidth=0)
            # Clear any state-based mappings by setting them all to same value
            # This prevents color changes on hover, click, or selection
            style.map("Toggle.TCheckbutton",
                      background=[],  # No state-based background changes
                      foreground=[],  # No state-based foreground changes
                      relief=[])      # No state-based relief changes
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
    virtual_ip: str = ""      # HSRP/VRRP virtual IP (if any)
    hsrp_group: str = ""      # HSRP group ID (if configured)
    vrrp_group: str = ""      # VRRP group ID (if configured)


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
class HsrpGroup:
    interface: str
    group_id: str
    vip: str = ""
    priority: str = ""
    state: str = ""
    timers: str = ""


@dataclass
class LoopbackInfo:
    interface: str
    ip: str = ""
    vrf: str = "default"
    description: str = ""


@dataclass
class BgpNeighbor:
    neighbor_ip: str
    remote_as: str = ""
    vrf: str = "default"
    state: str = ""
    description: str = ""


@dataclass
class OspfNeighbor:
    neighbor_id: str
    interface: str = ""
    state: str = ""
    area: str = ""


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
    bgp_neighbors: List[BgpNeighbor] = field(default_factory=list)
    ospf_neighbors: List[OspfNeighbor] = field(default_factory=list)
    loopbacks: List[LoopbackInfo] = field(default_factory=list)
    static_routes: List[RouteInfo] = field(default_factory=list)
    fhrp: List[FhrpGroup] = field(default_factory=list)
    hsrp_groups: List[HsrpGroup] = field(default_factory=list)

    stp_mode: str = ""
    stp_priority: str = ""
    stp_root_bridge: str = ""
    rapid_pvst_enabled: bool = False

    vpc_configured: bool = False
    vpc_domain: str = ""
    vpc_keepalive_dst: str = ""
    vpc_keepalive_src: str = ""
    vpc_peerlink_po: str = ""
    vpc_peerlink_members: List[str] = field(default_factory=list)

    mlag_domain: str = ""
    vlt_domain: str = ""

    cdp: List[CdpAdjacency] = field(default_factory=list)
    acls: Dict[str, List[str]] = field(default_factory=dict)
    parse_errors: List[str] = field(default_factory=list)
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
    reasons: List[str] = field(default_factory=list)


@dataclass
class TopologyData:
    devices: Dict[str, DeviceSummary] = field(default_factory=dict)
    links: List[Link] = field(default_factory=list)
    pairs: List[PairInference] = field(default_factory=list)


# ============================================================
# Analysis data structures
# ============================================================

@dataclass
class ValidationIssue:
    device: str
    severity: str  # "warning", "error", "info"
    category: str  # "mtu", "routing", "stp", "vlan", "hsrp", "config"
    message: str


@dataclass
class DeviceRole:
    device: str
    role: str  # "core", "border", "distribution", "access", "unknown"
    confidence: str  # "high", "medium", "low"
    reasoning: List[str] = field(default_factory=list)


@dataclass
class InterfaceStats:
    total_interfaces: int = 0
    routed_count: int = 0
    access_count: int = 0
    trunk_count: int = 0
    pc_count: int = 0
    svi_count: int = 0
    shutdown_count: int = 0
    vlan_distribution: Dict[str, int] = field(default_factory=dict)  # vlan -> count


@dataclass
class VRFAnalysis:
    vrf_name: str
    device_count: int = 0
    devices: List[str] = field(default_factory=list)
    route_count: int = 0
    interface_count: int = 0


# ============================================================
# Embedded parsing (fallback / default)
# ============================================================

HOST_RE = re.compile(r"^\s*(?:hostname|switchname)\s+(\S+)", re.IGNORECASE | re.MULTILINE)

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
STP_ROOT_RE = re.compile(r"(?im)Root ID.*?Priority\s+(\d+).*?Mac Address\s+([\w.]+)", re.MULTILINE)
RAPID_PVST_RE = re.compile(r"^\s*(?:feature\s+)?(?:spanning-tree\s+mode\s+)?rapid-pvst", re.IGNORECASE | re.MULTILINE)

# HSRP/VRRP
HSRP_GROUP_RE = re.compile(r"^\s*(?:standby|hsrp)\s+(\d+)", re.IGNORECASE | re.MULTILINE)
HSRP_VIP_RE = re.compile(r"^\s*(?:standby|hsrp)\s+\d+\s+ip\s+(\d+\.\d+\.\d+\.\d+)", re.IGNORECASE | re.MULTILINE)
HSRP_PRIORITY_RE = re.compile(r"^\s*(?:standby|hsrp)\s+\d+\s+priority\s+(\d+)", re.IGNORECASE | re.MULTILINE)
VRRP_GROUP_RE = re.compile(r"^\s*vrrp\s+(\d+)", re.IGNORECASE | re.MULTILINE)
VRRP_VIP_RE = re.compile(r"^\s*vrrp\s+\d+\s+address\s+(\d+\.\d+\.\d+\.\d+)", re.IGNORECASE | re.MULTILINE)

# ACLs
ACL_DEF_RE = re.compile(r"^\s*(?:ip\s+access-list|access-list)\s+(?:standard|extended)?\s*(\S+)", re.IGNORECASE | re.MULTILINE)
ACL_NAMED_RE = re.compile(r"^\s*ip\s+access-list\s+(?:standard|extended)?\s*(\S+)", re.IGNORECASE | re.MULTILINE)
ACL_RULE_RE = re.compile(r"^\s*(?:\d+)?\s*(?:permit|deny)\s+(.+)$", re.IGNORECASE | re.MULTILINE)

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
FTD_HINT = re.compile(r"firepower|ftd|threat defense|firewall threat defense", re.IGNORECASE)

# show version hints (best effort)
MODEL_RE = re.compile(r"(?im)^\s*Model\s*:\s*(.+)$|^\s*Model number\s*:\s*(.+)$|^\s*cisco\s+nexus\s+(\S+)", re.MULTILINE)
NXOS_VER_RE = re.compile(r"(?im)\bNXOS:\s+version\s+(\S+)|\bsystem:\s+version\s+(\S+)|^software\s+version\s+(\S+)", re.MULTILINE)
IOS_VER_RE = re.compile(r"(?im)\bCisco IOS(?:XE)?\s+Software(?:.*\n)*?.*?Version\s+([\w.()]+)|Cisco IOS.*?Version\s+([\S.()]+)", re.MULTILINE)
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

# FTD-specific patterns
FTD_HOSTNAME_RE = re.compile(r"(?im)^\s*hostname\s*(\S+)|firepower>\s*show\s+(?:running-config|version).*?^hostname\s+(\S+)", re.MULTILINE)
FTD_INTERFACE_RE = re.compile(r"(?im)^interface\s+(\S+)$", re.MULTILINE)
FTD_INTERFACE_IP_RE = re.compile(r"(?im)^\s*ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", re.MULTILINE)
FTD_VERSION_RE = re.compile(r"(?im)(?:fw\s+version|model|firepower\s+version)\s*:?\s*(\S+.*?)(?:\n|$)", re.MULTILINE)
FTD_MODEL_RE = re.compile(r"(?im)(?:model|platform)\s*:?\s*(\S+.*?)(?:\n|$)", re.MULTILINE)
FTD_ROUTE_RE = re.compile(r"(?im)^(\d+\.\d+\.\d+\.\d+/\d+)\s+via\s+(\d+\.\d+\.\d+\.\d+)\s+.*?(?:\n|$)", re.MULTILINE)
FTD_ACL_RE = re.compile(r"(?im)^(?:access-list|access_list)\s+(\S+).*?(?:\n|$)", re.MULTILINE)
FTD_RUN_CONFIG_RE = re.compile(r"(?im)running-config|^firepower.*?#show\s+running-config", re.MULTILINE)


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
    # Check for switchname (NX-OS specific) or vPC membership (NX-OS specific)
    if re.search(r'switchname\s+\S+|vpc\s+domain\s+\d+', t, re.MULTILINE):
        return "Cisco Nexus (NX-OS)"
    if FTD_HINT.search(t):
        return "Cisco FTD (Firewall Threat Defense)"
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
    
    # Try NXOS first (most specific for this deployment)
    vm = NXOS_VER_RE.search(text)
    if not vm:
        vm = IOS_VER_RE.search(text)
    if not vm:
        vm = EOS_VER_RE.search(text)
    
    if vm:
        # Get first non-None group
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


def _parse_loopbacks(d: DeviceSummary, text: str) -> None:
    """Extract loopback interfaces with IPs and VRFs."""
    loopbacks: List[LoopbackInfo] = []
    
    # Pattern for loopback interfaces
    loopback_pattern = re.compile(
        r"interface\s+(Loopback|loopback|lo)(\d+).*?(?=^interface|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL
    )
    
    for m in loopback_pattern.finditer(text):
        ifname = f"{m.group(1)}{m.group(2)}"
        block = m.group(0)
        
        # Extract IP
        ip = ""
        ip_match = re.search(r"ip\s+address\s+(\S+(?:\s+\S+)?)", block, re.IGNORECASE)
        if ip_match:
            ip = ip_match.group(1).strip()
        
        # Extract VRF
        vrf = "default"
        vrf_match = re.search(r"(?:vrf\s+(?:member|forwarding)\s+|ip\s+vrf\s+forwarding\s+)(\S+)", block, re.IGNORECASE)
        if vrf_match:
            vrf = vrf_match.group(1).strip()
        
        # Extract description
        desc = ""
        desc_match = re.search(r"description\s+(.+)", block, re.IGNORECASE)
        if desc_match:
            desc = desc_match.group(1).strip()
        
        if ip:  # Only add if it has an IP
            loopbacks.append(LoopbackInfo(interface=ifname, ip=ip, vrf=vrf, description=desc))
    
    d.loopbacks = loopbacks


def _parse_bgp_neighbors(d: DeviceSummary, text: str) -> None:
    """Extract BGP neighbor relationships."""
    neighbors: List[BgpNeighbor] = []
    
    # Pattern for BGP neighbor configuration
    neighbor_pattern = re.compile(
        r"neighbor\s+(\S+)\s+remote-as\s+(\d+)",
        re.IGNORECASE
    )
    
    for m in neighbor_pattern.finditer(text):
        neighbor_ip = m.group(1)
        remote_as = m.group(2)
        
        # Try to find VRF context (look backwards for vrf or address-family)
        vrf = "default"
        start_pos = max(0, m.start() - 500)
        context = text[start_pos:m.start()]
        vrf_match = re.search(r"(?:vrf\s+|address-family\s+\S+\s+vrf\s+)(\S+)", context, re.IGNORECASE)
        if vrf_match:
            vrf = vrf_match.group(1)
        
        # Try to find description
        desc = ""
        desc_search = re.search(rf"neighbor\s+{re.escape(neighbor_ip)}\s+description\s+(.+)", text, re.IGNORECASE)
        if desc_search:
            desc = desc_search.group(1).strip()
        
        neighbors.append(BgpNeighbor(
            neighbor_ip=neighbor_ip,
            remote_as=remote_as,
            vrf=vrf,
            description=desc
        ))
    
    d.bgp_neighbors = neighbors


def _parse_ospf_neighbors(d: DeviceSummary, text: str) -> None:
    """Extract OSPF neighbor information from show commands."""
    neighbors: List[OspfNeighbor] = []
    
    # Pattern varies by vendor, but typically: neighbor_id interface state
    # NX-OS: "10.1.1.1    1    FULL/  -        Ethernet1/1"
    # IOS: "10.1.1.1    1    192.168.1.2    FULL/DR    Gi0/0/0"
    
    ospf_neighbor_pattern = re.compile(
        r"(\d+\.\d+\.\d+\.\d+)\s+\d+\s+(?:\d+\.\d+\.\d+\.\d+\s+)?(\w+/\S*)\s+\S*\s+(\S+)",
        re.IGNORECASE
    )
    
    # Also check for OSPF neighbor output in show commands
    for m in ospf_neighbor_pattern.finditer(text):
        neighbor_id = m.group(1)
        state = m.group(2)
        interface = m.group(3)
        
        # Only add if state suggests it's an OSPF neighbor (FULL, 2WAY, etc)
        if "FULL" in state.upper() or "2WAY" in state.upper():
            neighbors.append(OspfNeighbor(
                neighbor_id=neighbor_id,
                interface=interface,
                state=state
            ))
    
    d.ospf_neighbors = neighbors


def _parse_stp(d: DeviceSummary, text: str) -> None:
    m = STP_MODE_RE.search(text)
    if m:
        d.stp_mode = m.group(1).strip()
    mp = STP_PRI_RE.search(text) or STP_PRI_GLOBAL_RE.search(text)
    if mp:
        d.stp_priority = mp.group(1).strip()
    
    # Check for Rapid PVST
    if RAPID_PVST_RE.search(text):
        d.rapid_pvst_enabled = True
    
    # Try to extract root bridge info
    rm = STP_ROOT_RE.search(text)
    if rm:
        d.stp_root_bridge = rm.group(2).strip()


def _parse_hsrp_vrrp(d: DeviceSummary, text: str) -> None:
    """Parse HSRP and VRRP groups with enhanced details."""
    groups: List[HsrpGroup] = []
    
    # HSRP groups
    for m in HSRP_GROUP_RE.finditer(text):
        group_id = m.group(1).strip()
        start = m.end()
        # Look for VIP and priority in the following 500 chars
        window = text[start:min(start + 500, len(text))]
        
        vip = ""
        priority = ""
        
        vip_m = HSRP_VIP_RE.search(window)
        if vip_m:
            vip = vip_m.group(1).strip()
        
        pri_m = HSRP_PRIORITY_RE.search(window)
        if pri_m:
            priority = pri_m.group(1).strip()
        
        # Try to find interface name from context
        # Look backward from this point for the "interface" keyword
        intf_name = "—"
        lines_before = text[:m.start()].split('\n')
        # Search from the END backwards to find the most recent interface declaration
        # (which would be the one containing this HSRP group)
        for line in reversed(lines_before[-30:]):  # Look back up to 30 lines
            if re.match(r"^\s*interface", line, re.IGNORECASE):
                parts = line.split()
                if len(parts) >= 2:
                    intf_name = parts[1]
                break
        
        logger.debug(f"_parse_hsrp_vrrp: Found HSRP group {group_id} on interface {intf_name}, VIP={vip}")
        groups.append(HsrpGroup(interface=intf_name, group_id=group_id, vip=vip, priority=priority))
    
    # VRRP groups (similar pattern)
    for m in VRRP_GROUP_RE.finditer(text):
        group_id = m.group(1).strip()
        start = m.end()
        window = text[start:min(start + 500, len(text))]
        
        vip = ""
        vip_m = VRRP_VIP_RE.search(window)
        if vip_m:
            vip = vip_m.group(1).strip()
        
        intf_name = "—"
        lines_before = text[:m.start()].split('\n')
        for line in reversed(lines_before[-30:]):
            if re.match(r"^\s*interface", line, re.IGNORECASE):
                parts = line.split()
                if len(parts) >= 2:
                    intf_name = parts[1]
                break
        
        logger.debug(f"_parse_hsrp_vrrp: Found VRRP group {group_id} on interface {intf_name}, VIP={vip}")
        groups.append(HsrpGroup(interface=intf_name, group_id=group_id, vip=vip, priority=""))
    
    # De-dupe by group_id
    seen = set()
    deduped: List[HsrpGroup] = []
    for g in groups:
        key = (g.interface, g.group_id)
        if key not in seen:
            seen.add(key)
            deduped.append(g)
    
    d.hsrp_groups = deduped


def _link_hsrp_to_interfaces(d: DeviceSummary) -> None:
    """Link HSRP/VRRP virtual IPs to their interface objects."""
    for hsrp in d.hsrp_groups:
        intf_name = _norm_intf(hsrp.interface)
        
        # Find the matching interface (normalization required)
        for iface in d.interfaces.values():
            if _norm_intf(iface.name) == intf_name or iface.name == hsrp.interface:
                # Determine if it's HSRP or VRRP based on group patterns
                # HSRP groups are typically smaller numbers (0-255)
                # VRRP groups use "vrrp" keyword
                try:
                    gid = int(hsrp.group_id)
                    # If we parsed it from an HSRP section, mark as HSRP
                    if gid <= 255:
                        iface.hsrp_group = hsrp.group_id
                        iface.virtual_ip = hsrp.vip
                    else:
                        # Could be VRRP 
                        iface.vrrp_group = hsrp.group_id
                        iface.virtual_ip = hsrp.vip
                except Exception:
                    # Default to HSRP
                    iface.hsrp_group = hsrp.group_id
                    iface.virtual_ip = hsrp.vip
                logger.debug(f"Linked HSRP/VRRP to {iface.name}: VIP={hsrp.vip}, group={hsrp.group_id}")
                break


def _parse_acls(d: DeviceSummary, text: str) -> None:
    """Parse ACL definitions and their rules."""
    acls: Dict[str, List[str]] = {}
    
    # Find all named ACLs
    for m in ACL_NAMED_RE.finditer(text):
        acl_name = m.group(1).strip()
        start = m.end()
        
        # Get ACL rules until next 'exit' or next ACL definition
        end_idx = text.find('\nexit\n', start)
        if end_idx == -1:
            # Look for next ACL definition
            next_acl = ACL_NAMED_RE.search(text[start:])
            if next_acl:
                end_idx = start + next_acl.start()
            else:
                end_idx = len(text)
        else:
            end_idx = text.find('\n', end_idx) + 1
        
        acl_block = text[start:end_idx]
        
        # Extract rules from this block
        rules: List[str] = []
        for rule_m in ACL_RULE_RE.finditer(acl_block):
            rule_text = rule_m.group(0).strip()
            if "access-list" not in rule_text.lower():
                rules.append(rule_text[:100])  # Truncate long rules
        
        if rules:
            acls[acl_name] = rules[:20]  # Keep top 20 rules per ACL
    
    d.acls = acls


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


def _parse_ftd_hostname(text: str) -> Optional[str]:
    """Parse hostname from FTD output."""
    # Try FTD-specific hostname patterns
    m = FTD_HOSTNAME_RE.search(text)
    if m:
        for g in m.groups():
            if g and g.strip():
                return g.strip()
    return None


def _parse_ftd_interfaces(d: DeviceSummary, text: str) -> None:
    """Parse FTD interface configuration."""
    current_iface = None
    lines = text.splitlines()
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Detect interface start
        if stripped.lower().startswith("interface "):
            current_iface = stripped.split()[1]
            iface = d.interfaces.get(current_iface) or InterfaceInfo(name=current_iface)
            d.interfaces[current_iface] = iface
            continue
        
        # Parse interface properties
        if current_iface and stripped:
            iface = d.interfaces[current_iface]
            
            # Description
            if stripped.lower().startswith("description "):
                iface.description = stripped.split(" ", 1)[1].strip().strip('"')
            
            # IP address
            elif stripped.lower().startswith("ip address "):
                parts = stripped.split()
                if len(parts) >= 3:
                    iface.ip = f"{parts[2]}/{_mask_to_prefix(parts[3])}"
            
            # Shutdown state (if present, interface is down - track for later)
            elif stripped.lower() == "no shutdown":
                pass  # Interface is active
            elif stripped.lower() == "shutdown":
                pass  # Interface is inactive


def _parse_ftd_routes(d: DeviceSummary, text: str) -> None:
    """Parse FTD static routes."""
    routes: List[RouteInfo] = []
    
    for m in FTD_ROUTE_RE.finditer(text):
        prefix = m.group(1).strip()
        nexthop = m.group(2).strip()
        routes.append(RouteInfo(vrf="default", prefix=prefix, nexthop=nexthop))
    
    # De-dupe
    seen = set()
    deduped: List[RouteInfo] = []
    for r in routes:
        k = (r.vrf, r.prefix, r.nexthop)
        if k not in seen:
            seen.add(k)
            deduped.append(r)
    
    d.static_routes = deduped


def _parse_ftd_acls(d: DeviceSummary, text: str) -> None:
    """Parse FTD access-lists."""
    acls: Dict[str, List[str]] = {}
    
    # Find all ACL definitions
    acl_pattern = re.compile(r"(?im)^access-list\s+(\S+)\s+(.+)$", re.MULTILINE)
    
    for m in acl_pattern.finditer(text):
        acl_name = m.group(1).strip()
        acl_rule = m.group(2).strip()[:100]  # Truncate long rules
        
        if acl_name not in acls:
            acls[acl_name] = []
        
        if len(acls[acl_name]) < 20:  # Keep top 20 rules per ACL
            acls[acl_name].append(acl_rule)
    
    d.acls = acls


def _parse_ftd_version(d: DeviceSummary, text: str) -> None:
    """Parse FTD version and model information."""
    vm = FTD_VERSION_RE.search(text)
    if vm:
        d.os_ver = vm.group(1).strip()
    
    mm = FTD_MODEL_RE.search(text)
    if mm:
        d.model = mm.group(1).strip()


def _extract_config_from_ssh_dump(text: str) -> str:
    """
    Extract actual configuration from SSH session dumps.
    SSH dumps often contain: login banners, command prompts, command output.
    This function finds and extracts just the configuration section.
    """
    
    # Look for 'show running-config' or 'show configuration' markers
    config_markers = [
        r'!Command:\s*show\s+running-config',
        r'!Executing\s+.*?show\s+running-config',
        r'show\s+running-config',
        r'show\s+configuration',
    ]
    
    # Try to find config start
    config_start_match = None
    for marker in config_markers:
        m = re.search(marker, text, re.IGNORECASE | re.MULTILINE)
        if m:
            config_start_match = m
            break
    
    # If we found a config marker, extract from there
    if config_start_match:
        # Start from the marker
        config_section = text[config_start_match.start():]
        
        # Try to find end markers (common end-of-output patterns)
        end_markers = [
            r'^(\S+[#>])\s*exit',  # Device prompt followed by exit
            r'^(\S+[#>])\s*$\n^(\S+[#>])\s*$',  # Double prompt (end of output)
            r'^connection closed',
            r'^Bye\n',
            r'^logout',
        ]
        
        config_end = None
        for end_marker in end_markers:
            m = re.search(end_marker, config_section, re.IGNORECASE | re.MULTILINE)
            if m:
                config_end = m.start()
                break
        
        if config_end is None:
            config_end = len(config_section)
        
        config_section = config_section[:config_end]
    else:
        # No clear SSH dump format, use whole content
        config_section = text
    
    # Remove common SSH artifacts
    # Remove device prompts at the beginning of lines
    config_section = re.sub(r'^\s*\S+[#>]\s*', '', config_section, flags=re.MULTILINE)
    
    # Remove "terminal length" and similar setup commands 
    config_section = re.sub(r'^\s*terminal\s+length\s+\d+\s*$', '', config_section, flags=re.MULTILINE | re.IGNORECASE)
    
    # Remove blank lines created by prompt removal
    config_section = re.sub(r'^\s*$\n', '', config_section, flags=re.MULTILINE)
    
    # Remove SSH login banners (text before first config line)
    # Config typically starts with '!' (comment), 'version', 'hostname/', 'switchname', 'interface', 'vlan', etc.
    lines = config_section.split('\n')
    config_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and (
            stripped.startswith('!') or
            stripped.lower().startswith('version ') or
            stripped.lower().startswith('hostname ') or
            stripped.lower().startswith('switchname ') or
            stripped.lower().startswith('interface ') or
            stripped.lower().startswith('vlan ') or
            stripped.lower().startswith('feature ') or
            stripped.lower().startswith('router ') or
            stripped.lower().startswith('access-list ') or
            stripped.lower().startswith('line ') or
            stripped.lower().startswith('spanning-tree ')
        ):
            config_start = i
            break
    
    config_section = '\n'.join(lines[config_start:])
    
    # Ensure we have content
    if not config_section.strip():
        logger.warning("_extract_config_from_ssh_dump: No valid config extracted, returning original text")
        return text
    
    logger.debug(f"_extract_config_from_ssh_dump: Extracted {len(config_section)} chars from SSH dump")
    return config_section


def _parse_single_text(text: str, fallback_name: str) -> DeviceSummary:
    # Pre-process: Extract config from SSH dumps (if applicable)
    text = _extract_config_from_ssh_dump(text)
    logger.debug(f"_parse_single_text: Starting parse for {fallback_name}, text size={len(text)}")
    
    # Detect vendor first
    vendor = _guess_vendor(text)
    is_ftd = "FTD" in vendor
    
    # Extract hostname - try FTD-specific first if FTD, then standard
    if is_ftd:
        ftd_host = _parse_ftd_hostname(text)
        hostname = ftd_host if ftd_host else (HOST_RE.search(text).group(1) if HOST_RE.search(text) else fallback_name)
    else:
        hostm = HOST_RE.search(text)
        hostname = hostm.group(1) if hostm else fallback_name

    d = DeviceSummary(hostname=hostname, vendor=vendor, raw_text=text)
    logger.debug(f"_parse_single_text: Detected hostname={hostname}, vendor={vendor}")
    
    # FTD-specific parsing pipeline
    if is_ftd:
        try:
            _parse_ftd_version(d, text)
        except Exception as e:
            d.parse_errors.append(f"FTD version parse: {str(e)[:100]}")
        
        try:
            _parse_ftd_interfaces(d, text)
        except Exception as e:
            d.parse_errors.append(f"FTD interface parse: {str(e)[:100]}")
        
        try:
            _parse_ftd_routes(d, text)
        except Exception as e:
            d.parse_errors.append(f"FTD route parse: {str(e)[:100]}")
        
        try:
            _parse_ftd_acls(d, text)
        except Exception as e:
            d.parse_errors.append(f"FTD ACL parse: {str(e)[:100]}")
        
        return d
    
    # Standard parsing pipeline for non-FTD devices
    try:
        _parse_show_version(d, text)
    except Exception as e:
        d.parse_errors.append(f"Version parse: {str(e)[:100]}")
    
    try:
        d.vlans = _parse_vlans(text)
    except Exception as e:
        d.parse_errors.append(f"VLAN parse: {str(e)[:100]}")
    
    try:
        _parse_interfaces_and_portchannels(d, text)
    except Exception as e:
        d.parse_errors.append(f"Interface parse: {str(e)[:100]}")
    
    try:
        _parse_vrfs(d, text)
    except Exception as e:
        d.parse_errors.append(f"VRF parse: {str(e)[:100]}")
    
    try:
        _parse_routing_and_routes(d, text)
    except Exception as e:
        d.parse_errors.append(f"Routing parse: {str(e)[:100]}")
    
    try:
        _parse_loopbacks(d, text)
    except Exception as e:
        d.parse_errors.append(f"Loopback parse: {str(e)[:100]}")
    
    try:
        _parse_bgp_neighbors(d, text)
    except Exception as e:
        d.parse_errors.append(f"BGP neighbor parse: {str(e)[:100]}")
    
    try:
        _parse_ospf_neighbors(d, text)
    except Exception as e:
        d.parse_errors.append(f"OSPF neighbor parse: {str(e)[:100]}")
    
    try:
        _parse_stp(d, text)
    except Exception as e:
        d.parse_errors.append(f"STP parse: {str(e)[:100]}")
    
    try:
        _parse_vpc_mlag_vlt(d, text)
    except Exception as e:
        d.parse_errors.append(f"vPC/MLAG/VLT parse: {str(e)[:100]}")
    
    try:
        _parse_cdp(d, text)
    except Exception as e:
        d.parse_errors.append(f"CDP parse: {str(e)[:100]}")
    
    try:
        _parse_hsrp_vrrp(d, text)
        _link_hsrp_to_interfaces(d)  # Link HSRP/VRRP to interface objects
    except Exception as e:
        d.parse_errors.append(f"HSRP/VRRP parse: {str(e)[:100]}")
    
    try:
        _parse_acls(d, text)
    except Exception as e:
        d.parse_errors.append(f"ACL parse: {str(e)[:100]}")
    
    return d


def parse_configs_fallback(paths: List[str]) -> Tuple[TopologyData, Dict[str, str]]:
    """Parse config files and return topology plus error tracking."""
    logger.info(f"================== FALLBACK PARSER START ==================")
    logger.info(f"Parsing {len(paths)} file(s)...")
    
    topo = TopologyData()
    file_errors: Dict[str, str] = {}  # filename -> error message
    
    for i, p in enumerate(paths, 1):
        filename = os.path.basename(p)
        device_key = os.path.splitext(filename)[0]  # Use filename (without extension) as the key
        
        logger.info(f"--- File {i}/{len(paths)}: {filename}")
        
        # Read file
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            file_size = len(text)
            logger.debug(f"✓ File read successfully ({file_size} bytes)")
        except Exception as e:
            error_msg = f"Cannot read file: {str(e)[:60]}"
            file_errors[filename] = error_msg
            logger.error(f"✗ {error_msg}")
            continue
        
        if not text.strip():
            error_msg = "File is empty"
            file_errors[filename] = error_msg
            logger.error(f"✗ {error_msg}")
            continue
        
        # Parse file
        try:
            logger.debug(f"Starting parse of {filename}...")
            d = _parse_single_text(text, device_key)
            
            # Log parsed device information
            logger.info(f"✓ Parse successful for {device_key}")
            logger.debug(f"  Hostname: {d.hostname}")
            logger.debug(f"  Vendor: {d.vendor}")
            logger.debug(f"  Interfaces: {len(d.interfaces)}")
            logger.debug(f"  Port-channels: {len(d.port_channels)}")
            logger.debug(f"  VLANs: {len(d.vlans)}")
            logger.debug(f"  SVIs: {sum(1 for iface in d.interfaces.values() if iface.is_svi)}")
            logger.debug(f"  VRFs: {len(d.vrfs) if d.vrfs else 0}")
            logger.debug(f"  Routing protocols: {d.routing_protocols}")
            logger.debug(f"  BGP neighbors: {len(d.bgp_neighbors)}")
            logger.debug(f"  OSPF neighbors: {len(d.ospf_neighbors)}")
            logger.debug(f"  vPC configured: {d.vpc_configured}")
            if d.vpc_configured:
                logger.debug(f"    vPC domain: {d.vpc_domain}")
                logger.debug(f"    vPC keepalive: {d.vpc_keepalive_dst}")
                logger.debug(f"    vPC peerlink: {d.vpc_peerlink_po}")
            
            if d.parse_errors:
                logger.warning(f"  Parse warnings ({len(d.parse_errors)}):")
                for err in d.parse_errors:
                    logger.warning(f"    - {err}")
            
            # Always use filename as the device key, but keep parsed hostname in the object
            # This ensures filenames don't change in the UI
            topo.devices[device_key] = d
            
        except Exception as e:
            error_msg = f"Parse error: {str(e)[:60]}"
            file_errors[filename] = error_msg
            logger.error(f"✗ {error_msg}")
            logger.debug(f"Full error: {str(e)}", exc_info=True)
    
    logger.info(f"Fallback parser complete: {len(topo.devices)} devices parsed, {len(file_errors)} file errors")
    logger.info(f"================== FALLBACK PARSER END ==================\n")
    
    return topo, file_errors


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


def _norm_intf(name: str) -> str:
    """Normalize interface names across vendors for comparison while preserving actual numbers."""
    n = (name or "").strip()
    
    # Port-channel variants
    n = re.sub(r"^Po(\d+)$", r"port-channel\1", n, flags=re.IGNORECASE)
    n = re.sub(r"^PortChannel(\d+)$", r"port-channel\1", n, flags=re.IGNORECASE)
    n = n.replace("Port-Channel", "port-channel").replace("Port-channel", "port-channel")
    n = n.replace("Port Channel", "port-channel")
    
    # Expand common shorthand: Gi → GigabitEthernet, Te → TenGigabit, Eth → Ethernet
    vendor_shorts = {
        r"^Gi(\d+/\d+(?:/\d+)?)$": r"GigabitEthernet\1",
        r"^Te(\d+/\d+(?:/\d+)?)$": r"TenGigabitEthernet\1",
        r"^Fo(\d+/\d+(?:/\d+)?)$": r"FortyGigabitEthernet\1",
        r"^Eth(\d+/\d+(?:/\d+)?)$": r"Ethernet\1",
        r"^Fa(\d+/\d+(?:/\d+)?)$": r"FastEthernet\1",
        r"^Lo(\d+)$": r"Loopback\1",
        r"^Vlan(\d+)$": r"Vlan\1",
    }
    for pattern, replacement in vendor_shorts.items():
        n = re.sub(pattern, replacement, n, flags=re.IGNORECASE)
    
    # Only lowercase for case-insensitive comparison - preserve actual interface numbers from file
    return n.lower()


def _calc_link_evidence_score(evidence_types: Set[str]) -> Tuple[str, int]:
    """Score link confidence based on evidence types present.
    
    Returns (confidence_level, score) where:
    - HIGH = 3 points (CDP or multi-side config match)
    - MEDIUM = 2 points (description + port-channel or subnet)
    - LOW = 1 point (description only or subnet only)
    """
    if not evidence_types:
        return "low", 0
    
    # Multi-evidence from configuration tracking
    cdp_evidence = "cdp" in evidence_types
    port_channel_evidence = "port-channel-match" in evidence_types
    description_evidence = "description" in evidence_types
    subnet_evidence = "subnet" in evidence_types
    vpc_evidence = "vpc-peerlink" in evidence_types
    
    # vPC/MLAG/VLT peer-links are always HIGH
    if vpc_evidence:
        return "high", 3
    
    # CDP is always HIGH (direct evidence)
    if cdp_evidence:
        return "high", 3
    
    # Configuration-based evidence
    if cdp_evidence or (port_channel_evidence and description_evidence):
        return "high", 3
    
    if (port_channel_evidence and subnet_evidence) or (description_evidence and subnet_evidence):
        return "medium", 2
    
    if port_channel_evidence or (description_evidence and subnet_evidence):
        return "medium", 2
    
    # Single evidence types
    if description_evidence or subnet_evidence:
        return "low", 1
    
    return "low", 0


def _describe_link_evidence(evidence_types: List[str]) -> str:
    """Generate human-readable evidence description."""
    descriptions = []
    
    evidence_map = {
        "cdp": "CDP adjacency detected",
        "description": "matched interface descriptions",
        "port-channel": "port-channel members match",
        "port-channel-match": "port-channel symmetry",
        "subnet": "routed adjacency on same subnet",
        "vpc-peerlink": "vPC peer-link configured",
        "mlag-peerlink": "MLAG peer-link configured",
        "vlt-peerlink": "VLT peer-link configured"
    }
    
    for evt in evidence_types:
        if evt in evidence_map:
            descriptions.append(evidence_map[evt])
    
    if not descriptions:
        return "inferred from config patterns"
    
    return " + ".join(descriptions)


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
            # Evidence tracking
            evidence_types = {"cdp"}
            confidence, _score = _calc_link_evidence_score(evidence_types)
            evidence_desc = _describe_link_evidence(["cdp"])
            reasons = [
                f"CDP adjacency: {a_name} {a_if} ↔ {b} {b_if or 'unknown'}",
                evidence_desc,
                f"Link type {kind} determined from interface configuration"
            ]
            links.append(Link(
                a=a_name, b=b,
                a_intf=a_if, b_intf=b_if or "—",
                kind=kind, confidence=confidence, evidence="cdp",
                label=f"{a_if} ↔ {b_if or '—'} (cdp)",
                reasons=reasons
            ))
    return links


def _infer_vpc_pairs(topo: TopologyData) -> List[PairInference]:
    # vPC pair detection using multiple signals: keepalive, domain, peer-link
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
        if not da.vpc_configured:
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

            # If we have at least 2 signals, elevate to high
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
        # Evidence tracking
        evidence_types = {"vpc-peerlink"}
        confidence, _score = _calc_link_evidence_score(evidence_types)
        evidence_desc = _describe_link_evidence(["vpc-peerlink"])
        reasons = [
            f"vPC peer-link: {a} {a_if} ↔ {b} {b_if}",
            evidence_desc,
            f"Both devices in vPC domain {da.vpc_domain}"
        ]
        links.append(Link(
            a=a, b=b,
            a_intf=a_if, b_intf=b_if,
            kind="L2", confidence=confidence, evidence="vpc-peerlink",
            label=f"{a_if} ↔ {b_if} (vPC peer-link)",
            reasons=reasons
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

    # mutual = high confidence (both sides reference each other)
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

            # Evidence tracking: mutual descriptions = higher confidence
            evidence_types = {"description"}
            evidence_desc = _describe_link_evidence(["description"])
            reasons = [
                f"Mutual interface descriptions: {a} {a_if} references {b} {chosen_b_if} and vice versa",
                evidence_desc
            ]
            links.append(Link(
                a=a, b=b,
                a_intf=a_if, b_intf=chosen_b_if,
                kind=kind, confidence="high", evidence="description-mutual",
                label=f"{a_if} ↔ {chosen_b_if} (desc-mutual)",
                reasons=reasons
            ))

    # one-sided = medium confidence (only peer device interface exists)
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
            # Evidence tracking: one-sided description
            evidence_types = {"description"}
            evidence_desc = _describe_link_evidence(["description"])
            reasons = [
                f"One-sided interface description: {a} {a_if} references {b} {b_if_hint}",
                evidence_desc,
                f"Peer interface {b_if_hint} exists on {b}"
            ]
            links.append(Link(
                a=a, b=b,
                a_intf=a_if, b_intf=b_if_hint,
                kind=kind, confidence="medium", evidence="description-one-side",
                label=f"{a_if} ↔ {b_if_hint} (desc-one)",
                reasons=reasons
            ))
    return links


def _build_links_from_bgp_neighbors(topo: TopologyData) -> List[Link]:
    """Build L3 links from BGP adjacencies (peer-to-peer routed connections)."""
    links: List[Link] = []
    seen = set()
    
    devs = topo.devices
    
    # Build a map of BGP neighbors for quick lookup
    # Map: neighbor_ip -> list of (device, bgp_neighbor)
    bgp_map: Dict[str, List[Tuple[str, BgpNeighbor]]] = {}
    for hn, d in devs.items():
        for bgp_neighbor in d.bgp_neighbors:
            if bgp_neighbor.neighbor_ip not in bgp_map:
                bgp_map[bgp_neighbor.neighbor_ip] = []
            bgp_map[bgp_neighbor.neighbor_ip].append((hn, bgp_neighbor))
    
    # For each device, find if any BGP neighbors are on other devices
    for hn, d in devs.items():
        for bgp_neighbor in d.bgp_neighbors:
            neighbor_ip = bgp_neighbor.neighbor_ip
            
            # Find the other end: find a device with this neighbor_ip in its interfaces
            for other_hn, other_d in devs.items():
                if hn == other_hn:
                    continue
                
                # Check if this other device has an interface with neighbor_ip
                neighbor_intf = None
                for ifn, iface in other_d.interfaces.items():
                    if iface.ip and neighbor_ip in iface.ip:
                        neighbor_intf = ifn
                        break
                
                if neighbor_intf:
                    # Found a match! Create the link
                    # Try to find which interface on this device reaches this neighbor
                    this_intf = None
                    try:
                        this_ip = ipaddress.ip_address(neighbor_ip)
                        # Find an interface on 'hn' in the same subnet as neighbor_ip
                        for ifn, iface in d.interfaces.items():
                            if iface.ip:
                                try:
                                    this_ipi = ipaddress.ip_interface(iface.ip)
                                    if this_ipi.network == ipaddress.ip_network(f"{neighbor_ip}/32", strict=False).supernet(new_prefix=this_ipi.network.prefixlen):
                                        this_intf = ifn
                                        break
                                except Exception:
                                    continue
                    except Exception:
                        pass
                    
                    # If we couldn't find the exact interface, just use "BGP" as placeholder
                    if not this_intf:
                        this_intf = "BGP"
                    if not neighbor_intf:
                        neighbor_intf = "BGP"
                    
                    # Create unique key to avoid duplicates
                    key = tuple(sorted([f"{hn}:{this_intf}", f"{other_hn}:{neighbor_intf}", f"BGP:{neighbor_ip}"]))
                    if key in seen:
                        continue
                    seen.add(key)
                    
                    # Evidence tracking
                    evidence_types = {"bgp"}
                    confidence, _score = _calc_link_evidence_score(evidence_types)
                    evidence_desc = _describe_link_evidence(["bgp"])
                    reasons = [
                        f"BGP adjacency between {hn} (AS {d.bgp_asn}) and {other_hn} (AS {other_d.bgp_asn})",
                        f"{hn} BGP neighbor: {neighbor_ip} (remote AS {bgp_neighbor.remote_as}, state: {bgp_neighbor.state})",
                        f"Peer IP {neighbor_ip} found on {other_hn} interface {neighbor_intf}",
                        evidence_desc
                    ]
                    
                    links.append(Link(
                        a=hn, b=other_hn,
                        a_intf=this_intf, b_intf=neighbor_intf,
                        kind="L3", confidence=confidence, evidence="bgp",
                        label=f"{this_intf} ↔ {neighbor_intf} (BGP)",
                        reasons=reasons
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

            # Evidence tracking
            evidence_types = {"subnet"}
            confidence, _score = _calc_link_evidence_score(evidence_types)
            evidence_desc = _describe_link_evidence(["subnet"])
            reasons = [
                f"Routed adjacency inferred from {a_ip.network} subnet",
                f"{a} {a_if} has IP {a_ip}",
                f"{b} {b_if} has IP {b_ip}",
                evidence_desc,
                f"Prefix length /{plen} suggests point-to-point link"
            ]
            links.append(Link(
                a=a, b=b,
                a_intf=a_if, b_intf=b_if,
                kind="L3", confidence=confidence, evidence="ip-subnet",
                label=f"{a_if} ↔ {b_if} ({a_ip.network})",
                reasons=reasons
            ))
    return links


def build_topology(topo: TopologyData) -> TopologyData:
    logger.info("================== TOPOLOGY BUILDING START ==================")
    logger.info(f"Building topology from {len(topo.devices)} device(s)")
    
    # Infer vPC pairs
    logger.debug("Inferring vPC/MLAG/VLT pairs...")
    pairs = _infer_vpc_pairs(topo)
    topo.pairs = pairs
    logger.info(f"Found {len(pairs)} peer pair(s)")
    for pair in pairs:
        logger.debug(f"  {pair.a} ↔ {pair.b} ({pair.kind}, confidence={pair.confidence})")

    # Build links from multiple evidence sources
    links: List[Link] = []
    
    logger.debug("Building links from CDP...")
    cdp_links = _build_links_from_cdp(topo)
    links.extend(cdp_links)
    logger.debug(f"  → {len(cdp_links)} CDP link(s)")
    
    logger.debug("Building links from vPC peer-links...")
    vpc_links = _build_links_from_vpc_peerlink(topo, pairs)
    links.extend(vpc_links)
    logger.debug(f"  → {len(vpc_links)} vPC peer-link(s)")
    
    logger.debug("Building links from interface descriptions...")
    desc_links = _build_links_from_descriptions(topo)
    links.extend(desc_links)
    logger.debug(f"  → {len(desc_links)} description-based link(s)")
    
    logger.debug("Building links from IP subnets...")
    ip_links = _build_links_from_ip_subnet(topo)
    links.extend(ip_links)
    logger.debug(f"  → {len(ip_links)} IP subnet link(s)")
    
    logger.debug("Building links from BGP adjacencies...")
    bgp_links = _build_links_from_bgp_neighbors(topo)
    links.extend(bgp_links)
    logger.debug(f"  → {len(bgp_links)} BGP adjacency link(s)")

    # De-dupe final links (undirected)
    logger.debug(f"De-duplicating {len(links)} total links...")
    seen = set()
    final: List[Link] = []
    for l in links:
        key = tuple(sorted([f"{l.a}:{l.a_intf}", f"{l.b}:{l.b_intf}", f"{l.kind}:{l.evidence}"]))
        if key in seen:
            logger.debug(f"  Skipping duplicate: {l.a}:{l.a_intf} ↔ {l.b}:{l.b_intf}")
            continue
        seen.add(key)
        # If label empty, populate
        if not l.label:
            l.label = f"{l.a_intf} ↔ {l.b_intf}"
        final.append(l)

    topo.links = final
    
    logger.info(f"Topology built: {len(final)} unique link(s)")
    logger.info("Link summary:")
    for link in final:
        logger.debug(f"  {link.a}:{link.a_intf} ↔ {link.b}:{link.b_intf} ({link.kind}, {link.evidence}, confidence={link.confidence})")
    
    logger.info("================== TOPOLOGY BUILDING END ==================")
    return topo


# ============================================================
# Analysis functions
# ============================================================

def detect_device_role(dev: DeviceSummary, topo: TopologyData, device_name: str) -> DeviceRole:
    """Infer device role based on connectivity and features."""
    reasoning: List[str] = []
    role = "unknown"
    confidence = "low"
    
    # Count connections by type
    connection_count = 0
    l2_connections = 0
    l3_connections = 0
    for link in topo.links:
        if link.a == device_name or link.b == device_name:
            connection_count += 1
            if link.kind == "L2":
                l2_connections += 1
            else:
                l3_connections += 1
    
    # Check for vPC pairs (high-availability feature)
    is_vpc_pair = any(p.a == device_name or p.b == device_name for p in topo.pairs if p.kind == "vPC")
    
    # Check for routing protocols
    has_routing = len(dev.routing_protocols) > 0
    has_bgp = "BGP" in dev.routing_protocols
    has_ospf = "OSPF" in dev.routing_protocols
    
    # Check for VRFs (multi-tenant or multi-VRF = likely core/border)
    vrf_count = len(dev.vrfs) if dev.vrfs else 0
    
    # Check port-channel density (high = core/distribution)
    pc_density = len(dev.port_channels) / max(len(dev.interfaces), 1)
    
    # Check interface density (routed vs switched)
    routed_count = sum(1 for i in dev.interfaces.values() if i.mode == "routed" or i.is_svi)
    routed_ratio = routed_count / max(len(dev.interfaces), 1)
    
    # Check for loopback interfaces (common in core)
    loopback_count = sum(1 for i in dev.interfaces.keys() if i.lower().startswith("loopback"))
    
    # Confidence heuristics
    if has_bgp and connection_count > 4:
        # BGP with high connectivity = core/border
        role = "core"
        confidence = "high"
        reasoning.append(f"BGP enabled with {connection_count} total connections")
        if is_vpc_pair:
            reasoning.append("vPC pair configured (high availability)")
        if vrf_count > 1:
            reasoning.append(f"{vrf_count} VRFs configured (multi-tenant)")
        
    elif has_bgp:
        # BGP without high connectivity = border
        role = "border"
        confidence = "high"
        reasoning.append("BGP configured (external routing)")
        if l3_connections > l2_connections:
            reasoning.append("Primarily L3 connections")
    
    elif has_ospf and (connection_count > 3 or pc_density > 0.15):
        # OSPF with good connectivity = distribution/core
        role = "distribution"
        confidence = "high" if connection_count > 4 else "medium"
        reasoning.append(f"OSPF enabled with {connection_count} connections")
        if is_vpc_pair:
            reasoning.append("vPC pair (high availability)")
            confidence = "high"
    
    elif has_routing and routed_ratio > 0.25:
        # Stateful routing = distribution layer
        role = "distribution"
        confidence = "medium"
        reasoning.append(f"Routing protocols with {routed_ratio:.0%} routed interfaces")
    
    elif is_vpc_pair or pc_density > 0.15 or len(dev.port_channels) > 3:
        # vPC or high PC density = distribution/core
        role = "distribution"
        confidence = "high" if is_vpc_pair else "medium"
        if is_vpc_pair:
            reasoning.append("vPC pair (indicates aggregation/core)")
        reasoning.append(f"{len(dev.port_channels)} port-channels configured")
    
    elif connection_count > 4 and not has_routing:
        # High connectivity but no routing = distribution/aggregation
        role = "distribution"
        confidence = "medium"
        reasoning.append(f"High L2 connectivity ({connection_count} links)")
    
    elif connection_count <= 2:
        # Low connectivity = access layer
        role = "access"
        confidence = "medium"
        reasoning.append(f"Limited connectivity ({connection_count} links)")
    
    elif connection_count > 2:
        # Moderate connectivity without special features = access/distribution
        role = "access"
        confidence = "low"
        reasoning.append(f"Moderate connectivity ({connection_count} links) without routing")
    
    if not reasoning:
        reasoning.append(f"{len(dev.interfaces)} interfaces, {len(dev.port_channels)} PCs, {connection_count} links, {vrf_count} VRFs")
    
    return DeviceRole(device=device_name, role=role, confidence=confidence, reasoning=reasoning)


def validate_configuration(topo: TopologyData) -> List[ValidationIssue]:
    """Check for configuration issues and inconsistencies."""
    issues: List[ValidationIssue] = []
    
    for dev_name, dev in topo.devices.items():
        # Check for untagged interfaces on trunks
        for iface_name, iface in dev.interfaces.items():
            if iface.mode == "trunk" and not iface.native_vlan:
                issues.append(ValidationIssue(
                    device=dev_name,
                    severity="warning",
                    category="vlan",
                    message=f"Trunk interface {iface_name} has no native VLAN configured"
                ))
        
        # Check for SVIs without HSRP
        svi_without_hsrp = []
        for iface_name, iface in dev.interfaces.items():
            if iface.is_svi and iface.ip and not any(h.interface == iface_name for h in dev.hsrp_groups):
                svi_without_hsrp.append(iface_name)
        
        if svi_without_hsrp and len(topo.devices) > 1:
            issues.append(ValidationIssue(
                device=dev_name,
                severity="warning",
                category="hsrp",
                message=f"SVI(s) without HSRP: {', '.join(svi_without_hsrp[:3])}"
            ))
        
        # Check for devices with vPC/MLAG configured but not paired
        if dev.vpc_configured and not any(p for p in topo.pairs if p.a == dev_name or p.b == dev_name):
            issues.append(ValidationIssue(
                device=dev_name,
                severity="info",
                category="config",
                message="vPC configured but peer not detected"
            ))
        
        # Check for routing without ospf/bgp enabled but static routes present
        if not dev.routing_protocols and len(dev.static_routes) > 10:
            issues.append(ValidationIssue(
                device=dev_name,
                severity="info",
                category="routing",
                message=f"{len(dev.static_routes)} static routes with no dynamic routing"
            ))
    
    # Link-level checks
    for link in topo.links:
        dev_a = topo.devices.get(link.a)
        dev_b = topo.devices.get(link.b)
        
        if dev_a and dev_b:
            # Check for VLAN mismatches
            if link.kind == "L2":
                iface_a = dev_a.interfaces.get(link.a_intf)
                iface_b = dev_b.interfaces.get(link.b_intf)
                
                if iface_a and iface_b:
                    if iface_a.mode == "access" and iface_b.mode == "access":
                        if iface_a.access_vlan != iface_b.access_vlan:
                            issues.append(ValidationIssue(
                                device=link.a,
                                severity="error",
                                category="vlan",
                                message=f"VLAN mismatch on {link.a_intf} (VLAN {iface_a.access_vlan}) <-> {link.b} (VLAN {iface_b.access_vlan})"
                            ))
    
    return issues


def get_interface_statistics(topo: TopologyData) -> Dict[str, InterfaceStats]:
    """Calculate interface statistics for each device."""
    stats: Dict[str, InterfaceStats] = {}
    
    for dev_name, dev in topo.devices.items():
        stat = InterfaceStats()
        stat.total_interfaces = len(dev.interfaces)
        stat.pc_count = len(dev.port_channels)
        
        vlan_dist: Dict[str, int] = {}
        
        for iface_name, iface in dev.interfaces.items():
            if iface.mode == "routed" or (iface.ip and iface.is_switchport is False):
                stat.routed_count += 1
            elif iface.mode == "access":
                stat.access_count += 1
                if iface.access_vlan:
                    vlan_dist[iface.access_vlan] = vlan_dist.get(iface.access_vlan, 0) + 1
            elif iface.mode == "trunk":
                stat.trunk_count += 1
            
            if iface.is_svi:
                stat.svi_count += 1
        
        stat.vlan_distribution = vlan_dist
        stats[dev_name] = stat
    
    return stats


def analyze_vrfs(topo: TopologyData) -> List[VRFAnalysis]:
    """Analyze VRF membership and routing."""
    vrf_analysis: Dict[str, VRFAnalysis] = {}
    
    for dev_name, dev in topo.devices.items():
        for vrf_name, ifaces in dev.vrfs.items():
            if vrf_name not in vrf_analysis:
                vrf_analysis[vrf_name] = VRFAnalysis(vrf_name=vrf_name)
            
            analysis = vrf_analysis[vrf_name]
            if dev_name not in analysis.devices:
                analysis.devices.append(dev_name)
                analysis.device_count += 1
            
            analysis.interface_count += len(ifaces)
            analysis.route_count += sum(1 for r in dev.static_routes if r.vrf == vrf_name)
    
    return sorted(vrf_analysis.values(), key=lambda x: x.vrf_name)
    

def get_vendor_color(vendor: str) -> str:
    """Return color code for vendor."""
    vendor_colors = {
        "Cisco Nexus (NX-OS)": "#FF9999",          # Bright coral red
        "Cisco Catalyst (IOS/IOS-XE)": "#99CC99",  # Bright sage green
        "Cisco FTD (Firewall Threat Defense)": "#CC99FF",  # Bright lavender
        "Arista EOS": "#99E5E5",                   # Bright mint
        "Dell OS10": "#99CCFF",                    # Bright slate blue
        "AUTODETECT": "#CCCCCC",                   # Light gray
    }
    return vendor_colors.get(vendor, "#CCCCCC")


# ============================================================
# Adapters: attempt to use repo modules if present
# ============================================================

def parse_with_adapters(paths: List[str]) -> Tuple[TopologyData, Dict[str, str]]:
    """
    Tries:
      1) parser.orchestrator.parse_paths(paths)
      2) parser.orchestrator.parse_configs(paths)
      3) parser.orchestrator.parse_files(paths)
      4) fallback parser in this file
    Returns (TopologyData, file_errors_dict)
    """
    logger.info(f"================== PARSE_WITH_ADAPTERS START ==================")
    logger.info(f"Files to parse: {paths}")
    
    topo: Optional[TopologyData] = None
    file_errors: Dict[str, str] = {}
    used_external = False

    try:
        from parser import orchestrator  # type: ignore
        logger.debug("Successfully imported parser.orchestrator")

        for fn_name in ("parse_paths", "parse_configs", "parse_files", "parse"):
            fn = getattr(orchestrator, fn_name, None)
            if callable(fn):
                try:
                    logger.debug(f"Trying orchestrator.{fn_name}()...")
                    result = fn(list(paths))
                    # If external returns dict-like, convert best-effort
                    topo = _coerce_topology(result)
                    used_external = True
                    logger.info(f"✓ External parser succeeded using {fn_name}()")
                    break
                except Exception as e:
                    logger.debug(f"✗ orchestrator.{fn_name}() failed: {e}")
                    continue
    except Exception as e:
        logger.debug(f"Failed to import parser.orchestrator: {e}")
        topo = None

    if topo is None:
        logger.info("Using fallback parser...")
        topo, file_errors = parse_configs_fallback(paths)
    else:
        # External parser succeeded - no file-level errors yet
        logger.info(f"External parser returned {len(topo.devices)} device(s)")
        file_errors = {}

    logger.info(f"After initial parse: {len(topo.devices)} devices, {len(file_errors)} file errors")

    # If external already built links, keep them but also add missing evidence links.
    # We'll treat external links as evidence="external".
    if used_external and topo.links:
        logger.info(f"Merging external parser links with evidence-based topology...")
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
        logger.info("Building topology from fallback parser...")
        topo = build_topology(topo)

    logger.info(f"Final topology: {len(topo.devices)} devices, {len(topo.links)} links, {len(topo.pairs)} pairs")
    logger.info(f"================== PARSE_WITH_ADAPTERS END ==================\n")
    
    return topo, file_errors


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

        # Enhanced scrolling: mousewheel, keyboard, and click support
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)  # Linux scroll up
        self.canvas.bind("<Button-5>", self._on_mousewheel)  # Linux scroll down
        self.canvas.bind("<Up>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Down>", lambda e: self.canvas.yview_scroll(3, "units"))
        self.canvas.bind("<Prior>", lambda e: self.canvas.yview_scroll(-10, "units"))  # Page Up
        self.canvas.bind("<Next>", lambda e: self.canvas.yview_scroll(10, "units"))    # Page Down
        self.canvas.bind("<Home>", lambda e: self.canvas.yview_moveto(0))
        self.canvas.bind("<End>", lambda e: self.canvas.yview_moveto(1))
        
        # Focus canvas on mouse enter for keyboard scrolling
        self.canvas.bind("<Enter>", lambda e: self.canvas.focus_set())
        
        # Allow mousewheel everywhere in frame
        self.inner.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_configure(self, _evt=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, evt):
        # keep inner width synced to canvas width
        self.canvas.itemconfigure(self.inner_id, width=evt.width)

    def _on_mousewheel(self, evt):
        try:
            # Improve sensitivity: Linux buttons-4/5 vs Windows MouseWheel
            if evt.num == 4:
                self.canvas.yview_scroll(-5, "units")
            elif evt.num == 5:
                self.canvas.yview_scroll(5, "units")
            else:
                # Windows MouseWheel: delta is typically 120 per notch
                self.canvas.yview_scroll(int(-1 * (evt.delta / 120)) * 3, "units")
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

        # Analysis results
        self._validation_issues: List[ValidationIssue] = []
        self._interface_stats: Dict[str, InterfaceStats] = {}
        self._vrf_analysis: List[VRFAnalysis] = []
        self._device_roles: Dict[str, DeviceRole] = {}

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
        ttk.Button(btns, text="View Logs", command=self.view_logs).pack(fill="x", pady=(0, 6))
        ttk.Button(btns, text="Export", command=self.export_menu).pack(fill="x", pady=(0, 6))
        ttk.Button(btns, text="Clear", command=self.clear_all).pack(fill="x")

    def _build_main(self):
        self.nb = ttk.Notebook(self.main)
        self.nb.grid(row=0, column=0, sticky="nsew")

        self.tab_details = ttk.Frame(self.nb, style="Panel.TFrame")
        self.tab_topology = ttk.Frame(self.nb, style="Panel.TFrame")
        self.tab_interfaces = ttk.Frame(self.nb, style="Panel.TFrame")
        self.tab_raw = ttk.Frame(self.nb, style="Panel.TFrame")
        self.tab_validation = ttk.Frame(self.nb, style="Panel.TFrame")
        self.tab_vrf = ttk.Frame(self.nb, style="Panel.TFrame")

        self.nb.add(self.tab_details, text="Details")
        self.nb.add(self.tab_topology, text="Topology")
        self.nb.add(self.tab_interfaces, text="Interfaces")
        self.nb.add(self.tab_validation, text="Validation")
        self.nb.add(self.tab_vrf, text="VRF")
        self.nb.add(self.tab_raw, text="Raw")

        self._build_details_tab()
        self._build_topology_tab()
        self._build_interfaces_tab()
        self._build_validation_tab()
        self._build_vrf_tab()
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

        for s in (self.sec_identity, self.sec_pairing, self.sec_l2, self.sec_l3):
            s.pack(fill="x", pady=(0, 2))

        # Default open a couple sections
        self.sec_identity.toggle()
        self.sec_pairing.toggle()

    def _build_topology_tab(self):
        # Compact topology toolbar (no metrics area) — focused on topology interaction
        # Topology controls - organized into 3 rows for better visibility
        ctrl_frame = ttk.Frame(self.tab_topology, style="Panel.TFrame")
        ctrl_frame.pack(fill="x", padx=10, pady=(10, 6))

        # Row 1: Main action buttons
        row1 = ttk.Frame(ctrl_frame, style="Panel.TFrame")
        row1.pack(fill="x", pady=(0, 4))
        ttk.Button(row1, text="Auto-layout", style="Accent.TButton", command=self.auto_layout).pack(side="left", padx=(0, 6))
        ttk.Button(row1, text="Export PNG", style="Accent.TButton", command=self.export_png).pack(side="left", padx=(0, 6))
        ttk.Label(row1, text="|", style="Panel.TLabel").pack(side="left", padx=6)
        ttk.Button(row1, text="Zoom +", command=self._zoom_in).pack(side="left", padx=2)
        ttk.Button(row1, text="Zoom -", command=self._zoom_out).pack(side="left", padx=2)
        ttk.Button(row1, text="Reset", command=self._zoom_reset).pack(side="left", padx=2)
        ttk.Button(row1, text="Fit All", command=self._zoom_fit_all).pack(side="left", padx=2)

        # Row 2: Visibility toggles - part 1
        row2 = ttk.Frame(ctrl_frame, style="Panel.TFrame")
        row2.pack(fill="x", pady=(0, 4))
        ttk.Label(row2, text="Show:", style="Panel.TLabel").pack(side="left", padx=(0, 8))
        tk.Checkbutton(row2, text="L2 Links", variable=self.var_show_l2, bg=self.colors.panel, fg=self.colors.text, activebackground=self.colors.panel, activeforeground=self.colors.text, selectcolor=self.colors.panel, highlightthickness=0, relief="flat", borderwidth=0).pack(side="left", padx=4)
        tk.Checkbutton(row2, text="L3 Links", variable=self.var_show_l3, bg=self.colors.panel, fg=self.colors.text, activebackground=self.colors.panel, activeforeground=self.colors.text, selectcolor=self.colors.panel, highlightthickness=0, relief="flat", borderwidth=0).pack(side="left", padx=4)
        tk.Checkbutton(row2, text="Medium Confidence", variable=self.var_show_medium, bg=self.colors.panel, fg=self.colors.text, activebackground=self.colors.panel, activeforeground=self.colors.text, selectcolor=self.colors.panel, highlightthickness=0, relief="flat", borderwidth=0).pack(side="left", padx=4)
        tk.Checkbutton(row2, text="Edge Labels", variable=self.var_show_labels, bg=self.colors.panel, fg=self.colors.text, activebackground=self.colors.panel, activeforeground=self.colors.text, selectcolor=self.colors.panel, highlightthickness=0, relief="flat", borderwidth=0).pack(side="left", padx=4)
        tk.Checkbutton(row2, text="Grid", variable=self.var_show_grid, bg=self.colors.panel, fg=self.colors.text, activebackground=self.colors.panel, activeforeground=self.colors.text, selectcolor=self.colors.panel, highlightthickness=0, relief="flat", borderwidth=0).pack(side="left", padx=4)

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

    def _build_validation_tab(self):
        """Build validation/warnings tab with details panel."""
        self.tab_validation.columnconfigure(0, weight=1)
        self.tab_validation.rowconfigure(1, weight=1)
        
        ttk.Label(self.tab_validation, text="Configuration Validation & Warnings", style="Header.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 8))
        
        # Issues tree
        self.validation_tree = ttk.Treeview(
            self.tab_validation,
            columns=("device", "severity", "message"),
            show="headings",
            height=12
        )
        
        self.validation_tree.heading("device", text="Device")
        self.validation_tree.heading("severity", text="Type")
        self.validation_tree.heading("message", text="Issue")
        self.validation_tree.column("device", width=120)
        self.validation_tree.column("severity", width=80)
        self.validation_tree.column("message", width=400)
        
        self.validation_tree.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))
        self.validation_tree.bind("<<TreeviewSelect>>", self._on_validation_select)
        
        # Details section
        ttk.Label(self.tab_validation, text="Issue Details", style="Section.TLabel").grid(row=2, column=0, sticky="w", padx=12, pady=(6, 4))
        
        self.validation_detail = tk.Text(
            self.tab_validation,
            height=4,
            width=100,
            bg=self.colors.bg,
            fg=self.colors.text,
            wrap="word",
            font=("Segoe UI", 9),
            relief="flat",
            highlightthickness=0,
            selectbackground=self.colors.bg,
            selectforeground=self.colors.text,
            inactiveselectbackground=self.colors.bg
        )
        self.validation_detail.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.validation_detail.config(state="disabled")

    def _build_vrf_tab(self):
        """Build VRF and device role analysis tab."""
        self.tab_vrf.columnconfigure(0, weight=1)
        self.tab_vrf.columnconfigure(1, weight=1)
        self.tab_vrf.rowconfigure(1, weight=1)
        
        ttk.Label(self.tab_vrf, text="VRF Analysis & Device Roles", style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 8))
        
        # VRF tree
        ttk.Label(self.tab_vrf, text="VRFs", style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(0, 6))
        
        self.vrf_tree = ttk.Treeview(
            self.tab_vrf,
            columns=("vrf", "devices", "routes", "interfaces"),
            show="headings",
            height=12
        )
        
        self.vrf_tree.heading("vrf", text="VRF")
        self.vrf_tree.heading("devices", text="Devices")
        self.vrf_tree.heading("routes", text="Routes")
        self.vrf_tree.heading("interfaces", text="Interfaces")
        
        self.vrf_tree.column("vrf", width=100)
        self.vrf_tree.column("devices", width=80)
        self.vrf_tree.column("routes", width=80)
        self.vrf_tree.column("interfaces", width=80)
        
        self.vrf_tree.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        
        # Device roles tree
        ttk.Label(self.tab_vrf, text="Device Roles", style="Section.TLabel").grid(row=0, column=1, sticky="w", padx=12, pady=(0, 6))
        
        self.roles_tree = ttk.Treeview(
            self.tab_vrf,
            columns=("device", "role", "confidence"),
            show="headings",
            height=12
        )
        
        self.roles_tree.heading("device", text="Device")
        self.roles_tree.heading("role", text="Role")
        self.roles_tree.heading("confidence", text="Confidence")
        
        self.roles_tree.column("device", width=120)
        self.roles_tree.column("role", width=100)
        self.roles_tree.column("confidence", width=80)
        
        self.roles_tree.grid(row=1, column=1, sticky="nsew", padx=12, pady=(0, 12))

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
            relief="flat",
            highlightthickness=0,
            wrap="word", height=4,
            selectbackground=self.colors.panel,
            selectforeground=self.colors.text,
            inactiveselectbackground=self.colors.panel
        )
        self.l2_text.pack(fill="x", pady=(0, 6))
        self.l2_text.configure(state="disabled")

        ttk.Label(body, text="VLANs", style="Muted.TLabel").pack(anchor="w", pady=(4, 2))
        # Wrap VLAN tree in a frame with scrollbar
        vlan_frame = ttk.Frame(body)
        vlan_frame.pack(fill="both", expand=True, pady=(0, 8))
        
        self.vlan_tree = ttk.Treeview(vlan_frame, columns=("vid", "name"), show="headings", height=6)
        self.vlan_tree.heading("vid", text="VLAN")
        self.vlan_tree.heading("name", text="Name")
        self.vlan_tree.column("vid", width=70, anchor="w")
        self.vlan_tree.column("name", width=320, anchor="w")
        
        # Add scrollbar to VLAN tree
        vlan_scroll = ttk.Scrollbar(vlan_frame, orient="vertical", command=self.vlan_tree.yview)
        self.vlan_tree.configure(yscroll=vlan_scroll.set)
        self.vlan_tree.grid(row=0, column=0, sticky="nsew")
        vlan_scroll.grid(row=0, column=1, sticky="ns")
        vlan_frame.rowconfigure(0, weight=1)
        vlan_frame.columnconfigure(0, weight=1)

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
            relief="flat",
            highlightthickness=0,
            wrap="word", height=5,
            selectbackground=self.colors.panel,
            selectforeground=self.colors.text,
            inactiveselectbackground=self.colors.panel
        )
        self.l3_text.pack(fill="x", pady=(0, 6))
        self.l3_text.configure(state="disabled")

        ttk.Label(body, text="SVIs / Routed Interfaces (IP)", style="Muted.TLabel").pack(anchor="w", pady=(4, 2))
        # Wrap IP tree in a frame with scrollbar
        ip_frame = ttk.Frame(body)
        ip_frame.pack(fill="both", expand=True, pady=(0, 8))
        
        self.ip_tree = ttk.Treeview(ip_frame, columns=("iface", "ip", "vrf"), show="headings", height=7)
        for c, t, w in [("iface", "Interface", 140), ("ip", "IP/Prefix", 160), ("vrf", "VRF", 120)]:
            self.ip_tree.heading(c, text=t)
            self.ip_tree.column(c, width=w, anchor="w")
        
        # Add scrollbar to IP tree
        ip_scroll = ttk.Scrollbar(ip_frame, orient="vertical", command=self.ip_tree.yview)
        self.ip_tree.configure(yscroll=ip_scroll.set)
        self.ip_tree.grid(row=0, column=0, sticky="nsew")
        ip_scroll.grid(row=0, column=1, sticky="ns")
        ip_frame.rowconfigure(0, weight=1)
        ip_frame.columnconfigure(0, weight=1)
 
        ttk.Label(body, text="Static Routes", style="Muted.TLabel").pack(anchor="w", pady=(4, 2))
        # Wrap route tree in a frame with scrollbar for better scrolling
        route_frame = ttk.Frame(body)
        route_frame.pack(fill="both", expand=True, pady=(0, 6))
        
        self.route_tree = ttk.Treeview(route_frame, columns=("vrf", "prefix", "nh"), show="headings", height=6)
        for c, t, w in [("vrf", "VRF", 120), ("prefix", "Prefix", 170), ("nh", "Next-hop", 150)]:
            self.route_tree.heading(c, text=t)
            self.route_tree.column(c, width=w, anchor="w")
        
        # Add scrollbar to route tree
        route_scroll = ttk.Scrollbar(route_frame, orient="vertical", command=self.route_tree.yview)
        self.route_tree.configure(yscroll=route_scroll.set)
        self.route_tree.grid(row=0, column=0, sticky="nsew")
        route_scroll.grid(row=0, column=1, sticky="ns")
        route_frame.rowconfigure(0, weight=1)
        route_frame.columnconfigure(0, weight=1)

    def _build_interfaces_tab(self):
        """Build dedicated Interfaces tab."""
        self.tab_interfaces.columnconfigure(0, weight=1)
        self.tab_interfaces.rowconfigure(2, weight=1)
        
        ttk.Label(self.tab_interfaces, text="Device Interfaces", style="Header.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 8))
        
        # Filter row
        filter_frame = ttk.Frame(self.tab_interfaces, style="Panel.TFrame")
        filter_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        
        ttk.Label(filter_frame, text="Filter:", style="Panel.TLabel").pack(side="left", padx=(0, 10))
        self.if_filter_var = tk.StringVar(value="all")
        for key, label in [("all", "All"), ("access", "Access"), ("trunk", "Trunk"), ("routed", "Routed"), ("pc", "In Po")]:
            rb = ttk.Radiobutton(filter_frame, text=label, value=key, variable=self.if_filter_var, command=self._render_interfaces_table)
            rb.pack(side="left", padx=(0, 10))
        
        # Interfaces tree
        self.if_tree = ttk.Treeview(
            self.tab_interfaces,
            columns=("iface", "mode", "access", "trunk", "native", "po", "ip", "vrf", "desc", "vip"),
            show="headings",
            height=20
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
            ("vip", "Virtual IP (HSRP/VRRP)", 200),
        ]
        for c, t, w in cols:
            self.if_tree.heading(c, text=t)
            self.if_tree.column(c, width=w, anchor="w")
        self.if_tree.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))

    # ---------------- Actions ----------------

    def load_files(self):
        logger.info("================== USER INITIATED FILE LOAD ==================")
        
        paths = filedialog.askopenfilenames(
            title="Select device configs / runbooks",
            filetypes=[("Text / Config", "*.txt *.log *.cfg *.conf *.*")]
        )
        if not paths:
            logger.info("User cancelled file selection")
            return

        files_selected = len(paths)
        logger.info(f"User selected {files_selected} file(s): {list(paths)}")
        
        try:
            logger.info("Starting parsing...")
            topo, file_errors = parse_with_adapters(list(paths))
            logger.info(f"Parsing complete: {len(topo.devices)} devices loaded")
        except Exception as e:
            error_msg = f"Failed to parse files:\n{e}"
            logger.error(f"Parse Exception: {error_msg}", exc_info=True)
            messagebox.showerror("Parse Error", error_msg)
            return

        devices_loaded = len(topo.devices)
        logger.info(f"Devices loaded: {devices_loaded}, File errors: {len(file_errors)}")
        
        # Only show errors if there are errors AND we got some devices
        if file_errors and devices_loaded > 0:
            error_msg = f"Loaded {devices_loaded} device(s), but {len(file_errors)} file(s) had issues:\n\n"
            for fname, err in list(file_errors.items())[:8]:  # Show top 8 errors
                error_msg += f"• {fname}: {err[:60]}\n"
                logger.warning(f"File error in {fname}: {err}")
            if len(file_errors) > 8:
                error_msg += f"\n...and {len(file_errors) - 8} more"
            messagebox.showwarning("File Load Report", error_msg)

        if not topo.devices:
            if file_errors:
                error_list = [f"{fname}: {err}" for fname, err in file_errors.items()]
                logger.error(f"No devices loaded. Errors: {error_list}")
                error_msg = f"Failed to load any devices from {files_selected} file(s):\n\n"
                for fname, err in list(file_errors.items())[:5]:
                    error_msg += f"• {fname}: {err[:60]}\n"
                messagebox.showerror("No Data", error_msg)
            else:
                logger.error("No devices loaded and no errors recorded")
                messagebox.showerror("No Data", "No devices were found in the selected files.")
            logger.info("================== FILE LOAD FAILED ==================\n")
            return

        self._topo = topo
        self._cached_detail_text.clear()
        self._cached_device_json.clear()
        self._cached_pair_text.clear()

        self._device_order = sorted(self._topo.devices.keys())
        self.lbl_loaded.configure(text=f"Loaded: {len(self._device_order)}")
        logger.info(f"Device list sorted: {self._device_order}")
        self._refresh_device_list()

        # Auto-select first device to populate Details tab immediately
        if self._device_order:
            first_device = self._device_order[0]
            self._select_device(first_device)
            logger.info(f"Auto-selected first device: {first_device}")
        
        self._node_pos.clear()
        logger.info("Running auto-layout...")
        self.auto_layout()

        # Run analysis
        logger.info("Running configuration analysis...")
        self._validation_issues = validate_configuration(topo)
        logger.debug(f"Found {len(self._validation_issues)} validation issues")
        
        self._interface_stats = get_interface_statistics(topo)
        logger.debug(f"Calculated interface statistics")
        
        self._vrf_analysis = analyze_vrfs(topo)
        logger.info(f"Analyzed {len(self._vrf_analysis)} VRF(s)")
        
        self._device_roles = {hn: detect_device_role(dev, topo, hn) for hn, dev in topo.devices.items()}
        logger.info(f"Detected device roles:")
        for hn, role in self._device_roles.items():
            logger.info(f"  {hn}: {role.role} ({role.confidence})")
        
        # Update analysis tabs
        logger.info("Refreshing UI tabs...")
        self._refresh_validation_tab()
        self._refresh_vrf_roles_tab()

        # auto select first device
        if self._device_order:
            selected = self._device_order[0]
            logger.info(f"Auto-selecting first device: {selected}")
            self._select_device(selected)
        
        logger.info("================== FILE LOAD SUCCESSFUL ==================\n")

    def clear_all(self):
        self._topo = TopologyData()
        self._active_device = None
        self._device_order = []
        self._node_pos.clear()
        self._cached_detail_text.clear()
        self._cached_device_json.clear()
        self._cached_pair_text.clear()
        self._validation_issues.clear()
        self._interface_stats.clear()
        self._vrf_analysis.clear()
        self._device_roles.clear()

        self.lbl_loaded.configure(text="Loaded: 0")
        self.device_list.delete(0, "end")
        self._set_inspector_text("")

        self._set_text(self.raw_text, "")
        self._set_text(self.json_text, "")

        # clear details widgets if built
        for wname in ("identity_text", "pair_text", "l2_text", "l3_text"):
            if hasattr(self, wname):
                self._set_text(getattr(self, wname), "")

        for tname in ("vlan_tree", "pc_tree", "ip_tree", "route_tree", "if_tree", "validation_tree", "vrf_tree", "roles_tree"):
            if hasattr(self, tname):
                tree = getattr(self, tname)
                for item in tree.get_children():
                    tree.delete(item)

        self.draw_topology()

    def view_logs(self):
        """Open a window to view and manage application logs"""
        logger.info("User opened View Logs window")
        
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        if not os.path.exists(log_dir):
            messagebox.showinfo("Logs", "No logs directory found. Logs will be created when files are loaded.")
            return
        
        # Get all log files, sorted by modification time (newest first)
        log_files = []
        try:
            for filename in os.listdir(log_dir):
                if filename.endswith('.log'):
                    filepath = os.path.join(log_dir, filename)
                    mtime = os.path.getmtime(filepath)
                    size = os.path.getsize(filepath)
                    log_files.append((filename, filepath, mtime, size))
            log_files.sort(key=lambda x: x[2], reverse=True)
        except Exception as e:
            messagebox.showerror("Logs", f"Error reading logs: {e}")
            return
        
        if not log_files:
            messagebox.showinfo("Logs", f"No log files found in {log_dir}")
            return
        
        # Create logs window
        win = tk.Toplevel(self)
        win.title("Application Logs")
        win.geometry("900x700")
        win.configure(bg=self.colors.bg)
        apply_dark_theme(win, self.colors)
        win.rowconfigure(2, weight=1)
        
        # Header
        header = ttk.Frame(win, style="Panel.TFrame")
        header.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(header, text="Application Logs", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text=f"{len(log_files)} log file(s) in {log_dir}", style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        
        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=12, pady=(0, 8))
        
        # Log file selector
        selector_frame = ttk.Frame(win, style="Panel.TFrame")
        selector_frame.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(selector_frame, text="Select log file:", style="Panel.TLabel").pack(side="left", padx=(0, 10))
        
        selected_log = tk.StringVar(value=log_files[0][0] if log_files else "")
        dropdown = ttk.Combobox(selector_frame, textvariable=selected_log, state="readonly", width=50)
        dropdown['values'] = [f"{f[0]} ({f[3]/1024:.1f}KB)" for f in log_files]
        dropdown.pack(side="left", fill="x", expand=True)
        
        # Text area
        text_frame = ttk.Frame(win, style="Panel.TFrame")
        text_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        
        log_text = tk.Text(
            text_frame,
            bg=self.colors.panel,
            fg=self.colors.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors.border,
            wrap="word",
            font=("Courier New", 9)
        )
        log_text.pack(fill="both", expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=log_text.yview)
        log_text.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", before=log_text)
        
        def load_selected_log(*args):
            """Load the selected log file"""
            try:
                idx = dropdown.current()
                if idx >= 0 and idx < len(log_files):
                    log_path = log_files[idx][1]
                    with open(log_path, 'r') as f:
                        content = f.read()
                    log_text.config(state="normal")
                    log_text.delete("1.0", "end")
                    log_text.insert("1.0", content)
                    log_text.config(state="disabled")
                    # Jump to end
                    log_text.see("end")
            except Exception as e:
                log_text.config(state="normal")
                log_text.delete("1.0", "end")
                log_text.insert("1.0", f"Error loading log: {e}")
                log_text.config(state="disabled")
        
        dropdown.bind("<<ComboboxSelected>>", load_selected_log)
        # Load first log automatically
        load_selected_log()
        log_text.config(state="disabled")
        
        # Button frame
        btn_frame = ttk.Frame(win, style="Panel.TFrame")
        btn_frame.pack(fill="x", padx=12, pady=(0, 12))
        
        def export_log():
            """Export current log to file"""
            idx = dropdown.current()
            if idx < 0 or idx >= len(log_files):
                messagebox.showwarning("Export", "No log selected")
                return
            src = log_files[idx][1]
            save_path = filedialog.asksaveasfilename(
                title="Export log file",
                defaultextension=".log",
                initialfile=log_files[idx][0],
                filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All", "*.*")]
            )
            if save_path:
                try:
                    with open(src, 'r') as f:
                        content = f.read()
                    with open(save_path, 'w') as f:
                        f.write(content)
                    messagebox.showinfo("Export", f"Log exported to:\n{save_path}")
                    logger.info(f"Log exported: {save_path}")
                except Exception as e:
                    messagebox.showerror("Export Error", f"Failed to export log: {e}")
        
        def open_log_folder():
            """Open logs folder in file explorer"""
            try:
                if os.name == 'nt':  # Windows
                    os.startfile(log_dir)
                elif os.name == 'posix':  # macOS/Linux
                    os.system(f'open "{log_dir}"')
                logger.info(f"Opened logs folder: {log_dir}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open folder: {e}")
        
        ttk.Button(btn_frame, text="Export Current Log", command=export_log).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Open Logs Folder", command=open_log_folder).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Close", command=win.destroy).pack(side="right")
        
        win.grab_set()
        win.transient(self.master)

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

    def _on_validation_select(self, event):
        """Show full details of selected validation issue."""
        selection = self.validation_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        values = self.validation_tree.item(item, "values")
        if not values or len(values) < 3:
            return
        
        device_str, severity_str, message_str = values[0], values[1], values[2]
        
        # Skip if it's a header
        if severity_str in ["—", "SUMMARY"] or not message_str or message_str.startswith("("):
            self.validation_detail.config(state="normal")
            self.validation_detail.delete("1.0", "end")
            self.validation_detail.insert("1.0", "Select a specific issue to view details")
            self.validation_detail.config(state="disabled")
            return
        
        # Find the matching issue for full message
        full_message = message_str
        for issue in self._validation_issues:
            if (device_str.strip() == issue.device and 
                severity_str.lower() == issue.severity):
                # Build detailed message
                details = [
                    f"Device: {issue.device}",
                    f"Severity: {issue.severity.upper()}",
                    f"Category: {issue.category}",
                    f"\nFull Message:\n{issue.message}"
                ]
                full_message = "\n".join(details)
                break
        
        self.validation_detail.config(state="normal")
        self.validation_detail.delete("1.0", "end")
        self.validation_detail.insert("1.0", full_message)
        self.validation_detail.config(state="disabled")

    def _refresh_validation_tab(self):
        """Update validation issues tree with improved formatting and grouping."""
        for item in self.validation_tree.get_children():
            self.validation_tree.delete(item)
        
        if not self._validation_issues:
            self.validation_tree.insert("", "end", values=("—", "INFO", "No validation issues found"))
            return
        
        # Count by severity
        error_count = sum(1 for i in self._validation_issues if i.severity == "error")
        warn_count = sum(1 for i in self._validation_issues if i.severity == "warning")
        info_count = sum(1 for i in self._validation_issues if i.severity == "info")
        
        # Add summary row
        summary = f"Errors: {error_count} | Warnings: {warn_count} | Info: {info_count}"
        self.validation_tree.insert("", "end", values=("SUMMARY", "—", summary), tags=("summary",))
        
        # Group by severity then by category for better organization
        by_severity = {}
        for issue in self._validation_issues:
            if issue.severity not in by_severity:
                by_severity[issue.severity] = {}
            by_severity[issue.severity].setdefault(issue.category, []).append(issue)
        
        # Add issues, high severity first
        severity_order = ["error", "warning", "info"]
        for severity in severity_order:
            for category in sorted(by_severity.get(severity, {}).keys()):
                issues = by_severity[severity][category]
                
                # Add category header
                category_name = category.upper() if category else "OTHER"
                count_str = f"({len(issues)})" if len(issues) > 1 else ""
                self.validation_tree.insert("", "end", 
                    values=(f"  {category_name}", severity.upper(), count_str),
                    tags=(f"category-{severity}",))
                
                # Add ALL individual issues (no limit - show all data)
                for issue in issues:
                    # Format device and message for readability
                    msg_short = issue.message[:120] if len(issue.message) > 120 else issue.message
                    self.validation_tree.insert("", "end", 
                        values=(f"    {issue.device}", severity.upper(), msg_short),
                        tags=(f"issue-{severity}",))

    def _refresh_vrf_roles_tab(self):
        """Update VRF and device roles trees."""
        # Clear VRF tree
        for item in self.vrf_tree.get_children():
            self.vrf_tree.delete(item)
        
        # Add VRF data
        for vrf_analysis in self._vrf_analysis:
            self.vrf_tree.insert("", "end", values=(
                vrf_analysis.vrf_name,
                vrf_analysis.device_count,
                vrf_analysis.route_count,
                vrf_analysis.interface_count
            ))
        
        # Clear roles tree
        for item in self.roles_tree.get_children():
            self.roles_tree.delete(item)
        
        # Add device roles
        for hn, role in sorted(self._device_roles.items()):
            self.roles_tree.insert("", "end", values=(
                role.device, role.role.upper(), role.confidence.upper()
            ))
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
            for v in sorted(d.vlans, key=lambda x: int(x.vid) if x.vid.isdigit() else 9999):
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
            for r in d.static_routes:
                self.route_tree.insert("", "end", values=(r.vrf, r.prefix, r.nexthop))

        # Update interfaces tab
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

            # Format virtual IP (if HSRP/VRRP configured)
            vip = ""
            if iface.virtual_ip:
                vip = iface.virtual_ip
                if iface.hsrp_group:
                    vip += f" (HSRP:{iface.hsrp_group})"
                elif iface.vrrp_group:
                    vip += f" (VRRP:{iface.vrrp_group})"

            rows.append((
                ifn,
                mode or "—",
                iface.access_vlan or "—",
                iface.trunk_vlans_raw or "—",
                iface.native_vlan or "—",
                po or "—",
                iface.ip or "—",
                iface.vrf or "default",
                iface.description or "—",
                vip or "—"
            ))

        for r in rows[:800]:
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
        hsrp_count = 0
        vrrp_count = 0
        for iface in d.interfaces.values():
            if iface.ip:
                ip_count += 1
            if iface.is_svi and iface.ip:
                svi_count += 1
            if iface.hsrp_group:
                hsrp_count += 1
            if iface.vrrp_group:
                vrrp_count += 1

        vrfs = sorted(d.vrfs.keys()) if d.vrfs else ["default"]
        
        lines = [
            "Layer 3 Summary",
            f"  IP interfaces : {ip_count}",
            f"  SVIs          : {svi_count}",
            f"  Loopbacks     : {len(d.loopbacks)}",
            f"  VRFs          : {', '.join(vrfs)}",
            f"  Routing protos: {', '.join(d.routing_protocols) if d.routing_protocols else '—'}",
            f"  Static routes : {len(d.static_routes)}",
        ]
        
        # HSRP/VRRP details
        if hsrp_count > 0 or vrrp_count > 0:
            lines.append(f"")
            if hsrp_count > 0:
                lines.append(f"  HSRP Groups   : {hsrp_count}")
                for iface in d.interfaces.values():
                    if iface.hsrp_group and iface.virtual_ip:
                        gid = iface.hsrp_group
                        vip = iface.virtual_ip
                        lines.append(f"    • {iface.name} group {gid}: VIP {vip}")
            if vrrp_count > 0:
                lines.append(f"  VRRP Groups   : {vrrp_count}")
                for iface in d.interfaces.values():
                    if iface.vrrp_group and iface.virtual_ip:
                        gid = iface.vrrp_group
                        vip = iface.virtual_ip
                        lines.append(f"    • {iface.name} group {gid}: VIP {vip}")
        
        # BGP details
        if d.bgp_asn or d.bgp_neighbors:
            lines.append(f"")
            lines.append("Routing Protocols - BGP")
            if d.bgp_asn:
                lines.append(f"  ASN           : {d.bgp_asn}")
            if d.bgp_neighbors:
                lines.append(f"  Neighbors     : {len(d.bgp_neighbors)}")
                # Show ALL BGP neighbors
                for bgp in d.bgp_neighbors:
                    vrf_str = f" (VRF: {bgp.vrf})" if bgp.vrf != "default" else ""
                    state_str = f" [{bgp.state}]" if bgp.state else ""
                    lines.append(f"    • {bgp.neighbor_ip} AS{bgp.remote_as}{vrf_str}{state_str}")
        
        # OSPF details
        if d.ospf_neighbors:
            lines.append(f"")
            lines.append("Routing Protocols - OSPF")
            lines.append(f"  Neighbors     : {len(d.ospf_neighbors)}")
            # Show ALL OSPF neighbors
            for ospf in d.ospf_neighbors:
                lines.append(f"    • {ospf.neighbor_id} via {ospf.interface} ({ospf.state})")
        
        # Loopback details  
        if d.loopbacks:
            lines.append(f"")
            lines.append("Loopback Interfaces:")
            for lb in d.loopbacks:
                vrf_str = f" (VRF: {lb.vrf})" if lb.vrf != "default" else ""
                lines.append(f"  • {lb.interface}: {lb.ip}{vrf_str}")
        
        # Static routes details (including default routes)
        if d.static_routes:
            lines.append(f"")
            lines.append(f"Static Routes ({len(d.static_routes)}):")
            
            # Separate default routes from others
            default_routes = [r for r in d.static_routes if r.prefix == "0.0.0.0/0"]
            other_routes = [r for r in d.static_routes if r.prefix != "0.0.0.0/0"]
            
            # Show ALL default routes
            if default_routes:
                lines.append("  Default Routes:")
                for route in default_routes:
                    vrf_str = f" (VRF: {route.vrf})" if route.vrf != "default" else ""
                    lines.append(f"    • 0.0.0.0/0 via {route.nexthop}{vrf_str}")
            
            # Show ALL other routes
            if other_routes:
                lines.append(f"  Other Routes ({len(other_routes)}):")
                for route in other_routes:
                    vrf_str = f" (VRF: {route.vrf})" if route.vrf != "default" else ""
                    lines.append(f"    • {route.prefix} via {route.nexthop}{vrf_str}")
        
        # Other L3 info
        lines.append(f"")
        lines.append(f"  CDP neighbors : {len(d.cdp)}")
        
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
        """Draw edge labels with improved contrast, multi-line stacking for same-pair links, and zoom scaling."""
        if not link_labels:
            return
        
        # Group labels by device pair to handle multiple links between same devices
        from collections import defaultdict
        pair_groups = defaultdict(list)
        
        for label_data in link_labels:
            link = label_data["link"]
            # Create normalized pair key (sort to treat A-B = B-A)
            pair_key = tuple(sorted([link.a, link.b]))
            pair_groups[pair_key].append(label_data)
        
        used_regions = []  # Track label positions to avoid collisions
        
        # Scale font size and background with zoom level
        base_font_size = max(6, int(8 * (self.zoom_level ** 0.6)))
        bg_width = max(50, int(70 * (self.zoom_level ** 0.5)))
        line_height = max(12, int(16 * (self.zoom_level ** 0.6)))  # Height per line of text
        offset_distance = max(15, int(25 * (self.zoom_level ** 0.5)))
        
        # Process each device pair group
        for pair_key, labels_in_pair in pair_groups.items():
            if not labels_in_pair:
                continue
            
            # Use first link's geometry as base position
            first_label = labels_in_pair[0]
            x1, y1 = first_label["x1"], first_label["y1"]
            x2, y2 = first_label["x2"], first_label["y2"]
            
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
                offsets = [0, offset_distance, -offset_distance]
                placed = False
                
                for offset in offsets:
                    label_x = mx + perp_x * offset
                    label_y = my + perp_y * offset
                    
                    # Calculate total height needed for all labels in this group
                    total_lines = len(labels_in_pair)
                    total_height = line_height * total_lines
                    bg_height = max(10, int(total_height / 2 + 4))
                    
                    # Check collision (scale collision box with zoom)
                    collision = False
                    for region in used_regions:
                        if abs(label_x - region[0]) < bg_width * 1.2 and abs(label_y - region[1]) < bg_height * 1.5:
                            collision = True
                            break
                    
                    if not collision:
                        # Build multi-line text for all links in this pair
                        label_lines = []
                        for label_data in labels_in_pair:
                            link = label_data["link"]
                            # Compact format: interfaces and evidence on one line
                            line_text = f"{link.a_intf} ↔ {link.b_intf} ({link.evidence})"
                            label_lines.append(line_text)
                        
                        combined_text = "\n".join(label_lines)
                        
                        # Create dark background sized for multi-line text
                        canvas.create_rectangle(
                            label_x - bg_width, label_y - bg_height,
                            label_x + bg_width, label_y + bg_height,
                            fill=self.colors.panel2, outline=self.colors.border, width=max(1, int(self.zoom_level))
                        )
                        
                        # Draw multi-line text with high contrast and scaled font
                        canvas.create_text(
                            label_x, label_y,
                            text=combined_text, fill="#e8e3d7",
                            font=("Segoe UI", base_font_size, "bold"),
                            justify="center"
                        )
                        
                        used_regions.append((label_x, label_y))
                        placed = True
                        break
                
                # Fallback: just place it if no good location found
                if not placed:
                    label_lines = []
                    for label_data in labels_in_pair:
                        link = label_data["link"]
                        line_text = f"{link.a_intf} ↔ {link.b_intf} ({link.evidence})"
                        label_lines.append(line_text)
                    
                    combined_text = "\n".join(label_lines)
                    total_lines = len(labels_in_pair)
                    total_height = line_height * total_lines
                    bg_height = max(10, int(total_height / 2 + 4))
                    
                    canvas.create_rectangle(
                        mx - bg_width, my - bg_height,
                        mx + bg_width, my + bg_height,
                        fill=self.colors.panel2, outline=self.colors.border, width=max(1, int(self.zoom_level))
                    )
                    canvas.create_text(
                        mx, my,
                        text=combined_text, fill="#e8e3d7",
                        font=("Segoe UI", base_font_size, "bold"),
                        justify="center"
                    )

    def _format_node_info(self, d: DeviceSummary) -> List[str]:
        """Format device info for display inside topology node - clean and minimal."""
        lines = []
        
        # Line 1: Hostname
        lines.append(d.hostname)
        
        # Line 2: Device type (vendor and model if available)
        if d.model and d.model != "—":
            device_type = f"{d.vendor} {d.model}"
        else:
            device_type = d.vendor
        lines.append(device_type)
        
        # Line 3: Code version
        code_version = d.os_ver if d.os_ver and d.os_ver != "—" else "Version unknown"
        lines.append(code_version)
        
        # Line 4: Default route (find 0.0.0.0/0 in static routes)
        default_route = "No default route"
        for route in d.static_routes:
            if route.prefix in ("0.0.0.0/0", "0.0.0.0 0.0.0.0", "::/0"):
                if route.nexthop:
                    # Show full route with prefix and nexthop
                    prefix_display = route.prefix if route.prefix != "0.0.0.0 0.0.0.0" else "0.0.0.0/0"
                    nh_display = route.nexthop if len(route.nexthop) <= 25 else route.nexthop[:22] + "..."
                    default_route = f"Default: {prefix_display} via {nh_display}"
                else:
                    default_route = "Default: 0.0.0.0/0 (configured)"
                break
        lines.append(default_route)
        
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

            # Scale node size with zoom to prevent text overlap
            # Increased width to accommodate full default route display with prefix (0.0.0.0/0 via IP)
            base_node_w, base_node_h = 520, 160
            node_w = max(320, int(base_node_w * (self.zoom_level ** 0.7)))
            node_h = max(140, int(base_node_h * (self.zoom_level ** 0.7)))
            x0 = x - node_w // 2
            y0 = y - node_h // 2
            x1 = x + node_w // 2
            y1 = y + node_h // 2

            # Transform node corners
            x0_zoom, y0_zoom = xform(x0, y0)
            x1_zoom, y1_zoom = xform(x1, y1)

            # Color by vendor
            vendor_color = get_vendor_color(d.vendor)
            node_fill = vendor_color if not is_active else self.colors.accent
            outline = self.colors.border if not is_active else self.colors.accent
            line_width = max(1, int(2 * self.zoom_level)) if not is_active else max(1, int(3 * self.zoom_level))

            tag = f"node:{name}"
            c.create_rectangle(x0_zoom, y0_zoom, x1_zoom, y1_zoom, fill=node_fill, outline=outline, width=line_width, tags=(tag,))

            # Format and draw multi-line node info with better spacing
            info_lines = self._format_node_info(d)
            line_height = max(12, int(16 * (self.zoom_level ** 0.6)))
            start_y = y0_zoom + max(6, int(12 * (self.zoom_level ** 0.5)))
            padding_x = max(8, int(12 * (self.zoom_level ** 0.5)))
            
            for idx, line in enumerate(info_lines):
                y_pos = start_y + (idx * line_height)
                if y_pos > y1_zoom - 12:
                    break
                # Scale font size intelligently with zoom (less aggressive)
                font_size = max(7, int((10 if idx == 0 else 8.5) * (self.zoom_level ** 0.5)))
                font_weight = "bold" if idx == 0 else "normal"
                c.create_text(x0_zoom + padding_x, y_pos, anchor="nw", text=line, fill="black",
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