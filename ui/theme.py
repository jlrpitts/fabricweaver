# fabricweaver/ui/theme.py

import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeColors:
    bg: str = "#0f1116"
    panel: str = "#141822"
    panel2: str = "#111521"
    border: str = "#242a3a"
    text: str = "#e6e6e6"
    muted: str = "#a8b0c0"
    accent: str = "#2f6fed"
    accent2: str = "#3a86ff"
    good: str = "#2dd4bf"
    warn: str = "#f59e0b"
    bad: str = "#ef4444"

    l2: str = "#2dd4bf"
    l3: str = "#f59e0b"


def apply_dark_theme(root: tk.Tk | tk.Toplevel, colors: ThemeColors | None = None) -> ThemeColors:
    c = colors or ThemeColors()

    root.configure(bg=c.bg)

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=c.bg, foreground=c.text)

    style.configure("TFrame", background=c.bg)
    style.configure("Panel.TFrame", background=c.panel)
    style.configure("Panel2.TFrame", background=c.panel2)

    style.configure("TLabel", background=c.bg, foreground=c.text)
    style.configure("Panel.TLabel", background=c.panel, foreground=c.text)
    style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), background=c.panel, foreground=c.text)

    style.configure(
        "TButton",
        background=c.panel,
        foreground=c.text,
        padding=(10, 6),
        relief="flat"
    )

    style.configure(
        "Primary.TButton",
        background=c.accent,
        foreground="#ffffff",
        padding=(12, 7)
    )

    style.configure("TNotebook", background=c.bg)
    style.configure(
        "TNotebook.Tab",
        background=c.panel,
        foreground=c.muted,
        padding=(14, 8)
    )

    style.map(
        "TNotebook.Tab",
        background=[("selected", c.panel2)],
        foreground=[("selected", c.text)]
    )

    style.configure(
        "Treeview",
        background=c.panel,
        fieldbackground=c.panel,
        foreground=c.text,
        rowheight=26
    )

    style.configure(
        "Treeview.Heading",
        background=c.panel2,
        foreground=c.text
    )

    return c