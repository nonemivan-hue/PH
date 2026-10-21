# E2E: реальное скачивание в фоновом потоке, mainloop крутится в основном потоке
import time, threading, tempfile, os
src = open('PH.py', encoding='utf-8').read()

test_src = src.replace('root.mainloop()', '''
result = {'done': False, 'err': None}
def worker():
    try:
        save_path = tempfile.mkdtemp()
        url = "https://www.w3schools.com/html/mov_bbb.mp4"
        set_ui_state(True)
        set_progress(0)
        print_info("Подготовка к скачиванию...")
        logger = DownloadProgressLogger()
        ydl_opts = {
            'outtmpl': f'{save_path}/%(title)s.%(ext)s',
            'format': 'best',
            'logger': logger,
            'progress_hooks': [logger.update_progress],
            'noplaylist': True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        set_progress(100)
        print_info("Готово!")
        result['files'] = os.listdir(save_path)
        result['done'] = True
    except Exception as e:
        result['err'] = str(e)
        print_info(f"Ошибка: {e}")
    finally:
        set_ui_state(False)

threading.Thread(target=worker, daemon=True).start()

def poll():
    if not (result['done'] or result['err']):
        root.after(50, poll)
    else:
        def check():
            print("FINAL STATUS:", status_label.cget("text"))
            print("BAR:", progress_bar_var.get(), "LABEL:", percent_label.cget("text"))
            print("ERR:", result['err'])
            print("FILES:", result.get('files'))
            assert result['err'] is None, result['err']
            assert result['done']
            assert any(f.endswith('.mp4') for f in result.get('files', []))
            assert abs(progress_bar_var.get() - 100.0) < 0.6
            assert str(download_button["state"]) == "normal"
            print("E2E DOWNLOAD TEST PASSED")
            root.destroy()
        root.after(100, check)

root.after(50, poll)
root.mainloop()
''')
exec(compile(test_src, 'PH.py', 'exec'), {'__name__': '__main__'})
