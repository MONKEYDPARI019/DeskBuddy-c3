"""`deskbuddy ui`: a small Tkinter installer window with a live serial monitor.

Threading model: the Tk main loop owns every widget. Flashing runs on a worker thread and the
serial monitor on its own thread; both talk to the window only through `self.events` (a queue
drained by `root.after`). The monitor thread receives requests (send/pause/resume) through its
own queue, so the serial port is only ever touched by one thread at a time.
"""

from __future__ import annotations

import contextlib
import functools
import queue
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Any, Callable, Optional

from deskbuddy import __version__, cmd_history, flasher, github, installer, monitor, paths, ports
from deskbuddy.errors import DeskBuddyError

POLL_MS = 80
POLL_BUDGET_S = 0.05  # at most 50 ms of each 80 ms tick goes to events, so the window never freezes
MAX_LINES = 5000
MAX_DRAWN_PER_POLL = 300  # newest line groups drawn per tick; anything older is counted, not drawn
EMPTY_CHIP = "invalid header: 0xffffffff"  # what an erased ESP32-C3 prints, over and over
# Kawaii pastel look: the same colours as the phone app (app/.../ui/Theme.kt, Figma "Kawaii / Light").
THEME = {
    "bg": "#fff5f8",  # window background (soft pink)
    "surface": "#ffffff",  # the two white cards
    "surface2": "#ffe9f1",  # fields, soft buttons, progress track
    "line": "#f4d7e3",  # outlines
    "ink": "#3a2840",  # text
    "sub": "#8a7590",  # secondary text
    "accent": "#ff8fb3",  # INSTALL, progress, selected options
    "accent_hover": "#ff7aa6",
    "accent_down": "#f0679a",
    "soft_hover": "#ffdbe8",
    "berry": "#c2185b",  # Erase chip text, warnings
    "mint": "#2e9e6b",  # monitor "on"
    "oled": "#241c2c",  # serial monitor background (Mochi's screen)
    "oled_text": "#f6eaf3",
    "oled_dim": "#a895b0",
}
# serial monitor line colours (monitor.line_colour), readable on the dark monitor background
COLOURS = {"red": "#ff7b9c", "blue": "#8ec5ff", "green": "#86e3b4", "yellow": "#ffd873"}


@dataclass
class Event:
    kind: str  # line | status | progress | hint | monitor | done | erased | error | releases | ports
    value: Any = None


class MonitorThread(threading.Thread):
    """Runs a ReconnectingMonitor; accepts requests from the GUI thread."""

    def __init__(self, events: queue.Queue[Event]) -> None:
        super().__init__(daemon=True)
        self.events = events
        self.requests: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.port: Optional[str] = None
        self.paused = threading.Event()
        self._halt = threading.Event()
        self.mon = monitor.ReconnectingMonitor(
            resolve_port=self._resolve,
            on_line=lambda line: events.put(Event("line", line)),
            on_status=lambda s: events.put(Event("monitor", s)),
        )

    def _resolve(self) -> Optional[str]:
        names = [p.device for p in ports.board_candidates(ports.list_ports())]
        if self.port in names:
            return self.port
        return names[0] if names else None

    def request(self, kind: str, value: Any = None) -> None:
        self.requests.put((kind, value))

    def run(self) -> None:
        try:
            self._loop()
        except Exception as exc:  # report instead of dying silently
            self.events.put(Event("monitor", f"monitor stopped: {exc}"))
        finally:
            self.paused.set()  # never leave an installer waiting for the port
            self.mon.close()

    def _loop(self) -> None:
        last_error = ""
        while not self._halt.is_set():
            while not self.requests.empty():
                kind, value = self.requests.get_nowait()
                if kind == "send":
                    self.mon.send(value)
                elif kind == "pause":
                    self.mon.pause()
                    self.paused.set()
                    self.events.put(Event("monitor", "paused while flashing"))
                elif kind == "resume":
                    self.port = value or self.port
                    self.paused.clear()
                    self.mon.resume()
                elif kind == "port":
                    self.port = value
            try:
                self.mon.step()
                last_error = ""
            except DeskBuddyError as exc:
                if exc.message != last_error:  # say it once, then keep retrying quietly
                    self.events.put(Event("monitor", exc.message))
                    last_error = exc.message
                self.mon.pause()
                self._halt.wait(2.0)
                self.mon.resume()

    def stop(self) -> None:
        self._halt.set()


def _pick_font(root: tk.Misc, *families: str) -> str:
    """First of `families` installed on this computer (the last one is a Tk built-in fallback)."""
    available = set(tkfont.families(root))
    return next((f for f in families if f in available), families[-1])


def apply_theme(root: tk.Tk) -> dict[str, str]:
    """Colour every ttk widget in the kawaii palette. Returns the fonts chosen ("ui", "mono").

    Windows' own ttk theme ("vista") ignores colours, so this uses Tk's "clam" theme, which takes them.
    """
    t = THEME
    ui_font = _pick_font(root, "Segoe UI", "Nunito", "DejaVu Sans", "Helvetica")
    mono_font = _pick_font(root, "Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Courier")
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        with contextlib.suppress(tk.TclError):
            tkfont.nametofont(name).configure(family=ui_font, size=10)
    root.configure(background=t["bg"])

    style = ttk.Style(root)
    style.theme_use("clam")

    def flat(colour: str) -> dict[str, str]:
        # clam draws 3D edges in lightcolor / darkcolor: same colour as the fill = flat
        return {"background": colour, "lightcolor": colour, "darkcolor": colour}

    def flat_map(*states: tuple[str, str]) -> dict[str, Any]:
        pairs = list(states)
        return {"background": pairs, "lightcolor": pairs, "darkcolor": pairs, "bordercolor": pairs}

    style.configure(
        ".",
        **flat(t["surface"]),
        foreground=t["ink"],
        bordercolor=t["line"],
        troughcolor=t["surface2"],
        focuscolor=t["accent"],
        selectbackground=t["accent"],
        selectforeground=t["ink"],
        font=(ui_font, 10),
    )
    style.configure("TFrame", background=t["surface"])
    style.configure("Card.TFrame", background=t["surface"], bordercolor=t["line"], relief="solid", borderwidth=1)
    style.configure("TLabel", background=t["surface"], foreground=t["ink"])
    style.configure("Field.TLabel", foreground=t["sub"], font=(ui_font, 10, "bold"))
    style.configure("Prompt.TLabel", foreground=t["accent_down"], font=(mono_font, 11, "bold"))

    # buttons: soft pink by default, INSTALL / Send in the accent pink, Erase chip outlined
    style.configure(
        "TButton",
        **flat(t["surface2"]),
        bordercolor=t["surface2"],
        foreground=t["ink"],
        focuscolor=t["surface2"],
        padding=(12, 5),
        relief="flat",
        font=(ui_font, 10, "bold"),
    )
    style.map(
        "TButton",
        **flat_map(("disabled", t["surface"]), ("pressed", t["line"]), ("active", t["soft_hover"])),
        foreground=[("disabled", t["sub"])],
    )
    style.configure("Accent.TButton", **flat(t["accent"]), bordercolor=t["accent"], focuscolor=t["accent"])
    style.map(
        "Accent.TButton",
        **flat_map(("disabled", t["line"]), ("pressed", t["accent_down"]), ("active", t["accent_hover"])),
        foreground=[("disabled", t["sub"])],
    )
    style.configure(
        "Install.TButton",
        **flat(t["accent"]),
        bordercolor=t["accent"],
        focuscolor=t["accent"],
        font=(ui_font, 13, "bold"),
    )
    style.map(
        "Install.TButton",
        **flat_map(("disabled", t["line"]), ("pressed", t["accent_down"]), ("active", t["accent_hover"])),
        foreground=[("disabled", t["sub"])],
    )
    style.configure(
        "Erase.TButton",
        **flat(t["surface"]),
        bordercolor=t["accent"],
        foreground=t["berry"],
        focuscolor=t["surface"],
        relief="solid",
        borderwidth=2,
    )
    style.map(
        "Erase.TButton",
        background=[("disabled", t["surface"]), ("pressed", t["line"]), ("active", t["surface2"])],
        lightcolor=[("pressed", t["line"]), ("active", t["surface2"])],
        darkcolor=[("pressed", t["line"]), ("active", t["surface2"])],
        bordercolor=[("disabled", t["line"])],
        foreground=[("disabled", t["sub"])],
    )

    # fields
    style.configure(
        "TCombobox",
        **flat(t["surface2"]),
        fieldbackground=t["surface2"],
        bordercolor=t["line"],
        foreground=t["ink"],
        arrowcolor=t["ink"],
        arrowsize=14,
        padding=(8, 5),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", t["surface2"])],
        background=[("active", t["soft_hover"]), ("readonly", t["surface2"])],
        bordercolor=[("focus", t["accent"])],
        foreground=[("readonly", t["ink"])],
        selectbackground=[("readonly", t["surface2"])],
        selectforeground=[("readonly", t["ink"])],
    )
    for option, value in (
        ("background", t["surface"]),
        ("foreground", t["ink"]),
        ("selectBackground", t["accent"]),
        ("selectForeground", t["ink"]),
        ("font", f"{{{ui_font}}} 10"),
    ):
        root.option_add(f"*TCombobox*Listbox.{option}", value)  # the drop-down list
    style.configure(
        "TEntry",
        **flat(t["surface2"]),
        fieldbackground=t["surface2"],
        bordercolor=t["line"],
        foreground=t["ink"],
        insertcolor=t["ink"],
        padding=(8, 4),
    )
    style.map("TEntry", bordercolor=[("focus", t["accent"])])

    # options, progress, monitor frame, scrollbar
    for kind in ("TRadiobutton", "TCheckbutton"):
        style.configure(
            kind,
            background=t["surface"],
            foreground=t["ink"],
            indicatorbackground=t["surface"],
            indicatorforeground=t["surface"],
            upperbordercolor=t["sub"],
            lowerbordercolor=t["sub"],
            focuscolor=t["surface"],
            indicatormargin=(0, 0, 6, 0),
        )
        style.map(
            kind,
            background=[("active", t["surface"])],
            indicatorbackground=[("selected", t["accent"]), ("pressed", t["surface2"])],
            upperbordercolor=[("selected", t["accent_down"])],
            lowerbordercolor=[("selected", t["accent_down"])],
        )
    style.configure(
        "Horizontal.TProgressbar",
        **flat(t["accent"]),
        troughcolor=t["surface2"],
        bordercolor=t["surface2"],
        thickness=12,
    )
    style.configure("Title.TLabel", foreground=t["ink"], font=(ui_font, 11, "bold"))
    style.configure("Small.TButton", padding=(8, 3), width=-4, font=(ui_font, 9, "bold"))
    style.configure(
        "Vertical.TScrollbar",
        **flat(t["line"]),
        troughcolor=t["oled"],
        bordercolor=t["oled"],
        arrowcolor=t["ink"],
        gripcount=0,
    )
    style.map("Vertical.TScrollbar", background=[("active", t["accent"])])
    return {"ui": ui_font, "mono": mono_font}


class InstallerWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.fonts = apply_theme(root)
        self.history = cmd_history.CommandHistory(paths.command_history_file())
        self.events: queue.Queue[Event] = queue.Queue()
        self.releases: list[github.Release] = []
        self.board_ports: list[ports.BoardPort] = []
        self.custom_file: Optional[Path] = None
        self.busy = False
        self._ports_generation = 0
        root.title(f"DeskBuddy Installer {__version__}")
        root.minsize(640, 520)
        self._build()
        self.monitor = MonitorThread(self.events)
        self.monitor.start()
        self.refresh_ports()
        threading.Thread(target=self._load_releases, daemon=True).start()
        root.after(POLL_MS, self._poll)
        root.protocol("WM_DELETE_WINDOW", self._close)

    # --- layout -------------------------------------------------------------------------

    def _build(self) -> None:
        pad: dict[str, Any] = {"padx": 6, "pady": 3}
        t = THEME
        top = ttk.Frame(self.root, padding=10, style="Card.TFrame")
        top.pack(fill="x", padx=10, pady=(10, 8))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Board:", style="Field.TLabel").grid(row=0, column=0, sticky="w", **pad)
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(top, textvariable=self.port_var, state="readonly")
        self.port_box.grid(row=0, column=1, sticky="ew", **pad)
        self.port_box.bind("<<ComboboxSelected>>", lambda e: self.monitor.request("port", self._selected_port()))
        ttk.Button(top, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, sticky="ew", **pad)

        ttk.Label(top, text="Firmware:", style="Field.TLabel").grid(row=1, column=0, sticky="w", **pad)
        self.fw_var = tk.StringVar(value="loading releases...")
        self.fw_box = ttk.Combobox(top, textvariable=self.fw_var, state="readonly")
        self.fw_box.grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(top, text="Choose .bin...", command=self.choose_file).grid(row=1, column=2, sticky="ew", **pad)

        ttk.Label(top, text="Build:", style="Field.TLabel").grid(row=2, column=0, sticky="w", **pad)
        opts = ttk.Frame(top)
        opts.grid(row=2, column=1, columnspan=2, sticky="w", **pad)
        self.env_var = tk.StringVar(value="usb")
        ttk.Radiobutton(opts, text="USB", value="usb", variable=self.env_var).pack(side="left")
        ttk.Radiobutton(opts, text="Battery", value="battery", variable=self.env_var).pack(side="left", padx=8)
        self.erase_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Erase settings", variable=self.erase_var).pack(side="left", padx=16)

        self.install_btn = ttk.Button(top, text="INSTALL", command=self.install, style="Install.TButton")
        self.install_btn.grid(row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=8, ipady=6)
        self.erase_btn = ttk.Button(top, text="Erase chip", command=self.erase_chip, style="Erase.TButton")
        self.erase_btn.grid(row=3, column=2, sticky="ew", padx=6, pady=8, ipady=6)
        self.progress = ttk.Progressbar(top, maximum=100)
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)
        self.status_var = tk.StringVar(value="Ready.")
        # own full-width row: a long status must not widen the button column and squeeze the buttons
        ttk.Label(top, textvariable=self.status_var).grid(row=5, column=0, columnspan=3, sticky="w", **pad)
        self.hint_var = tk.StringVar()
        self.hint_label = tk.Label(
            top, textvariable=self.hint_var, fg="white", bg=t["berry"], font=(self.fonts["ui"], 11, "bold"), pady=4
        )

        mon = ttk.Frame(self.root, padding=10, style="Card.TFrame")
        mon.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        head = ttk.Frame(mon)
        head.pack(fill="x", pady=(0, 6))
        ttk.Label(head, text="Serial monitor", style="Title.TLabel").pack(side="left")
        self.mon_state = tk.StringVar(value="● off")
        self.mon_label = tk.Label(
            head, textvariable=self.mon_state, fg=t["sub"], bg=t["surface"], font=(self.fonts["ui"], 10, "bold")
        )
        self.mon_label.pack(side="right")
        body = ttk.Frame(mon)
        body.pack(fill="both", expand=True)
        self.text = tk.Text(
            body,
            height=14,
            wrap="none",
            state="disabled",
            font=(self.fonts["mono"], 9),
            background=t["oled"],
            foreground=t["oled_text"],
            insertbackground=t["oled_text"],
            selectbackground=t["accent"],
            selectforeground=t["ink"],
            borderwidth=0,
            highlightthickness=0,
            padx=8,
            pady=6,
        )
        scroll = ttk.Scrollbar(body, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for name, colour in COLOURS.items():
            self.text.tag_configure(name, foreground=colour)
        self.text.tag_configure("sent", foreground=t["oled_dim"])

        entry_row = ttk.Frame(mon)
        entry_row.pack(fill="x", pady=6)
        ttk.Label(entry_row, text=">", style="Prompt.TLabel").pack(side="left")
        self.entry = ttk.Entry(entry_row)
        self.entry.pack(side="left", fill="x", expand=True, padx=4)
        self.entry.bind("<Return>", lambda e: self.send_entry())
        self.entry.bind("<Up>", self._history_older)  # earlier commands, like PowerShell
        self.entry.bind("<Down>", self._history_newer)
        self.entry.bind("<Escape>", self._clear_entry)
        ttk.Button(entry_row, text="Send", command=self.send_entry, style="Accent.TButton").pack(side="left")

        buttons = ttk.Frame(mon)
        buttons.pack(fill="x")
        for label, command in (
            ("status", "status"),
            ("help", "help"),
            ("Bluetooth", "link ble"),
            ("WiFi", "link wifi"),
            ("Change WiFi", "wifi setup"),
            ("Reboot", "reboot"),
        ):
            ttk.Button(buttons, text=label, command=functools.partial(self.send, command), style="Small.TButton").pack(
                side="left", padx=2
            )
        ttk.Button(buttons, text="Clear", command=self.clear, style="Small.TButton").pack(side="left", padx=2)
        ttk.Button(buttons, text="Save log", command=self.save_log, style="Small.TButton").pack(side="left", padx=2)

    # --- actions ----------------------------------------------------------------------

    def _selected_port(self) -> Optional[str]:
        index = self.port_box.current()
        return self.board_ports[index].device if 0 <= index < len(self.board_ports) else None

    def refresh_ports(self) -> None:
        # Listing ports can take a second on Windows: never on the Tk thread
        self._ports_generation += 1
        threading.Thread(target=self._list_ports, args=(self._ports_generation,), daemon=True).start()

    def _list_ports(self, generation: int) -> None:
        try:
            found = ports.list_ports()
        except Exception as exc:  # a broken driver must not kill the window
            self.events.put(Event("monitor", f"could not list the ports: {exc}"))
            found = []
        self.events.put(Event("ports", (generation, found)))

    def _show_ports(self, value: tuple[int, list[ports.BoardPort]]) -> None:
        generation, found = value
        if generation != self._ports_generation:
            return  # Refresh was pressed again: a newer list is on its way
        previous = self._selected_port()
        boards = ports.board_candidates(found)
        self.board_ports = boards or found
        labels = [
            f"{p.device} - {p.label or p.description}" + (" (found)" if p in boards else "") for p in self.board_ports
        ]
        self.port_box["values"] = labels or ["no board found - plug it in and press Refresh"]
        devices = [p.device for p in self.board_ports]
        self.port_box.current(devices.index(previous) if previous in devices else 0)
        self.monitor_port_changed()

    def monitor_port_changed(self) -> None:
        if hasattr(self, "monitor"):
            self.monitor.request("port", self._selected_port())

    def _load_releases(self) -> None:
        try:
            self.events.put(Event("releases", github.GitHubClient().list_releases()))
        except DeskBuddyError as exc:
            self.events.put(Event("releases", exc))

    def _show_releases(self, value: Any) -> None:
        if isinstance(value, DeskBuddyError):
            self.fw_box["values"] = []
            self.fw_var.set(f"(offline: {value.message}) - use Choose .bin...")
            return
        self.releases = value
        labels = [
            f"{r.tag}{' (latest)' if i == 0 else ''}{' pre-release' if r.prerelease else ''}"
            for i, r in enumerate(self.releases)
        ]
        self.fw_box["values"] = labels or ["no releases yet - use Choose .bin..."]
        self.fw_box.current(0)

    def choose_file(self) -> None:
        name = filedialog.askopenfilename(
            title="Choose a merged DeskBuddy image", filetypes=[("Firmware image", "*.bin"), ("All files", "*.*")]
        )
        if name:
            self.custom_file = Path(name)
            values = [*self.fw_box["values"], f"file: {self.custom_file.name}"]
            self.fw_box["values"] = values
            self.fw_box.current(len(values) - 1)

    def _options(self) -> installer.InstallOptions:
        selected = self.fw_var.get()
        opts = installer.InstallOptions(env=self.env_var.get(), port=self._selected_port(), erase=self.erase_var.get())
        if selected.startswith("file: ") and self.custom_file:
            opts.file = self.custom_file
        elif self.releases and 0 <= self.fw_box.current() < len(self.releases):
            opts.version = self.releases[self.fw_box.current()].tag
        else:
            raise DeskBuddyError("No firmware selected", "Pick a release, or use Choose .bin... for a local file.")
        return opts

    def install(self) -> None:
        if self.busy:
            return
        try:
            opts = self._options()
        except DeskBuddyError as exc:
            messagebox.showerror("DeskBuddy", f"{exc.message}\n\n{exc.hint}")
            return
        if opts.erase and not messagebox.askyesno("DeskBuddy", "Erase all saved settings (WiFi, link mode, ...)?"):
            return
        self._set_busy(True)
        self.progress["value"] = 0
        self.monitor.request("pause")
        threading.Thread(target=self._install_worker, args=(opts,), daemon=True).start()

    def erase_chip(self) -> None:
        if self.busy:
            return
        port = self._selected_port()
        if port is None or port not in {p.device for p in ports.board_candidates(self.board_ports)}:
            # never erase a serial device that doesn't look like an ESP32
            messagebox.showerror("DeskBuddy", "No DeskBuddy board found.\n\nPlug it in, then press Refresh.")
            return
        question = (
            f"Erase EVERYTHING on {port}?\n\n"
            "This removes the firmware, the settings and the saved WiFi. "
            "The screen stays dark until you press INSTALL again."
        )
        if not messagebox.askyesno("DeskBuddy", question, icon="warning"):
            return
        self._set_busy(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start(15)
        self.monitor.request("pause")
        threading.Thread(target=self._erase_worker, args=(port,), daemon=True).start()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        for button in (self.install_btn, self.erase_btn):
            button.state(["disabled"] if busy else ["!disabled"])
        self.hint_label.grid_forget()

    def _callbacks(self) -> flasher.FlashCallbacks:
        return flasher.FlashCallbacks(
            progress=lambda p: self.events.put(Event("progress", p)),
            status=lambda s: self.events.put(Event("status", s)),
            boot_hint=lambda h: self.events.put(Event("hint", h)),
            output=lambda line: None,
        )

    def _install_worker(self, opts: installer.InstallOptions) -> None:
        self.monitor.paused.wait(5.0)  # the port must be free before esptool opens it
        self._run_job("done", lambda: installer.install(opts, callbacks=self._callbacks()))

    def _erase_worker(self, port: str) -> None:
        self.monitor.paused.wait(5.0)  # the port must be free before esptool opens it
        self._run_job("erased", lambda: installer.erase(port, callbacks=self._callbacks()))

    def _run_job(self, kind: str, job: Callable[[], Any]) -> None:
        """Run a flashing job on the worker thread and report its result through the event queue."""
        try:
            self.events.put(Event(kind, job()))
        except DeskBuddyError as exc:
            self.events.put(Event("error", exc))
        except Exception as exc:  # keep the window alive whatever happens
            self.events.put(
                Event("error", DeskBuddyError(f"Unexpected error: {exc}", "Try the command line with --debug."))
            )

    def send(self, text: str) -> None:
        self._append(f"> {text}", "sent")
        self.monitor.request("send", text)

    def send_entry(self) -> None:
        text = self.entry.get().strip()
        if text:
            self.send(text)
            self.history.add(text)
            self.entry.delete(0, "end")

    def _set_entry(self, text: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.icursor("end")

    def _history_older(self, _event: Any = None) -> str:
        text = self.history.older(self.entry.get())
        if text is not None:
            self._set_entry(text)
        return "break"

    def _history_newer(self, _event: Any = None) -> str:
        text = self.history.newer()
        if text is not None:
            self._set_entry(text)
        return "break"

    def _clear_entry(self, _event: Any = None) -> str:
        self.entry.delete(0, "end")
        self.history.reset()
        return "break"

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def save_log(self) -> None:
        name = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if name:
            Path(name).write_text(self.text.get("1.0", "end-1c") + "\n", encoding="utf-8")

    # --- event pump ---------------------------------------------------------------------

    def _append(self, line: str, tag: Optional[str] = None) -> None:
        self.text.configure(state="normal")
        chosen = tag or monitor.line_colour(line)
        self.text.insert("end", line + "\n", (chosen,) if chosen else ())
        self._trim_and_scroll()
        self.text.configure(state="disabled")

    def _trim_and_scroll(self) -> None:
        total = int(self.text.index("end-1c").split(".")[0])
        if total > MAX_LINES:
            self.text.delete("1.0", f"{total - MAX_LINES + 500}.0")
        self.text.see("end")

    def _show_lines(self, lines: list[str]) -> None:
        """Draw a batch of monitor lines at once: repeats collapsed, a flood reduced to its newest part."""
        if not lines:
            return
        groups = monitor.collapse_repeats(lines)
        dropped = groups[:-MAX_DRAWN_PER_POLL]
        groups = groups[-MAX_DRAWN_PER_POLL:]
        if not self.busy and any(text == EMPTY_CHIP for text, _ in groups):
            self.status_var.set("Board is empty: click INSTALL.")
        self.text.configure(state="normal")
        skipped = sum(count for _, count in dropped)
        if skipped:
            self.text.insert("end", f"[... {skipped} lines skipped: the board is printing very fast ...]\n", ("sent",))
        for text, count in groups:
            shown = f"{text}   [x{count}]" if count > 1 else text
            chosen = monitor.line_colour(text)
            self.text.insert("end", shown + "\n", (chosen,) if chosen else ())
        self._trim_and_scroll()
        self.text.configure(state="disabled")

    def _poll(self) -> None:
        """Drain the event queue for at most POLL_BUDGET_S, drawing monitor lines in one batch.

        A board that prints thousands of lines a second (an erased chip) must never keep this loop
        busy for good: the window would stop responding.
        """
        deadline = time.monotonic() + POLL_BUDGET_S
        lines: list[str] = []
        try:
            while time.monotonic() < deadline:
                ev = self.events.get_nowait()
                if ev.kind == "line":
                    lines.append(ev.value)
                    continue
                self._show_lines(lines)  # keep the order of lines and status messages
                lines = []
                self._handle(ev)
        except queue.Empty:
            pass
        self._show_lines(lines)
        self.root.after(POLL_MS, self._poll)

    def _handle(self, ev: Event) -> None:
        if ev.kind == "line":
            self._append(ev.value)
        elif ev.kind == "monitor":
            on = str(ev.value).startswith("connected")
            self.mon_state.set(f"● {'on' if on else 'off'}")
            self.mon_label.configure(fg=THEME["mint"] if on else THEME["sub"])
            self._append(f"[{ev.value}]", "sent")
        elif ev.kind == "status":
            self.status_var.set(ev.value)
        elif ev.kind == "progress":
            self.progress["value"] = ev.value
        elif ev.kind == "hint":
            self.hint_var.set(f"  {ev.value}  ")
            self.hint_label.grid(row=6, column=0, columnspan=3, sticky="ew", padx=6, pady=4)
        elif ev.kind == "releases":
            self._show_releases(ev.value)
        elif ev.kind == "ports":
            self._show_ports(ev.value)
        elif ev.kind in ("done", "erased", "error"):
            self._finish(ev)

    def _finish(self, ev: Event) -> None:
        self._set_busy(False)
        self.progress.stop()
        self.progress.configure(mode="determinate")
        if ev.kind == "done":
            result: installer.InstallResult = ev.value
            self.progress["value"] = 100
            self.status_var.set(result.message)
            self.monitor.request("resume", result.port)
        elif ev.kind == "erased":
            self.progress["value"] = 100
            self.status_var.set("Chip erased (empty): click INSTALL.")
            self.mon_state.set("● paused")
            self.mon_label.configure(fg=THEME["sub"])
            # Like `deskbuddy erase`: leave the port alone until INSTALL. Re-opening it can reset the empty
            # chip out of download mode into a restart loop (USB dropping out, a flood of output).
            self._append(
                "[chip erased: no firmware, waiting in download mode. Monitor paused; INSTALL puts DeskBuddy back]",
                "sent",
            )
        else:
            exc: DeskBuddyError = ev.value
            self.status_var.set(f"Failed: {exc.message}")
            self.monitor.request("resume", None)
            messagebox.showerror("DeskBuddy", f"{exc.message}\n\n{exc.hint}")

    def _close(self) -> None:
        question = "Installing or erasing is still running. Closing now can leave the board empty.\n\nClose anyway?"
        if self.busy and not messagebox.askyesno("DeskBuddy", question, icon="warning"):
            return
        self.monitor.stop()
        self.root.destroy()


def _set_icon(root: tk.Tk) -> None:
    """DeskBuddy icon on the window and taskbar in the ready-made Windows app (bundled .ico)."""
    base = getattr(sys, "_MEIPASS", None)
    if not base or sys.platform != "win32":
        return
    ico = Path(base) / "deskbuddy.ico"
    if ico.is_file():
        with contextlib.suppress(tk.TclError):  # only cosmetic
            root.iconbitmap(default=str(ico))


def main(quit_after_ms: Optional[int] = None) -> None:
    root = tk.Tk()
    _set_icon(root)
    window = InstallerWindow(root)
    if quit_after_ms is not None:  # self-test of the ready-made app: open, run briefly, close
        root.after(quit_after_ms, window._close)
    root.mainloop()
