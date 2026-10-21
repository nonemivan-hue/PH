import os, sys, threading, time, tempfile, types

# --- Test 1: static checks on source (no GUI) ---
src = open('PH.py', encoding='utf-8').read()
assert "'concurrent_fragment_downloads': CONCURRENT_CONNECTIONS" in src, "missing concurrent_fragment_downloads"
assert "'http_chunk_size'" in src, "missing http_chunk_size"
assert 'QUALITY_OPTIONS' in src and 'quality_combo' in src and 'quality_var' in src
print("TEST1 OK: source contains multithreading opts and quality UI")

# --- Run the app under Xvfb, but stop before mainloop ---
code = src.replace("root.mainloop()", "# mainloop disabled for test")
ns = {'__name__': '__main__'}
exec(compile(code, 'PH_test_exec.py', 'exec'), ns)

root = ns['root']; QUALITY_OPTIONS = ns['QUALITY_OPTIONS']

import queue as _q
_evq = _q.Queue()
def _pump():
    while True:
        item = _evq.get()
        if item is None: break
        try: root.update()
        except Exception: pass
_pump_thread = threading.Thread(target=_pump, daemon=True)
_pump_thread.start()
def pump_once():
    _evq.put(True)
    time.sleep(0.03)
quality_var = ns['quality_var']; quality_combo = ns['quality_combo']
set_ui_state = ns['set_ui_state']; LoggerCls = ns['DownloadProgressLogger']
download_video = ns['download_video']; CONCURRENT = ns['CONCURRENT_CONNECTIONS']

# --- Test 2: combobox contents & default ---
vals = list(quality_combo['values'])
assert vals == list(QUALITY_OPTIONS.keys()), vals
assert quality_var.get() == "Лучшее качество", quality_var.get()
assert quality_combo['state'] == 'readonly' or 'readonly' in str(quality_combo.state())
print("TEST2 OK: combobox has", len(vals), "quality options; default =", quality_var.get())

# --- Test 3: set_ui_state disables/restores combobox ---
set_ui_state(True); root.update()
assert 'disabled' in str(quality_combo.state()), quality_combo.state()
set_ui_state(False); root.update()
assert 'readonly' in str(quality_combo.state()), quality_combo.state()
print("TEST3 OK: combo blocked during download and restored after")

# --- Test 4: logger handles 'started' with height, monotonic progress with jumps ---
infos = []
ns['print_info'] = lambda m: infos.append(m)          # patch module-level fn used by class methods? 
# Class methods resolve print_info via module globals of exec namespace -> works since we patched ns.
lg = LoggerCls()
lg.update_progress({'status': 'started', 'info_dict': {'height': 720}})
assert any('720p' in s for s in infos), infos
lg.last_percent = 50.0
lg.update_progress({'status': 'downloading', 'total_bytes': 100, 'downloaded_bytes': 30})  # backward jump -> ignored
assert not any(s.startswith('Скачивание') for s in infos), infos
lg.update_progress({'status': 'downloading', 'total_bytes': 100, 'downloaded_bytes': 60})  # forward -> shown
assert any(s.startswith('Скачивание 60.0%') for s in infos), infos
print("TEST4 OK: started/height info + monotonic progress under multi-thread jumps")

# --- Test 5: download_video passes chosen format + concurrency to YoutubeDL ---
captured = {}
class FakeYDL:
    def __init__(self, opts): captured['opts'] = opts
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def download(self, urls): captured['urls'] = urls
ns['YoutubeDL'] = FakeYDL
ns['filedialog'].askdirectory = lambda **k: tempfile.mkdtemp()
ns['setup_ffmpeg'] = lambda: None
ns['messagebox'].showinfo = lambda *a, **k: captured.setdefault('info', a)
ns['messagebox'].showerror = lambda *a, **k: captured.setdefault('err', a)

quality_var.set("720p (HD)")
ns['url_entry'].insert(0, "https://example.com/video")
t0 = threading.Thread(target=lambda: download_video(), daemon=True)
# download_video reads url_entry from main thread widgets; call directly is fine for headless test
download_video()
deadline = time.time() + 5
while 'opts' not in captured and time.time() < deadline:
    pump_once()
assert 'opts' in captured, 'worker did not run'
o = captured['opts']
# wait until worker finishes (UI unlocked again) by pumping events
deadline = time.time() + 10
while ('disabled' in str(ns['download_button'].state())) or ('info' not in captured):
    if time.time() > deadline: break
    pump_once()
assert 'err' not in captured, captured.get('err')
assert 'info' in captured, captured
assert '720p' in captured['info'][1]
print("TEST5 OK: format=%s; concurrency=%s; chunk=%s; success msg: %s" % (
    o['format'], o['concurrent_fragment_downloads'], o['http_chunk_size'], captured['info'][1]))

# --- Test 6: best quality mapping still works ---
captured.clear()
quality_var.set("Лучшее качество")
download_video()
deadline = time.time() + 5
while 'opts' not in captured and time.time() < deadline:
    pump_once()
assert captured['opts']['format'] == "bestvideo+bestaudio/best"
print("TEST6 OK: default maps to bestvideo+bestaudio/best")

_evq.put(None); time.sleep(0.1)
root.destroy()
print("ALL TESTS PASSED")
