import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from yt_dlp import YoutubeDL
try:
    from yt_dlp.utils import UserNotAuthorized  # доступен в новых версиях yt-dlp
except ImportError:
    class UserNotAuthorized(Exception):
        pass
import queue
import os
import platform
import requests
import zipfile
import shutil
import stat
import threading

# Проверка доступности «браузерного» impersonation для обхода защит сайтов.
# Требуется пакет curl_cffi: pip install "yt-dlp[default,curl-cffi]"
def _check_impersonate():
    try:
        from yt_dlp import YoutubeDL
        ydl = YoutubeDL({'quiet': True, 'logger': None})
        handler = ydl._request_director.handlers.get('CurlCFFI')
        targets = getattr(handler, 'supported_targets', ()) or ()
        return any(getattr(t, 'client', '') == 'chrome' for t in targets)
    except Exception:
        return False


IMPERSONATE_AVAILABLE = _check_impersonate()

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

# Очередь сообщений от фоновых потоков в интерфейс (обработчик запускается позже)
ui_queue = queue.Queue()


def _process_ui_queue():
    """Обрабатывает сообщения из фонового потока в главном цикле Tk."""
    try:
        while True:
            func = ui_queue.get_nowait()
            try:
                func()
            except Exception:
                pass
    except queue.Empty:
        pass
    root.after(50, _process_ui_queue)


def post_to_ui(func):
    """Безопасно передаёт колбэк для выполнения в потоке интерфейса."""
    ui_queue.put(func)

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

# Варианты выбора качества видео: отображаемый текст -> формат yt-dlp
QUALITY_OPTIONS = {
    "Лучшее качество": "bestvideo+bestaudio/best",
    "2160p (4K)": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
    "1440p (2K)": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
    "1080p (Full HD)": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p (HD)": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
}

# Количество параллельных потоков загрузки фрагментов
CONCURRENT_CONNECTIONS = 8

# Пользовательский заголовок User-Agent (задаётся явно, чтобы не зависеть
# от дефолтного UA yt-dlp, который сайты-защиты блокируют охотнее всего)
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36')


def get_impersonate_target():
    """Возвращает строку цели impersonation по первому доступному Chrome-таргету."""
    try:
        from yt_dlp import YoutubeDL
        ydl = YoutubeDL({'quiet': True})
        handler = ydl._request_director.handlers.get('CurlCFFI')
        targets = getattr(handler, 'supported_targets', ()) or ()
        for t in targets:
            if getattr(t, 'client', '') == 'chrome' and getattr(t, 'version', None):
                return f"chrome-{t.version}"
        return 'chrome'
    except Exception:
        return 'chrome'


def build_error_message(err):
    """Формирует человекочитаемое описание ошибки yt-dlp с подсказками."""
    text = str(err)
    low = text.lower()
    # Извлекаем код HTTP-статуса, если он есть в сообщении
    status = ''
    import re
    m = re.search(r'HTTP Error (\d{3})', text)
    if m:
        status = m.group(1)

    if isinstance(err, UserNotAuthorized) or status in ('401', '403'):
        return (f"{text}\n\nСайт отклонил запрос (ошибка {status or '401/403'}):\n"
                "• видео может требовать входа в аккаунт — передайте cookies;\n"
                "• или включите «браузерное» представление: установите пакет curl_cffi\n"
                "  (pip install \"yt-dlp[default,curl-cffi]\") и/или включите чтение\n"
                "  cookies из браузера на панели настроек.")
    if status == '410':
        return (f"{text}\n\nОшибка 410 Gone означает, что страница больше не существует:\n"
                "• проверьте, что ссылка полная и актуальная (видео могли удалить или перенести);\n"
                "• откройте страницу в браузере и скопируйте адрес заново;\n"
                "• обновите yt-dlp до последней версии (pip install -U yt-dlp).")
    if status == '404':
        return f"{text}\n\nСтраница по ссылке не найдена (404). Проверьте правильность URL."
    if 'unable to extract' in low or 'unsupported url' in low:
        return (f"{text}\n\nОбновите yt-dlp до последней версии: pip install -U yt-dlp\n"
                "или установите ночную сборку: pip install --pre -U yt-dlp-nightly-builds")
    return text


def set_progress(percent):
    """Обновляет индикатор выполнения (0-100) и метку процента."""
    percent = max(0.0, min(float(percent), 100.0))
    if progress_bar_var is not None:
        post_to_ui(lambda p=percent: progress_bar_var.set(p))


def set_ui_state(downloading):
    """Блокирует/разблокирует элементы управления на время скачивания."""
    if download_button is not None:
        state = 'disabled' if downloading else 'normal'
        def _apply():
            download_button.configure(state=state)
            paste_button.configure(state=state)
            browse_button.configure(state=state)
            quality_combo.configure(state='disabled' if downloading else 'readonly')
            url_entry.configure(state='readonly' if downloading else 'normal')
            cookie_entry.configure(state='readonly' if downloading else 'normal')
            for cb in (cookie_browser_check, cookie_file_check):
                cb.configure(state=state)
        post_to_ui(_apply)


def print_info(message):
    """Выводит информационное сообщение в статус-бар и консоль."""
    print(message)
    if status_label is not None:
        post_to_ui(lambda: status_label.configure(text=message))


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
                # При многопоточной загрузке (несколько соединений) проценты
                # могут «прыгать» между потоками — показываем только рост прогресса
                if percent >= 100 or percent - self.last_percent >= 0.99:
                    self.last_percent = percent
                    set_progress(percent)
                    speed_txt = f" {speed / 1024 / 1024:.2f} МБ/с" if speed else ""
                    eta_txt = f" ETA {eta} c" if eta is not None else ""
                    mb_done = done / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    print_info(f"Скачивание {percent:.1f}% ({mb_done:.1f} из {mb_total:.1f} МБ){speed_txt}{eta_txt}")
        elif status == 'started':
            info = d.get('info_dict') or {}
            height = info.get('height')
            if height:
                print_info(f"Загружаемое качество: {height}p")
        elif status == 'finished':
            print_info("Загрузка потока завершена. Обработка...")
        elif status == 'error':
            print_info("Ошибка при загрузке фрагмента, повторная попытка...")

    def warning(self, msg):
        print(f"[Предупреждение] {msg}")

    def error(self, msg):
        print(f"[Ошибка] {msg}")


def build_ydl_opts(save_path, fmt, cookie_source='none', cookie_file=''):
    """Собирает настройки YoutubeDL с учётом выбранных параметров загрузки.

    cookie_source: 'none' | 'browser' | 'file'
    Возвращает словарь opts; при недоступности curl_cffi молча работает
    со стандартным HTTP-клиентом, но с актуальным User-Agent.
    """
    ydl_opts = {
        'outtmpl': f'{save_path}/%(title)s.%(ext)s',
        'format': fmt,
        'merge_output_format': 'mp4',
        'ffmpeg_location': FFMPEG_PATH,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'noplaylist': True,
        # Многопоточная загрузка: файл разбивается на фрагменты,
        # которые скачиваются параллельно в несколько потоков
        'concurrent_fragment_downloads': CONCURRENT_CONNECTIONS,
        'http_chunk_size': 10 * 1024 * 1024,  # 10 МБ на фрагмент
        # Заголовки «как у браузера» — снижает число блокировок со стороны CDN
        'http_headers': {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru,en-US;q=0.9,en;q=0.8',
            'Referer': 'https://www.pornhub.com/',
        },
    }

    logger = DownloadProgressLogger()
    ydl_opts['logger'] = logger
    ydl_opts['progress_hooks'] = [logger.update_progress]

    # Чтение cookies из браузера (помогает для видео, требующих входа)
    if cookie_source == 'browser':
        ydl_opts['cookiesfrombrowser'] = ('chrome',)
    elif cookie_source == 'file' and cookie_file:
        ydl_opts['cookiefile'] = cookie_file

    # Браузерное представление (impersonation) — если доступен curl_cffi.
    # Убирает предупреждение «The extractor is attempting impersonation,
    # but no impersonate target is available».
    if IMPERSONATE_AVAILABLE:
        ydl_opts['impersonate'] = get_impersonate_target()

    return ydl_opts


# Функция для скачивания видео
def download_video():
    url = url_entry.get().strip()
    save_path = filedialog.askdirectory(title="Выберите папку для сохранения")

    if not url:
        messagebox.showerror("Ошибка", "Введите URL видео!")
        return

    # Проверка ссылки: не «съеденный» фрагмент и отсутствие лишних символов.
    # Неполные/грязные URL — частая причина ошибок 410 Gone / 404.
    if '://' not in url:
        messagebox.showerror(
            "Ошибка",
            "Похоже, ссылка скопирована не полностью.\n"
            "URL должен начинаться с https:// (например, https://www.pornhub.com/view_video.php?viewkey=...)")
        return
    bad_chars = [c for c in url if c.isspace()]
    if bad_chars:
        messagebox.showerror(
            "Ошибка",
            "Ссылка содержит пробелы или переносы строк — скопируйте адрес целиком из адресной строки браузера.")
        return

    if not save_path:
        messagebox.showerror("Ошибка", "Выберите папку для сохранения!")
        return

    # Выбранное качество видео
    quality_label = quality_var.get()
    fmt = QUALITY_OPTIONS.get(quality_label, "bestvideo+bestaudio/best")

    # Источник cookies из интерфейса
    cookie_source = cookie_var.get()  # 'none' | 'browser' | 'file'
    cookie_file = cookie_file_var.get().strip() if cookie_source == 'file' else ''
    if cookie_source == 'file':
        if not cookie_file:
            messagebox.showerror("Ошибка", "Укажите файл cookies (формат Netscape).")
            return
        if not os.path.isfile(cookie_file):
            messagebox.showerror("Ошибка", f"Файл cookies не найден:\n{cookie_file}")
            return

    # Блокируем интерфейс и запускаем скачивание в отдельном потоке
    set_ui_state(True)
    set_progress(0)
    print_info(f"Подготовка к скачиванию (качество: {quality_label})...")

    def worker():
        try:
            # Убедимся, что FFmpeg установлен
            setup_ffmpeg()

            ydl_opts = build_ydl_opts(save_path, fmt, cookie_source, cookie_file)

            with YoutubeDL(ydl_opts) as ydl:
                print_info("Получение информации о видео...")
                ydl.download([url])

            set_progress(100)
            print_info("Готово!")
            post_to_ui(lambda: messagebox.showinfo(
                "Успех", f"Видео успешно скачано в качестве «{quality_label}»!"))
        except Exception as e:
            msg = build_error_message(e)
            print_info(f"Ошибка: {str(e)}")
            post_to_ui(lambda err=msg: messagebox.showerror("Ошибка", err))
        finally:
            set_ui_state(False)

    threading.Thread(target=worker, daemon=True).start()


def browse_cookie_file():
    """Открывает диалог выбора файла cookies и подставляет путь."""
    path = filedialog.askopenfilename(
        title="Выберите файл cookies (Netscape format)",
        filetypes=[("Cookies", "*.txt"), ("Все файлы", "*.*")])
    if path:
        cookie_file_var.set(path)
        cookie_var.set('file')

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

    # Флажки (чекбоксы) панели настроек
    style.configure('Check.TLabel', background='#1a1a1a', foreground='#bbbbbb',
                    font=('Helvetica', 10))
    style.configure('TCheckbutton', background='#1a1a1a', foreground='#ffffff',
                    font=('Helvetica', 10))
    style.map('TCheckbutton',
              background=[('active', '#1a1a1a')],
              foreground=[('disabled', '#666666')])

    # Выбор качества (Combobox)
    style.configure('Quality.TCombobox',
                    fieldbackground='#2d2d2d', background='#2d2d2d',
                    foreground='#ffffff', arrowcolor='#ff9900',
                    font=('Helvetica', 11, 'bold'), padding=6,
                    borderwidth=0, relief='flat')
    style.map('Quality.TCombobox',
              fieldbackground=[('readonly', '#2d2d2d'), ('disabled', '#222222')],
              foreground=[('readonly', '#ff9900'), ('disabled', '#666666')],
              selectbackground=[('readonly', '#2d2d2d')],
              selectforeground=[('readonly', '#ff9900')])
    root.option_add('*TCombobox*Listbox.background', '#2d2d2d')
    root.option_add('*TCombobox*Listbox.foreground', '#ffffff')
    root.option_add('*TCombobox*Listbox.selectBackground', '#ff9900')
    root.option_add('*TCombobox*Listbox.selectForeground', '#000000')

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
root.geometry("700x560")
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

# Выбор качества видео
quality_frame = ttk.Frame(main_frame)
quality_frame.pack(fill='x', pady=(5, 0))

quality_label_caption = ttk.Label(quality_frame, text="Качество:", font=('Helvetica', 12, 'bold'))
quality_label_caption.pack(side='left', padx=(0, 10))

quality_var = tk.StringVar(value="Лучшее качество")
quality_combo = ttk.Combobox(quality_frame, textvariable=quality_var,
                             values=list(QUALITY_OPTIONS.keys()),
                             state='readonly', width=20, style='Quality.TCombobox')
quality_combo.pack(side='left')

# Панель настроек обхода блокировок / авторизации
settings_frame = ttk.Frame(main_frame)
settings_frame.pack(fill='x', pady=(8, 0))

cookies_status_var = tk.StringVar()


def update_cookies_status(*args):
    """Показывает статус поддержки impersonation и выбранный источник cookies."""
    imp = "curl_cffi установлен" if IMPERSONATE_AVAILABLE else \
        "curl_cffi НЕ установлен (pip install \"yt-dlp[default,curl-cffi]\")"
    src = {'none': 'без cookies', 'browser': 'cookies из Chrome', 'file': 'файл cookies'}.get(cookie_var.get(), '')
    cookies_status_var.set(f"Impersonation: {imp} | Авторизация: {src}")


cookie_var = tk.StringVar(value='none')
cookie_browser_check = ttk.Checkbutton(settings_frame, text="Cookies из браузера",
                                       variable=cookie_var, value='browser',
                                       command=update_cookies_status)
cookie_browser_check.pack(side='left')
cookie_file_check = ttk.Checkbutton(settings_frame, text="Файл cookies:",
                                    variable=cookie_var, value='file',
                                    command=update_cookies_status)
cookie_file_check.pack(side='left', padx=(12, 4))

cookie_file_var = tk.StringVar()
cookie_entry = ttk.Entry(settings_frame, textvariable=cookie_file_var, width=28)
cookie_entry.pack(side='left', padx=(0, 5))

browse_button = ttk.Button(settings_frame, text="Обзор...", command=browse_cookie_file,
                           style='Paste.TButton', width=7)
browse_button.pack(side='left')

cookies_status_label = ttk.Label(main_frame, textvariable=cookies_status_var,
                                 style='Check.TLabel', anchor='w')
cookies_status_label.pack(fill='x', pady=(4, 0))
update_cookies_status()

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
_process_ui_queue()
root.mainloop()