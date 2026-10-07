"""Local bridge preferences shown in a normal, scrollable Tk settings window."""
import tkinter as tk
from tkinter import ttk
from native_labels import wrap_details


class SettingsWindow:
    def __init__(self,root,font,client,snapshot):
        self.client,self.snapshot,self.pending=client,snapshot,None
        self.window=tk.Toplevel(root)
        self.window.title('望包设置 · 连接与显示')
        self.window.configure(bg='#f5f2e8')
        self.window.attributes('-topmost',True)
        self.window.geometry('510x610')
        self.window.minsize(440,420)
        self.font=font
        self.preferences={};self.sources={};self.tasks={}
        self.codex_window=None
        self.catalog_signature=None
        tk.Label(self.window,text='望包设置',font=('Microsoft YaHei UI',-18,'bold'),bg='#f5f2e8',fg='#315449').pack(anchor='w',padx=18,pady=(16,8))
        tk.Label(self.window,text='任务开始时自动分配工位，已读后归队离开。\n关闭连接会暂停监控，保留已有通知。',font=font,bg='#f5f2e8',fg='#687a6a',justify='left').pack(anchor='w',padx=18,pady=(0,10))
        controls=tk.Frame(self.window,bg='#f5f2e8');controls.pack(fill='x',padx=18)
        for key,label in [('movement_locked','锁定移动（角色和整组窗口）'),('always_on_top','桌宠置顶'),('show_labels','显示工位文字'),('auto_discover','自动发现 Codex / Cursor / ZCode 任务')]:
            variable=tk.BooleanVar(value=snapshot.get('settings',{}).get(key,key!='movement_locked'))
            self.preferences[key]=variable
            tk.Checkbutton(controls,text=label,variable=variable,font=font,bg='#f5f2e8',anchor='w').pack(fill='x')
        scale_row=tk.Frame(controls,bg='#f5f2e8');scale_row.pack(fill='x',pady=(5,0))
        tk.Label(scale_row,text='桌宠缩放',font=font,bg='#f5f2e8').pack(side='left')
        self.scale=tk.StringVar(value=str(snapshot.get('settings',{}).get('desktop_scale',100))+'%')
        ttk.Combobox(scale_row,textvariable=self.scale,values=('50%','75%','100%','125%','150%'),
                     state='readonly',width=8,font=font).pack(side='left',padx=10)
        body=tk.Frame(self.window,bg='#f5f2e8');body.pack(fill='both',expand=True,padx=18,pady=10)
        self.canvas=tk.Canvas(body,highlightthickness=0,bg='#f5f2e8')
        scroll=tk.Scrollbar(body,command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.content=tk.Frame(self.canvas,bg='#f5f2e8')
        item=self.canvas.create_window(0,0,anchor='nw',window=self.content)
        self.content.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(item,width=e.width))
        self.window.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-1 if e.delta>0 else 1,'units'))
        self.populate(snapshot)
        self.message=tk.Label(self.window,text='选择后点击“保存设置”。',font=font,bg='#f5f2e8',fg='#637563')
        self.message.pack(anchor='w',padx=18,pady=4)
        row=tk.Frame(self.window,bg='#f5f2e8');row.pack(fill='x',padx=18,pady=(4,14))
        self.save_button=tk.Button(row,text='保存设置',font=font,command=self.save,bg='#dde9d9')
        self.save_button.pack(side='right',padx=4)
        tk.Button(row,text='关闭',font=font,command=self.window.destroy).pack(side='right',padx=4)

    def open_codex(self):
        if self.codex_window and self.codex_window.exists():
            self.codex_window.window.lift();return
        from native_connections import CodexSessionWindow
        self.codex_window=CodexSessionWindow(self.window,self.font,self.client)

    def open_extensions(self):
        try:
            self.client.open_extensions()
        except (OSError, ValueError, KeyError):
            self.message.configure(text='设置页暂时打不开，请检查本地桥是否运行。')

    def populate(self,snapshot):
        for source in snapshot.get('connections',{}).get('sources',[]):
            variable=tk.BooleanVar(value=source['enabled']);self.sources[source['id']]=variable
            state='已暂停' if not source['enabled'] else source.get('status','等待软件事件')
            tk.Checkbutton(self.content,text=source['label']+' · '+state,variable=variable,font=self.font,bg='#f5f2e8',anchor='w').pack(fill='x',pady=(6,0))
            tk.Label(self.content,text=source['method'],font=self.font,fg='#6c7a68',bg='#f5f2e8',anchor='w').pack(fill='x',padx=22)
        tk.Button(self.content,text='添加 Codex 分身…',font=self.font,command=self.open_codex,bg='#dde9d9').pack(anchor='w',pady=(12,0))
        tk.Button(self.content,text='订阅与助手…',font=self.font,command=self.open_extensions,bg='#dde9d9').pack(anchor='w',pady=(8,0))
        tk.Label(self.content,text='选择要连接的已有会话',font=('Microsoft YaHei UI',-13,'bold'),bg='#f5f2e8',fg='#315449').pack(anchor='w',pady=(16,6))
        self.task_frame=tk.Frame(self.content,bg='#f5f2e8');self.task_frame.pack(fill='x')
        self.populate_tasks(snapshot)

    def populate_tasks(self,snapshot):
        catalog=snapshot.get('connections',{}).get('tasks',[])
        signature=[(t['id'],t['label']) for t in catalog]
        if signature==self.catalog_signature:return
        self.catalog_signature=signature
        previous={key:value.get() for key,value in self.tasks.items()}
        self.tasks={}
        for widget in self.task_frame.winfo_children():widget.destroy()
        if not catalog:tk.Label(self.task_frame,text='接入 Codex 分身或收到软件事件后，会话会出现在这里。',font=self.font,bg='#f5f2e8',wraplength=390,justify='left').pack(anchor='w')
        for task in catalog:
            variable=tk.BooleanVar(value=previous.get(task['id'],task['enabled']));self.tasks[task['id']]=variable
            caption=wrap_details([task['source']+' · '+task['label']],self.font.measure,390,4)
            tk.Checkbutton(self.task_frame,text=caption,variable=variable,font=self.font,bg='#f5f2e8',justify='left',anchor='w').pack(fill='x',pady=2)

    def save(self):
        patch={key:value.get() for key,value in self.preferences.items()}
        patch['desktop_scale']=int(self.scale.get().rstrip('%'))
        patch['sources']={key:value.get() for key,value in self.sources.items()}
        patch['disabled_tasks']=[key for key,value in self.tasks.items() if not value.get()]
        self.pending=self.client.update_settings(patch)
        self.save_button.configure(state='disabled');self.message.configure(text='正在保存；连接中断时会等待恢复。')

    def update(self,snapshot):
        if not self.window.winfo_exists():return
        if self.codex_window and self.codex_window.exists():self.codex_window.update(snapshot)
        if not snapshot.get('offline'):self.populate_tasks(snapshot)
        result=snapshot.get('settings_result') or {}
        if self.pending and result.get('serial')==self.pending:
            self.pending=None;self.save_button.configure(state='normal')
            self.message.configure(text='已保存，桌宠和网页同步生效。' if result['ok'] else '保存未通过，请关闭后重新打开设置。')

    def exists(self):return bool(self.window.winfo_exists())
