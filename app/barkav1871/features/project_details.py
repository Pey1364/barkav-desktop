"""Canonical project profile editor backed by ``ProjectService``."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from barkav1871.services import FinanceDB, ProjectService


class ProjectDetailsPanel(ttk.Frame):
    _FIELDS = (
        ("name", "نام پروژه"),
        ("address", "آدرس"),
        ("postal_code", "کدپستی"),
        ("registration_plate", "پلاک ثبتی"),
        ("municipal_file_no", "شماره پروندهٔ شهرداری"),
    )

    def __init__(self, parent, *, db: FinanceDB, base_dir):
        super().__init__(parent, padding=12, style="Panel.TFrame")
        self.service = ProjectService(db, base_dir)
        self.values = {key: tk.StringVar() for key, _label in self._FIELDS}
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="ذخیره", style="Primary.TButton", command=self.save).pack(side="right")
        ttk.Label(toolbar, text="مشخصات پروژه", style="Title.TLabel", anchor="e").pack(side="right", fill="x", expand=True, padx=12)
        form = ttk.Frame(self, style="Panel.TFrame")
        form.pack(fill="x", anchor="ne")
        form.grid_columnconfigure(0, weight=1)
        for row, (key, label) in enumerate(self._FIELDS):
            ttk.Label(form, text=label, style="Panel.TLabel", anchor="e").grid(row=row, column=1, sticky="e", padx=(12, 6), pady=6)
            ttk.Entry(form, textvariable=self.values[key], justify="right").grid(row=row, column=0, sticky="ew", padx=(6, 12), pady=6)
        ttk.Label(form, text="توضیحات", style="Panel.TLabel", anchor="ne").grid(row=len(self._FIELDS), column=1, sticky="ne", padx=(12, 6), pady=6)
        style = ttk.Style()
        field_background = style.lookup("TEntry", "fieldbackground") or "#ffffff"
        field_foreground = style.lookup("TEntry", "foreground") or "#101827"
        self.description_box = tk.Text(
            form, height=4, wrap="word", undo=False, relief="solid", bd=1,
            background=field_background, foreground=field_foreground, insertbackground=field_foreground,
        )
        self.description_box.grid(row=len(self._FIELDS), column=0, sticky="ew", padx=(6, 12), pady=6)

        documents = ttk.LabelFrame(self, text="اسناد ثبت‌شدهٔ پروژه", padding=8, style="TLabelframe")
        documents.pack(fill="both", expand=True, pady=(12, 0))
        columns = ("created", "type", "title", "notes")
        self.documents_tree = ttk.Treeview(documents, columns=columns, show="headings", style="Barkav.Data.Treeview", selectmode="browse")
        for key, label, width in (
            ("created", "تاریخ ثبت", 170), ("type", "نوع", 160), ("title", "عنوان", 260), ("notes", "یادداشت", 450),
        ):
            self.documents_tree.heading(key, text=label, anchor="e")
            self.documents_tree.column(key, anchor="e", width=width, stretch=True)
        self.documents_tree.configure(displaycolumns=tuple(reversed(columns)))
        self.documents_tree.pack(fill="both", expand=True)

    def refresh(self) -> None:
        record = self.service.get_project()
        for key, _label in self._FIELDS:
            self.values[key].set(str(record.get(key) or ""))
        self.description_box.delete("1.0", "end")
        self.description_box.insert("1.0", str(record.get("description") or ""))
        for item in self.documents_tree.get_children():
            self.documents_tree.delete(item)
        for document in self.service.list_documents():
            self.documents_tree.insert("", "end", values=(
                document.get("created_at") or "—", document.get("document_type") or "—",
                document.get("title") or "—", document.get("notes") or "—",
            ))

    def save(self) -> None:
        try:
            self.service.save_project(
                **{key: value.get().strip() for key, value in self.values.items()},
                description=self.description_box.get("1.0", "end-1c").strip(),
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("مشخصات پروژه", str(exc), parent=self)
            return
        messagebox.showinfo("مشخصات پروژه", "اطلاعات پروژه ذخیره شد.", parent=self)
