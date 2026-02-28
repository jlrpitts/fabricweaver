"""
FabricWeaver - Desktop Entry Point

This file controls:
- UI rendering
- File selection
- Calling parser.orchestrator
- Printing structured device snapshot output

No parsing logic lives here.
No topology logic lives here.
"""

import tkinter as tk
from tkinter import filedialog
import json

from parser import orchestrator


class FabricWeaverApp:
    """
    Main Desktop Application Controller.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("FabricWeaver")
        self.root.geometry("1000x650")

        # Title Label
        self.title = tk.Label(
            root,
            text="FabricWeaver - Network Topology Engine",
            font=("Arial", 18)
        )
        self.title.pack(pady=20)

        # Upload Button
        self.upload_btn = tk.Button(
            root,
            text="Upload Config Files",
            command=self.load_files,
            width=30,
            height=2
        )
        self.upload_btn.pack(pady=10)

        # Output Window
        self.output = tk.Text(root, height=30, width=120)
        self.output.pack(pady=10)

    def load_files(self):
        """
        Triggered when Upload button is pressed.
        - Opens file selector
        - Sends each file to parser
        - Prints structured snapshot
        """

        files = filedialog.askopenfilenames(
            title="Select Configuration Files"
        )

        if not files:
            return

        self.output.delete("1.0", tk.END)

        for file in files:
            snapshot = orchestrator.parse_file(file)

            # Convert structured dictionary to formatted JSON
            formatted_output = json.dumps(snapshot, indent=2)

            self.output.insert(tk.END, formatted_output)
            self.output.insert(tk.END, "\n\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = FabricWeaverApp(root)
    root.mainloop()