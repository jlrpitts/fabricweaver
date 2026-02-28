# fabricweaver/ui/layout.py
# Tkinter layout (Devices / Topology / Raw Data + Options)

from __future__ import annotations

import os
import re
import math
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
class DeviceSummary:
    hostname: str = "—"
    vendor: str = "—"
    mgmt_ip: str = "—"
    model: str = "—"
    os_ver: str = "—"
    vpc_role: str = "—"
    mlag: str = "—"
    vlans: List[VlanInfo] = field(default_factory=list)
    l3_interfaces: List[InterfaceIP] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class Link:
    a: str
    b: str
    label: str = ""
    kind: str = "L2"  # "L2" or "L3"


@dataclass
class TopologyData:
    devices: Dict[str, DeviceSummary] = field(default_factory=dict)
    links: List[Link] = field(default_factory=list)


# -----------------------------
# Lightweight parser fallback (NX-OS aware)
# -----------------------------
HOST_RE = re.compile(r"^\s*hostname\s+(\S+)", re.IGNORECASE | re.MULTILINE)
INT_RE = re.compile(r"^\s*interface\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)

# NX-OS / IOS mask format
IP_MASK_RE = re.compile(
    r"^\s*ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# NX-OS prefix format (very common)
IP_PREFIX_RE = re.compile(
    r"^\s*ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s*/\s*(\d{1,2})\s*$",
    re.IGNORECASE | re.MULTILINE,
)

VLAN_HDR_RE = re.compile(r"^\s*vlan\s+([0-9,\-\s]+)\s*$", re.IGNORECASE | re.MULTILINE)
VLAN_NAME_RE = re.compile(r"^\s*name\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

# -----------------------------
# Vendor detection (FIXED)
# -----------------------------
# The bug you hit: treating "interface vlan" as Dell.
# NX-OS also uses "interface Vlan###", so that's a false-positive.
# Use strong Dell-only hints, and evaluate NX-OS before Dell.
NXOS_VENDOR_HINT = re.compile(r"\bnxos\b|\bnexus\b|feature\s+vpc|vpc\s+domain", re.IGNORECASE)
IOS_VENDOR_HINT = re.compile(r"\bcatalyst\b|\bios\b|\bios-xe\b|switchport|spanning-tree", re.IGNORECASE)
ARISTA_HINT = re.compile(r"\barista\b|\beos\b|terminattr|management\s+api", re.IGNORECASE)
DELL_OS10_HINT = re.compile(r"\bos10\b|dell\s+emc|\bvlt\s+domain\b|\bsmartfabric\b", re.IGNORECASE)


def _guess_vendor(text: str) -> str:
    # Order matters: check strongest + most specific first.
    if ARISTA_HINT.search(text):
        return "Arista EOS"
    if NXOS_VENDOR_HINT.search(text):
        return "Cisco Nexus (NX-OS)"
    if DELL_OS10_HINT.search(text):
        return "Dell OS10"
    if IOS_VENDOR_HINT.search(text):
        return "Cisco Catalyst (IOS/IOS-XE)"
    return "AUTODETECT"


def _mask_to_prefix(mask: str) -> int:
    parts = [int(p) for p in mask.split(".")]
    bits = "".join(f"{p:08b}" for p in parts)
    return bits.count("1")


def _expand_vlan_spec(spec: str) -> List[str]:
    """
    Expand "10,20,30-32" -> ["10","20","30","31","32"].
    """
    out: List[str] = []
    spec = spec.replace(" ", "")
    for chunk in spec.split(","):
        if not chunk:
            continue
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            if a.isdigit() and b.isdigit():
                start = int(a)
                end = int(b)
                if start <= end:
                    out.extend([str(v) for v in range(start, end + 1)])
        else:
            if chunk.isdigit():
                out.append(chunk)
    return out


def _parse_vlans(text: str) -> List[VlanInfo]:
    """
    Works with:
      vlan 10
        name USERS
      vlan 10,20,30
        name SERVERS
      vlan 100-110
        name TRANSIT
    """
    vlan_map: Dict[str, VlanInfo] = {}
    current_vids: List[str] = []

    for line in text.splitlines():
        hm = VLAN_HDR_RE.match(line)
        if hm:
            current_vids = _expand_vlan_spec(hm.group(1))
            for vid in current_vids:
                vlan_map.setdefault(vid, VlanInfo(vid=vid, name="—"))
            continue

        nm = VLAN_NAME_RE.match(line)
        if nm and current_vids:
            name = nm.group(1).strip()
            for vid in current_vids:
                vlan_map[vid] = VlanInfo(vid=vid, name=name)

    def sort_key(v: VlanInfo) -> int:
        try:
            return int(v.vid)
        except Exception:
            return 0

    return sorted(vlan_map.values(), key=sort_key)[:300]


def _parse_interface_block_ip(block_text: str) -> Optional[str]:
    m = IP_PREFIX_RE.search(block_text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = IP_MASK_RE.search(block_text)
    if m:
        return f"{m.group(1)}/{_mask_to_prefix(m.group(2))}"
    return None


def _iter_interface_blocks(text: str) -> List[Tuple[str, str]]:
    """
    Returns list of (ifname, block_text) where block_text is the lines
    between this interface header and the next interface header.
    """
    matches = list(INT_RE.finditer(text))
    blocks: List[Tuple[str, str]] = []
    for idx, im in enumerate(matches):
        ifname = im.group(1)
        start = im.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        blocks.append((ifname, text[start:end]))
    return blocks


def _parse_l3_ints(text: str) -> List[InterfaceIP]:
    """
    Finds interface blocks with IPs.
    NX-OS commonly: ip address A.B.C.D/NN
    IOS commonly:   ip address A.B.C.D MASK
    """
    out: List[InterfaceIP] = []
    for ifname, block in _iter_interface_blocks(text):
        ip = _parse_interface_block_ip(block)
        if ip:
            out.append(InterfaceIP(name=ifname, ip=ip))
    return out[:120]


def _parse_mgmt0_ip(text: str) -> str:
    """
    Prefer mgmt0 address if found.
    """
    for ifname, block in _iter_interface_blocks(text):
        if ifname.lower() == "mgmt0":
            ip = _parse_interface_block_ip(block)
            return ip or "—"
    return "—"


def parse_configs_fallback(paths: List[str]) -> TopologyData:
    topo = TopologyData()

    for p in paths:
        try:
            text = open(p, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue

        hostm = HOST_RE.search(text)
        hostname = hostm.group(1) if hostm else os.path.splitext(os.path.basename(p))[0]

        vendor = _guess_vendor(text)
        mgmt_ip = _parse_mgmt0_ip(text)
        if mgmt_ip == "—":
            mgmt_ip = "STATIC_FILE"

        d = DeviceSummary(
            hostname=hostname,
            vendor=vendor,
            mgmt_ip=mgmt_ip,
            raw_text=text,
        )
        d.vlans = _parse_vlans(text)
        d.l3_interfaces = _parse_l3_ints(text)

        topo.devices[hostname] = d

    # Placeholder links (until real adjacency parsing)
    names = list(topo.devices.keys())
    for i in range(len(names) - 1):
        topo.links.append(Link(a=names[i], b=names[i + 1], label="Auto", kind="L2"))

    return topo


def parse_configs(paths: List[str]) -> TopologyData:
    """
    Tries your real parser if present; otherwise uses the fallback parser above.
    """
    try:
        from parser.orchestrator import parse_configs as real_parse  # type: ignore
        parsed = real_parse(paths)
        if isinstance(parsed, TopologyData):
            return parsed

        # Best-effort adaptation if orchestrator returns different objects
        topo = TopologyData()
        for dev in getattr(parsed, "devices", []) or []:
            hostname = getattr(dev, "hostname", "—")
            d = DeviceSummary(
                hostname=hostname,
                vendor=getattr(dev, "vendor", "—"),
                mgmt_ip=getattr(dev, "mgmt_ip", "—"),
                model=getattr(dev, "model", "—"),
                os_ver=getattr(dev, "os_ver", "—"),
                vpc_role=getattr(dev, "vpc_role", "—"),
                mlag=getattr(dev, "mlag", "—"),
                raw_text=getattr(dev, "raw_text", "") or "",
            )
            for v in getattr(dev, "vlans", []) or []:
                d.vlans.append(VlanInfo(str(getattr(v, "vid", "")), str(getattr(v, "name", ""))))
            for i in getattr(dev, "l3_interfaces", []) or []:
                d.l3_interfaces.append(InterfaceIP(str(getattr(i, "name", "")), str(getattr(i, "ip", ""))))
            topo.devices[hostname] = d

        for l in getattr(parsed, "links", []) or []:
            topo.links.append(
                Link(
                    a=str(getattr(l, "a", "")),
                    b=str(getattr(l, "b", "")),
                    label=str(getattr(l, "label", "")),
                    kind=str(getattr(l, "kind", "L2")).upper(),
                )
            )
        return topo
    except Exception:
        return parse_configs_fallback(paths)


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
        self._static_flow_labels = tk.BooleanVar(value=True)

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
        title.pack(side="left", padx=(12, 12), pady=10)

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
        ttk.Button(top, text="Export", command=self._export_placeholder).pack(side="left", padx=8)
        ttk.Button(top, text="Clear", command=self._clear_all).pack(side="left", padx=8)

        body = ttk.Frame(root, style="TFrame")
        body.pack(fill="both", expand=True)

        # Left panel (device list)
        left = ttk.Frame(body, style="Panel.TFrame")
        left.pack(side="left", fill="y", padx=(0, 10))

        ttk.Label(left, text="Devices", style="Header.TLabel").pack(anchor="w", padx=12, pady=(10, 8))

        list_frame = ttk.Frame(left, style="Panel.TFrame")
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.device_list = tk.Listbox(
            list_frame,
            bg=self.colors.panel,
            fg=self.colors.text,
            highlightthickness=1,
            highlightbackground=self.colors.border,
            selectbackground="#1f2a44",
            selectforeground=self.colors.text,
            relief="flat",
            width=22,
            height=22,
        )
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.device_list.yview)
        self.device_list.configure(yscrollcommand=sb.set)
        self.device_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.device_list.bind("<<ListboxSelect>>", self._on_device_select)

        # Right panel (summary)
        right = ttk.Frame(body, style="Panel.TFrame")
        right.pack(side="left", fill="both", expand=True)

        self.detail_title = ttk.Label(right, text="FABRICWEAVER — SUMMARY VIEW (UI v2)", style="Header.TLabel")
        self.detail_title.pack(anchor="w", padx=12, pady=(10, 8))

        text_frame = ttk.Frame(right, style="Panel.TFrame")
        text_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.detail_text = tk.Text(
            text_frame,
            bg=self.colors.panel,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors.border,
            wrap="none",
            font=("Consolas", 10),
        )
        sb2 = ttk.Scrollbar(text_frame, orient="vertical", command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=sb2.set)
        self.detail_text.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        self.detail_text.config(state="disabled")

    def _render_device_summary(self, d: DeviceSummary) -> str:
        lines: List[str] = []
        lines.append("")
        lines.append("DEVICE")
        lines.append(f"Hostname : {d.hostname}")
        lines.append(f"Vendor   : {d.vendor}")
        lines.append(f"Mgmt IP  : {d.mgmt_ip}")
        if d.model != "—":
            lines.append(f"Model    : {d.model}")
        if d.os_ver != "—":
            lines.append(f"OS Ver   : {d.os_ver}")
        if d.vpc_role != "—":
            lines.append(f"vPC Role : {d.vpc_role}")
        if d.mlag != "—":
            lines.append(f"MLAG     : {d.mlag}")

        lines.append("")
        lines.append("L2: VLANs")
        if d.vlans:
            for v in d.vlans[:120]:
                lines.append(f"VLAN {v.vid:<5}  name: {v.name}")
        else:
            lines.append("—")

        lines.append("")
        lines.append("L3: Interfaces (with IP)")
        if d.l3_interfaces:
            for i in d.l3_interfaces[:120]:
                lines.append(f"{i.name:<18} {i.ip}")
        else:
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
        ttk.Button(top, text="Re-Layout", command=self._draw_topology).pack(side="left", padx=8)

        legend = ttk.Frame(top, style="Panel.TFrame")
        legend.pack(side="right", padx=8)

        ttk.Label(legend, text="L2", style="Panel.TLabel").pack(side="left", padx=(10, 6), pady=6)
        l2 = tk.Canvas(legend, width=28, height=10, bg=self.colors.panel, highlightthickness=0)
        l2.pack(side="left")
        l2.create_line(2, 5, 26, 5, fill=self.colors.l2, width=3)

        ttk.Label(legend, text="L3", style="Panel.TLabel").pack(side="left", padx=(12, 6), pady=6)
        l3 = tk.Canvas(legend, width=28, height=10, bg=self.colors.panel, highlightthickness=0)
        l3.pack(side="left", padx=(0, 10))
        l3.create_line(2, 5, 26, 5, fill=self.colors.l3, width=3)

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
        self.topo_canvas.bind("<Configure>", lambda e: self._draw_topology())

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

        w = max(400, c.winfo_width())
        h = max(300, c.winfo_height())

        names = list(self._topo.devices.keys())
        n = len(names)

        cx, cy = w // 2, h // 2
        r = int(min(w, h) * 0.32)

        pos: Dict[str, Tuple[int, int]] = {}
        for i, name in enumerate(names):
            angle = (i / max(1, n)) * 2.0 * math.pi
            x = int(cx + r * 0.95 * math.cos(angle))
            y = int(cy + r * 0.95 * math.sin(angle))
            pos[name] = (x, y)

        # Links
        for link in self._topo.links:
            if link.a not in pos or link.b not in pos:
                continue
            ax, ay = pos[link.a]
            bx, by = pos[link.b]

            color = self.colors.l2 if link.kind.upper() == "L2" else self.colors.l3
            width = 3 if link.kind.upper() == "L2" else 2
            c.create_line(ax, ay, bx, by, fill=color, width=width)

            if self._static_flow_labels.get() and link.label:
                mx, my = (ax + bx) // 2, (ay + by) // 2
                c.create_text(mx, my - 10, text=link.label, fill=self.colors.muted, font=("Segoe UI", 9))

        # Nodes
        for name in names:
            x, y = pos[name]
            is_active = (name == self._active_device)

            node_w, node_h = 110, 56
            x0, y0 = x - node_w // 2, y - node_h // 2
            x1, y1 = x + node_w // 2, y + node_h // 2

            fill = "#1b2232" if not is_active else "#223050"
            outline = self.colors.border if not is_active else self.colors.accent2

            c.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=2)
            c.create_text(x, y - 6, text=name, fill=self.colors.text, font=("Segoe UI", 10, "bold"))

            if self._show_interface_labels.get():
                vendor = self._topo.devices[name].vendor
                c.create_text(x, y + 12, text=vendor, fill=self.colors.muted, font=("Segoe UI", 8))

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

        text_frame = ttk.Frame(body, style="Panel.TFrame")
        text_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.raw_text = tk.Text(
            text_frame,
            bg=self.colors.panel,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors.border,
            wrap="none",
            font=("Consolas", 10),
        )
        sb = ttk.Scrollbar(text_frame, orient="vertical", command=self.raw_text.yview)
        self.raw_text.configure(yscrollcommand=sb.set)
        self.raw_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
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
        tab_ssh = ttk.Frame(nb, style="Panel.TFrame")
        tab_export = ttk.Frame(nb, style="Panel.TFrame")
        nb.add(tab_general, text="General")
        nb.add(tab_ssh, text="SSH / CLI")
        nb.add(tab_export, text="Export")

        ttk.Label(tab_general, text="General", style="Header.TLabel").pack(anchor="w", padx=12, pady=(12, 8))

        frame_checks = ttk.Frame(tab_general, style="Panel.TFrame")
        frame_checks.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Checkbutton(frame_checks, text="Theme Dark Mode", command=lambda: None).pack(anchor="w", pady=4)
        ttk.Checkbutton(frame_checks, text="Auto-Detect Peer Links", command=lambda: None).pack(anchor="w", pady=4)
        ttk.Checkbutton(frame_checks, text="Auto-Detect Uplinks", command=lambda: None).pack(anchor="w", pady=4)

        ttk.Separator(tab_general, orient="horizontal").pack(fill="x", padx=12, pady=10)

        ttk.Label(tab_general, text="Topology Display", style="Header.TLabel").pack(anchor="w", padx=12, pady=(0, 8))

        display = ttk.Frame(tab_general, style="Panel.TFrame")
        display.pack(fill="x", padx=12, pady=(0, 12))

        ttk.Checkbutton(display, text="Show Interface Labels", variable=self._show_interface_labels, command=self._draw_topology).pack(anchor="w", pady=4)
        ttk.Checkbutton(display, text="Show VLAN IDs", variable=self._show_vlan_ids, command=self._refresh_active_detail).pack(anchor="w", pady=4)
        ttk.Checkbutton(display, text="Enable Static Flow Labels", variable=self._static_flow_labels, command=self._draw_topology).pack(anchor="w", pady=4)

        ttk.Label(tab_ssh, text="SSH Mode", style="Header.TLabel").pack(anchor="w", padx=12, pady=(12, 8))
        ttk.Label(tab_ssh, text="(Hook this into ssh/live_collect.py when you’re ready)", style="Panel.TLabel").pack(anchor="w", padx=12, pady=(0, 12))

        ttk.Label(tab_export, text="Export", style="Header.TLabel").pack(anchor="w", padx=12, pady=(12, 8))
        ttk.Label(tab_export, text="(Hook this into core/exporter.py for PNG/PDF export)", style="Panel.TLabel").pack(anchor="w", padx=12, pady=(0, 12))

        btns = ttk.Frame(win, style="TFrame")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btns, text="Save", style="Primary.TButton", command=win.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")

        win.grab_set()
        win.transient(self.winfo_toplevel())

    def _refresh_active_detail(self) -> None:
        if not self._active_device:
            return
        d = self._topo.devices.get(self._active_device)
        if not d:
            return
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", self._render_device_summary(d))
        self.detail_text.config(state="disabled")

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
        self._draw_topology()
        self._set_status(f"Loaded {len(self._topo.devices)} config(s)")

    def _clear_all(self) -> None:
        self._topo = TopologyData()
        self._active_device = None
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

    def _export_placeholder(self) -> None:
        messagebox.showinfo(
            "Export",
            "Export wiring is stubbed.\n\n"
            "Next step: wire this button to core/exporter.py "
            "to export the topology canvas to PNG/PDF.",
        )