import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from yt_dlp import YoutubeDL
import os
import platform
import requests
import zipfile
import shutil
import stat

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
        response = requests.get(url, stream=True)
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
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
    
    # Убедимся, что FFmpeg установлен
    try:
        setup_ffmpeg()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось установить FFmpeg: {str(e)}")
        return
    
    ydl_opts = {
        'outtmpl': f'{save_path}/%(title)s.%(ext)s',
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'ffmpeg_location': FFMPEG_PATH,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        messagebox.showinfo("Успех", "Видео успешно скачано в максимальном качестве!")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Произошла ошибка: {str(e)}")

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
root.geometry("700x300")
root.resizable(False, False)

# Применение темы
set_custom_theme(root)

# Основной фрейм
main_frame = ttk.Frame(root)
main_frame.pack(expand=True, fill='both', padx=20, pady=20)

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
download_button.pack(pady=20)

# Запуск
root.mainloop()