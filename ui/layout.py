# fabricweaver/ui/layout.py
# Tkinter layout (Devices / Topology / Raw Data + Options)
from __future__ import annotations

import os
import re
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
# Light parser fallback (works without your core/parser modules)
# -----------------------------

HOST_RE = re.compile(r"^\s*hostname\s+(\S+)", re.IGNORECASE | re.MULTILINE)
VLAN_RE = re.compile(r"^\s*vlan\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
VLAN_NAME_RE = re.compile(r"^\s*name\s+(.+)$", re.IGNORECASE | re.MULTILINE)
INT_RE = re.compile(r"^\s*interface\s+(\S+)", re.IGNORECASE | re.MULTILINE)
IP_RE = re.compile(r"^\s*ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", re.IGNORECASE | re.MULTILINE)

NXOS_VENDOR_HINT = re.compile(r"nxos|nexus|feature\s+vpc|vpc\s+domain", re.IGNORECASE)
IOS_VENDOR_HINT = re.compile(r"catalyst|ios|spanning-tree|switchport", re.IGNORECASE)
ARISTA_HINT = re.compile(r"arista|eos|transceiver\s+qsfp|daemon\s+terminattr", re.IGNORECASE)
DELL_OS10_HINT = re.compile(r"os10|dell\s+emc|interface\s+vlan|vlt\s+domain", re.IGNORECASE)


def _guess_vendor(text: str) -> str:
    if DELL_OS10_HINT.search(text):
        return "Dell OS10"
    if ARISTA_HINT.search(text):
        return "Arista EOS"
    if NXOS_VENDOR_HINT.search(text):
        return "Cisco Nexus (NX-OS)"
    if IOS_VENDOR_HINT.search(text):
        return "Cisco Catalyst (IOS/IOS-XE)"
    return "AUTODETECT"


def _parse_vlans(text: str) -> List[VlanInfo]:
    vlans: List[VlanInfo] = []
    for m in VLAN_RE.finditer(text):
        vid = m.group(1)
        # Try to find "name" within the vlan block by looking ahead a bit
        start = m.end()
        window = text[start:start + 250]
        nm = VLAN_NAME_RE.search(window)
        name = nm.group(1).strip() if nm else "—"
        vlans.append(VlanInfo(vid=vid, name=name))
    # de-dupe by VLAN ID
    seen = set()
    out: List[VlanInfo] = []
    for v in vlans:
        if v.vid not in seen:
            seen.add(v.vid)
            out.append(v)
    return out[:80]


def _parse_l3_ints(text: str) -> List[InterfaceIP]:
    # Naive: find interface blocks, then ip address lines after each interface header
    results: List[InterfaceIP] = []
    for im in INT_RE.finditer(text):
        ifname = im.group(1)
        start = im.end()
        window = text[start:start + 400]
        ipm = IP_RE.search(window)
        if ipm:
            ip = f"{ipm.group(1)}/{_mask_to_prefix(ipm.group(2))}"
            results.append(InterfaceIP(name=ifname, ip=ip))
    # keep only first N for UI
    return results[:50]


def _mask_to_prefix(mask: str) -> int:
    parts = [int(p) for p in mask.split(".")]
    bits = "".join(f"{p:08b}" for p in parts)
    return bits.count("1")


def parse_configs_fallback(paths: List[str]) -> TopologyData:
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
            mgmt_ip="STATIC_FILE",
            raw_text=text,
        )
        d.vlans = _parse_vlans(text)
        d.l3_interfaces = _parse_l3_ints(text)

        topo.devices[hostname] = d

    # Minimal auto-links (placeholder) so topology view isn’t empty:
    names = list(topo.devices.keys())
    for i in range(len(names) - 1):
        topo.links.append(Link(a=names[i], b=names[i + 1], label="Auto", kind="L2"))
    return topo


def parse_configs(paths: List[str]) -> TopologyData:
    """
    Tries your real parser if present; otherwise uses the fallback parser above.
    Expected (optional) integration:
      - parser.orchestrator.parse_configs(paths) -> TopologyData-like object
    """
    try:
        from parser.orchestrator import parse_configs as real_parse  # type: ignore
        parsed = real_parse(paths)
        # If your orchestrator returns your own models, adapt here.
        # For now, assume it returns something compatible or already TopologyData.
        if isinstance(parsed, TopologyData):
            return parsed
        # Best-effort adaptation:
        topo = TopologyData()
        # devices
        for dev in getattr(parsed, "devices", []):
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
            # VLANs
            for v in getattr(dev, "vlans", []) or []:
                topo.devices[hostname] = topo.devices.get(hostname, d)
                topo.devices[hostname].vlans.append(VlanInfo(str(getattr(v, "vid", "")), str(getattr(v, "name", ""))))
            # L3 interfaces
            for i in getattr(dev, "l3_interfaces", []) or []:
                topo.devices[hostname] = topo.devices.get(hostname, d)
                topo.devices[hostname].l3_interfaces.append(
                    InterfaceIP(str(getattr(i, "name", "")), str(getattr(i, "ip", "")))
                )
            topo.devices[hostname] = d

        # links
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
        self._show_vlan_ids = tk.BooleanVar(value=False)
        self._static_flow_labels = tk.BooleanVar(value=True)

        self._build_shell()
        self._build_tabs()
        self._build_statusbar()

        self._set_status("Ready")

    # ---- Shell / Tabs ----

    def _build_shell(self) -> None:
        self.configure(style="TFrame")
        self.pack(fill="both", expand=True)

        # Top header strip
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

        # Top controls row
        top = ttk.Frame(root, style="TFrame")
        top.pack(fill="x", pady=(0, 10))

        ttk.Button(top, text="Load Configs", style="Primary.TButton", command=self._load_configs).pack(side="left")
        ttk.Button(top, text="Export", command=self._export_placeholder).pack(side="left", padx=8)
        ttk.Button(top, text="Clear", command=self._clear_all).pack(side="left", padx=8)

        # Main split: left list / right detail
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
            width=22,
            height=22,
        )
        self.device_list.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.device_list.bind("<<ListboxSelect>>", self._on_device_select)

        right = ttk.Frame(body, style="Panel.TFrame")
        right.pack(side="left", fill="both", expand=True)

        self.detail_title = ttk.Label(right, text="FABRICWEAVER — SUMMARY VIEW (UI v2)", style="Header.TLabel")
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
        lines.append(f"Model    : {d.model}")
        lines.append(f"OS Ver   : {d.os_ver}")
        lines.append(f"vPC Role : {d.vpc_role}")
        lines.append(f"MLAG     : {d.mlag}")
        lines.append("")
        lines.append("L2: VLANs")
        if d.vlans:
            for v in d.vlans[:40]:
                if self._show_vlan_ids.get():
                    lines.append(f"VLAN {v.vid:<5}  name: {v.name}")
                else:
                    lines.append(f"VLAN {v.vid:<5}  name: {v.name}")
        else:
            lines.append("—")

        lines.append("")
        lines.append("L3: Interfaces (with IP)")
        if d.l3_interfaces:
            for i in d.l3_interfaces[:40]:
                lines.append(f"{i.name:<14} {i.ip}")
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

        # Sync raw tab view
        self._render_raw(d)

        # Refresh topology highlights
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

        # Simple ring layout (clean + predictable)
        cx, cy = w // 2, h // 2
        r = int(min(w, h) * 0.32)

        pos: Dict[str, Tuple[int, int]] = {}
        for i, name in enumerate(names):
            angle = (i / max(1, n)) * 6.283185307179586
            x = int(cx + r * (0.95 * (tk.math.cos(angle) if hasattr(tk, "math") else __import__("math").cos(angle))))
            y = int(cy + r * (0.95 * (tk.math.sin(angle) if hasattr(tk, "math") else __import__("math").sin(angle))))
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

            node_w, node_h = 92, 54
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
        tab_ssh = ttk.Frame(nb, style="Panel.TFrame")
        tab_export = ttk.Frame(nb, style="Panel.TFrame")
        nb.add(tab_general, text="General")
        nb.add(tab_ssh, text="SSH / CLI")
        nb.add(tab_export, text="Export")

        # General
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

        # SSH tab placeholder
        ttk.Label(tab_ssh, text="SSH Mode", style="Header.TLabel").pack(anchor="w", padx=12, pady=(12, 8))
        ttk.Label(tab_ssh, text="(Hook this into ssh/live_collect.py when you’re ready)", style="Panel.TLabel").pack(
            anchor="w", padx=12, pady=(0, 12)
        )

        # Export tab placeholder
        ttk.Label(tab_export, text="Export", style="Header.TLabel").pack(anchor="w", padx=12, pady=(12, 8))
        ttk.Label(tab_export, text="(Hook this into core/exporter.py for PNG/PDF export)", style="Panel.TLabel").pack(
            anchor="w", padx=12, pady=(0, 12)
        )

        # Buttons
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
