"""Реальный прогон: многопоточная загрузка фрагментов + выбор качества (качество 360p)."""
import tempfile, os, threading, time

src = open('PH.py', encoding='utf-8').read()
code = src.replace("root.mainloop()", "# manual")
ns = {'__name__': '__main__'}
exec(compile(code, 'PH_exec.py', 'exec'), ns)
root = ns['root']

out_dir = tempfile.mkdtemp()
ns['filedialog'].askdirectory = lambda **k: out_dir
done = {}
ns['messagebox'].showinfo = lambda t_, m_: done.setdefault('info', m_)
ns['messagebox'].showerror = lambda t_, m_: done.setdefault('err', m_)

def ui_click():
    ns['url_entry'].insert(0, "https://media.w3.org/2010/05/sintel/trailer.mp4")
    ns['quality_var'].set("360p")
    ns['download_video']()
root.after(100, ui_click)
deadline = time.time() + 90
while not done and time.time() < deadline:
    root.update(); time.sleep(0.05)
root.destroy()

assert 'err' not in done, done.get('err')
assert 'info' in done, "timeout"
files = [f for f in os.listdir(out_dir) if not f.endswith('.part')]
print("REAL DOWNLOAD PASSED:", done['info'], "| files:", files)
fmt_used = None
