"""Cancel Tcl timers before Tk deletes the Python commands they reference.

The root owns one additive Destroy binding for all its widgets. Only after
jobs registered by the destroyed widget are cancelled; timers on surviving
widgets and native Tcl scripts are left alone. No tkinter methods are patched.
"""
from __future__ import annotations
import tkinter as tk


def install_callback_cleanup(widget: tk.Misc) -> None:
    root = widget._root()
    if getattr(root, "_barkav_callback_cleanup", None):
        return

    def destroyed(event):
        owner = event.widget
        commands = set(getattr(owner, "_tclCommands", None) or ())
        if not commands:
            return
        try:
            jobs = root.tk.call("after", "info")
            for job in jobs:
                script, _kind = root.tk.call("after", "info", job)
                words = root.tk.splitlist(script)
                if words and words[0] in commands:
                    # Use the owner so after_cancel also removes its command
                    # from _tclCommands. Cancelling via root would leave a stale
                    # name which Widget.destroy would then delete a second time.
                    owner.after_cancel(job)
        except tk.TclError:
            # The interpreter can already be tearing down; no UI work remains.
            if root.tk.call("info", "commands", "after"):
                raise

    root._barkav_callback_cleanup = root.bind_all("<Destroy>", destroyed, add="+")
