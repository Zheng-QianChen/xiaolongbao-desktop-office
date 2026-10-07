"""Session picker for the native pet; all I/O runs in BridgeClient's worker."""
import tkinter as tk

BG = '#f5f2e8'


class CodexSessionWindow:
    def __init__(self, parent, font, client):
        self.client, self.font = client, font
        self.pending = None
        self.action = None
        self.added_message = ''
        self.choices = {}
        self.window = tk.Toplevel(parent)
        self.window.title('添加 Codex 分身')
        self.window.configure(bg=BG)
        self.window.attributes('-topmost', True)
        self.window.geometry('510x570')
        self.window.minsize(440, 420)
        tk.Label(self.window, text='选择 Codex 会话', font=('Microsoft YaHei UI', -18, 'bold'),
                 bg=BG, fg='#315449').pack(anchor='w', padx=18, pady=(16, 8))
        self.help = tk.Label(self.window, text='接入后立即生效，仅观察选中的会话。\n历史完成结果不会新增提醒；已登记会话可在上级设置中暂停。',
                 font=font, bg=BG, fg='#687a6a', justify='left', wraplength=460)
        self.help.pack(anchor='w', padx=18)
        search = tk.Frame(self.window, bg=BG)
        search.pack(fill='x', padx=18, pady=12)
        tk.Label(search, text='标题 / 会话 ID', font=font, bg=BG).pack(side='left', padx=(0, 6))
        self.query = tk.StringVar()
        self.entry = tk.Entry(search, textvariable=self.query, font=font)
        self.entry.pack(side='left', fill='x', expand=True)
        self.entry.bind('<Return>', lambda e: self.refresh())
        self.refresh_button = tk.Button(search, text='刷新会话', font=font, command=self.refresh)
        self.refresh_button.pack(side='left', padx=(8, 0))
        body = tk.Frame(self.window, bg=BG)
        body.pack(fill='both', expand=True, padx=18)
        self.canvas = tk.Canvas(body, highlightthickness=0, bg=BG)
        scroll = tk.Scrollbar(body, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = tk.Frame(self.canvas, bg=BG)
        item = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        self.content.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        def resize_list(event):
            self.canvas.itemconfigure(item, width=event.width)
            for widget in self.content.winfo_children():
                if isinstance(widget, tk.Checkbutton):
                    widget.configure(wraplength=max(100, event.width-32))
        self.canvas.bind('<Configure>', resize_list)
        self.window.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units'))
        self.message = tk.Label(self.window, text='', font=font, bg=BG, fg='#637563',
                                wraplength=460, justify='left', anchor='w')
        self.message.pack(fill='x', padx=18, pady=10)
        def resize_window(event):
            if event.widget == self.window:
                self.help.configure(wraplength=max(100, event.width-36))
                self.message.configure(wraplength=max(100, event.width-36))
        self.window.bind('<Configure>', resize_window)
        row = tk.Frame(self.window, bg=BG)
        row.pack(fill='x', padx=18, pady=(0, 14))
        self.add_button = tk.Button(row, text='接入选中会话', font=font, command=self.add,
                                    bg='#dde9d9', state='disabled')
        self.add_button.pack(side='right', padx=4)
        tk.Button(row, text='关闭', font=font, command=self.window.destroy).pack(side='right', padx=4)
        self.refresh()

    def busy(self, action):
        self.action = action
        self.refresh_button.configure(state='disabled' if action else 'normal')
        self.entry.configure(state='disabled' if action else 'normal')
        for widget in self.content.winfo_children():
            if isinstance(widget, tk.Checkbutton):
                widget.configure(state='disabled' if action or widget.registered else 'normal')
        self.selection_changed()

    def selection_changed(self):
        count = sum(v.get() for v in self.choices.values())
        self.add_button.configure(state='normal' if not self.action and 1 <= count <= 20 else 'disabled',
                                  text='接入选中会话' + ('（{}）'.format(count) if count else ''))
        if count > 20:
            self.message.configure(text='每次最多接入 20 个会话，请减少勾选。')

    def refresh(self):
        if self.pending:
            return
        self.pending = self.client.codex_sessions(query=self.query.get())
        self.added_message = ''
        self.busy('refresh')
        self.message.configure(text='正在读取本机会话列表…')

    def add(self):
        ids = [ident for ident, variable in self.choices.items() if variable.get()]
        if self.pending or not 1 <= len(ids) <= 20:
            return
        self.pending = self.client.codex_sessions(ids=ids)
        self.busy('add')
        self.message.configure(text='正在接入选中会话…')

    def populate(self, data):
        for widget in self.content.winfo_children():
            widget.destroy()
        self.choices = {}
        for session in data['sessions']:
            registered = session['selected']
            caption = session['label'] + '\n' + session['id'][:8] + '…' + session['id'][-6:] + (' · 已登记' if registered else '')
            variable = tk.BooleanVar(value=False)
            button = tk.Checkbutton(self.content,
                text=caption, wraplength=max(100, self.canvas.winfo_width()-32), variable=variable,
                command=self.selection_changed, font=self.font, bg=BG, justify='left', anchor='w',
                state='disabled' if registered else 'normal')
            button.registered = registered
            button.pack(fill='x', pady=4)
            if not registered:
                self.choices[session['id']] = variable
        self.canvas.yview_moveto(0)
        if not data['sessions']:
            message = '没有找到可接入的会话，请换个关键词或先在 Codex 中创建会话。'
        elif data['truncated']:
            message = '仅显示最近 100 个会话，可输入标题或 ID 搜索。'
        else:
            message = '找到 {} 个会话，每次最多接入 20 个。'.format(len(data['sessions']))
        if not data['source_enabled']:
            message += '\nCodex 来源已暂停；接入后需在上级设置中开启并保存。'
        self.message.configure(text=(self.added_message+'\n' if self.added_message else '')+message)

    def update(self, snapshot):
        if not self.exists() or self.pending is None:
            return
        if snapshot.get('offline'):
            self.message.configure(text='本地连接中断，恢复后将继续；可关闭此窗口。')
            return
        result = snapshot.get('codex_result') or {}
        if result.get('serial') != self.pending:
            return
        action = self.action
        self.pending = None
        self.busy(None)
        if not result['ok']:
            self.message.configure(text=result['error'])
        elif action == 'refresh':
            self.populate(result['data'])
        else:
            count = result['data']['registered']
            self.refresh()
            self.added_message='已登记 {} 个会话。'.format(count)
            # Display successful persistence before the following refresh response arrives.
            self.message.configure(text='已登记 {} 个会话，正在刷新。'.format(count))

    def exists(self):
        return bool(self.window.winfo_exists())
