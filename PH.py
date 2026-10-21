import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from yt_dlp import YoutubeDL
import os
import platform
import requests
import zipfile
import shutil
import stat
import threading

# Определение платформы
OS_TYPE = platform.system()
ARCH = platform.machine()

# Определение путей для разных ОС
if OS_TYPE == "Windows":
    PROGRAM_DATA = os.environ.get('PROGRAMDATA', 'C:\\ProgramData')
    PH_DOWNLOAD_DIR = os.path.join(PROGRAM_DATA, 'PHdownload')
    FFMPEG_NAME = 'ffmpeg.exe'
elif OS_TYPE == "Darwin":  # macOS
    PH_DOWNLOAD_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'PHdownload')
    FFMPEG_NAME = 'ffmpeg'
elif OS_TYPE == "Linux":
    PH_DOWNLOAD_DIR = os.path.join(os.path.expanduser('~'), '.phdownload')
    FFMPEG_NAME = 'ffmpeg'
else:
    raise OSError("Unsupported operating system")

FFMPEG_PATH = os.path.join(PH_DOWNLOAD_DIR, FFMPEG_NAME)

# Функция для загрузки и установки FFmpeg
def setup_ffmpeg():
    if not os.path.exists(PH_DOWNLOAD_DIR):
        os.makedirs(PH_DOWNLOAD_DIR)
    
    if not os.path.exists(FFMPEG_PATH):
        # Определение URL для загрузки FFmpeg в зависимости от ОС
        if OS_TYPE == "Windows":
            url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
            zip_path = os.path.join(PH_DOWNLOAD_DIR, 'ffmpeg.zip')
        elif OS_TYPE == "Darwin":
            url = "https://evermeet.cx/ffmpeg/getrelease/zip"
            zip_path = os.path.join(PH_DOWNLOAD_DIR, 'ffmpeg.zip')
        elif OS_TYPE == "Linux":
            url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
            zip_path = os.path.join(PH_DOWNLOAD_DIR, 'ffmpeg.tar.xz')
        
        # Скачивание FFmpeg
        print_info(f"FFmpeg не найден. Скачивание: {url}")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        percent = downloaded * 100 / total_size
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        print_info(f"Загрузка FFmpeg: {percent:.1f}% ({mb_done:.1f} МБ из {mb_total:.1f} МБ)")
        print_info("Загрузка FFmpeg завершена.")
        
        # Распаковка
        if OS_TYPE == "Linux":
            import tarfile
            with tarfile.open(zip_path, 'r:xz') as tar_ref:
                tar_ref.extractall(PH_DOWNLOAD_DIR)
            # Перемещение ffmpeg
            extracted_folder = os.path.join(PH_DOWNLOAD_DIR, [d for d in os.listdir(PH_DOWNLOAD_DIR) if d.startswith('ffmpeg-')][0])
            shutil.move(os.path.join(extracted_folder, 'ffmpeg'), FFMPEG_PATH)
            shutil.rmtree(extracted_folder)
        else:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(PH_DOWNLOAD_DIR)
            # Перемещение ffmpeg
            if OS_TYPE == "Windows":
                extracted_folder = os.path.join(PH_DOWNLOAD_DIR, 'ffmpeg-master-latest-win64-gpl', 'bin')
                shutil.move(os.path.join(extracted_folder, 'ffmpeg.exe'), FFMPEG_PATH)
                shutil.rmtree(os.path.join(PH_DOWNLOAD_DIR, 'ffmpeg-master-latest-win64-gpl'))
            elif OS_TYPE == "Darwin":
                shutil.move(os.path.join(PH_DOWNLOAD_DIR, 'ffmpeg'), FFMPEG_PATH)
        
        # Установка прав на выполнение для macOS и Linux
        if OS_TYPE in ["Darwin", "Linux"]:
            os.chmod(FFMPEG_PATH, stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH)
        
        # Удаление временных файлов
        os.remove(zip_path)

# Элементы интерфейса для отображения процесса скачивания (создаются позже)
progress_bar = None
status_label = None
progress_bar_var = None


def set_progress(percent):
    """Обновляет индикатор выполнения (0-100) и метку процента."""
    percent = max(0.0, min(float(percent), 100.0))
    if progress_bar_var is not None:
        root.after(0, lambda p=percent: progress_bar_var.set(p))


def set_ui_state(downloading):
    """Блокирует/разблокирует элементы управления на время скачивания."""
    if download_button is not None:
        state = 'disabled' if downloading else 'normal'
        def _apply():
            download_button.configure(state=state)
            paste_button.configure(state=state)
            url_entry.configure(state='readonly' if downloading else 'normal')
        root.after(0, _apply)


def print_info(message):
    """Выводит информационное сообщение в статус-бар и консоль."""
    print(message)
    if status_label is not None:
        root.after(0, lambda: status_label.configure(text=message))


class DownloadProgressLogger:
    """Логгер yt-dlp, выводящий процесс скачивания в интерфейс."""
    def __init__(self):
        self.filename = ''
        self.last_percent = -1

    def debug(self, msg):
        # yt-dlp отправляет служебные сообщения через tqdm — не выводим их
        pass

    def info(self, msg):
        text = str(msg)
        if text.startswith('[download]'):
            if 'Destination:' in text:
                name = text.split('Destination:', 1)[-1].strip()
                self.filename = os.path.basename(name)
                print_info(f"Файл: {self.filename}")
            elif 'has already been downloaded' in text:
                print_info("Файл уже был скачан ранее.")
            elif '%' in text and ' of ' in text:
                try:
                    percent = float(text.split('%', 1)[0].replace('[download]', '').strip())
                    speed_part = ''
                    if ' at ' in text:
                        rest = text.split(' at ', 1)[1]
                        speed_part = ' Скорость: ' + rest.split(' ETA')[0].strip()
                    eta_part = ''
                    if ' ETA ' in text:
                        eta_part = ' Осталось: ' + text.split(' ETA ', 1)[1].strip()
                    # Обновляем индикатор при каждом прогрессе (не чаще 1 раза на процент)
                    if abs(percent - self.last_percent) >= 0.99 or percent >= 100:
                        self.last_percent = percent
                        set_progress(percent)
                        print_info(f"Скачивание {percent:.1f}%{speed_part}{eta_part}")
                except (IndexError, ValueError):
                    pass
            elif 'Finished downloading' in text:
                print_info("Загрузка потока завершена.")
        elif text.startswith('[Merger]') or 'Merging formats' in text:
            print_info("Объединение видео и аудио (FFmpeg)...")
        elif 'Extracting' in text:
            print_info("Извлечение информации о видео...")

    def update_progress(self, d):
        """Progress-hook yt-dlp: точный процент из словаря состояния."""
        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            done = d.get('downloaded_bytes') or 0
            speed = d.get('speed') or 0
            eta = d.get('eta')
            if total and done is not None:
                percent = min(done * 100.0 / total, 100.0)
                if abs(percent - self.last_percent) >= 0.99 or percent >= 100:
                    self.last_percent = percent
                    set_progress(percent)
                    speed_txt = f" {speed / 1024 / 1024:.2f} МБ/с" if speed else ""
                    eta_txt = f" ETA {eta} c" if eta is not None else ""
                    mb_done = done / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    print_info(f"Скачивание {percent:.1f}% ({mb_done:.1f} из {mb_total:.1f} МБ){speed_txt}{eta_txt}")
        elif status == 'finished':
            print_info("Загрузка потока завершена. Обработка...")
        elif status == 'error':
            print_info("Ошибка при загрузке фрагмента, повторная попытка...")

    def warning(self, msg):
        print(f"[Предупреждение] {msg}")

    def error(self, msg):
        print(f"[Ошибка] {msg}")


# Функция для скачивания видео
def download_video():
    url = url_entry.get()
    save_path = filedialog.askdirectory(title="Выберите папку для сохранения")
    
    if not url:
        messagebox.showerror("Ошибка", "Введите URL видео!")
        return
    
    if not save_path:
        messagebox.showerror("Ошибка", "Выберите папку для сохранения!")
        return
    
    # Блокируем интерфейс и запускаем скачивание в отдельном потоке
    set_ui_state(True)
    set_progress(0)
    print_info("Подготовка к скачиванию...")

    def worker():
        try:
            # Убедимся, что FFmpeg установлен
            setup_ffmpeg()

            logger = DownloadProgressLogger()

            ydl_opts = {
                'outtmpl': f'{save_path}/%(title)s.%(ext)s',
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
                'ffmpeg_location': FFMPEG_PATH,
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                'logger': logger,
                'progress_hooks': [logger.update_progress],
                'noplaylist': True,
            }

            with YoutubeDL(ydl_opts) as ydl:
                print_info("Получение информации о видео...")
                ydl.download([url])

            set_progress(100)
            print_info("Готово!")
            root.after(0, lambda: messagebox.showinfo("Успех", "Видео успешно скачано в максимальном качестве!"))
        except Exception as e:
            print_info(f"Ошибка: {str(e)}")
            root.after(0, lambda err=e: messagebox.showerror("Ошибка", f"Произошла ошибка: {str(err)}"))
        finally:
            set_ui_state(False)

    threading.Thread(target=worker, daemon=True).start()

# Настройка современного дизайна
def set_custom_theme(root):
    root.configure(bg='#1a1a1a')
    style = ttk.Style()
    style.theme_use('clam')
    
    # Стили
    style.configure('TFrame', background='#1a1a1a')
    style.configure('TLabel', background='#1a1a1a', foreground='#ffffff', font=('Helvetica', 16, 'bold'))
    style.configure('TEntry', fieldbackground='#2d2d2d', foreground='#ffffff', font=('Helvetica', 12), 
                   relief='flat', padding=10, borderwidth=0, insertbackground='#ff9900')
    
    # Кнопка скачивания
    style.configure('Download.TButton', background='#ff9900', foreground='#000000', 
                   font=('Helvetica', 12, 'bold'), padding=12, relief='flat', borderwidth=0)
    style.map('Download.TButton', 
             background=[('active', '#e68a00'), ('disabled', '#666666')],
             foreground=[('active', '#000000')])
    
    # Кнопка вставки
    style.configure('Paste.TButton', background='#333333', foreground='#ff9900', 
                   font=('Helvetica', 10, 'bold'), padding=6, relief='flat', borderwidth=0)
    style.map('Paste.TButton', 
             background=[('active', '#444444')],
             foreground=[('active', '#ffaa33')])

    # Индикатор выполнения
    style.configure('Custom.Horizontal.TProgressbar',
                    troughcolor='#2d2d2d', background='#ff9900',
                    lightcolor='#ff9900', darkcolor='#ff9900', borderwidth=0)

    # Статус-бар
    style.configure('Status.TLabel', background='#111111', foreground='#bbbbbb',
                   font=('Helvetica', 10))

# Функция для вставки ссылки из буфера обмена
def paste_url():
    try:
        url = root.clipboard_get()
        url_entry.delete(0, tk.END)
        url_entry.insert(0, url)
    except:
        messagebox.showerror("Ошибка", "Не удалось вставить ссылку из буфера обмена!")

# Создание интерфейса
root = tk.Tk()
root.title("PornHub Video Downloader")
root.geometry("700x380")
root.resizable(False, False)

# Применение темы
set_custom_theme(root)

# Основной фрейм
main_frame = ttk.Frame(root)
main_frame.pack(expand=True, fill='both', padx=20, pady=(20, 10))

# Заголовок
title_label = ttk.Label(main_frame, text="PornHub Video Downloader", font=('Helvetica', 24, 'bold'), foreground='#ff9900')
title_label.pack(pady=(0, 20))

# Поле ввода и кнопка вставки
input_frame = ttk.Frame(main_frame)
input_frame.pack(fill='x', pady=10)

url_entry = ttk.Entry(input_frame, width=50)
url_entry.pack(side='left', fill='x', expand=True, padx=(0, 10))

paste_button = ttk.Button(input_frame, text="Вставить", command=paste_url, style='Paste.TButton')
paste_button.pack(side='left')

# Кнопка скачивания
download_button = ttk.Button(main_frame, text="Скачать видео", command=download_video, style='Download.TButton')
download_button.pack(pady=10)

# Индикатор процесса скачивания
progress_frame = ttk.Frame(main_frame)
progress_frame.pack(fill='x', pady=(10, 0))

progress_bar = ttk.Progressbar(progress_frame, orient='horizontal', length=100,
                               mode='determinate', maximum=100,
                               style='Custom.Horizontal.TProgressbar')
progress_bar.pack(fill='x', side='left', expand=True)

percent_label = ttk.Label(progress_frame, text="0%", width=6, anchor='e')
percent_label.pack(side='left', padx=(10, 0))

# Статус-бар с информационным процессом скачивания
status_frame = tk.Frame(root, bg='#111111')
status_frame.pack(fill='x', side='bottom')

status_label = ttk.Label(status_frame, text="Готов к работе. Вставьте ссылку и нажмите «Скачать видео».",
                         anchor='w', style='Status.TLabel')
status_label.pack(fill='x', padx=10, pady=5)


def update_percent_label(*args):
    """Синхронизирует текстовую метку процента с индикатором."""
    percent_label.configure(text=f"{progress_bar_var.get():.0f}%")

progress_bar_var = tk.DoubleVar()
progress_bar.configure(variable=progress_bar_var)
progress_bar_var.trace_add('write', update_percent_label)

# Запуск
root.mainloop()