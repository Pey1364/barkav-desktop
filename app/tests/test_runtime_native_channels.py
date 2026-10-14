"""Native Tcl channels stay usable across independently captured test phases."""
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import ttk

import pytest


def test_default_capture_preserves_native_standard_channel_handles(request):
    assert '--capture=sys' in request.config.getini('addopts')


@pytest.mark.parametrize('batch', range(8))
def test_native_tcl_channels_library_reads_and_sqlite_survive_fresh_roots(batch, tmp_path):
    # No skip/retry: a failed Tk initialization or native read fails this test.
    root = tk.Tk()
    try:
        root.withdraw()
        root.tk.call('puts', 'stderr', 'BARKAV native channel regression')
        root.tk.call('flush', 'stderr')
        ttk.Label(root, text='native regression').pack()
        root.update_idletasks()
        library = Path(str(root.tk.call('info', 'library')))
        assert root.tk.call('file', 'exists', str(library / 'init.tcl')) == 1
        assert root.tk.call('package', 'require', 'msgcat')
        for locale in ('fa', 'en', 'nl'):
            catalog = library / 'msgs' / f'{locale}.msg'
            if catalog.is_file():
                root.tk.call('source', str(catalog))
        script = tmp_path / 'source.tcl'
        script.write_text('set barkav_native_read_ok 42\n', encoding='utf-8')
        assert root.tk.call('source', str(script)) == '42'
        connection = sqlite3.connect(tmp_path / 'native.sqlite3')
        try:
            connection.execute('CREATE TABLE sample (value INTEGER)')
            connection.execute('INSERT INTO sample VALUES (?)', (batch,))
            assert connection.execute('SELECT value FROM sample').fetchone() == (batch,)
        finally:
            connection.close()
    finally:
        root.destroy()


def test_python_output_capture_is_still_assertable(capsys):
    print('native capture remains checked')
    assert capsys.readouterr().out == 'native capture remains checked\n'
