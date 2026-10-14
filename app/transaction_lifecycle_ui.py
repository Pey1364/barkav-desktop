"""Shared deletion confirmation and data-entry lifecycle actions for Tk."""
from tkinter import ttk
import tkinter as tk
from transaction_lifecycle import TransactionLifecycle, LifecycleDecision, is_resolution_payload
from table_actions import DeleteChoice, normalize_delete_choice, current_delete_choice, confirmed_delete

#: Entries other features add to the right-click menu of the tables: the generic
#: SmartTable menu below and the Transactions tab's own one (Stage187Dashboard.
#: _financial_context_menu_187), both through add_menu_extras(). Each item is a
#: function of a table that returns its entries: dicts with a label, a command and
#: a test (no arguments) for whether the rows selected right now suit it.
MENU_EXTRAS=[]

def add_menu_extras(menu,table):
    """Put the entries of MENU_EXTRAS on a table's right-click menu (the menus of
    both the generic tables and the Transactions tab call this)."""
    for provider in MENU_EXTRAS:
        for extra in provider(table) or ():
            menu.add_command(label=extra['label'],command=extra['command'],
                             state='normal' if extra['enabled']() else 'disabled')

def confirm_delete(parent,count=1,*,permanent=False,messagebox=None,financial=True,detail=''):
    # Behavioral tests may supply a lightweight center without Tk.
    if not hasattr(parent,'tk'):
        return DeleteChoice(permanent) if messagebox.askyesno('حذف',f'{count} ردیف انتخاب‌شده حذف شوند؟',parent=parent) else None
    from barkav_ui.window import BarkavWindow
    dialog=BarkavWindow(parent,'تأیید حذف',size_class='tiny',show_footer=False)
    result=[None];purge=tk.BooleanVar(dialog,value=permanent)
    mode=tk.StringVar(dialog,value='group' if count>1 else 'single')
    body=ttk.Frame(dialog.body);body.pack(fill='both',expand=True,padx=16,pady=12)
    ttk.Label(body,text=f'{count} ردیف حذف شود؟',anchor='e').pack(fill='x',pady=7)
    ttk.Radiobutton(body,text='حذف تکی — فقط اولین ردیف انتخاب‌شده',variable=mode,value='single').pack(anchor='e',pady=4)
    ttk.Radiobutton(body,text=f'حذف گروهی — همهٔ {count} ردیف انتخاب‌شده',variable=mode,value='group',
                    state='normal' if count>1 else 'disabled').pack(anchor='e',pady=4)
    if financial:
        ttk.Label(body,text='اثر ثبت از بخش‌های مرتبط برداشته می‌شود.',anchor='e').pack(fill='x',pady=7)
        box=ttk.Checkbutton(body,text='در دسته رد شده‌ها ثبت نشود',variable=purge)
        box.pack(anchor='e',pady=12)
        if permanent:
            box.configure(state='disabled')
            ttk.Label(body,text='حذف از دسته ردشده‌ها قابل بازگردانی نیست.',anchor='e').pack(fill='x')
    if detail:
        ttk.Label(body,text=detail,anchor='e',wraplength=420,justify='right').pack(fill='x',pady=7)
    def accept():
        result[0]=DeleteChoice(bool(purge.get()),mode.get()=='group');dialog.close()
    actions=ttk.Frame(body);actions.pack(fill='x',pady=12)
    ttk.Button(actions,text='تأیید حذف',command=accept,style='Toolbar.TButton').pack(side='right',padx=4)
    ttk.Button(actions,text='انصراف',command=dialog.close,style='Toolbar.TButton').pack(side='left',padx=4)
    dialog.grab_set();parent.wait_window(dialog)
    return result[0]

def cheque_reject_notice(db,pids):
    """What rejecting these records does to a cheque, in a sentence for the confirmation window."""
    lifecycle=TransactionLifecycle(db)
    notes=[]
    for pid in dict.fromkeys(str(p) for p in pids):
        item=db.get_pending_item(pid) or {}
        if item.get('status') not in ('APPROVED','EDIT_PENDING'):
            continue
        if is_resolution_payload(item.get('payload')):
            note='رد رکورد تعیین تکلیف، چک را به وضعیت پیش از تعیین تکلیف برمی‌گرداند؛ بعد می‌توان با رکوردی تازه آن را تعیین تکلیف کرد.'
        elif lifecycle._cheque_dependents(pid):
            note=('با رد رکورد صدور، رکورد تعیین تکلیف همان چک هم به ردشده‌ها می‌رود و اثر مالی چک تا تأیید دوبارهٔ '
                  'رکورد صدور حذف می‌ماند. رکورد تعیین تکلیف را می‌توان جداگانه تأیید کرد.')
        else:
            continue
        if note not in notes:
            notes.append(note)
    return ' '.join(notes)

def delete_rows(center,rows,db,messagebox,*,ask=True,kind='reject'):
    """«حذف» (kind='delete') asks whether to hide the rows or delete their record and transaction;
    «رد» (kind='reject', the default) moves them to the rejected pile as it always did."""
    if not rows: return
    unresolved=[r for r in rows if r.get('_lifecycle_decision_only187')]
    if unresolved:
        messagebox.showerror('تعیین تکلیف','\n'.join(r['_lifecycle_decision187'] for r in unresolved),parent=center)
        return
    all_rejected=all(r.get('status')=='REJECTED' for r in rows)
    notice=cheque_reject_notice(db,[row.get('pending_id') for row in rows if row.get('status')!='REJECTED'])
    if kind=='delete' and ask and hasattr(center,'tk'):
        import data_entry_extras_ui as extras
        decision=extras.ask_delete(center,rows,messagebox=messagebox,notice=notice)
        if decision is None:return
        rows=list(rows) if decision.grouped else list(rows)[:1]
        ids=list(dict.fromkeys(str(row['pending_id']) for row in rows))
        if decision.action=='hide':
            return extras.hide_rows(center,ids)
        choice=DeleteChoice(permanent=decision.action=='delete',grouped=decision.grouped)
    else:
        choice=normalize_delete_choice(confirm_delete(center,len(rows),permanent=all_rejected,messagebox=messagebox,detail=notice)) if ask else DeleteChoice()
        if choice is None:return
        rows=list(rows) if choice.grouped else list(rows)[:1]
    ids=list(dict.fromkeys(str(row['pending_id']) for row in rows))
    permanent=choice.permanent or any(row.get('status')=='REJECTED' for row in rows)
    lifecycle=TransactionLifecycle(db)
    import row_journal
    try:
        with row_journal.suspended():
            lifecycle.change_many(ids,permanent=choice.permanent,purge_rejected=True)
    except (ValueError,KeyError) as exc:
        messagebox.showerror('حذف انجام نشد',str(exc)+'\nهیچ‌یک از ردیف‌های انتخاب‌شده حذف نشد.',parent=center)
        return
    _record_history(center,lifecycle,ids,permanent)
    center.refresh()
    if callable(getattr(center,'on_posted',None)):center.on_posted()
    if getattr(center,'action',None):center.action.set(f'{len(ids)} ردیف حذف شدند.' if permanent else f'{len(ids)} ردیف به دسته ردشده منتقل شدند.')

def restore_rows(center,rows,db,messagebox):
    lifecycle=TransactionLifecycle(db)
    ids=list(dict.fromkeys(str(row['pending_id']) for row in rows if row.get('status')=='REJECTED'))
    failures=[]
    try:
        import row_journal
        with row_journal.suspended():lifecycle.change_many(ids,restore=True)
    except (ValueError,KeyError) as exc:
        for pid in ids:lifecycle.flag_decision(pid,'RESTORE',exc)
        failures.append(str(exc)+'\nهیچ‌یک از ردیف‌های انتخاب‌شده بازگردانی نشد.')
    center.refresh()
    if callable(getattr(center,'on_posted',None)):center.on_posted()
    if failures:messagebox.showerror('تعیین تکلیف','\n'.join(failures),parent=center)


def _record_history(owner,lifecycle,ids,permanent):
    from action_history import HistoryAction, UndoRefused
    import row_journal
    def change(restore):
        try:
            with row_journal.suspended():
                TransactionLifecycle(lifecycle.db,source='GUI_UNDO' if restore else 'GUI_REDO').change_many(ids,restore=restore)
        except (ValueError,KeyError) as exc:raise UndoRefused(str(exc)) from exc
    action=HistoryAction('حذف ثبت و آثار وابسته',lambda:change(True),lambda:change(False),
        undoable=not permanent,reason='حذف کامل بازگردانی نمی‌شود.')
    if hasattr(owner,'_push_history'):
        owner._push_history({'kind':'lifecycle','action':action})
    else:
        history=getattr(owner,'_window_history',None)
        if history:history.flush();history.hub.record(action)


def install_runtime(dashboard,center,editor,runtime):
    """Bind every active financial table to the original Data Entry record."""
    from types import MethodType
    from action_history import UndoRefused
    import row_journal
    import dashboard_stage12
    def generic_delete(table):
        handler=getattr(table,'delete_handler',None)
        rows=list(table.selected_rows() or [])
        if not callable(handler) or not rows:return
        choice=normalize_delete_choice(confirm_delete(table,len(rows),messagebox=runtime.messagebox,financial=False))
        if choice is None:return
        if not choice.grouped:rows=rows[:1]
        owners=[];owner=table
        while owner is not None:
            owners.append((owner,getattr(owner,'_bulk_delete_confirmed',False)))
            owner=getattr(owner,'master',None)
        for owner,_previous in owners:owner._bulk_delete_confirmed=True
        try:
            with confirmed_delete(choice):
                for row in rows:handler(row)
        except Exception as exc:
            runtime.messagebox.showerror('حذف انجام نشد', str(exc), parent=table)
        finally:
            for owner,previous in owners:owner._bulk_delete_confirmed=previous
    # Both SmartTable definitions are still used by inherited dialogs. Install
    # before widgets are built, so toolbar, Delete key and context callbacks
    # take the same stable selection snapshot.
    for table_class in {runtime.SmartTable,dashboard_stage12.SmartTable}:
        table_class._delete_selected_many=generic_delete
        table_class._delete_selected=generic_delete
    def generic_context(table,event):
        iid=table.tree.identify_row(event.y)
        if iid:
            if iid not in table.tree.selection():table.tree.selection_set(iid)
            table.tree.focus(iid)
        menu=tk.Menu(table,tearoff=0)
        if table.edit_handler:menu.add_command(label='✏️ ویرایش',command=table._double_edit)
        if table.delete_handler:menu.add_command(label='🗑 حذف/ابطال انتخاب‌ها',command=table._delete_selected_many)
        add_menu_extras(menu,table)
        if table.edit_handler or table.delete_handler:menu.add_separator()
        menu.add_command(label='📋 کپی',command=table.copy_selected)
        menu.add_command(label='📥 پیست در فیلتر',command=table.paste_filter)
        refresh=getattr(table,'_barkav_refresh_187',None)
        menu.add_command(label='🔄 بروزرسانی',command=refresh if callable(refresh) else table.apply_filter)
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()
    for table_class in {runtime.SmartTable,dashboard_stage12.SmartTable}:
        table_class._context_menu=generic_context
    def edit(window,row,table=None):
        if not row:return
        # The cheque tab edits status metadata with the source-transaction
        # consistency guard; the generic record route bypasses that dialog.
        cheque_table = getattr(window, 'cheque_table', None)
        if row.get('cheque_id') and (table is None or table is cheque_table):
            return window._open_cheque_status_editor_187(row)
        lifecycle=TransactionLifecycle(runtime.DB)
        try:
            pid=lifecycle.pending_for_row(row)
            pending=runtime.DB.get_pending_item(pid)
            if not pending:raise LifecycleDecision('رکورد ثبت دیتا پیدا نشد؛ تعیین تکلیف لازم است.')
            if table is None:
                name='document_table' if row.get('document_id') else ('cheque_table' if row.get('cheque_id') else ('exp_table' if row.get('expense_id') else 'all_tx_table'))
                table=getattr(window,name,None)
            source_rows=getattr(table,'filtered_rows',None) or getattr(table,'all_rows',None) or []
            navigation=[];seen=set()
            for source in source_rows:
                try:source_pid=lifecycle.pending_for_row(source)
                except (ValueError,KeyError):continue
                if source_pid in seen:continue
                source_pending=runtime.DB.get_pending_item(source_pid)
                if source_pending:navigation.append(source_pending);seen.add(source_pid)
            return window.approval_center.open_editor(pending,navigation_rows=navigation)
        except (ValueError,KeyError) as exc:
            lifecycle.flag_decision(row.get('pending_id') or row.get('transaction_id') or row.get('cheque_id') or 'UNKNOWN','EDIT',exc)
            runtime.messagebox.showerror('تعیین تکلیف',str(exc),parent=window)
    def remove(window,rows):
        if not rows:return
        lifecycle=TransactionLifecycle(runtime.DB)
        choice=normalize_delete_choice(current_delete_choice() or confirm_delete(window,len(rows),messagebox=runtime.messagebox))
        if choice is None:return
        rows=list(rows) if choice.grouped else list(rows)[:1]
        permanent=choice.permanent
        succeeded=[];failures=[];resolved=[]
        for row in rows:
            pid=''
            try:
                pid=lifecycle.pending_for_row(row)
                if pid in succeeded:continue
                succeeded.append(pid)
                if row.get('cheque_id') and 'issue_date_shamsi' in row and lifecycle._cheque_dependents(pid):
                    resolved.append(pid)
            except (ValueError,KeyError) as exc:
                key=pid or row.get('transaction_id') or row.get('cheque_id') or row.get('document_id') or 'UNKNOWN'
                lifecycle.flag_decision(key,'DELETE',exc);failures.append(str(key)+': '+str(exc))
        if failures:
            runtime.messagebox.showerror('تعیین تکلیف','\n'.join(failures)+'\nهیچ‌یک از ردیف‌های انتخاب‌شده حذف نشد.',parent=window)
            return
        if resolved:
            # A resolved cheque is not thrown away: its issue and resolution records go back to
            # review, the cheque's money effect is taken off, and approving them brings the row back.
            if not runtime.messagebox.askyesno('انتقال به دردست بررسی',
                    'این چک تعیین تکلیف شده است. رکوردهای صدور و تعیین تکلیف آن از تأییدشده به «در دست بررسی» '
                    'منتقل می‌شوند و اثر مالی چک تا تأیید دوباره برداشته می‌شود. ادامه می‌دهید؟',parent=window):return
            from transaction_review import ReviewReturn
            review=ReviewReturn(runtime.DB)
            try:
                review.backup()
                with row_journal.suspended():moved=review.return_to_review(resolved)
            except (ValueError,KeyError) as exc:
                runtime.messagebox.showerror('انتقال به دردست بررسی',str(exc),parent=window)
                return
            succeeded=[pid for pid in succeeded if pid not in resolved and pid not in moved]
            if not succeeded:
                window.refresh_all()
                return
        try:
            purged=permanent or any((runtime.DB.get_pending_item(pid) or {}).get('status')=='REJECTED' for pid in succeeded)
            with row_journal.suspended():lifecycle.change_many(succeeded,permanent=permanent,purge_rejected=True)
        except (ValueError,KeyError) as exc:
            runtime.messagebox.showerror('حذف انجام نشد',str(exc)+'\nهیچ‌یک از ردیف‌های انتخاب‌شده حذف نشد.',parent=window)
            return
        if succeeded:_record_history(window,lifecycle,succeeded,purged)
        window.refresh_all()
        if failures:runtime.messagebox.showerror('تعیین تکلیف','\n'.join(failures),parent=window)
    def remove_one(window,row=None):return remove(window,[row] if row else [])
    for name in ('_delete_tx_row','_delete_expense_row','_cancel_cheque_row','_delete_manager_record_187'):
        setattr(dashboard,name,remove_one)
    for name in ('edit_transaction_row','edit_expense_row','edit_cheque_row','edit_loan_row','_open_document_edit_wizard_187'):
        setattr(dashboard,name,edit)
    original_contract=dashboard._install_financial_table_contract_187
    def table_contract(window,table):
        result=original_contract(window,table)
        if table is not None:
            table.set_edit_handler(lambda row:edit(window,row,table))
            table.set_delete_handler(lambda row:remove_one(window,row))
            def bulk(_table):return remove(window,list(_table.selected_rows() or []))
            table._delete_selected_many=MethodType(bulk,table)
            table._delete_selected=MethodType(bulk,table)
            # Tk stores the bound callback at button creation time; replacing
            # the method alone left the old per-row confirmation loop active.
            button=getattr(table,'b_bulk_delete',None)
            if button is not None:button.configure(command=table._delete_selected_many)
        return result
    dashboard._install_financial_table_contract_187=table_contract
    original_action=dashboard._transaction_action_187
    def table_action(window,table,action):
        if action=='delete':return remove(window,list(table.selected_rows() or []))
        if action=='edit':return edit(window,window._one(table),table)
        return original_action(window,table,action)
    dashboard._transaction_action_187=table_action
    dashboard._delete_lifecycle_rows187=remove
    def editor_reject(dialog):
        item=runtime.DB.get_pending_item(dialog.pid) or {}
        if item.get('status') in ('APPROVED','EDIT_PENDING') and runtime.DB.get_financial_posting(dialog.pid):
            # A confirmed record has money behind it: say so, and that the open edit is dropped too.
            question='این رکورد تأیید شده و اثر مالی دارد. با رد، اثر مالی آن حذف و رکورد به دسته ردشده منتقل می‌شود؛ ویرایش جاری هم کنار گذاشته می‌شود. رد شود؟'
        else:
            question='ثبت و همه آثار آن به دسته ردشده منتقل شود؟'
        notice=cheque_reject_notice(runtime.DB,[dialog.pid])
        if notice: question=f'{question}\n\n{notice}'
        if not runtime.messagebox.askyesno('رد',question,parent=dialog):return
        try:
            with row_journal.suspended():runtime.v182.APPROVAL.reject(dialog.pid,actor_id='GUI_LIFECYCLE')
            root=dialog.master.winfo_toplevel()
            history=getattr(root,'_window_history',None)
            from history_scope import DATA_ENTRY_SCOPE
            owner=root.approval_center if history and history.hub.current_scope()==DATA_ENTRY_SCOPE else root
            _record_history(owner,TransactionLifecycle(runtime.DB),[dialog.pid],False)
            dialog.on_done()
            dialog.destroy()
        except (ValueError,KeyError) as exc:
            TransactionLifecycle(runtime.DB).flag_decision(dialog.pid,'REJECT',exc)
            runtime.messagebox.showerror('تعیین تکلیف',str(exc),parent=dialog)
    editor.reject=editor_reject
    original_menu=center._install_data_entry_context_actions_187
    def menu(owner):
        original_menu(owner)
        owner.table.menu.add_command(label='بازگردانی / Restore',state='disabled',
            command=lambda:owner.restore_rejected_rows_187(owner.table.selected_rows()))
        def update():
            rows=owner.table.selected_rows()
            allowed=bool(rows) and all(r.get('status')=='REJECTED' for r in rows)
            owner.table.menu.entryconfigure('بازگردانی / Restore',state='normal' if allowed else 'disabled')
        owner.table.menu.configure(postcommand=update)
    center._install_data_entry_context_actions_187=menu
    for method,source,destination,restore in (
        ('undo_data_entry','_undo_stack','_redo_stack',True),('redo_data_entry','_redo_stack','_undo_stack',False)):
        original=getattr(center,method)
        def action(owner,_original=original,_source=source,_destination=destination,_restore=restore):
            stack=getattr(owner,_source)
            if not stack or stack[-1].get('kind')!='lifecycle':return _original(owner)
            entry=stack[-1];history=entry['action']
            if not history.undoable:return history.reason
            try:(history.undo if _restore else history.redo)()
            except UndoRefused as exc:
                # As in the window's tabs: a step that cannot be reversed any more is
                # dropped, or it would stand in front of every older one for good.
                stack.pop()
                return f'{exc} این مورد از سابقه حذف شد.'
            stack.pop();getattr(owner,_destination).append(entry)
            owner.refresh()
            if callable(owner.on_posted):owner.on_posted()
            # A step may bring its own sentences (the move to review does).
            said=entry.get('undone' if _restore else 'redone')
            return said or ('ثبت و آثار وابسته بازگردانی شد.' if _restore else 'حذف ثبت دوباره اعمال شد.')
        setattr(center,method,action)

    def approve_many(owner,rows):
        rows=[r for r in rows if not r.get('_lifecycle_decision_only187') and r.get('status') not in ('APPROVED','REJECTED')]
        if not rows or not runtime.messagebox.askyesno('تأیید انتخاب‌ها',f'{len(rows)} رکورد تأیید شوند؟',parent=owner):return
        failures=[]
        for row in rows:
            try:runtime.v18.submit_v18(str(row['pending_id']),dict(row.get('payload') or {}),owner.rich)
            except (ValueError,KeyError) as exc:failures.append(str(exc))
        owner.refresh()
        if callable(owner.on_posted):owner.on_posted()
        if failures:runtime.messagebox.showerror('تأیید',"\n".join(failures),parent=owner)
    center.batch_approve18=approve_many
