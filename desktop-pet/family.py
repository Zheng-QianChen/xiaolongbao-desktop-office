"""One overall-status bun and per-agent buns at exactly one-third image size."""
import argparse
import math
import time
import tkinter as tk
from tkinter import font as tkfont
import json
import traceback
from pathlib import Path
from PIL import Image, ImageTk
from events import EventTail
from workstations import Workers,Worker
from travel import Travel,desk_position,phase_frame
from bounce import notification_bounce,CYCLE
from rendering import COLOR_KEY,pixel_sprite,geometry
from native_scene import NativeScene,draw_house
from native_labels import elide,sign_text,wrap_details
from native_zoom import ZoomCanvas,SCALE_LEVELS
from presentation_layout import PresentationLayout,reunion_offset
from asset_config import FRAME_WIDTH,FRAME_HEIGHT,LEFT_PADDING,OUT,COUNTS
from asset_config import EXTENDED,EXTENDED_SIZE,EXTENDED_ORIGIN,EXTENDED_CLIPS,extended_frame
from app_paths import APP_NAME,runtime_dir

ROOT = Path(__file__).resolve().parent
RUNTIME = runtime_dir()
FRAMES = OUT
BIG, SMALL = 255, 85
BIG_WIDTH=round(BIG*FRAME_WIDTH/FRAME_HEIGHT)
SMALL_WIDTH=round(SMALL*FRAME_WIDTH/FRAME_HEIGHT)
SMALL_LEFT_PADDING=LEFT_PADDING*SMALL/FRAME_HEIGHT
LABELS = {'idle':'休息', 'running':'工作', 'waiting':'待确认', 'review':'检查',
          'failed':'出错', 'disconnected':'断开', 'completed':'已完成', 'unread':'有未读结果'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo',action='store_true')
    parser.add_argument('--agents',type=int,default=3)
    parser.add_argument('--events',type=Path,default=RUNTIME/'events.jsonl')
    parser.add_argument('--bridge',action='store_true',help='Use the durable local notification bridge')
    parser.add_argument('--bridge-runtime',type=Path,default=RUNTIME/'bridge')
    parser.add_argument('--smoke-test',action='store_true')
    args=parser.parse_args()
    if not 1 <= args.agents <= 100:
        parser.error('--agents must be 1..100')
    if args.demo and args.bridge:
        parser.error('--demo and --bridge are separate modes')
    args.events.parent.mkdir(parents=True,exist_ok=True)
    RUNTIME.mkdir(parents=True,exist_ok=True)
    tail=EventTail(args.events)
    workers=Workers()
    bridge=None
    bridge_snapshot=None
    bridge_offline=False
    settings_window=None
    show_labels=True
    if args.bridge:
        from bridge_client import BridgeClient,worker_events
        bridge=BridgeClient(args.bridge_runtime)
    travel=Travel()
    shared_layout=PresentationLayout()
    leader_worker=Worker('leader','leader','望包',has_computer=True)
    snapshot=args.events.with_suffix('.pets-state.json')
    if not args.demo and not bridge:workers.restore(snapshot,time.monotonic())
    root=tk.Tk()
    scene=NativeScene(None if args.smoke_test or args.demo else RUNTIME/'family-scene.json')
    root.title(APP_NAME if args.bridge else APP_NAME+' · '+('演示' if args.demo else '事件模式'))
    root.overrideredirect(True)
    root.attributes('-topmost',True)
    root.configure(bg=COLOR_KEY)
    root.wm_attributes('-transparentcolor',COLOR_KEY)
    canvas=ZoomCanvas(root,bg=COLOR_KEY,highlightthickness=0)
    canvas.pack(fill='both',expand=True)
    # Negative font sizes are pixels, matching the fixed-size artwork and signs
    # even when Windows/Tk uses a larger points-to-pixels scale.
    label_font=tkfont.Font(root=root,family='Microsoft YaHei UI',size=-12)
    ui_font=tkfont.Font(root=root,family='Microsoft YaHei UI',size=-12)
    toolbar_font=tkfont.Font(root=root,family='Microsoft YaHei UI',size=-12)
    groups={}
    leader_groups={}
    leader_bounds={}
    for name,count in COUNTS.items():
        groups[name]=[ImageTk.PhotoImage(pixel_sprite(Image.open(FRAMES/f'{name}-{i:02}.png'),(SMALL_WIDTH,SMALL))) for i in range(count)]
        leader_groups[name]=[ImageTk.PhotoImage(pixel_sprite(Image.open(FRAMES/f'{name}-{i:02}.png'),(BIG_WIDTH,BIG))) for i in range(count)]
    for name,(count,_) in EXTENDED_CLIPS.items():
        groups[name]=[ImageTk.PhotoImage(pixel_sprite(Image.open(EXTENDED/name/f'{i:03}.png'),
                     tuple(round(v/3) for v in EXTENDED_SIZE))) for i in range(count)]
        if name in {'disconnected','read'}:
            leader_groups[name]=[ImageTk.PhotoImage(pixel_sprite(Image.open(EXTENDED/name/f'{i:03}.png'),EXTENDED_SIZE)) for i in range(count)]
            leader_bounds[name]=[Image.open(EXTENDED/name/f'{i:03}.png').getchannel('A').getbbox() for i in range(count)]
    rest_image=Image.open(FRAMES/'rest.png')
    rest=ImageTk.PhotoImage(pixel_sprite(rest_image,(SMALL_WIDTH,SMALL)))
    big=ImageTk.PhotoImage(pixel_sprite(rest_image,(BIG_WIDTH,BIG)))
    bounce_frames=[]
    # Native scene transforms: cache deformed versions for smooth, bounded-memory playback.
    for i in range(96):
        dy,sx,sy=notification_bounce(i*CYCLE/96)
        picture=ImageTk.PhotoImage(pixel_sprite(rest_image,(round(BIG_WIDTH*sx),round(BIG*sy))))
        bounce_frames.append((picture,dy,sx,sy))
    bounds=rest_image.getchannel('A').getbbox()
    foot_offset=(bounds[3]/rest_image.height-.5)*BIG
    head_offset=(bounds[1]/rest_image.height-.5)*BIG
    prop_image=Image.open(ROOT/'assets/closed-laptop-v2.png').convert('RGBA')
    prop_image=prop_image.crop(prop_image.getchannel('A').getbbox())
    prop=ImageTk.PhotoImage(pixel_sprite(prop_image,(27,10)))
    leader=[150.0,220.0]
    leader_sprite=canvas.create_image(*leader,image=big,tags='leader')
    alert=canvas.create_text(150,25,text='!',font=('Microsoft YaHei UI',27,'bold'),fill='#e75b39',state='hidden',tags='leader')
    leader_flower=[canvas.create_line(0,0,0,0,width=5,capstyle=tk.ROUND,fill='#16a9b1',state='hidden') for _ in range(8)]
    summary_box=canvas.create_rectangle(0,0,0,0,fill='#fffbed',outline='#b6c2a7',tags='leader')
    summary=canvas.create_text(150,25,fill='#42523c',font=ui_font,tags='leader')
    footer_box=canvas.create_rectangle(0,0,0,0,fill='#e5e9dc',outline='')
    footer=canvas.create_text(150,290,text='双击未读小包子：标记已读',fill='#777777',font=ui_font)
    details_box=canvas.create_rectangle(0,0,0,0,fill='#fffbed',outline='#a6b4a0',state='hidden')
    details_text=canvas.create_text(0,0,anchor='nw',font=ui_font,fill='#344c40',state='hidden')
    items={}
    page=0
    last_layout=None
    stage=-1
    epoch=time.monotonic()
    def clock():
        return epoch+(time.monotonic()-epoch)*(12 if args.smoke_test else 1)
    start=clock()
    last_tick=start
    playback={'ticks':0,'stages':set(),'phases':set(),'groups':set(),'errors':[],'replays':0,'eggs':0,'scene_checks':[]}
    saved_visual=None
    last_report=0
    def callback_error(kind,value,tb):
        message=''.join(traceback.format_exception(kind,value,tb))
        playback['errors'].append(message)
        print(message,flush=True)
        (RUNTIME/'family-error.log').write_text(message,encoding='utf-8')
        root.destroy()
    root.report_callback_exception=callback_error
    alert_started=None
    previous_unread=0
    read_started=-100
    drag=[0,0]
    dragging=None
    desk_cols=max(1,min(3,(root.winfo_screenwidth()-380)//110))
    capacity=desk_cols*2
    scene_size=[350+desk_cols*110,min(540,root.winfo_screenheight()-80)]
    displayed={}

    def hide_details(e=None):
        canvas.itemconfigure(details_box,state='hidden')
        canvas.itemconfigure(details_text,state='hidden')

    def show_details(e,key):
        if dragging:return
        worker=workers.items.get(key)
        if not worker:return
        w,h=scene_size
        width=min(340,w-40)
        status=LABELS[worker.state]+(' · 未读' if worker.unread else '')
        task=next((t for t in (bridge_snapshot or {}).get('tasks',[]) if t['id']==key),{})
        hint=('双击打开所在工作区' if task.get('source')=='zcode' else '双击打开对应会话') if task.get('open_url') else ''
        if task.get('retire_at'):hint='收工归队，稍后离开'
        elif task.get('read_mode')=='app' and not task.get('read_known'):hint+=' · 等待原软件已读状态'
        text=wrap_details([worker.label,status,worker.summary,hint],lambda text:canvas.measure(ui_font,text),width,
                          max(1,int((h-60)/canvas.linespace(ui_font))))
        canvas.itemconfigure(details_text,text=text,state='normal')
        canvas.coords(details_text,0,0)
        bx1,by1,bx2,by2=canvas.bbox(details_text)
        tw,th=bx2-bx1+20,by2-by1+16
        x=max(10,min(w-tw-10,e.x+12))
        y=e.y+20 if e.y+20+th<=h-10 else max(10,e.y-th-16)
        canvas.coords(details_box,x,y,x+tw,y+th)
        canvas.coords(details_text,x+10-bx1,y+8-by1)
        canvas.itemconfigure(details_box,state='normal')
        canvas.tag_raise(details_box);canvas.tag_raise(details_text)

    def begin(e):
        nonlocal dragging
        hide_details()
        if scene.locked:return
        tags=canvas.gettags('current')
        key='leader' if 'leader' in tags else next((k for k,item in items.items() if item['sprite'] in canvas.find_withtag('current')),None)
        dragging=key if scene.mode=='free' else None
        if dragging:
            xy=leader if dragging=='leader' else displayed.get(dragging,[e.x,e.y])
            drag[:]=[e.x-xy[0],e.y-xy[1]]
            canvas.configure(cursor='fleur')
        else:drag[:]=[e.x_root-root.winfo_x(),e.y_root-root.winfo_y()]

    def move(e):
        if scene.locked:return
        if dragging:
            scene.positions[dragging]=[e.x-drag[0],e.y-drag[1]]
            size=(BIG_WIDTH,BIG) if dragging=='leader' else (SMALL_WIDTH,SMALL)
            scene.positions[dragging]=scene.position(dragging,scene.positions[dragging],*scene_size,size,dragging=='leader')
        else:
            root.geometry(f'+{e.x_root-drag[0]}+{e.y_root-drag[1]}')

    def release(e):
        nonlocal dragging
        if dragging:scene.save()
        dragging=None
        canvas.configure(cursor='')

    def choose_mode(value):
        nonlocal dragging,last_layout
        hide_details()
        dragging=None;canvas.configure(cursor='')
        scene.mode=value;scene.save();last_layout=None
        free_button.configure(relief='sunken' if value=='free' else 'flat')
        house_button.configure(relief='sunken' if value=='house' else 'flat')
        reset_button.configure(state='normal' if value=='free' and not scene.locked else 'disabled')

    def reunite():
        if scene.locked:return
        scene.positions.clear();scene.save()

    def update_lock():
        lock_button.configure(text='解锁移动' if scene.locked else '锁定移动')
        grip.configure(cursor='arrow' if scene.locked else 'fleur',fg='#949b8d' if scene.locked else '#53644f')
        reset_button.configure(state='normal' if scene.mode=='free' and not scene.locked else 'disabled')

    def toggle_lock():
        nonlocal dragging
        dragging=None;canvas.configure(cursor='');scene.locked=not scene.locked
        scene.save();update_lock()
        if bridge:bridge.update_settings({'movement_locked':scene.locked})

    def open_settings():
        nonlocal settings_window
        if not bridge:return
        if settings_window and settings_window.exists():settings_window.window.lift();return
        if not bridge_snapshot:return
        from native_settings import SettingsWindow
        settings_window=SettingsWindow(root,ui_font,bridge,bridge_snapshot)

    bar=tk.Frame(root,bg='#e5e9dc')
    bar.place(x=10,y=8)
    def mode_button(text,command):
        button=tk.Button(bar,text=text,command=command,font=toolbar_font,bg='#f8f5e9',fg='#315b4c',relief='flat',cursor='hand2',takefocus=True)
        button.pack(side='left',padx=2,pady=3)
        return button
    free_button=mode_button('自由模式',lambda:choose_mode('free'))
    house_button=mode_button('黑工模式',lambda:choose_mode('house'))
    reset_button=mode_button('叠叠归队',reunite)
    lock_button=mode_button('锁定移动',toggle_lock)
    settings_button=mode_button('设置',open_settings)
    settings_button.configure(state='disabled')
    grip=tk.Label(bar,text=' ⠿ 移动整组 ',bg='#e5e9dc',fg='#53644f',cursor='fleur',font=toolbar_font)
    grip.pack(side='left')
    def grip_begin(e):
        nonlocal dragging
        if scene.locked:return
        dragging=None;drag[:]=[e.x_root-root.winfo_x(),e.y_root-root.winfo_y()]
    grip.bind('<ButtonPress-1>',grip_begin);grip.bind('<B1-Motion>',move);grip.bind('<ButtonRelease-1>',release)
    choose_mode(scene.mode)
    update_lock()

    def apply_scale(percent):
        nonlocal last_layout,dragging
        scene.desktop_scale=percent
        # Keep the entire pet usable on smaller screens as well.
        zoom=min(percent/100,(root.winfo_screenwidth()-20)/scene_size[0],
                 (root.winfo_screenheight()-60)/scene_size[1])
        zoom=max(.25,zoom)
        if abs(canvas.zoom-zoom)<.0001:return
        hide_details();dragging=None;canvas.configure(cursor='')
        canvas.set_zoom(zoom)
        toolbar_font.configure(size=-max(1,round(12*zoom)))
        bar.place_configure(x=round(10*zoom),y=round(8*zoom))
        for button in bar.winfo_children():
            if isinstance(button,tk.Button):
                button.configure(padx=round(3*zoom),pady=round(zoom))
                button.pack_configure(padx=round(2*zoom),pady=round(3*zoom))
        last_layout=None

    def choose_scale(percent):
        apply_scale(percent);scene.save()
        if bridge:bridge.update_settings({'desktop_scale':percent})

    def scale_wheel(e):
        index=SCALE_LEVELS.index(scene.desktop_scale)
        choose_scale(SCALE_LEVELS[max(0,min(len(SCALE_LEVELS)-1,index+(1 if e.delta>0 else -1)))])
        return 'break'

    apply_scale(scene.desktop_scale)

    def page_change(e):
        nonlocal page,last_layout
        hide_details()
        pages=shared_layout.pages(capacity)
        page=(page+(1 if e.delta<0 else -1))%pages
        last_layout=None

    def read_worker(key):
        worker=workers.items.get(key)
        if bridge and worker:
            from provider_links import open_conversation
            task=next((t for t in (bridge_snapshot or {}).get('tasks',[]) if t['id']==key),None)
            try:opened=bool(task and open_conversation(task))
            except OSError:opened=False
            if not opened:
                from tkinter import messagebox
                messagebox.showinfo('打开会话','此来源尚未提供可用的会话跳转链接。请在原软件中打开对应会话；未读状态会保留。',parent=root)
            return
        if worker and worker.unread:
            # Local acknowledgement only; no remote Codex read state is changed.
            workers.ingest({'agent_id':key,'thread_id':worker.thread_id,'method':'agent/read'},clock())
            if not args.demo:workers.save(snapshot)

    def restart(e=None):
        nonlocal stage,start,alert_started,last_tick,page
        if args.demo:
            workers.items.clear()
            workers.next_slot=0
            travel.positions.clear()
            page=0
            stage=-1
            start=clock()
            last_tick=start
            alert_started=None
            playback['replays']+=1

    def preview_easter():
        if not args.demo:return
        # Explicit preview only; real completions choose the rare variant once.
        now=clock()
        for worker in workers.items.values():
            if worker.at_desk:
                worker.has_computer=True
                worker.set_state('running',now)
                worker.set_state('completed',now)
                worker.easter_egg=True
                playback['eggs']+=1
                break

    canvas.bind('<ButtonPress-1>',begin)
    canvas.bind('<B1-Motion>',move)
    canvas.bind('<ButtonRelease-1>',release)
    canvas.bind('<MouseWheel>',page_change)
    canvas.bind('<Leave>',hide_details)
    context_menu=tk.Menu(root,tearoff=False,font=ui_font)
    scale_menu=tk.Menu(context_menu,tearoff=False,font=ui_font)
    menu_mode=tk.StringVar(root,value=scene.mode)
    menu_scale=tk.IntVar(root,value=scene.desktop_scale)
    def show_context(e):
        current=set(canvas.find_withtag('current'))
        selected=next((k for k,item in items.items() if item['sprite'] in current),None)
        selected_task=next((t for t in (bridge_snapshot or {}).get('tasks',[]) if t['id']==selected),None)
        hide_details()
        menu_mode.set(scene.mode);menu_scale.set(scene.desktop_scale)
        context_menu.delete(0,'end');scale_menu.delete(0,'end')
        context_menu.add_radiobutton(label='自由模式',variable=menu_mode,value='free',command=lambda:choose_mode('free'))
        context_menu.add_radiobutton(label='黑工模式',variable=menu_mode,value='house',command=lambda:choose_mode('house'))
        for percent in SCALE_LEVELS:
            scale_menu.add_radiobutton(label=str(percent)+'%',variable=menu_scale,value=percent,
                                      command=lambda p=percent:choose_scale(p))
        context_menu.add_cascade(label='缩放 · 当前 {}%'.format(round(canvas.zoom*100)),menu=scale_menu)
        context_menu.add_separator()
        context_menu.add_command(label='解锁移动' if scene.locked else '锁定移动',command=toggle_lock)
        context_menu.add_command(label='叠叠归队',command=reunite,
                                 state='normal' if scene.mode=='free' and not scene.locked else 'disabled')
        context_menu.add_command(label='设置…',command=open_settings,
                                 state='normal' if bridge and bridge_snapshot else 'disabled')
        if selected_task and selected_task.get('read_mode')!='app' and selected_task['unread_ids']:
            context_menu.add_command(label='确认已查看此结果',command=lambda:bridge.read(selected_task['unread_ids']))
        context_menu.add_separator()
        context_menu.add_command(label='退出桌宠',command=root.destroy)
        try:
            context_menu.tk_popup(root.winfo_pointerx(),root.winfo_pointery())
        finally:
            # Choosing Exit destroys the menu before tk_popup returns.
            try:context_menu.grab_release()
            except tk.TclError:pass
        return 'break'
    def dismiss_context(e=None):
        context_menu.unpost()
        hide_details()
        return 'break'
    root.bind('<Button-3>',show_context)
    root.bind('<Shift-F10>',show_context)
    root.bind('<Escape>',dismiss_context)
    canvas.bind('<Control-MouseWheel>',scale_wheel)
    root.bind('<r>',restart)
    root.bind('<R>',restart)
    if args.demo:
        replay_button=tk.Button(root,text='↻ 重播',command=restart,
                                font=('Microsoft YaHei UI',10),bg='#222222',fg='white',
                                activebackground='#444444',activeforeground='white',
                                relief='flat',cursor='hand2',takefocus=False)
        replay_button.place(relx=1,x=-12,y=10,anchor='ne')
        egg_button=tk.Button(root,text='彩蛋',command=preview_easter,
                             font=('Microsoft YaHei UI',10),bg='#222222',fg='white',
                             activebackground='#444444',activeforeground='white',
                             relief='flat',cursor='hand2',takefocus=False)
        egg_button.place(relx=1,x=-98,y=10,anchor='ne')

    def create(key):
        tag='worker-'+str(len(items))+'-'+str(time.monotonic_ns())
        tags=(tag,'pet-task-'+key)
        item={'plate':canvas.create_rectangle(0,0,0,0,fill='#111111',outline='#111111',tags=tags),
              'sprite':canvas.create_image(0,0,image=rest,anchor='nw',tags=tags),
              'prop':canvas.create_image(0,0,image=prop,anchor='nw',state='hidden'),
              'desk_prop':canvas.create_image(0,0,image=prop,anchor='nw',state='hidden'),
              'label':canvas.create_text(0,0,font=label_font,fill='#eeeeee',justify='center',tags=tags),
              'flower':[canvas.create_line(0,0,0,0,width=3,capstyle=tk.ROUND,fill='#16a9b1',state='hidden') for _ in range(8)],
              'glasses':[canvas.create_line(0,0,0,0,width=1,fill='#222222',state='hidden') for _ in range(3)],
              'position':None}
        canvas.tag_bind(tag,'<Double-Button-1>',lambda e,k=key:read_worker(k))
        for part in ('plate','label','sprite'):
            canvas.tag_bind(item[part],'<Enter>',lambda e,k=key:show_details(e,k))
            canvas.tag_bind(item[part],'<Motion>',lambda e,k=key:show_details(e,k))
            canvas.tag_bind(item[part],'<Leave>',hide_details)
        return item

    def tick():
        nonlocal stage,last_tick,last_layout,page,alert_started,last_report,saved_visual,bridge_snapshot,show_labels,dragging,bridge_offline,previous_unread,read_started
        now=clock()
        playback['ticks']+=1
        dt=min(.25,now-last_tick)
        last_tick=now
        elapsed=now-start
        if args.demo:
            current=int(elapsed/10)%10
            if current!=stage:
                stage=current
                playback['stages'].add(stage)
                for i in range(args.agents):
                    key=f'demo-{i}'
                    state='running'
                    if current==1 and i==0:state='waiting'
                    if current==3 and i%2==0:state='completed'
                    if current in [4,5,6]:state='completed'
                    if current==8:state=['failed','disconnected','review'][i%3]
                    workers.ingest({'thread_id':key,'agent_id':key,'label':f'演示{i+1}','state':state,
                                    'summary':['整理资料','检查代码','生成动画'][i%3]},now)
                    if current==5 and i%2==0 or current in [6,7,8,9]:
                        workers.ingest({'thread_id':key,'agent_id':key,'method':'agent/read'},now)
        elif bridge:
            received=bridge.poll()
            if received is not None:
                if settings_window and settings_window.exists():settings_window.update(received)
                if received.get('offline'):
                    bridge_offline=True
                    archived={t['id'] for t in (bridge_snapshot or {}).get('tasks',[]) if t.get('archived')}
                    for worker in workers.items.values():
                        if worker.key not in archived:worker.set_state('disconnected',now)
                    canvas.itemconfigure(footer,text='本地通知桥未连接 · 正在重试')
                else:
                    bridge_offline=False
                    bridge_snapshot=received
                    canvas.itemconfigure(footer,text='双击小包子打开会话 · 已读跟随原软件')
                    preferences=received.get('settings',{})
                    was_locked=scene.locked
                    scene.locked=preferences.get('movement_locked',False)
                    if scene.locked and not was_locked:dragging=None;canvas.configure(cursor='')
                    show_labels=preferences.get('show_labels',True)
                    apply_scale(preferences.get('desktop_scale',100))
                    if bool(root.attributes('-topmost'))!=preferences.get('always_on_top',True):
                        root.attributes('-topmost',preferences.get('always_on_top',True))
                    update_lock();settings_button.configure(state='normal')
                    tasks=received['tasks']
                    active={t['id'] for t in tasks}
                    for key in set(workers.items)-active:workers.items.pop(key)
                    for event in worker_events({**received,'tasks':tasks}):workers.ingest(event,now)
                    for task in tasks:workers.items[task['id']].slot=task['slot']
                    workers.next_slot=len(tasks)
        else:
            changed=False
            for event in tail.read():changed=workers.ingest(event,now) or changed
            if changed:workers.save(snapshot)
        leader[:]=scene.position('leader',[161,260],*scene_size,(BIG_WIDTH,BIG),True)
        workers.update(now)
        views=shared_layout.update([{'id':key,'order':w.slot,'gathered':w.completed,
                                    'needs_desk':not w.completed or w.at_desk}
                                   for key,w in workers.items.items()])
        def scene_desk(worker):
            view=views[worker.key]
            slot=view['desk_slot'] if view['desk_slot'] is not None else view['origin_slot']
            x,y=desk_position(slot,desk_cols,capacity)
            fallback=[x,y+80] if scene.mode=='house' else [x,max(65,y)]
            return scene.position(worker.key,fallback,*scene_size,(SMALL_WIDTH,SMALL))
        def scene_follow(worker,index):
            # Web uses the leader's top-left; Tk's leader image uses its centre.
            index=views[worker.key]['gather_index']
            base_y=leader[1]-BIG/2+130
            ox,oy=reunion_offset(index,len(shared_layout.gathered),min(120,scene_size[1]-base_y-SMALL-12))
            fallback=[leader[0]-BIG_WIDTH/2+164+ox,base_y+oy]
            return scene.position(worker.key,fallback,*scene_size,(SMALL_WIDTH,SMALL))
        travel.update(workers,leader,desk_cols,capacity,dt,now,scene_desk,scene_follow)
        playback['phases'].update(worker.phase for worker in workers.items.values())
        visual=tuple((k,w.at_desk,w.has_computer,w.phase if w.phase in {'closing','departing','following','returning'} else '')
                     for k,w in workers.items.items())
        if not args.demo and not bridge and visual!=saved_visual:
            workers.save(snapshot)
            saved_visual=visual
        for key in list(items):
            if key not in workers.items:
                old=items.pop(key)
                for name,value in old.items():
                    if name=='position':continue
                    for ident in value if isinstance(value,list) else [value]:canvas.delete(ident)
        for key in workers.items:
            if key not in items:items[key]=create(key)
        pages=shared_layout.pages(capacity)
        page=min(page,pages-1)
        desks=sorted((k for k in workers.items if views[k]['desk_slot'] is not None and views[k]['desk_slot']//capacity==page),key=lambda k:views[k]['desk_slot'])
        followers=[k for k in shared_layout.gathered if views[k]['desk_slot'] is None]
        visible=desks+followers
        slots=[views[k]['desk_slot']%capacity for k in desks]
        rows=1+max((s//desk_cols for s in slots),default=0)
        cols=1+max((s%desk_cols for s in slots),default=0)
        w,h=scene_size
        layout=(w,h,scene.mode,cols,rows,canvas.zoom)
        if layout!=last_layout:
            width,height=round(w*canvas.zoom),round(h*canvas.zoom)
            if last_layout is None and root.winfo_width()<=1:
                root.geometry(geometry(width,height,root.winfo_screenwidth(),root.winfo_screenheight()))
            else:
                x=max(0,min(root.winfo_x(),root.winfo_screenwidth()-width))
                y=max(0,min(root.winfo_y(),root.winfo_screenheight()-height-40))
                root.geometry(f'{width}x{height}+{x}+{y}')
            if scene.mode=='house':draw_house(canvas,desk_cols,max(2,rows))
            else:canvas.delete('house')
            last_layout=layout
        overall='disconnected' if bridge_offline else workers.overall_state
        if previous_unread and not workers.unread_count and overall=='idle':read_started=now
        previous_unread=workers.unread_count
        leader_worker.set_state(overall if overall!='unread' else 'idle',now)
        leader_worker.update(now)
        hop=math.sin(elapsed*1.7)
        leader_y=leader[1]+hop
        leader_frame=big
        leader_group='rest'
        alerting=bool(workers.unread_count and overall!='disconnected')
        if alerting:
            if alert_started is None:alert_started=now
            leader_frame,hop,sx,sy=bounce_frames[int(((now-alert_started)%CYCLE)/CYCLE*96)%96]
            # Scale about the actual foot baseline, not the image centre.
            leader_y=leader[1]+foot_offset*(1-sy)+hop
            canvas.coords(alert,leader[0],max(20,leader_y+head_offset*sy-24))
            canvas.itemconfigure(alert,state='normal')
        else:
            alert_started=None
            canvas.itemconfigure(alert,state='hidden')
            if overall!='idle':
                group,index=phase_frame(leader_worker,now,None)
                leader_group=group
                leader_frame=leader_groups[group][index] if group!='rest' else big
            elif now-read_started<8:
                leader_group,index=extended_frame('read',now-read_started)
                leader_frame=leader_groups[leader_group][index]
        canvas.itemconfigure(leader_sprite,image=leader_frame)
        padded=leader_group in EXTENDED_CLIPS
        # The laptop is pushed left of the ordinary body canvas. Ease into a
        # safe margin rather than clipping it at the desktop window's edge.
        overflow_x=0
        if leader_group=='disconnected':
            u=min(1,max(0,(now-leader_worker.phase_at-.15)/.7))
            overflow_x=max(0,64-(leader[0]-BIG_WIDTH/2))*u*u*(3-2*u)
        elif leader_group=='read':
            u=min(1,max(0,(now-read_started-1)/.9))
            overflow_x=max(0,26-(leader[0]-BIG_WIDTH/2))*u*u*(3-2*u)
        canvas.coords(leader_sprite,leader[0]+overflow_x+(EXTENDED_SIZE[0]/2-EXTENDED_ORIGIN[0]-BIG_WIDTH/2 if padded else 0),
                      leader_y+(EXTENDED_SIZE[1]/2-EXTENDED_ORIGIN[1]-BIG/2 if padded else 0))
        for j,ident in enumerate(leader_flower):
            angle=elapsed*2.2+j*math.tau/8
            cx,cy=leader[0]-22,leader[1]-99+hop
            canvas.coords(ident,cx+math.cos(angle)*5,cy+math.sin(angle)*5,cx+math.cos(angle)*15,cy+math.sin(angle)*15)
            canvas.itemconfigure(ident,state='normal' if overall=='running' else 'hidden',
                                 fill=['#096c78','#098593','#10a4ad','#18bec5','#43d2d7','#7be2e4','#49c4ca','#25a8b5'][j])
        canvas.itemconfigure(summary,text=('演示 · ' if args.demo else '')+LABELS[overall]+(f' ({workers.unread_count})' if workers.unread_count else ''))
        # Attach status to the visible animated feet, including the unread bounce.
        feet=leader_y+foot_offset*(sy if alerting else 1)
        if padded:feet=leader_y-BIG/2-EXTENDED_ORIGIN[1]+leader_bounds[leader_group][index][3]
        canvas.coords(summary,leader[0],min(h-38,feet+18))
        sx1,sy1,sx2,sy2=canvas.bbox(summary)
        canvas.coords(summary_box,sx1-7,sy1-4,sx2+7,sy2+4)
        canvas.coords(footer,18,53)
        canvas.itemconfigure(footer,anchor='nw',text=elide(f'{page+1}/{pages} 面 · 滚轮翻页 · {len(followers)}只归队 · '+('双击打开会话' if bridge else '双击分身已读'),lambda text:canvas.measure(ui_font,text),280))
        fx1,fy1,fx2,fy2=canvas.bbox(footer)
        canvas.coords(footer_box,10,48,fx2+8,fy2+5)
        displayed.clear()
        for key,item in items.items():
            for name,value in item.items():
                if name=='position':continue
                for ident in value if isinstance(value,list) else [value]:
                    canvas.itemconfigure(ident,state='hidden')
            if key not in visible:continue
            worker=workers.items[key]
            pos=travel.positions[key]
            x,y=pos.xy
            group,index=phase_frame(worker,now,pos)
            playback['groups'].add(group)
            frame=rest if group=='rest' else groups[group][index]
            age=now-worker.phase_at
            desk_slot=views[key]['desk_slot']
            dx,dy=desk_position(desk_slot if desk_slot is not None else views[key]['origin_slot'],desk_cols,capacity)
            if scene.mode=='house':
                dy+=80
            displayed[key]=[x,y]
            if desk_slot is not None and not worker.at_desk and worker.has_computer:
                canvas.coords(item['desk_prop'],dx+4,dy+70)
                canvas.itemconfigure(item['desk_prop'],state='normal')
            if worker.at_desk and worker.state=='running' and not pos.moving:
                phase=worker.phase
                if phase=='drop':
                    t=min(1,age/.85)
                    canvas.coords(item['prop'],x+4,y-25+95*t*t)
                    canvas.itemconfigure(item['prop'],state='normal')
                elif phase=='glasses':
                    gy=y+(175-45*min(1,age/.75))/3
                    for ident,cx in zip(item['glasses'][:2],[x+22,x+43]):
                        canvas.coords(ident,cx,gy,cx+13,gy,cx+13,gy+9,cx,gy+9,cx,gy)
                        canvas.itemconfigure(ident,state='normal')
                    canvas.coords(item['glasses'][2],x+35,gy+3,x+43,gy+3)
                    canvas.itemconfigure(item['glasses'][2],state='normal')
                if phase in {'typing','blink','drink'}:
                    for j,ident in enumerate(item['flower']):
                        a=elapsed*2.2+j*math.tau/8
                        cx,cy=x+33,y+10
                        canvas.coords(ident,cx+math.cos(a)*2.5,cy+math.sin(a)*2.5,cx+math.cos(a)*7,cy+math.sin(a)*7)
                        canvas.itemconfigure(ident,state='normal',fill=['#096c78','#098593','#10a4ad','#18bec5','#43d2d7','#7be2e4','#49c4ca','#25a8b5'][j])
            canvas.coords(item['sprite'],x-SMALL_LEFT_PADDING-(EXTENDED_ORIGIN[0]/3 if group in EXTENDED_CLIPS else 0),
                          y-(EXTENDED_ORIGIN[1]/3 if group in EXTENDED_CLIPS else 0)-(16 if group=='disconnected' else 0))
            canvas.itemconfigure(item['sprite'],image=frame,state='normal')
            label_x,label_y=(dx,dy) if scene.mode=='house' else (dx,max(65,dy))
            canvas.coords(item['plate'],label_x-10,label_y+84,label_x+95,label_y+126)
            canvas.itemconfigure(item['plate'],state='normal')
            canvas.coords(item['label'],label_x+42,label_y+105)
            status=LABELS[worker.state]+(' · 未读' if worker.unread else '')
            canvas.itemconfigure(item['label'],text=sign_text(worker.label,status,worker.summary,lambda text:canvas.measure(label_font,text),93),
                                 fill='#ffc07a' if worker.unread else '#eeeeee',state='normal')
            if not show_labels or desk_slot is None:
                canvas.itemconfigure(item['plate'],state='hidden');canvas.itemconfigure(item['label'],state='hidden')
        # One draw order for the global pile, independent of the house page.
        for key in followers: canvas.tag_raise(items[key]['sprite'])
        canvas.tag_raise(details_box);canvas.tag_raise(details_text)
        # A user can place followers beside/under the leader. Keep the badge out
        # of their actual opaque sprite bounds, not just above their draw order.
        sx1,sy1,sx2,sy2=canvas.coords(summary_box)
        for key in visible:
            if not workers.items[key].completed:continue
            x,y=displayed[key]
            left=x-SMALL_LEFT_PADDING+bounds[0]/rest_image.width*SMALL_WIDTH
            right=x-SMALL_LEFT_PADDING+bounds[2]/rest_image.width*SMALL_WIDTH
            top=y+bounds[1]/rest_image.height*SMALL
            bottom=y+bounds[3]/rest_image.height*SMALL
            if sx1<right and sx2>left and sy1<bottom and sy2>top:
                head=leader_y+head_offset*(sy if alerting else 1)
                canvas.coords(summary,leader[0],max(85,head-22))
                sx1,sy1,sx2,sy2=canvas.bbox(summary)
                canvas.coords(summary_box,sx1-7,sy1-4,sx2+7,sy2+4)
                break
        root.after(16,tick)
        if args.demo and time.monotonic()-last_report>=1:
            last_report=time.monotonic()
            report={'assets':FRAMES.name,'ticks':playback['ticks'],'stage':stage,'replays':playback['replays'],
                    'leader_state':overall,'workers':{key:worker.phase for key,worker in workers.items.items()}}
            (RUNTIME/'live-playback.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

    tick()
    root.after(150,lambda:(root.lift(),print('FAMILY_WINDOW_VISIBLE '+root.winfo_geometry(),flush=True)))
    if args.smoke_test:
        # Exercise both real buttons and the full 100s accelerated cycle.
        if args.demo:root.after(150,replay_button.invoke)
        if args.demo:root.after(2300,egg_button.invoke)
        def check_free_drag():
            x,y=map(round,leader)
            canvas.event_generate('<Motion>',x=x,y=y)
            canvas.event_generate('<ButtonPress-1>',x=x,y=y)
            assert dragging=='leader','Leader hit target must start individual drag'
            canvas.event_generate('<B1-Motion>',x=x+25,y=y+20)
            canvas.event_generate('<ButtonRelease-1>',x=x+25,y=y+20)
            assert scene.positions['leader']==[x+25,y+20]
            playback['scene_checks'].append('leader-pointer-drag')
            key=next(iter(displayed))
            x,y=map(round,displayed[key])
            canvas.event_generate('<Motion>',x=x+35,y=y+40)
            canvas.event_generate('<ButtonPress-1>',x=x+35,y=y+40)
            assert dragging==key,'Clone hit target must start individual drag'
            canvas.event_generate('<B1-Motion>',x=x+65,y=y+70)
            canvas.event_generate('<ButtonRelease-1>',x=x+65,y=y+70)
            assert (abs(scene.positions[key][0]-min(scene_size[0]-SMALL_WIDTH-8,x+30))<=1 and
                    abs(scene.positions[key][1]-min(scene_size[1]-SMALL-12,y+30))<=1),scene.positions[key]
            playback['scene_checks'].append('clone-pointer-drag')
            house_button.invoke()
        def check_house():
            assert scene.mode=='house' and canvas.find_withtag('house')
            assert scene.positions,'Changing modes must retain free placement'
            playback['scene_checks'].append('house-mode')
            free_button.invoke()
        def check_restore():
            assert scene.mode=='free' and not canvas.find_withtag('house')
            assert leader==scene.positions['leader']
            reset_button.invoke();assert not scene.positions
            playback['scene_checks'].append('free-restore-and-reunite')
        root.after(600,check_free_drag)
        root.after(1100,check_house)
        root.after(1400,check_restore)
        root.after(9200,root.destroy)
    root.mainloop()
    if bridge:bridge.close()
    if args.smoke_test:
        report={**playback,'stages':sorted(playback['stages']),'phases':sorted(playback['phases']),
                'groups':sorted(playback['groups'])}
        (RUNTIME/'playback-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('PLAYBACK_CHECK '+json.dumps(report),flush=True)
        required={'closing','departing','following','returning','typing'}
        if report['errors'] or len(report['scene_checks'])!=4 or args.demo and (len(report['stages'])!=10 or report['replays']!=1 or
               report['eggs']!=1 or not required.issubset(report['phases']) or
               not {'walk','easter','waiting','failure'}.issubset(report['groups'])):
            raise SystemExit(1)


if __name__=='__main__':main()
