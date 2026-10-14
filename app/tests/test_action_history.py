"""Per-tab Undo/Redo stacks: routing, messages, and refusal handling."""

from __future__ import annotations

from action_history import (
    HISTORY_LIMIT, NO_HISTORY_FOR_TAB, NOTHING_TO_REDO, NOTHING_TO_UNDO,
    HistoryAction, HistoryHub, TabHistory, UndoRefused,
)


def _action(label, log):
    return HistoryAction(label, undo=lambda: log.append(('undo', label)),
                         redo=lambda: log.append(('redo', label)))


def test_undo_and_redo_walk_one_tab_in_order():
    log = []
    history = TabHistory()
    history.push(_action('حذف تراکنش', log))
    history.push(_action('ویرایش هزینه', log))

    assert history.undo() == '«ویرایش هزینه» بازگردانی شد.'
    assert history.undo() == '«حذف تراکنش» بازگردانی شد.'
    assert history.undo() == NOTHING_TO_UNDO
    assert history.redo() == '«حذف تراکنش» دوباره اجرا شد.'
    assert log == [('undo', 'ویرایش هزینه'), ('undo', 'حذف تراکنش'), ('redo', 'حذف تراکنش')]


def test_a_new_action_clears_the_redo_stack():
    history = TabHistory()
    history.push(_action('الف', []))
    history.undo()
    assert history.can_redo()
    history.push(_action('ب', []))
    assert not history.can_redo()
    assert history.redo() == NOTHING_TO_REDO


def test_history_keeps_only_the_latest_actions():
    history = TabHistory(limit=3)
    for number in range(5):
        history.push(_action(str(number), []))
    labels = [history.undo() for _ in range(4)]
    assert labels[:3] == ['«4» بازگردانی شد.', '«3» بازگردانی شد.', '«2» بازگردانی شد.']
    assert labels[3] == NOTHING_TO_UNDO
    assert HISTORY_LIMIT >= 50


def test_a_refused_undo_says_why_and_drops_the_action():
    history = TabHistory()
    older = []
    history.push(_action('قدیمی', older))

    def refuse():
        raise UndoRefused('ردیف‌ها پس از این عملیات دوباره تغییر کرده‌اند.')

    history.push(HistoryAction('حذف چک', undo=refuse, redo=lambda: None))

    message = history.undo()
    assert 'حذف چک' in message and 'ردیف‌ها پس از این عملیات دوباره تغییر کرده‌اند.' in message
    assert not history.can_redo()
    assert history.undo() == '«قدیمی» بازگردانی شد.'


def test_a_not_undoable_action_is_reported_not_skipped_over():
    history = TabHistory()
    history.push(_action('قبلی', []))
    history.push(HistoryAction('حذف وام', undo=lambda: None, redo=lambda: None,
                               undoable=False, reason='ردیف‌هایی به‌طور کامل حذف شده‌اند.'))

    assert history.undo() == '«حذف وام» قابل بازگشت نیست. ردیف‌هایی به‌طور کامل حذف شده‌اند.'
    assert history.undo() == '«قبلی» بازگردانی شد.'


def test_hub_keeps_every_tab_separate():
    scope = {'now': 'financial/all'}
    hub = HistoryHub(lambda: scope['now'])
    log = []
    hub.record(_action('حذف در همه تراکنش‌ها', log))
    scope['now'] = 'financial/loans'
    assert not hub.can_undo()
    assert hub.undo() == NOTHING_TO_UNDO
    assert hub.redo() == NOTHING_TO_REDO
    hub.record(_action('لغو وام', log))

    assert hub.undo() == '«لغو وام» بازگردانی شد.'
    scope['now'] = 'financial/all'
    assert hub.can_undo()
    assert hub.undo() == '«حذف در همه تراکنش‌ها» بازگردانی شد.'
    assert log == [('undo', 'لغو وام'), ('undo', 'حذف در همه تراکنش‌ها')]


def test_a_delegated_tab_uses_the_history_that_already_exists():
    hub = HistoryHub(lambda: 'data_entry')
    calls = []
    hub.delegate('data_entry', undo=lambda: calls.append('u') or 'برگشت شد', redo=lambda: 'دوباره شد',
                 can_undo=lambda: True, can_redo=lambda: False)

    hub.record(_action('نباید ثبت شود', []))

    assert hub.undo() == 'برگشت شد'
    assert hub.redo() == 'دوباره شد'
    assert hub.can_undo() and not hub.can_redo()
    assert calls == ['u']
    assert not hub.history('data_entry').can_undo()


def test_a_broken_scope_lookup_never_breaks_the_buttons():
    def broken():
        raise RuntimeError('tab lookup failed')

    hub = HistoryHub(broken)
    assert hub.current_scope() == ''
    assert hub.undo() == NO_HISTORY_FOR_TAB
    assert not hub.can_undo()
    hub.record(_action('بدون تب', []))
    assert not hub.can_undo()
