"""Independent project AI choices and the shared ordered model picker."""
from __future__ import annotations
import copy
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from v18_store import load_ui, save_ui
from barkav_ui.bidi import rtl

SECTION_LABELS = {'data_entry': 'ثبت دیتا', 'management': 'مدیریت پروژه', 'calendar': 'تقویم پروژه', 'all': 'همه'}
MODEL_LABELS = {
    'AUTO': 'خودکار و کم‌مصرف (پیش‌فرض)', 'ALL': 'همهٔ موتورهای مجاز؛ نگه‌داشتن بهترین نتیجه',
    'GEMINI': 'Gemini', 'OPENROUTER:QWEN': 'Qwen (OpenRouter)',
    'OPENROUTER:DEEPSEEK': 'DeepSeek (OpenRouter)', 'OPENROUTER:GLM': 'GLM (OpenRouter)',
    'BASETEN:DEEPSEEK': 'DeepSeek (Baseten)', 'BASETEN:DEEPSEEK_V4_PRO': 'DeepSeek V4 Pro (Baseten)',
    'BASETEN:DEEPSEEK_V4_PRO_0813': 'DeepSeek V4 Pro 0813 (Baseten)',
    'BASETEN:DEEPSEEK_V41_FLASH': 'DeepSeek V4.1 Flash (Baseten)',
    'BASETEN:GLM': 'GLM 5.3 (Baseten)', 'BASETEN:GLM_FLASH': 'GLM 5.3 Flash (Baseten)',
    'BASETEN:GLM_FAST': 'GLM 5.3 Fast (Baseten)', 'BASETEN:KIMI': 'Kimi K3 (Baseten)',
    'BASETEN:INKLING': 'Inkling (Baseten)', 'BASETEN:INKLING_SMALL': 'Inkling Small (Baseten)',
    'GROQ:LLAMA4': 'Llama-4 (Groq)', 'OPENAI': 'OpenAI (فقط انتخاب دستی)',
}
SETTINGS_KEY = 'ai_section_models187'
MODES = {'AUTO': MODEL_LABELS['AUTO'], 'ALL': MODEL_LABELS['ALL'], 'SELECTED': 'انتخاب یک تا سه مدل با اولویت'}


def normalize_choice(value):
    if isinstance(value, str):
        value = {'mode': value, 'models': []}
    value = value or {}
    mode = str(value.get('mode') or 'AUTO').upper()
    if mode in MODEL_LABELS and mode not in {'AUTO', 'ALL'}:
        return {'mode': 'SELECTED', 'models': [mode]}
    if mode not in MODES:
        raise ValueError('نوع انتخاب مدل معتبر نیست.')
    models = list(dict.fromkeys(str(x).upper() for x in value.get('models', [])))
    if mode != 'SELECTED':
        models = []
    elif not models or len(models) > 3 or any(x not in MODEL_LABELS or x in MODES for x in models):
        raise ValueError('یک تا سه مدل معتبر را انتخاب کنید.')
    return {'mode': mode, 'models': models}


def section_choice(section, ui=None):
    ui = load_ui() if ui is None else ui
    choices = ui.get(SETTINGS_KEY) or {}
    value = choices.get(section, ui.get('ai_engine_mode') or 'AUTO')
    return normalize_choice(value)


def update_choice(ui, section, choice):
    if section not in SECTION_LABELS:
        raise ValueError('بخش معتبر نیست.')
    choice = normalize_choice(choice)
    result = copy.deepcopy(ui)
    # Seed inherited preferences before changing one section: old defaults cannot leak.
    choices = {key: section_choice(key, ui) for key in SECTION_LABELS if key != 'all'}
    for key in choices if section == 'all' else (section,):
        choices[key] = copy.deepcopy(choice)
    result[SETTINGS_KEY] = choices
    if section in {'all', 'data_entry'}:
        result['ai_engine_mode'] = choice['models'][0] if choice['mode'] == 'SELECTED' else choice['mode']
    return result


def save_choice(section, choice):
    save_ui(update_choice(load_ui(), section, choice))


def configured_models(base_dir):
    # Credential values remain inside the existing provider configuration loader.
    from project_report_ai_187 import _model_config
    return {key: bool(_model_config(key, Path(base_dir), {})) for key in MODEL_LABELS if key not in MODES}


def provider_order(choice, available, automatic):
    choice = normalize_choice(choice)
    if choice['mode'] != 'SELECTED':
        return [name for name in automatic if name in available]
    return [name for selected in choice['models'] for name in available
            if name == selected or (selected == 'GEMINI' and name.startswith('GEMINI:'))]


class AIModelPicker187(ttk.Frame):
    """A dropdown with checkboxes, availability colours and explicit priority."""
    def __init__(self, parent, *, section, base_dir, choice=None, on_change=None, persist=True, width=30, default_caption=None):
        super().__init__(parent)
        self.section, self.base_dir = section, Path(base_dir)
        self.choice = normalize_choice(choice) if choice is not None else section_choice(section)
        self.on_change, self.persist = on_change, persist
        self.popup = None
        # What the button says while the default (automatic) choice is in force; None keeps the mode's own label.
        self.default_caption = default_caption
        self.button = ttk.Button(self, command=self.open, width=width)
        self.button.pack(fill='x')
        self._caption()

    def _caption(self):
        selected = self.choice['models']
        if selected:
            value = ' ← '.join(f'{i + 1}. {MODEL_LABELS[key]}' for i, key in enumerate(selected))
        elif self.default_caption and self.choice['mode'] == 'AUTO':
            value = self.default_caption
        else:
            value = MODES[self.choice['mode']]
        self.button.configure(text=rtl(value + ' ▾'))

    def set_choice(self, choice):
        self.choice = normalize_choice(choice)
        self._caption()

    def _apply(self, mode, selected):
        try:
            choice = normalize_choice({'mode': mode, 'models': selected})
        except ValueError as exc:
            messagebox.showwarning('انتخاب مدل', str(exc), parent=self.popup or self)
            return False
        if self.persist:
            save_choice(self.section, choice)
        self.set_choice(choice)
        if self.on_change:
            self.on_change(copy.deepcopy(choice))
        return True

    def open(self):
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.lift(); return
        if self.persist:
            self.set_choice(section_choice(self.section))
        from ui_stage18_7 import palette_187
        p = palette_187()
        popup = self.popup = tk.Toplevel(self)
        popup.title('انتخاب مدل هوش مصنوعی')
        popup.transient(self.winfo_toplevel())
        popup.configure(bg=p['surface'])
        mode = tk.StringVar(value=MODES[self.choice['mode']])
        selected = list(self.choice['models'])
        ttk.Combobox(popup, textvariable=mode, values=tuple(MODES.values()), state='readonly', justify='right', width=58).pack(fill='x', padx=10, pady=8)
        list_area = tk.Frame(popup, bg=p['surface'])
        list_area.pack(fill='both', expand=True, padx=10)
        canvas = tk.Canvas(list_area, bg=p['surface'], highlightthickness=0, bd=0, height=300)
        scrollbar = ttk.Scrollbar(list_area, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        list_frame = tk.Frame(canvas, bg=p['surface'])
        list_window = canvas.create_window((0, 0), window=list_frame, anchor='nw')
        def update_list(_event=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
            if canvas.winfo_width() > 1:
                canvas.itemconfigure(list_window, width=canvas.winfo_width())
        list_frame.bind('<Configure>', update_list, add='+')
        canvas.bind('<Configure>', update_list, add='+')
        def scroll_models(event):
            delta = getattr(event, 'delta', 0)
            if delta:
                canvas.yview_scroll(-max(1, abs(int(delta / 120))) * (1 if delta > 0 else -1), 'units')
            elif getattr(event, 'num', None) in (4, 5):
                canvas.yview_scroll(-1 if event.num == 4 else 1, 'units')
            return 'break'
        popup.bind('<MouseWheel>', scroll_models, add='+')
        popup.bind('<Button-4>', scroll_models, add='+')
        popup.bind('<Button-5>', scroll_models, add='+')
        availability = configured_models(self.base_dir)
        rows = {}
        def refresh():
            manual = mode.get() == MODES['SELECTED']
            for key, (variable, check, priority) in rows.items():
                variable.set(key in selected)
                check.configure(state='normal' if manual else 'disabled')
                priority.configure(text=f'اولویت {selected.index(key)+1}' if key in selected and manual else '')
        def toggle(key):
            if key in selected:
                selected.remove(key)
            elif len(selected) < 3:
                selected.append(key)
            else:
                messagebox.showinfo('انتخاب مدل', 'حداکثر سه مدل انتخاب کنید.', parent=popup)
            refresh()
        def move(key, step):
            if key in selected:
                old = selected.index(key); new = old + step
                if 0 <= new < len(selected):
                    selected[old], selected[new] = selected[new], selected[old]
            refresh()
        for key, title in MODEL_LABELS.items():
            if key in MODES: continue
            row = tk.Frame(list_frame, bg=p['surface']); row.pack(fill='x', pady=1)
            variable = tk.BooleanVar(value=key in selected)
            check = tk.Checkbutton(row, text=rtl(title), variable=variable, command=lambda k=key: toggle(k),
                bg=p['surface'], fg='#20ad79' if availability[key] else '#e36363',
                activebackground=p['surface'], selectcolor=p['surface'], anchor='e')
            check.pack(side='right', fill='x', expand=True)
            tk.Label(row, text='فعال' if availability[key] else 'غیرفعال', bg=p['surface'],
                fg='#20ad79' if availability[key] else '#e36363').pack(side='right', padx=5)
            priority = tk.Label(row, width=9, bg=p['surface'], fg=p['text']); priority.pack(side='left')
            ttk.Button(row, text='↑', width=2, command=lambda k=key: move(k,-1)).pack(side='left')
            ttk.Button(row, text='↓', width=2, command=lambda k=key: move(k,1)).pack(side='left')
            rows[key] = variable, check, priority
        def apply():
            key = next(k for k,v in MODES.items() if v == mode.get())
            if self._apply(key, selected): popup.destroy()
        mode.trace_add('write', lambda *_: refresh())
        refresh()
        tk.Label(popup, text=rtl('وضعیت بر اساس تنظیم بودن کلید مدل است؛ ترتیب انتخاب، اولویت اجراست.'),
                 bg=p['surface'], fg=p['muted'], justify='right').pack(fill='x', padx=10, pady=7)
        ttk.Button(popup, text='تأیید انتخاب', command=apply).pack(anchor='e', padx=10, pady=8)
        popup.update_idletasks()
        # Keep the controls fixed while the model list takes the remaining screen height.
        screen_width, screen_height = popup.winfo_screenwidth(), popup.winfo_screenheight()
        max_width, max_height = max(280, screen_width - 24), max(180, screen_height - 64)
        width = min(max(360, popup.winfo_reqwidth()), max_width)
        fixed_height = max(0, popup.winfo_reqheight() - canvas.winfo_reqheight())
        canvas_height = max(80, min(list_frame.winfo_reqheight(), max_height - fixed_height))
        canvas.configure(height=canvas_height)
        popup.update_idletasks()
        height = min(popup.winfo_reqheight(), max_height)
        x = max(0, min(self.winfo_rootx() + self.winfo_width() - width, screen_width - width))
        below = self.winfo_rooty() + self.winfo_height()
        above = self.winfo_rooty()
        if below + height <= screen_height - 8:
            y = below
        elif above - height >= 8:
            y = above - height
        else:
            y = max(8, min(below, screen_height - height - 8))
        popup.geometry(f'{width}x{height}+{x}+{y}')
