"""Independent 18.7.1 Project Center, extracted from active 18.7 hierarchy.

No historical stage module is imported or executed at runtime.
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from PIL import ImageTk
except ImportError:
    ImageTk = None

from barkav1871.core import APP_IDENTITY, ProjectEntry, ProjectRegistry
from barkav1871.design import ThemeManager
from barkav1871.design.controls import fa, themed_brand_image
from barkav1871.services import FinanceDB, ProjectService


def project_label(project: ProjectEntry) -> str:
    return f"{project.name}  ({project.project_id})"


class ProjectCenter(tk.Tk):
    """Selector, closeable tabs and one scrollable 18.7 card per project."""

    def __init__(self, base_dir: str | Path, *, on_project_opened=None):
        super().__init__()
        self.base_dir = Path(base_dir)
        self.registry = ProjectRegistry(self.base_dir)
        self.on_project_opened = on_project_opened
        self.theme = ThemeManager()
        self._projects: list[ProjectEntry] = []
        self._tab_project_ids: dict[str, str] = {}
        self._closed_project_ids: set[str] = set()
        self._images: dict[str, object] = {}
        self._status = tk.StringVar(value="")
        self.title(f"{APP_IDENTITY.product_name} {APP_IDENTITY.version} — مرکز پروژه")
        self.minsize(900, 620)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        self._build()
        self.refresh()

    @property
    def palette(self) -> dict[str, str]:
        return self.theme.palette

    def _build(self) -> None:
        p = self.palette
        self.configure(bg=p["bg"])
        header = tk.Frame(self, bg=p["surface"], height=66,
                          highlightbackground=p["line"], highlightthickness=1)
        header.pack(fill="x")
        header.pack_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)
        header.grid_columnconfigure(2, weight=1)
        self._add_brand(header, p)
        tk.Label(header, text="مرکز پروژه", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 14, "bold"), anchor="center").grid(row=0, column=1, padx=18, pady=14)
        tk.Button(header, text="پروژه جدید", command=self.create_project, bg=p["blue"], fg="#FFFFFF",
                  activebackground=p["cyan"], activeforeground="#FFFFFF", relief="flat", padx=14, pady=7).grid(
                      row=0, column=2, sticky="e", padx=8)

        selector_bar = tk.Frame(self, bg=p["bg"])
        selector_bar.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(selector_bar, text="انتخاب پروژه", bg=p["bg"], fg=p["text"],
                 font=("Segoe UI", 10, "bold"), anchor="e").pack(side="right", padx=(8, 4))
        self.project_selector = ttk.Combobox(selector_bar, state="readonly", justify="right", width=34)
        self.project_selector.pack(side="right", fill="x", expand=True, padx=(4, 0))
        self.project_selector.bind("<<ComboboxSelected>>", self._select_project, add="+")

        self.notebook = ttk.Notebook(self, style="ProjectCenter187.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=12, pady=12)
        self.notebook.bind("<Button-1>", self._notebook_click, add="+")
        self.notebook.bind("<<NotebookTabChanged>>", self._sync_project_selector, add="+")
        tk.Label(self, textvariable=self._status, bg=p["bg"], fg=p["muted"],
                 font=("Segoe UI", 10, "bold"), anchor="e").pack(fill="x", padx=14, pady=(0, 10), anchor="e")

    def _add_brand(self, header: tk.Frame, p: dict[str, str]) -> None:
        brand = tk.Frame(header, bg=p["surface"])
        brand.grid(row=0, column=0, sticky="w", padx=(14, 6), pady=4)
        try:
            if ImageTk is None:
                raise RuntimeError("Pillow unavailable")
            image = ImageTk.PhotoImage(themed_brand_image(
                self.base_dir / "assets" / "barkav_brand_header.png", fg=p["text"],
                bg=p["surface"], size=(132, 45)), master=self)
            self._images["brand"] = image
            tk.Label(brand, image=image, bg=p["surface"]).pack(side="left")
        except (OSError, RuntimeError, tk.TclError):
            tk.Label(brand, text="BARKAV", bg=p["surface"], fg=p["text"],
                     font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(brand, text="BARKAV\nEngineering & Construction", bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 8, "bold"), justify="left").pack(side="left", padx=9)

    def refresh(self) -> None:
        self._projects = [item for item in self.registry.list() if item.project_id not in self._closed_project_ids]
        self.project_selector.configure(values=[project_label(item) for item in self._projects])
        for tab_id in self.notebook.tabs():
            self.notebook.forget(tab_id)
        self._tab_project_ids.clear()
        for project in self._projects:
            tab = ttk.Frame(self.notebook, padding=20, style="Panel.TFrame")
            self.notebook.add(tab, text=f"{fa(project.name)}  ({fa(project.project_id)})  ×")
            self._tab_project_ids[str(tab)] = project.project_id
            self._build_project_view(tab, project, self.palette)
        if not self._projects:
            self.project_selector.set("")
            self._status.set("برای شروع، «پروژه جدید» را انتخاب کنید.")
            return
        active_id = self.registry.data.get("active_project_id")
        index = next((i for i, item in enumerate(self._projects) if item.project_id == active_id), 0)
        self.project_selector.current(index)
        self._select_project()

    def _build_project_view(self, tab: ttk.Frame, project: ProjectEntry, p: dict[str, str]) -> None:
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        viewport = tk.Frame(tab, bg=p["bg"])
        viewport.grid(row=0, column=0, sticky="nsew")
        viewport.grid_rowconfigure(0, weight=1)
        viewport.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(viewport, bg=p["bg"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        body = tk.Frame(canvas, bg=p["bg"])
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")), add="+")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width), add="+")
        self._build_project_card(body, project, p)

        def scroll(event) -> str:
            if event.delta:
                canvas.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1), "units")
            return "break"

        def bind_tree(widget: tk.Misc) -> None:
            widget.bind("<MouseWheel>", scroll, add="+")
            for child in widget.winfo_children():
                bind_tree(child)

        bind_tree(body)

    def _build_project_card(self, parent: tk.Frame, project: ProjectEntry, p: dict[str, str]) -> None:
        card = tk.Frame(parent, bg=p["surface"], highlightbackground=p["line"], highlightthickness=1)
        card.pack(fill="x", expand=True, padx=12, pady=12)
        tk.Label(card, text=fa(project.name), bg=p["surface"], fg=p["text"],
                 font=("Segoe UI", 18, "bold"), anchor="e").grid(row=0, column=0, columnspan=2,
                                                                       sticky="ew", padx=18, pady=(18, 5))
        summary, progress = self._summary(project)
        details = (("کد پروژه", project.project_id), ("Group ID", project.group_chat_id or "-"),
                   ("Google Sheet", project.spreadsheet_name or "-"), ("آدرس", project.address or "-"),
                   ("پرونده شهرداری", project.municipal_file_no or "-"), ("تعداد طبقه", summary["floor_count"]),
                   ("تعداد واحد", summary["unit_count"]), ("هزینه کل ساخت", summary["construction_cost"]))
        card.grid_columnconfigure((0, 1), weight=1, uniform="project_info")
        grid = tk.Frame(card, bg=p["surface"])
        grid.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=3)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="project_info_box")
        for box_index, subset in enumerate((details[:4], details[4:])):
            box = tk.Frame(grid, bg=p["panel2"], highlightbackground=p["line"], highlightthickness=1)
            box.grid(row=0, column=1 - box_index, sticky="nsew", padx=4)
            box.grid_columnconfigure(0, weight=1)
            for index, (label, value) in enumerate(subset):
                row = tk.Frame(box, bg=p["surface"], height=40, highlightbackground=p["line"], highlightthickness=1)
                row.grid(row=index, column=0, sticky="ew", padx=6, pady=3)
                row.grid_propagate(False)
                tk.Label(row, text=label, bg=p["surface"], fg=p["muted"], width=18,
                         anchor="e", font=("Segoe UI", 9)).pack(side="right", padx=8, pady=6)
                tk.Label(row, text=fa(value) if value not in (None, "") else "—", bg=p["surface"],
                         fg=p["text"], anchor="e", font=("Segoe UI", 9)).pack(side="right", fill="x", expand=True, padx=8)
        host = tk.Frame(card, bg=p["surface"])
        host.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(10, 3))
        tk.Label(host, text="نمودار پیشرفت", bg=p["surface"], fg=p["muted"], anchor="e").pack(fill="x", pady=(0, 4))
        self._progress_chart(host, progress, p).pack(fill="x")
        running = tk.Frame(card, bg=p["surface"], highlightbackground=p["line"], highlightthickness=1)
        running.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=3)
        tk.Label(running, text="فاز در حال اجرا", bg=p["surface"], fg=p["muted"], anchor="e").pack(fill="x", padx=8, pady=8)
        foot = tk.Frame(card, bg=p["surface"])
        foot.grid(row=4, column=0, columnspan=2, sticky="ew", padx=18, pady=18)
        tk.Label(foot, text="وضعیت: آماده", bg=p["surface"], fg=p["muted"], font=("Segoe UI", 10, "bold")).pack(side="right")
        tk.Button(foot, text="باز کردن پروژه", command=lambda item=project: self._open_project(item), bg=p["blue"],
                  fg="#FFFFFF", activebackground=p["cyan"], activeforeground="#FFFFFF", relief="flat",
                  font=("Segoe UI", 11, "bold"), padx=20, pady=8).pack(side="left")

    @staticmethod
    def _progress_chart(parent: tk.Frame, percent: float, p: dict[str, str]) -> tk.Canvas:
        chart = tk.Canvas(parent, height=42, bg=p["surface"], highlightbackground=p["line"], highlightthickness=1)
        def redraw(_event=None) -> None:
            chart.delete("all")
            width, margin = max(chart.winfo_width(), 120), 6
            chart.create_rectangle(margin, margin, width - margin, 36, fill=p["panel2"], outline=p["line"])
            filled = (width - 2 * margin) * percent / 100.0
            if filled > 0:
                chart.create_rectangle(margin, margin, margin + filled, 36, fill=p["blue"], outline="")
            chart.create_text(width / 2, 21, text="—" if percent <= 0 else f"{fa(f'{percent:.1f}')}٪",
                             fill=p["text"], font=("Segoe UI", 10, "bold"))
        chart.bind("<Configure>", redraw)
        chart.after_idle(redraw)
        return chart

    def _summary(self, project: ProjectEntry) -> tuple[dict[str, str], float]:
        result = {"floor_count": "—", "unit_count": "—", "construction_cost": "—"}
        try:
            profile = ProjectService(FinanceDB(project.db_path), self.base_dir).get_project()
            floors = [row for row in profile.get("floors", []) if isinstance(row, dict) and not row.get("is_roof")]
            if floors:
                result["floor_count"] = str(len(floors))
                result["unit_count"] = str(sum(len(row.get("units", [])) for row in floors))
            progress = max(0.0, min(float(profile.get("progress_percent", profile.get("physical_progress", 0)) or 0), 100.0))
            amount = FinanceDB(project.db_path).snapshot().construction_cost
            if amount:
                result["construction_cost"] = f"{amount:,} تومان"
            return result, progress
        except (OSError, TypeError, ValueError):
            return result, 0.0

    def _select_project(self, _event=None) -> None:
        index = self.project_selector.current()
        if index < 0 or index >= len(self._projects):
            return
        project = self.registry.set_active(self._projects[index].project_id)
        tab_id = next((tab for tab, item_id in self._tab_project_ids.items() if item_id == project.project_id), None)
        if tab_id:
            self.notebook.select(tab_id)
        self._status.set("وضعیت: آماده")

    def _sync_project_selector(self, _event=None) -> None:
        try:
            project_id = self._tab_project_ids.get(str(self.notebook.select()))
            index = next(i for i, item in enumerate(self._projects) if item.project_id == project_id)
        except (StopIteration, tk.TclError):
            return
        if self.project_selector.current() != index:
            self.project_selector.current(index)
            self.registry.set_active(project_id)

    def _notebook_click(self, event) -> str | None:
        try:
            index = self.notebook.index(f"@{event.x},{event.y}")
            x, _y, width, _height = self.notebook.bbox(index)
            if event.x < x + width - 24:
                return None
            project_id = self._tab_project_ids.get(str(self.notebook.tabs()[index]))
            if project_id:
                self._closed_project_ids.add(project_id)
                self.refresh()
                return "break"
        except tk.TclError:
            return None
        return None

    def create_project(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("پروژه جدید")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=self.palette["surface"])
        tk.Label(dialog, text="نام پروژه", bg=self.palette["surface"], fg=self.palette["text"], anchor="e").grid(row=0, column=1, padx=12, pady=(14, 4), sticky="e")
        name = tk.StringVar()
        field = tk.Entry(dialog, textvariable=name, justify="right", width=36)
        field.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew")
        dialog.grid_columnconfigure(0, weight=1)
        def save() -> None:
            try:
                project = self.registry.create(name=name.get(), group_chat_id=None, spreadsheet_name="")
            except (OSError, ValueError) as exc:
                messagebox.showerror("خطا", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._closed_project_ids.discard(project.project_id)
            self.registry.set_active(project.project_id)
            self.refresh()
        tk.Button(dialog, text="ثبت پروژه", command=save, bg=self.palette["blue"], fg="#FFFFFF", relief="flat").grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 14), sticky="ew")
        field.focus_set()

    def _open_project(self, project: ProjectEntry) -> None:
        self.registry.set_active(project.project_id)
        if self.on_project_opened:
            self.on_project_opened(project)
            return
        messagebox.showinfo("مرکز پروژه", "مسیر اجرای پروژه هنوز به برنامهٔ میزبان متصل نشده است.", parent=self)

    def open_selected_project(self) -> None:
        index = self.project_selector.current()
        if index < 0 or index >= len(self._projects):
            messagebox.showwarning("مرکز پروژه", "ابتدا یک پروژه انتخاب کنید.", parent=self)
            return
        self._open_project(self._projects[index])


def run_project_center(base_dir: str | Path, *, on_project_opened=None) -> None:
    ProjectCenter(base_dir, on_project_opened=on_project_opened).mainloop()
