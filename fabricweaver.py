# fabricweaver/fabricweaver.py
import tkinter as tk
from tkinter import messagebox

def main() -> None:
    root = tk.Tk()
    messagebox.showerror("PROOF", "If you see this, you ARE running fabricweaver/fabricweaver.py.")
    raise SystemExit("PROOF STOP")

if __name__ == "__main__":
    main()