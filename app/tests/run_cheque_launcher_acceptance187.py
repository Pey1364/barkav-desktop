"""Run the real 19.1.1 launcher/runner with disposable DB and no network.

Preflight, registry and external bot/probes are isolated; UI, launcher dispatch,
project environment, wizard callbacks and finance writes are real.
"""
import json
import sys
import tempfile
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
import pytest
from test_transaction_lifecycle_matrix import m, runtime, register
from test_cheque_workflow187 import cheque_payload
import launcher_stage18_7 as launcher
import project_runner_stage18_7 as runner
import project_registry
from types import SimpleNamespace


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='barkav-launcher-cheque-') as folder:
        base = Path(folder)
        with pytest.MonkeyPatch.context() as patch:
            state = runtime.__wrapped__(base, patch)
            project = project_registry.ProjectEntry('CHEQUE-ACCEPTANCE', 'آزمون چک', str(state.db.db_path))
            registry = SimpleNamespace(data={'active_project_id': project.project_id},
                                       list=lambda: [project], get=lambda ident: project)
            patch.setattr(project_registry, 'ProjectRegistry', lambda base: registry)
            patch.setattr(launcher, 'BASE', base)
            patch.setattr(launcher, 'LOG_DIR', base/'runtime')
            patch.setattr(launcher, 'STARTUP_LOG', base/'runtime'/'startup.log')
            patch.setattr(launcher, 'preflight', lambda: True)
            patch.setattr(runner, 'BASE', base)
            patch.setattr(runner.subprocess, 'Popen', lambda *a, **k: None)
            patch.setattr(m.v186.v185, 'fetch_tgju_usd_toman', lambda timeout=6: (70000, '2026-10-05'))
            patch.setattr(m.DataEntryCenter187, '_start_gemini_probe_187', lambda self: None)
            patch.setattr(m.DataEntryCenter187, '_start_telegram_probe_187', lambda self: None)
            patch.setattr(m.Stage187Dashboard, '_show_startup_reminders_187', lambda self: None)
            errors = []
            for name in ('showerror', 'showwarning'):
                patch.setattr(m.messagebox, name, lambda *a, **k: errors.append(str(a)))
            patch.setattr(m, '_confirm_debt_warning_187', lambda *a: True)
            results = []
            original_loop = m.Stage187Dashboard.mainloop

            def exercise(app):
                app.title('BARKAV 19.1.1 — CHEQUE LAUNCHER ACCEPTANCE')
                app.update()
                try:
                    payload = cheque_payload()
                    payload.update(v18_subtype='نقدی', cost_group='')
                    pid = register(state, payload)
                    w = m.v182.TransactionWizard182(app, state.db.get_pending_item(pid), state.rich, lambda: None, lambda: None)
                    assert m.CHEQUE_CLEARING_SUBTYPE_187 not in w.widgets['v18_subtype']['values']
                    w.vars['v18_subtype'].set('چک')
                    w.widgets['v18_subtype'].event_generate('<<ComboboxSelected>>')
                    app.update()
                    assert 'cheque_operation187' in w.widgets
                    assert w.vars['cost_group'].get() == 'مصالح'
                    assert not w.widgets['contract_id'].master.winfo_ismapped()
                    w.vars['cost_group'].set('پیمانکار'); app.update()
                    assert w.widgets['contract_id'].master.winfo_ismapped()
                    w.next(); app.update(); w.prev(); app.update()
                    assert w.widgets['contract_id'].master.winfo_ismapped()
                    w.vars['cost_group'].set('مصالح'); app.update()
                    while w.winfo_exists() and not errors:
                        w.next(); app.update()
                    assert not errors
                    cheques = state.db.list_cheques(open_only=False)
                    assert len(cheques) == 1
                    cheque_id = cheques[0]['cheque_id']
                    cost = state.db.snapshot().construction_cost
                    with state.db.read() as con:
                        count = con.execute('SELECT count(*) FROM transactions').fetchone()[0]
                    results.append('issue/select/back/register: PASS')
                    print(results[-1], flush=True)
                    for index, status in enumerate(m.CHEQUE_RESOLUTION_STATUS_CHOICES_187, 2):
                        payload = cheque_payload()
                        payload.update(cheque_operation187=m.CHEQUE_OPERATION_RESOLVE_187,
                                       selected_cheque_id187=cheque_id, selected_cheque_manual187=True)
                        if index > 2:
                            payload['_resolution_edit_cheque_id187'] = cheque_id
                        pid = register(state, payload, index)
                        w = m.v182.TransactionWizard182(app, state.db.get_pending_item(pid), state.rich, lambda: None, lambda: None)
                        app.update()
                        assert cheque_id in w.widgets['selected_cheque_id187'].get_children()
                        w.next(); app.update(); w.next(); app.update()
                        w.vars['cheque_resolution_status187'].set(status)
                        w.vars['cheque_resolution_registration187'].set('ثبت‌شده')
                        w.vars['cheque_resolution_account_holder187'].set('حساب آزمون')
                        w.vars['cheque_resolution_void_reason187'].set('دلیل آزمایشی')
                        w.next(); app.update(); w.next(); app.update()
                        assert not errors, errors
                        actual = state.db.get_cheque(cheque_id)
                        assert m._cheque_status_label_187(actual) == status
                        assert len(state.db.list_cheques(open_only=False)) == 1
                        assert state.db.snapshot().construction_cost == cost
                        with state.db.read() as con:
                            assert con.execute('SELECT count(*) FROM transactions').fetchone()[0] == count
                        results.append(status + ': PASS')
                        print(results[-1], flush=True)
                    from PIL import Image
                    before = state.db.get_cheque(cheque_id)
                    e=app.edit_cheque_row(before)
                    assert state.db.get_pending_item(e.pid)['status']=='EDIT_PENDING'
                    e.vars['issuer_name'].set('تغییر لغوشده')
                    e.destroy();app.update()
                    assert state.db.get_cheque(cheque_id)==before
                    results.append('record/cancel/restore: PASS')
                    e=app.edit_cheque_row(before)
                    e.vars['issuer_name'].set('نام ویرایش‌شده آزمون')
                    e.vars['cheque_status'].set('پاس‌شده')
                    e._receipt_controller187.upload(Image.new('RGB',(50,50),'red'))
                    e._receipt_controller187.upload(Image.new('RGB',(50,50),'blue'))
                    gallery=e._receipt_controller187.gallery
                    assert len(gallery.paths)==2
                    first=gallery.path;gallery.move(1);assert gallery.path!=first
                    e.approve();app.update();assert not errors,errors
                    assert state.db.get_cheque(cheque_id)['issuer_name']=='نام ویرایش‌شده آزمون'
                    assert len(state.db.list_cheques(open_only=False))==1
                    e.destroy();app.update()
                    results.append('record/approve/append/navigate: PASS')
                    print(json.dumps({'launcher': str(Path(launcher.__file__).resolve()),
                                      'results': results, 'errors': errors}, ensure_ascii=False), flush=True)
                finally:
                    app.destroy()

            def loop(app, *args, **kwargs):
                app.after(350, lambda: exercise(app))
                return original_loop(app, *args, **kwargs)
            patch.setattr(m.Stage187Dashboard, 'mainloop', loop)
            sys.argv = [str(Path(launcher.__file__).resolve())]
            launcher.main()
            assert len(results) == 7 and not errors, (results, errors)


if __name__ == '__main__':
    main()
