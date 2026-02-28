import tkinter as tk
from tkinter import messagebox

def main():
    root = tk.Tk()
    root.title("FabricWeaver")
    root.geometry("1200x750")

    try:
        from ui.layout import FabricWeaverApp
    except Exception as e:
        messagebox.showerror("Startup Error", f"Failed to load UI:\n\n{e}")
        return

    app = FabricWeaverApp(root)
    app.pack(fill="both", expand=True)

    root.mainloop()

if __name__ == "__main__":
    main()