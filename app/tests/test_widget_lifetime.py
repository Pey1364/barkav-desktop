"""Real Tcl ownership checks; failures must remain observable."""
import tkinter as tk
from tkinter import ttk
import pytest
from barkav_ui.widget_lifetime import install_callback_cleanup
from barkav_ui import row_overlay as overlay

@pytest.fixture
def root():
    window = tk.Tk()
    window.withdraw()
    install_callback_cleanup(window)
    yield window
    window.destroy()

@pytest.mark.parametrize("schedule", ["after", "after_idle"])
def test_destroy_cancels_only_callbacks_owned_by_destroyed_widget(root, schedule):
    owner = tk.Frame(root)
    sibling = tk.Frame(root)
    calls = []
    queue = lambda widget, label: (widget.after(20, lambda: calls.append(label))
                                 if schedule == "after" else widget.after_idle(lambda: calls.append(label)))
    dead_job = queue(owner, "dead")
    live_job = queue(sibling, "live")
    owner.destroy()
    pending = root.tk.call("after", "info")
    assert dead_job not in pending
    assert live_job in pending
    root.after(40, root.quit)
    root.mainloop()
    assert calls == ["live"]


def test_child_destroy_does_not_cancel_parent_or_native_tcl_timer(root):
    child = tk.Frame(root)
    calls = []
    parent_job = root.after_idle(lambda: calls.append("parent"))
    native_job = root.tk.call("after", "idle", "set lifetime_native 1")
    child.after_idle(lambda: calls.append("dead"))
    child.destroy()
    assert parent_job in root.tk.call("after", "info")
    assert native_job in root.tk.call("after", "info")
    root.update()
    assert calls == ["parent"]
    assert int(root.tk.getvar("lifetime_native")) == 1


def test_existing_destroy_handlers_run_and_installation_is_idempotent(root):
    old_script = root.bind_all("<Destroy>")
    install_callback_cleanup(root)
    assert root.bind_all("<Destroy>") == old_script
    child = tk.Toplevel(root)
    calls = []
    child.bind("<Destroy>", lambda e: calls.append(e.widget), add="+")
    child.after_idle(lambda: calls.append("timer"))
    child.destroy()
    root.update()
    assert calls == [child]


def test_live_callback_errors_are_not_swallowed(root):
    errors = []
    root.report_callback_exception = lambda cls, exc, tb: errors.append(exc)
    def fail():
        raise ValueError("live failure")
    root.after_idle(fail)
    root.update()
    assert len(errors) == 1 and str(errors[0]) == "live failure"


def test_closing_root_removes_all_owned_jobs_without_fixture_cleanup():
    window = tk.Tk()
    install_callback_cleanup(window)
    child = tk.Toplevel(window)
    grandchild = tk.Frame(child)
    jobs = [widget.after(5000, lambda: None) for widget in (window, child, grandchild)]
    window.destroy()
    assert not set(jobs) & set(window.tk.call("after", "info"))


def _images(master):
    p = {"accent": "#00AABB", "text_secondary": "#AAAAAA", "bg": "#101010", "on_accent": "#FFFFFF"}
    return (overlay._corner_images("#00AABB", "#101010", 6, 2, master),
            overlay._checkbox_image(True, 16, "#101010", p, master),
            overlay._ring_icon("inbox", ring="#222222", colour="#00AABB", background="#101010", master=master))


def test_images_are_shared_in_one_interpreter_but_not_between_roots():
    first, second = tk.Tk(), tk.Tk()
    first.withdraw(); second.withdraw()
    first_closed = False
    try:
        a, b = _images(first), _images(second)
        assert a[0] is _images(tk.Frame(first))[0]
        assert a[1] is _images(first)[1]
        for left, right in zip((*a[0], a[1], a[2]), (*b[0], b[1], b[2])):
            assert left is not right
            assert left.tk is first.tk and right.tk is second.tk
            assert str(right) in second.tk.call("image", "names")
        interpreter = id(first.tk)
        first.destroy()
        first_closed = True
        assert not any(key[0] == interpreter for key in overlay._images)
        assert _images(second)[1] is b[1]
        assert str(b[1]) in second.tk.call("image", "names")
    finally:
        if not first_closed: first.destroy()
        second.destroy()


def test_reopen_roots_rebuilds_photos_without_test_cache_clear():
    for _ in range(6):
        window = tk.Tk(); window.withdraw()
        _images(window)
        interpreter = id(window.tk)
        assert any(key[0] == interpreter for key in overlay._images)
        window.destroy()
        assert not any(key[0] == interpreter for key in overlay._images)


def test_actual_table_closes_with_queued_rtl_and_paint_jobs(root, monkeypatch):
    from barkav_ui.table import DataTable
    table = DataTable(root, [("row", "ردیف"), ("text", "شرح")])
    table.set_rows([(1, "متن آزمون")])
    commands = set(table._tclCommands or ()) | set(table.tree._tclCommands or ())
    def owned_jobs():
        return [job for job in root.tk.call("after", "info")
                if root.tk.splitlist(root.tk.call("after", "info", job)[0])[0] in commands]
    assert owned_jobs(), "must exercise an actual queued table job"
    table.destroy()
    assert not owned_jobs()
    root.update()


def test_common_window_helpers_install_cleanup_before_first_idle(root):
    from barkav_ui.window import hide_for_fade
    other = tk.Tk()
    try:
        hide_for_fade(other)
        assert other._barkav_callback_cleanup
        child = tk.Toplevel(other)
        job = child.after(120, lambda: None)
        child.destroy()
        assert job not in other.tk.call("after", "info")
    finally:
        other.destroy()


@pytest.mark.parametrize("background", ["white", "SystemWindow" if __import__("sys").platform == "win32" else "gray"])
def test_overlay_accepts_native_tk_color_names(root, background):
    p = {"accent": "#00AABB", "text_secondary": "#AAAAAA", "bg": "#101010", "on_accent": "#FFFFFF"}
    check = overlay._checkbox_image(True, 16, background, p, root)
    corners = overlay._corner_images("#00AABB", background, 6, 2, root)
    assert check.tk is root.tk and check.width() == 16
    assert all(photo.tk is root.tk for photo in corners)
    expected = overlay._hex(root, background)
    assert overlay._checkbox_image(True, 16, expected, p, root) is check
