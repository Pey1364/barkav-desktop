"""Independent BARKAV application shell for the canonical feature modules."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from PIL import Image, ImageTk
except ImportError:  # preflight reports Pillow before the app is opened
    Image = ImageTk = None

from .core import APP_IDENTITY, ProjectEntry, ProjectRegistry, apply_project_environment
from .design import ThemeManager, apply_ttk_theme
from .design.controls import themed_brand_image
from .features import ContractorsPanel, DashboardPanel, DataEntryPanel, ManagerAccountPanel, ProjectDetailsPanel, ReportsPanel, SalesClaimsPanel, TransactionsPanel
from .services import FinanceDB


class ApplicationShell(tk.Tk):
    """Canonical 18.7.1 shell, visually aligned to the approved 18.7 frame."""

    def __init__(self, base_dir: str | Path, project: ProjectEntry):
        super().__init__()
        self.base_dir = Path(base_dir)
        self.project = project
        self.registry = ProjectRegistry(self.base_dir)
        self.theme = ThemeManager()
        apply_ttk_theme(self, self.theme.selection)
        self.title(APP_IDENTITY.window_title)
        self.minsize(980, 640)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        apply_project_environment(project)
        self._pages: dict[str, ttk.Frame] = {}
        self._nav_buttons: dict[str, tk.Button] = {}
        self._images: dict[str, object] = {}
        self._active_module_id = "dashboard"
        self._build()

    def _build(self) -> None:
        palette = self.theme.palette
        self.configure(bg=palette["bg"])
        header = tk.Frame(self, bg=palette["surface"], height=62,
                          highlightbackground=palette["line_soft"], highlightthickness=1)
        header.pack(fill="x")
        header.pack_propagate(False)
        self._build_header(header, palette)
        navigation = tk.Frame(self, bg=palette["surface"], height=46,
                              highlightbackground=palette["line_soft"], highlightthickness=1)
        navigation.pack(fill="x")
        navigation.pack_propagate(False)
        self._build_navigation(navigation, palette)

        workspace = ttk.Frame(self, style="App.TFrame", padding=9)
        workspace.pack(fill="both", expand=True)
        self._workspace = workspace
        database = FinanceDB(self.project.db_path)
        self._mount("project_details", ProjectDetailsPanel, database, base_dir=self.base_dir)
        self._mount("dashboard", DashboardPanel, database)
        self._mount("data_entry", DataEntryPanel, database)
        self._mount("transactions", TransactionsPanel, database)
        self._mount("sales", SalesClaimsPanel, database, base_dir=self.base_dir)
        self._mount("reports", ReportsPanel, database)
        self._mount("manager_account", ManagerAccountPanel, database)
        self._mount("contractors", ContractorsPanel, database, base_dir=self.base_dir)
        self.select_module("dashboard")

        footer = tk.Frame(self, bg=palette["surface_alt"], height=54,
                          highlightbackground=palette["line"], highlightthickness=1)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self._build_footer(footer, palette)

    def _build_header(self, header: tk.Frame, palette: dict[str, str]) -> None:
        brand = tk.Frame(header, bg=palette["surface"])
        brand.pack(side="left", padx=(16, 10), pady=5)
        self._add_brand(brand, palette)
        commands = tk.Frame(header, bg=palette["surface"])
        commands.pack(side="left", pady=12)
        for text, action in (("Save", self._save_current_page),):
            tk.Button(commands, text=text, command=action, bg=palette["glass"], fg=palette["text"],
                      activebackground=palette["panel2"], activeforeground=palette["text"], relief="flat", bd=0,
                      highlightbackground=palette["line"], highlightthickness=1, padx=11, pady=5).pack(side="left", padx=2)
        for text in ("Undo", "Redo"):
            tk.Button(commands, text=text, state="disabled", bg=palette["glass"], fg=palette["muted"],
                      relief="flat", bd=0, highlightbackground=palette["line"], highlightthickness=1,
                      padx=11, pady=5).pack(side="left", padx=2)
        tools = tk.Frame(header, bg=palette["surface"])
        tools.pack(side="right", padx=12, pady=12)
        menu_button = tk.Menubutton(tools, text="File", direction="below", bg=palette["glass"], fg=palette["text"],
                                    activebackground=palette["panel2"], activeforeground=palette["text"], relief="flat", bd=0,
                                    highlightbackground=palette["line"], highlightthickness=1, padx=11, pady=5)
        menu = tk.Menu(menu_button, tearoff=False, bg=palette["surface"], fg=palette["text"], activebackground=palette["blue"], activeforeground="#FFFFFF")
        menu.add_command(label="Save", command=self._save_current_page)
        menu.add_command(label="مرکز پروژه", command=self.return_to_project_center)
        menu.add_separator()
        menu.add_command(label="خروج", command=self.destroy)
        menu_button.configure(menu=menu)
        menu_button.pack(side="right", padx=2)

    def _build_footer(self, footer: tk.Frame, palette: dict[str, str]) -> None:
        """Mirror the compact 18.7 footer control order without data writes."""
        message = tk.Button(footer, text="♧", command=lambda: self.select_module("dashboard"),
                            bg=palette["glass"], fg=palette["text"], activebackground=palette["panel2"],
                            activeforeground=palette["text"], relief="flat", bd=0,
                            highlightbackground=palette["line"], highlightthickness=1, padx=10, pady=6)
        message.pack(side="right", padx=(4, 8), pady=4)
        tk.Button(footer, text="فا", bg=palette["glass"], fg=palette["text"],
                  activebackground=palette["panel2"], activeforeground=palette["text"], relief="flat", bd=0,
                  highlightbackground=palette["line"], highlightthickness=1, padx=9, pady=5).pack(side="right", padx=3, pady=4)
        tk.Menubutton(footer, text="تیره", direction="above", bg=palette["glass"], fg=palette["text"],
                      activebackground=palette["panel2"], activeforeground=palette["text"], relief="flat", bd=0,
                      highlightbackground=palette["line"], highlightthickness=1, padx=10, pady=5).pack(side="right", padx=3, pady=4)
        tk.Menubutton(footer, text="تم", direction="above", bg=palette["glass"], fg=palette["text"],
                      activebackground=palette["panel2"], activeforeground=palette["text"], relief="flat", bd=0,
                      highlightbackground=palette["line"], highlightthickness=1, padx=10, pady=5).pack(side="right", padx=3, pady=4)
        self._clock_text = tk.StringVar(value="")
        clock = tk.Label(footer, textvariable=self._clock_text, bg=palette["glass"], fg=palette["text"],
                         highlightbackground=palette["line"], highlightthickness=1, anchor="e",
                         justify="right", font=("Segoe UI", 9), padx=8, pady=2, width=16)
        clock.pack(side="right", padx=(3, 8), pady=3, fill="y")
        tk.Label(footer, text=f"پروژه فعال: {self.project.project_id}", bg=palette["surface_alt"],
                 fg=palette["muted"], anchor="w", font=("Segoe UI", 9)).pack(side="left", padx=14, pady=10)
        self._tick_clock()

    def _tick_clock(self) -> None:
        if not self.winfo_exists():
            return
        self._clock_text.set(datetime.now().strftime("%Y/%m/%d\n%H:%M:%S"))
        self.after(1000, self._tick_clock)

    def _add_brand(self, parent: tk.Frame, palette: dict[str, str]) -> None:
        try:
            if ImageTk is None:
                raise RuntimeError("Pillow unavailable")
            image = ImageTk.PhotoImage(themed_brand_image(self.base_dir / "assets" / "barkav_brand_header.png", fg=palette["text"], bg=palette["surface"], size=(132, 45)), master=self)
            self._images["brand"] = image
            tk.Label(parent, image=image, bg=palette["surface"]).pack(side="left")
        except (OSError, RuntimeError, tk.TclError):
            tk.Label(parent, text="BARKAV", bg=palette["surface"], fg=palette["text"], font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(parent, text="BARKAV\nEngineering & Construction", bg=palette["surface"], fg=palette["text"],
                 justify="left", font=("Segoe UI", 8, "bold")).pack(side="left", padx=9)

    def _build_navigation(self, navigation: tk.Frame, palette: dict[str, str]) -> None:
        routes = (
            ("dashboard", "داشبورد", "nav_dashboard.png"),
            ("data_entry", "ثبت دیتا", "nav_data.png"),
            ("transactions", "تراکنش‌ها", "nav_transactions.png"),
            ("sales", "فروش و مطالبات", "nav_sales.png"),
            ("reports", "گزارش‌گیری", "nav_reports.png"),
            ("manager_account", "حساب مدیر", "nav_manager.png"),
            ("contractors", "پیمانکاران", "nav_market.png"),
        )
        for module_id, label, asset_name in routes:
            image = self._nav_image(module_id, asset_name)
            button = tk.Button(navigation, text=label, image=image, compound="left", command=lambda target=module_id: self.select_module(target),
                               bg=palette["surface"], fg=palette["muted"], activebackground=palette["panel2"], activeforeground=palette["cyan"],
                               relief="flat", bd=0, padx=14, pady=6, cursor="hand2", font=("Segoe UI", 9),
                               highlightbackground=palette["surface"], highlightthickness=1)
            button.pack(side="right", fill="y", padx=1, pady=2)
            self._nav_buttons[module_id] = button
        project_button = tk.Button(navigation, text="مشخصات پروژه", command=lambda: self.select_module("project_details"),
                                   bg=palette["glass"], fg=palette["text"], activebackground=palette["panel2"], activeforeground=palette["cyan"],
                                   relief="flat", bd=0, padx=14, pady=7, cursor="hand2", font=("Segoe UI", 8),
                                   highlightbackground=palette["line"], highlightthickness=1)
        project_button.pack(side="right", padx=(7, 4), pady=5)
        self._nav_buttons["project_details"] = project_button

    def _nav_image(self, key: str, asset_name: str):
        try:
            if Image is None or ImageTk is None:
                return None
            source = Image.open(self.base_dir / "assets" / asset_name).convert("RGBA")
            source.thumbnail((28, 28), Image.Resampling.LANCZOS)
            image = ImageTk.PhotoImage(source, master=self)
            self._images[key] = image
            return image
        except (OSError, RuntimeError, tk.TclError):
            return None

    def _mount(self, module_id: str, panel_type, database: FinanceDB, **kwargs) -> None:
        page = ttk.Frame(self._workspace, style="Panel.TFrame")
        panel_type(page, db=database, **kwargs).pack(fill="both", expand=True)
        self._pages[module_id] = page

    def select_module(self, module_id: str) -> None:
        page = self._pages.get(module_id)
        if page is None:
            return
        self._active_module_id = module_id
        for candidate in self._pages.values():
            candidate.pack_forget()
        page.pack(fill="both", expand=True)
        palette = self.theme.palette
        for candidate_id, button in self._nav_buttons.items():
            active = candidate_id == module_id
            button.configure(bg=palette["nav_active"] if active else palette["surface"], fg=palette["cyan"] if active else palette["muted"])

    def _save_current_page(self) -> None:
        page = self._pages.get(self._active_module_id)
        panel = page.winfo_children()[0] if page and page.winfo_children() else None
        save = getattr(panel, "save", None)
        if callable(save):
            save()
        else:
            messagebox.showinfo("Save", "این بخش دادهٔ قابل ذخیرهٔ مستقلی ندارد.", parent=self)

    def return_to_project_center(self) -> None:
        self.destroy()
        from .app import open_project_center
        open_project_center(self.base_dir)
