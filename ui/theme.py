# fabricweaver/ui/theme.py
# Dark dashboard theme with rounded-style buttons

from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeColors:
    bg: str = "#0e0f12"          # deep background
    panel: str = "#181a1f"       # card background
    panel2: str = "#22252b"      # secondary card
    border: str = "#2c3038"      # soft border
    text: str = "#e5e7eb"        # light text
    muted: str = "#9ca3af"       # muted text

    accent: str = "#ff7a00"      # orange accent
    accent2: str = "#ff8f1a"     # hover accent

    good: str = "#16a34a"
    warn: str = "#d97706"
    bad: str = "#dc2626"

    l2: str = "#38bdf8"
    l3: str = "#facc15"


def apply_theme(root: tk.Tk | tk.Toplevel, colors: ThemeColors | None = None) -> ThemeColors:
    c = colors or ThemeColors()

    root.configure(bg=c.bg)
    style = ttk.Style(root)
    style.theme_use("clam")

    # GLOBAL
    style.configure(".", background=c.bg, foreground=c.text, font=("Segoe UI", 10))

    # PANELS
    style.configure("TFrame", background=c.bg)
    style.configure("Panel.TFrame", background=c.panel)

    # LABELS
    style.configure("TLabel", background=c.bg, foreground=c.text)
    style.configure("Panel.TLabel", background=c.panel, foreground=c.text)
    style.configure("Header.TLabel",
                    font=("Segoe UI", 12, "bold"),
                    background=c.panel,
                    foreground=c.text)

    # BUTTONS — rounded illusion via padding + flat + darker bg
    style.configure(
        "TButton",
        background=c.panel2,
        foreground=c.text,
        padding=(14, 8),
        relief="flat",
        borderwidth=0,
    )
    style.map(
        "TButton",
        background=[("active", c.panel)],
        foreground=[("active", c.text)],
    )

    # PRIMARY BUTTONS — bright accent + pill‑like padding
    style.configure(
        "Primary.TButton",
        background=c.accent,
        foreground="#ffffff",
        padding=(16, 9),   # more padding = more rounded look
        relief="flat",
        borderwidth=0,
    )
    style.map(
        "Primary.TButton",
        background=[("active", c.accent2)],
        foreground=[("active", "#ffffff")],
    )

    # TABS
    style.configure("TNotebook", background=c.bg, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=c.panel2,
        foreground=c.muted,
        padding=(16, 10),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", c.panel)],
        foreground=[("selected", c.text)],
    )

    # TREEVIEW
    style.configure(
        "Treeview",
        background=c.panel,
        fieldbackground=c.panel,
        foreground=c.text,
        rowheight=28,
        bordercolor=c.border,
        lightcolor=c.border,
        darkcolor=c.border,
    )
    style.configure(
        "Treeview.Heading",
        background=c.panel2,
        foreground=c.text,
        relief="flat",
    )

    # CHECKBOXES
    style.configure("TCheckbutton", background=c.bg, foreground=c.text)
    style.map("TCheckbutton", foreground=[("active", c.text)])

    return c


def apply_dark_theme(root: tk.Tk | tk.Toplevel, colors: ThemeColors | None = None) -> ThemeColors:
    return apply_theme(root, colors)
