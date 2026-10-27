"""Run in your Python editor: official browser login and account/model selection."""
import threading
from chatgpt_auth import CredentialStore,AuthError,sign_in,list_models,sign_out


def main():
    import tkinter as tk
    from tkinter import ttk,messagebox
    window=tk.Tk()
    window.title('LOResearch-Agent | Sign in with ChatGPT')
    window.geometry('760x550')
    window.minsize(680,500)
    frame=ttk.Frame(window,padding=22);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='LOResearch-Agent：连接 ChatGPT',font=('Microsoft YaHei UI',17)).pack(anchor='w',pady=(0,14))
    ttk.Label(frame,text='通过 OpenAI 官方浏览器授权使用你的 ChatGPT 计划。\n不需要在本程序填写账号密码或 API Key；授权不代表账号一定具备可用权限。',
              wraplength=690,justify='left').pack(anchor='w',pady=(0,12))
    ttk.Label(frame,text='1. 选择已保存的账号，或添加新账号').pack(anchor='w')
    accounts=ttk.Combobox(frame,state='readonly',width=75);accounts.pack(fill='x',pady=6)
    button=ttk.Button(frame,text='Continue with ChatGPT');button.pack(anchor='w',pady=(4,16))
    ttk.Label(frame,text='2. 获取当前账号实际可用的模型').pack(anchor='w')
    models=ttk.Combobox(frame,state='readonly',width=75);models.pack(fill='x',pady=6)
    actions=ttk.Frame(frame);actions.pack(fill='x',pady=5)
    refresh_button=ttk.Button(actions,text='刷新模型列表');refresh_button.pack(side='left')
    save_button=ttk.Button(actions,text='保存账号和模型');save_button.pack(side='left',padx=12)
    logout_button=ttk.Button(actions,text='退出所选账号');logout_button.pack(side='left')
    status=tk.StringVar(value='尚未连接。浏览器授权时请核对应用名称 LOResearch-Agent 和所选 ChatGPT 账号。')
    ttk.Label(frame,textvariable=status,wraplength=690,justify='left').pack(anchor='w',pady=18)
    ttk.Label(frame,text='保存后运行 06_run_chatgpt_agent.py，最多 6 次模型请求。\n将消耗授权的 ChatGPT 计划额度；本程序不会自动切换到付费 API Key。\n可在 ChatGPT 设置 → Usage 中查看应用使用情况。',
              wraplength=690,justify='left').pack(anchor='w',pady=5)
    store=CredentialStore();registered=[];catalog=[]
    busy=False

    def refresh_accounts():
        nonlocal registered
        public=store.public();registered=public['accounts']
        labels=['添加新账号 / 工作区']+[f"{x.get('email') or x['subject']}  [{x['client_id'][-10:]}]" for x in registered]
        accounts['values']=labels
        selected=next((i+1 for i,x in enumerate(registered) if x['client_id']==public['active']),0)
        accounts.current(selected)
    def selected():
        i=accounts.current()
        return registered[i-1]['client_id'] if i>0 else None
    def set_busy(value):
        nonlocal busy
        busy=value
        for b in (button,refresh_button,save_button,logout_button):
            b.configure(state='disabled' if value else 'normal')
        accounts.configure(state='disabled' if value else 'readonly')
    def failed(message):
        set_busy(False);status.set(message);messagebox.showerror('连接未完成',message)
    def async_work(work,done):
        if busy: return
        set_busy(True)
        def target():
            try:
                result=work()
                window.after(0,lambda value=result: finish(value))
            except Exception as exc:
                # Display only known safe errors, never URLs or raw credential data.
                message=str(exc) if isinstance(exc,AuthError) else '本机处理失败，请先确认依赖已安装；不要发送凭证文件。'
                window.after(0,lambda text=message: failed(text))
        def finish(result):
            set_busy(False);done(result)
        threading.Thread(target=target,daemon=True).start()
    def show_models(values,client_id):
        nonlocal catalog
        catalog=values
        models['values']=[f"{x['display_name']}  ({x['slug']})" for x in catalog]
        saved=store.public().get('models',{}).get(client_id)
        models.current(next((i for i,x in enumerate(catalog) if x['slug']==saved),0))
        status.set('模型列表已获取。请选择模型，再点击“保存账号和模型”。获取列表不会运行研究实验。')
    def login():
        choice=selected()
        status.set('请在自动打开的 OpenAI 官方页面登录并审阅授权，完成后回到此窗口。最长等待 5 分钟。')
        def done(result):
            refresh_accounts();catalog.clear();models.set('')
            if not result['plan_enabled']:
                status.set('账号登录成功，但未获得 ChatGPT 计划调用权限。请检查授权页面或账号资格；尚未发起研究请求。')
                return
            status.set('账号授权成功，正在获取可用模型列表。')
            async_work(lambda:list_models(store,result['client_id']),lambda values:show_models(values,result['client_id']))
        async_work(lambda:sign_in(store,choice),done)
    def refresh():
        choice=selected()
        if not choice: messagebox.showinfo('先登录','请先完成 Continue with ChatGPT。');return
        async_work(lambda:list_models(store,choice),lambda values:show_models(values,choice))
    def save():
        choice=selected();i=models.current()
        if not choice or i<0 or i>=len(catalog):
            messagebox.showinfo('尚未完成','请先登录并刷新当前账号的模型列表。');return
        p=store.public();p['active']=choice;p.setdefault('models',{})[choice]=catalog[i]['slug'];store.save_public(p)
        status.set('已保存。可以关闭本窗口，再运行 06_run_chatgpt_agent.py 开始自动研究。')
    def logout():
        choice=selected()
        if not choice: return
        def done(confirmed):
            refresh_accounts();catalog.clear();models.set('')
            status.set('已退出，远程会话已撤销。' if confirmed else '已清除本机令牌，但未确认远程撤销。可到 ChatGPT 设置中断开本应用。')
        async_work(lambda:sign_out(store,choice),done)
    def account_changed(event=None):
        catalog.clear();models.set('');models['values']=[]
        status.set('账号已切换，请刷新模型列表；添加新账号请点击 Continue with ChatGPT。')
    accounts.bind('<<ComboboxSelected>>',account_changed)
    button.configure(command=login);refresh_button.configure(command=refresh)
    save_button.configure(command=save);logout_button.configure(command=logout)
    refresh_accounts()
    window.mainloop()


if __name__=='__main__': main()
