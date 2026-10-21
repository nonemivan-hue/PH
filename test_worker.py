"""Тест worker-потока приложения: качество + многопоточная загрузка (реальный Tk mainloop)."""
import threading, time

src = open('PH.py', encoding='utf-8').read()
code = src.replace("root.mainloop()", "# mainloop started manually by test")
ns = {'__name__': '__main__'}
exec(compile(code, 'PH_test_exec.py', 'exec'), ns)

root = ns['root']
QUALITY_OPTIONS = ns['QUALITY_OPTIONS']
captured = {}

class FakeYDL:
    def __init__(self, opts):
        captured['opts'] = opts
        self.opts = opts
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def download(self, urls):
        captured['urls'] = urls
        # имитация прогресса из worker-потока через реальные хуки приложения
        lg = self.opts['logger']; ph = self.opts['progress_hooks'][0]
        lg.info("[download] Destination: /tmp/test/видео.f720.mp4")
        ph({'status': 'started', 'info_dict': {'height': 720}})
        for pct in (10, 25, 60, 100):
            ph({'status': 'downloading', 'total_bytes': 1000, 'downloaded_bytes': pct * 10,
                'speed': 2_000_000, 'eta': 3})
ns['YoutubeDL'] = FakeYDL
import tempfile
ns['filedialog'].askdirectory = lambda **k: tempfile.mkdtemp()
ns['setup_ffmpeg'] = lambda: None
done = {}
def fake_showinfo(title, msg): done['info'] = msg
def fake_showerror(title, msg): done['err'] = msg
ns['messagebox'].showinfo = fake_showinfo
ns['messagebox'].showerror = fake_showerror

# выбор качества и запуск из потока UI (как при нажатии кнопки)
def ui_click():
    ns['quality_var'].set("720p (HD)")
    ns['url_entry'].insert(0, "https://example.com/v")
    ns['download_video']()
root.after(100, ui_click)
root.after(4000, root.quit)
root.mainloop()

o = captured.get('opts')
assert o is not None, "worker не выполнился"
assert o['format'] == QUALITY_OPTIONS["720p (HD)"], o['format']
assert o['concurrent_fragment_downloads'] == ns['CONCURRENT_CONNECTIONS'] == 8
assert o['http_chunk_size'] == 10 * 1024 * 1024
assert 'err' not in done, done.get('err')
assert done.get('info') and '720p (HD)' in done['info'], done
assert 'disabled' not in str(ns['download_button'].state()), ns['download_button'].state()
assert 'readonly' in str(ns['quality_combo'].state()), ns['quality_combo'].state()
assert abs(ns['progress_bar_var'].get() - 100.0) < 0.01, ns['progress_bar_var'].get()
assert ns['percent_label'].cget('text') == '100%', ns['percent_label'].cget('text')
print("WORKER TEST PASSED:")
print("  format:", o['format'])
print("  concurrent_fragment_downloads:", o['concurrent_fragment_downloads'])
print("  http_chunk_size:", o['http_chunk_size'])
print("  success dialog:", done['info'])
print("  progress bar:", ns['progress_bar_var'].get(), "| label:", ns['percent_label'].cget('text'))
print("  status bar:", ns['status_label'].cget('text'))
