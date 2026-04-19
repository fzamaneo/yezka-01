# -*- coding: utf-8 -*-
import os
import sys
import csv
import shutil
import subprocess
import webbrowser
import urllib.parse
import re
import threading
import time
import json
import tempfile
import struct
import array
import math
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pytablericons import TablerIcons, OutlineIcon 

# Motor Local Essentia
try:
    import essentia.standard as es
    ESSENTIA_AVAILABLE = True
except ImportError:
    ESSENTIA_AVAILABLE = False

# Motor de Audio Pygame
try:
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
    import pygame
    pygame.mixer.init()
    pygame.mixer.music.set_volume(0.5) 
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# --- CONFIGURACIÓN GLOBAL ---
ctk.set_appearance_mode("dark")

FONT_MONO = ("Menlo", 12)  
FONT_MONO_BOLD = ("Menlo", 12, "bold")
FONT_MONO_BOLD_SMALL = ("Menlo", 9, "bold")
FONT_TITLE = ("Menlo", 17, "bold")
FONT_NAME = ("Menlo", 14, "normal") 

BG_MAIN = "#000000"      
BG_HOVER = "#1C1C1C"     
BG_ELEMENT = "#141414"   
ACCENT = "#DCE038"       
COLOR_MODIFIED = "#E93B35" 
COLOR_SAVED = "#35E93B"    
TEXT_NORMAL = "#DFDFDF"  
TEXT_PURE = "#FFFFFF"    
TEXT_PALE = "#C0C0C0"    
TEXT_MUTED = "#555555"   
TEXT_DIM = "#5A5A5A"     
RADIUS = 4 

REGEX_KEY_START = re.compile(r'^(\d{1,2}[A-Za-z]{1,3})\s*[-_ ]\s*(.*)')
REGEX_BPM_START = re.compile(r'^(\d{2,3}(?:\.\d+)?)\s*(?:BPM)?\s*[-_ ]\s*(.*)', re.IGNORECASE)
REGEX_KEY_END = re.compile(r'(.*?)\s*[-_ ]\s*(\d{1,2}[A-Za-z]{1,3})$')
REGEX_BPM_END = re.compile(r'(.*?)\s*[-_ ]\s*(\d{2,3}(?:\.\d+)?)\s*(?:BPM)?$', re.IGNORECASE)
REGEX_KEY_STRICT = re.compile(r'^(\d{1,2})([A-Za-z]+)$')

class YezkaEntry(ctk.CTkEntry):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.undo_stack = []; self.redo_stack = []
        self._entry.bind("<KeyRelease>", self.save_state)
        self._entry.bind("<Command-z>", self.undo)
        self._entry.bind("<Command-y>", self.redo)
        self._entry.bind("<Control-z>", self.undo) 
        self._entry.bind("<Control-y>", self.redo)

    def set_initial_state(self):
        self.undo_stack = [self.get()]; self.redo_stack = []

    def save_state(self, event):
        if event.keysym in ("z", "y", "Z", "Command_L", "Command_R", "Control_L", "Control_R", "Shift_L", "Shift_R", "Return", "Meta_L", "Meta_R"): return
        current_text = self.get()
        if not self.undo_stack: self.undo_stack.append("")
        if current_text != self.undo_stack[-1]:
            self.undo_stack.append(current_text)
            self.redo_stack.clear()

    def undo(self, event):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self.delete(0, 'end'); self.insert(0, self.undo_stack[-1])
        return "break"

    def redo(self, event):
        if self.redo_stack:
            text = self.redo_stack.pop()
            self.undo_stack.append(text)
            self.delete(0, 'end'); self.insert(0, text)
        return "break"

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget; self.text = text; self.tooltip_window = None; self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.unschedule(); self.id = self.widget.after(400, self.showtip) 

    def leave(self, event=None):
        self.unschedule(); self.hidetip()

    def unschedule(self):
        if self.id: self.widget.after_cancel(self.id); self.id = None

    def showtip(self):
        if self.tooltip_window: return
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25; y += self.widget.winfo_rooty() + 25
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try: tw.tk.call("::tk::unsupported::MacWindowStyle", "style", tw._w, "help", "none")
        except: pass
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left', background=BG_ELEMENT, foreground=TEXT_NORMAL, font=FONT_MONO)
        label.pack(ipadx=6, ipady=3)

    def hidetip(self):
        if self.tooltip_window: self.tooltip_window.destroy(); self.tooltip_window = None

class SmartFolderHandler(FileSystemEventHandler):
    def __init__(self, add_callback, remove_callback):
        self.add_callback = add_callback; self.remove_callback = remove_callback
        self.valid_extensions = ('.wav', '.aiff', '.mp3', '.flac')

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(self.valid_extensions):
            if "_BACKUP_ORIGINALES" in event.src_path: return
            time.sleep(0.5); self.add_callback(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and event.src_path.lower().endswith(self.valid_extensions):
            if "_BACKUP_ORIGINALES" in event.src_path: return
            self.remove_callback(event.src_path)
                
    def on_moved(self, event):
        if not event.is_directory:
            if event.src_path.lower().endswith(self.valid_extensions):
                if "_BACKUP_ORIGINALES" not in event.src_path:
                    self.remove_callback(event.src_path)
            if event.dest_path.lower().endswith(self.valid_extensions):
                if "_BACKUP_ORIGINALES" not in event.dest_path:
                    time.sleep(0.5); self.add_callback(event.dest_path)

class YezkaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._init_done = False 
        
        self.title("YEZKA-01 - v0.9.46 (Definitive Tab Engine & Smart Extractor)") 
        self.geometry("1134x780") 
        self.resizable(True, True)
        self.configure(fg_color=BG_MAIN)

        self.csv_path = ""
        self.loaded_paths = [] 
        self.metadata_cache = {} 
        self.file_data = {} 
        self.session_history = {} 
        self.current_local_dir = "" 

        self.current_sort_col = "NOMBRE DE ARCHIVOS"
        self.sort_asc = True
        self.is_wav_all_applied = False
        
        self.pygame_active = PYGAME_AVAILABLE
        self.current_playing_path = None
        self.is_playing = False
        self.is_paused = False
        self.current_track_length = 0.0
        self.playback_offset = 0.0
        self.is_dragging_progress = False
        
        self._progress_loop_id = None
        self.watchdog_shield = set()

        self.config_file = os.path.expanduser("~/.yezka_config.json")
        self.default_smart_folder = os.path.expanduser("~/Documents/_ARCHIVOS_YEZKA_")
        
        self.format_options = [
            "Añadir solo metadatos", 
            "►KEY ►BPM - TITULO", 
            "►BPM ►KEY - TITULO", 
            "►BPM - TITULO", 
            "►KEY - TITULO", 
            "TITULO - ◄BPM ◄KEY", 
            "TITULO - ◄KEY ◄BPM", 
            "TITULO - ◄BPM", 
            "TITULO - ◄KEY"
        ]
        
        self.meta_separator_options = ["►", "-", "=", "+", "-►", "Espacio en blanco"]
        
        self.smart_folders = [] 
        self.smart_tab_widgets = {}
        self.active_smart_path = ""
        self.app_scale = 1.0
        self.bpm_range = "Electrónica (90-170)"
        self.show_log_default = False 
        self.default_tab_pref = "CARPETA INTELIGENTE"
        self.default_format_pref = "►KEY ►BPM - TITULO"
        self.meta_separator = "►"
        self.prompt_create_default_folder = True 
        self.first_run_completed = False 
        self.last_active_tab = "CARPETA INTELIGENTE"
        
        self.load_config()
        
        if not self.smart_folders:
            self.smart_folders.append(self.default_smart_folder)
            
        ctk.set_widget_scaling(self.app_scale)
        ctk.set_window_scaling(self.app_scale)

        self.observer = None

        self.NUM_VISIBLE_ROWS = 12 
        self.top_index = 0
        self.row_widgets = [] 
        self.visible_paths = [] 
        
        self.COL_WIDTHS = [28, 575, 75, 60, 60, 40, 155]

        self.ic_trash = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.TRASH, color=TEXT_NORMAL, size=24), size=(20, 20))
        self.ic_refresh = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.REFRESH, color=ACCENT, size=24), size=(20, 20))
        self.ic_web = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.WORLD_SEARCH, color=TEXT_NORMAL, size=24), size=(18, 18))
        self.ic_analyze = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.WAND, color=ACCENT, size=24), size=(18, 18))
        self.ic_undo_muted = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.ARROW_BACK_UP, color=TEXT_MUTED, size=24), size=(18, 18))
        self.ic_undo_accent = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.ARROW_BACK_UP, color=ACCENT, size=24), size=(18, 18))
        self.ic_undo_red = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.ARROW_BACK_UP, color=COLOR_MODIFIED, size=24), size=(18, 18))
        self.ic_settings = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.SETTINGS, color=TEXT_NORMAL, size=24), size=(22, 22))
        self.ic_folder = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.FOLDER, color=TEXT_NORMAL, size=24), size=(18, 18))
        folder_plus_icon = getattr(OutlineIcon, "FOLDER_PLUS", OutlineIcon.FOLDER)
        self.ic_folder_plus = ctk.CTkImage(light_image=TablerIcons.load(folder_plus_icon, color=TEXT_NORMAL, size=24), size=(18, 18))
        self.ic_play = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.PLAYER_PLAY, color=ACCENT, size=24), size=(16, 16))
        self.ic_pause = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.PLAYER_PAUSE, color=ACCENT, size=24), size=(16, 16))
        self.ic_stop = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.PLAYER_STOP, color=COLOR_MODIFIED, size=24), size=(16, 16))
        self.ic_volume = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.VOLUME, color=TEXT_MUTED, size=24), size=(18, 18))
        from PIL import ImageTk
        self._ic_wf_idle = ImageTk.PhotoImage(TablerIcons.load(OutlineIcon.HEADPHONES_OFF, color="#333333", size=22))

        self.frame_top = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0)
        self.frame_top.pack(side="top", fill="x", padx=20, pady=(15, 5))

        self.label_title = ctk.CTkLabel(self.frame_top, text="YEZKA-01  //  v0.9.46", font=FONT_TITLE, text_color=TEXT_NORMAL)
        self.label_title.pack(side="left")

        self.btn_settings = ctk.CTkButton(self.frame_top, text="", image=self.ic_settings, width=30, height=30, fg_color=BG_MAIN, hover_color=BG_HOVER, command=self.open_general_settings)
        self.btn_settings.pack(side="right")
        ToolTip(self.btn_settings, "Ajustes Generales")

        self.frame_toolbar = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0) 
        self.frame_toolbar.pack(side="top", pady=(5, 10), padx=20, fill="x")
        
        # FIX v0.9.45: pack_propagate(False) para blindar el contenedor de la zona negra
        self.frame_tabs_container = ctk.CTkFrame(self.frame_toolbar, fg_color=BG_MAIN, corner_radius=0, height=85)
        self.frame_tabs_container.pack_propagate(False)
        self.frame_tabs_container.pack(side="left", fill="both", expand=True)
        
        self.tabs = None
        self._build_tabs_completely(startup=True)

        self.frame_global_tools = ctk.CTkFrame(self.frame_toolbar, fg_color="transparent")
        self.frame_global_tools.pack(side="right", fill="y", pady=(24,0)) 
        
        self.btn_clear = ctk.CTkButton(self.frame_global_tools, text="", image=self.ic_trash, width=36, height=28, fg_color=BG_ELEMENT, hover_color="#1E1E1E", corner_radius=RADIUS, command=self.clear_all, border_width=0)
        self.btn_clear.pack(side="right", padx=(10, 0))
        self.tooltip_clear = ToolTip(self.btn_clear, "Vacía la lista de archivos y el registro")

        self.btn_csv = ctk.CTkButton(self.frame_global_tools, text="CSV", width=60, height=28, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO, command=self.select_csv, border_width=0)
        self.btn_csv.pack(side="right", padx=(10, 0))
        ToolTip(self.btn_csv, "Aplica etiquetas desde un archivo CSV")
        
        self.menu_format = ctk.CTkOptionMenu(self.frame_global_tools, values=self.format_options, variable=ctk.StringVar(value=self.default_format_pref), width=200, height=28, fg_color=BG_ELEMENT, button_color=BG_ELEMENT, button_hover_color=BG_HOVER, dropdown_fg_color=BG_ELEMENT, font=FONT_MONO, text_color=TEXT_NORMAL, command=self.on_format_change)
        self.format_var = self.menu_format._variable
        self.menu_format.pack(side="right", padx=(10, 0))
        
        self.btn_mass_wav = ctk.CTkButton(self.frame_global_tools, text="[ WAV ALL ]", width=90, height=28, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_MUTED, state="disabled", corner_radius=RADIUS, font=FONT_MONO_BOLD, command=self.toggle_wav_all, border_width=0)
        self.btn_mass_wav.pack(side="right", padx=(10, 0))
        ToolTip(self.btn_mass_wav, "Convierte todos los archivos que no sean WAV en la lista a formato WAV")

        self.frame_log_wrapper = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_log_wrapper.pack(side="bottom", fill="x", padx=20, pady=(0, 15))
        
        self.frame_log_header = ctk.CTkFrame(self.frame_log_wrapper, fg_color="transparent")
        self.frame_log_header.pack(side="top", fill="x", pady=(0, 2))
        
        self.btn_toggle_log = ctk.CTkButton(self.frame_log_header, text="-" if self.show_log_default else "+", width=24, height=24, fg_color="transparent", hover_color=BG_HOVER, text_color=TEXT_NORMAL, font=("Menlo", 16, "bold"), command=self.toggle_log)
        self.btn_toggle_log.pack(side="left", padx=(0, 5))
        
        self.label_log = ctk.CTkLabel(self.frame_log_header, text="REGISTRO", font=FONT_MONO_BOLD, text_color=TEXT_MUTED)
        self.label_log.pack(side="left")

        self.textbox_log = ctk.CTkTextbox(self.frame_log_wrapper, height=80, state="disabled", fg_color="transparent", text_color="#e93b35", border_width=0, corner_radius=0, font=FONT_MONO)
        
        if self.show_log_default:
            self.textbox_log.pack(side="top", fill="x")

        self.frame_player = ctk.CTkFrame(self, fg_color=BG_ELEMENT, corner_radius=RADIUS, height=88)
        self.frame_player.pack(side="bottom", fill="x", padx=20, pady=(5, 10))
        self.frame_player.pack_propagate(False)

        self.frame_waveform_row = ctk.CTkFrame(self.frame_player, fg_color="transparent", height=30)
        self.frame_waveform_row.pack(side="top", fill="x", padx=15, pady=(6, 0))
        self.frame_waveform_row.pack_propagate(False)

        self.waveform_canvas = tk.Canvas(self.frame_waveform_row, height=30, bg=BG_ELEMENT, highlightthickness=0, bd=0)
        self.waveform_canvas.pack(fill="both", expand=True)
        self.waveform_canvas.bind("<Button-1>", self.on_waveform_click)
        self.waveform_canvas.bind("<Configure>", self._on_waveform_configure)
        self.waveform_data = []

        self.frame_controls_row = ctk.CTkFrame(self.frame_player, fg_color="transparent")
        self.frame_controls_row.pack(side="bottom", fill="x", padx=0, pady=(2, 6))

        self.lbl_player_track = ctk.CTkLabel(self.frame_controls_row, text="▪ REPRODUCTOR EN ESPERA", font=FONT_MONO, text_color=TEXT_MUTED, width=220, anchor="w")
        self.lbl_player_track.pack(side="left", padx=(15, 10), pady=0)
        self.lbl_player_track.bind("<Button-1>", lambda e: self._player_bar_toggle())
        
        self.lbl_time = ctk.CTkLabel(self.frame_controls_row, text="00:00 / 00:00", font=FONT_MONO, text_color=TEXT_MUTED, width=100)
        self.lbl_time.pack(side="left", padx=(0, 10))

        self.slider_progress = ctk.CTkSlider(
            self.frame_controls_row, 
            from_=0, to=100, 
            height=6, 
            command=self.on_progress_drag, 
            fg_color=BG_MAIN, 
            progress_color=ACCENT,
            button_length=0, 
            button_color=ACCENT, 
            button_hover_color=TEXT_PURE
        )
        self.slider_progress.set(0)
        self.slider_progress.pack(side="left", fill="x", expand=True, padx=(0, 20))
        self.slider_progress.bind("<ButtonPress-1>", self.on_progress_press)
        self.slider_progress.bind("<ButtonRelease-1>", self.on_progress_release)
        
        self.lbl_vol_icon = ctk.CTkLabel(self.frame_controls_row, text="", image=self.ic_volume)
        self.lbl_vol_icon.pack(side="left", padx=(0, 5), pady=0)

        self.slider_vol = ctk.CTkSlider(
            self.frame_controls_row, 
            from_=0, to=1, 
            width=80, height=6, 
            command=self.set_volume, 
            fg_color=BG_MAIN, 
            progress_color=ACCENT,
            button_length=0, 
            button_color=ACCENT, 
            button_hover_color=ACCENT
        )
        self.slider_vol.set(0.5)
        self.slider_vol.pack(side="left", padx=(0, 10))
        ToolTip(self.slider_vol, "Ajustar Volumen")

        if not PYGAME_AVAILABLE:
            self.lbl_player_track.configure(text="⚠ Pygame no instalado.")
            self.slider_vol.configure(state="disabled")
            self.slider_progress.configure(state="disabled")

        self.btn_run = ctk.CTkButton(self.frame_controls_row, text="APLICAR CAMBIOS", height=28, command=self.run_rename_all, fg_color=BG_MAIN, text_color=TEXT_MUTED, state="disabled", corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=1, border_color="#222")
        self.btn_run.pack(side="right", padx=5, pady=0)

        self.table_container = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0)
        self.table_container.pack(side="top", fill="both", expand=True, padx=20, pady=(0, 5))

        self.frame_headers = ctk.CTkFrame(self.table_container, fg_color="transparent", corner_radius=0)
        self.frame_headers.pack(fill="x", pady=(0, 2), padx=(0, 16)) 
        self.label_loaded_count = None
        
        self.scroll_container = ctk.CTkFrame(self.table_container, fg_color="transparent")
        self.scroll_container.pack(fill="both", expand=True, pady=(0, 0)) 

        self.scrollbar = ctk.CTkScrollbar(self.scroll_container, command=self.on_scrollbar, fg_color=BG_MAIN, button_color=TEXT_MUTED, button_hover_color=TEXT_PALE)
        self.scrollbar.pack(side="right", fill="y")

        self.rows_frame = ctk.CTkFrame(self.scroll_container, fg_color="transparent")
        self.rows_frame.pack(side="left", fill="both", expand=True)

        self.rows_frame.bind("<MouseWheel>", self.on_mouse_wheel)
        self.bind("<MouseWheel>", self.on_mouse_wheel) 
        
        self.empty_frame = ctk.CTkFrame(self.scroll_container, fg_color="transparent")
        empty_ascii = r"""▓██   ██▓▓█████ ██▒   █▓ ██▒   █▓   ▒██   ██▒    ███▄ ▄███▓▓█████   ██████  ██ ▄█▀▄▄▄      
 ▒██  ██▒▓█   ▀▓██░   █▒▓██░   █▒   ▒▒ █ █ ▒░   ▓██▒▀█▀ ██▒▓█   ▀ ▒██    ▒  ██▄█▒▒████▄    
  ▒██ ██░▒███   ▓██  █▒░ ▓██  █▒░   ░░  █   ░   ▓██    ▓██░▒███   ░ ▓██▄   ▓███▄░▒██  ▀█▄  
  ░ ▐██▓░▒▓█  ▄  ▒██ █░░  ▒██ █░░    ░ █ █ ▒    ▒██    ▒██ ▒▓█  ▄   ▒   ██▒▓██ █▄░██▄▄▄▄██ 
  ░ ██▒▓░░▒████▒  ▒▀█░     ▒▀█░     ▒██▒ ▒██▒   ▒██▒   ░██▒░▒████▒▒██████▒▒▒██▒ █▄▓█   ▓██▒
   ██▒▒▒  ░░ ▒░ ░  ░ ▐░     ░ ▐░     ▒▒ ░ ░▓ ░   ░ ▒░   ░  ░░░ ▒░ ░▒ ▒▓▒ ▒ ░▒ ▒▒ ▓▒▒▒   ▓▒█░
 ▓██ ░▒░   ░ ░  ░  ░ ░░     ░ ░░     ░░   ░▒ ░   ░  ░      ░ ░ ░  ░░ ░▒  ░ ░░ ░▒ ▒░ ▒   ▒▒ ░
 ▒ ▒ ░░      ░       ░░       ░░     ░    ░      ░       ░     ░   ░  ░  ░ ░░ ░  ░   ▒   
 ░ ░         ░  ░    ░        ░      ░    ░              ░     ░  ░      ░  ░  ░       ░  ░
 ░ ░                 ░        ░                                                          """
        ctk.CTkLabel(self.empty_frame, text=empty_ascii, font=("Menlo", 10), text_color=TEXT_MUTED, justify="left").pack()
        
        self.lbl_empty_instruction = ctk.CTkLabel(self.empty_frame, text="", font=("Menlo", 10), text_color=TEXT_MUTED, justify="center")
        self.lbl_empty_instruction.pack(pady=(10, 0))

        self.is_loading = False
        self.loading_id = 0
        self.loading_base_msg = ""
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.row_spinner_idx = 0  
        
        self.loading_frame = ctk.CTkFrame(self, fg_color="#0C0C0C", corner_radius=12, border_width=1, border_color=ACCENT)
        self.loading_spinner_label = ctk.CTkLabel(self.loading_frame, text="", font=("Menlo", 40, "bold"), text_color=ACCENT)
        self.loading_spinner_label.pack(pady=(15, 0))
        self.loading_text_label = ctk.CTkLabel(self.loading_frame, text="", font=FONT_MONO, text_color=ACCENT, justify="center")
        self.loading_text_label.pack(pady=(10, 15), padx=20)

        self.draw_headers()
        self.build_virtual_rows()
        
        self._init_done = True 
        self.after(50, self._activate_initial_tab)
        
        if not ESSENTIA_AVAILABLE:
            self.after(500, lambda: self.log_message("> [ATENCIÓN] Essentia no detectado. Instálalo con: pip install essentia"))
        
        self.after(500, self._check_default_folder_startup)
        self.focus_force() 

    def _align_tabs_left(self):
        """Fija la barra de pestañas al borde izquierdo incluso después de recrear el TabView."""
        if not self.tabs:
            return

        try:
            self.tabs.configure(anchor="nw")
        except Exception:
            pass

        try:
            self.tabs._segmented_button.grid_configure(sticky="w", padx=0)
        except Exception:
            pass

    def _resolve_startup_tab(self):
        if self.default_tab_pref in self.smart_tab_widgets:
            return self.default_tab_pref
        if self.default_tab_pref == "MODO MANUAL":
            return "MODO MANUAL"
        return "CARPETA INTELIGENTE"

    def _activate_initial_tab(self):
        if not self.tabs:
            return

        try:
            startup_tab = self._resolve_startup_tab()
            self.tabs.set(startup_tab)
            self._align_tabs_left()
            self.update_idletasks()
            self.on_tab_change()
        except Exception as e:
            self.log_message(f"> Error al activar la pestaña inicial: {e}")

    def _style_add_tab_button(self):
        if not self.tabs:
            return

        try:
            add_button = self.tabs._segmented_button._buttons_dict.get("+")
            if add_button:
                add_button.configure(text="", image=self.ic_folder_plus, width=30)
        except Exception:
            pass

    def _build_tabs_completely(self, startup=False):
        """Fix Definitivo: Borra y recrea el TabView por completo para forzar un repintado seguro y evitar zonas negras"""
        active_tab = self.default_tab_pref if startup else "CARPETA INTELIGENTE"
        
        if not startup:
            try: active_tab = self.tabs.get()
            except: pass
            
            if self.tabs:
                self.tabs.destroy()
                self.tabs = None
                
        self.tabs = ctk.CTkTabview(self.frame_tabs_container, height=85, fg_color="transparent", bg_color="transparent", segmented_button_fg_color=BG_ELEMENT, segmented_button_selected_color="#2A2A2A", segmented_button_unselected_color=BG_ELEMENT, text_color=TEXT_NORMAL, command=self.on_tab_change)
        self.tabs.pack(side="left", fill="both", expand=True)
        self._align_tabs_left()

        self.smart_tab_widgets.clear()
        
        self.tab_local = self.tabs.add("MODO MANUAL")
        self._build_local_tab_ui()
        
        for i, path in enumerate(self.smart_folders):
            self.add_smart_tab_ui(i, path)
            
        self.tabs.add("+")
        self._style_add_tab_button()
        
        if not startup:
            if active_tab == "+" or active_tab not in self.smart_tab_widgets and active_tab != "MODO MANUAL":
                active_tab = f"CARPETA INTELIGENTE {len(self.smart_folders)}" if len(self.smart_folders) > 1 else "CARPETA INTELIGENTE"
            
            self.update_idletasks()
            self.after(50, lambda t=active_tab: self._delayed_tab_set(t))
        else:
            self.tabs.set(self._resolve_startup_tab())
            self._align_tabs_left()

    def _delayed_tab_set(self, tab_name):
        """Retardo microscópico para que macOS procese la geometría antes de mostrar el contenido"""
        try:
            self.tabs.set(tab_name)
            self._align_tabs_left()
            self.update_idletasks()
            self.on_tab_change()
        except Exception as e:
            self.log_message(f"> Error visual al cambiar pestaña: {e}")

    def _build_local_tab_ui(self):
        for w in self.tab_local.winfo_children(): w.destroy()
        
        self.frame_local_top = ctk.CTkFrame(self.tab_local, fg_color="transparent")
        self.frame_local_top.pack(fill="x", pady=(5, 2))

        self.btn_folder = ctk.CTkButton(self.frame_local_top, text="SELECCIONAR CARPETA", command=self.select_folder, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=0, width=160, height=28)
        self.btn_folder.pack(side="left", padx=(0, 10))
        
        self.btn_files = ctk.CTkButton(self.frame_local_top, text="SELECCIONAR ARCHIVO", command=self.select_files, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=0, width=160, height=28)
        self.btn_files.pack(side="left", padx=(0, 10))

        self.btn_open_local_dir = ctk.CTkButton(self.frame_local_top, text="", image=self.ic_folder, width=24, height=24, fg_color="transparent", hover_color=BG_HOVER, command=lambda: self.open_finder(self.current_local_dir))
        self.btn_open_local_dir.pack(side="left", padx=(4, 5))
        ToolTip(self.btn_open_local_dir, "Abrir carpeta en Finder")
        
        txt_path = f"Ruta: {self.current_local_dir}" if self.current_local_dir else "Ruta: Ninguna"
        self.lbl_local_path = ctk.CTkLabel(self.frame_local_top, text=txt_path, font=FONT_MONO, text_color=TEXT_DIM)
        self.lbl_local_path.pack(side="left")

    def add_smart_tab_ui(self, index, path):
        tab_name = "CARPETA INTELIGENTE" if index == 0 else f"CARPETA INTELIGENTE {index+1}"
        tab = self.tabs.add(tab_name)
        
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True, pady=(5,0))
        
        btn_change = ctk.CTkButton(frame, text="CAMBIAR RUTA", command=lambda idx=index: self.change_smart_folder(idx), fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=0, width=110, height=28)
        btn_change.pack(side="left", padx=(0, 8))
        ToolTip(btn_change, "Selecciona una nueva carpeta para monitorear automáticamente")

        if index > 0:
            btn_del = ctk.CTkButton(frame, text="QUITAR CARPETA", command=lambda idx=index: self.remove_smart_folder(idx), fg_color=BG_ELEMENT, hover_color="#3a1010", text_color=COLOR_MODIFIED, corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=1, border_color=COLOR_MODIFIED, width=120, height=23)
            btn_del.pack(side="left", padx=(0, 15))
            ToolTip(btn_del, "Quitar esta Carpeta Inteligente")

        btn_open = ctk.CTkButton(frame, text="", image=self.ic_folder, width=24, height=24, fg_color="transparent", hover_color=BG_HOVER, command=lambda idx=index: self.open_finder(self.smart_folders[idx]))
        btn_open.pack(side="left", padx=(0 if index == 0 else 0, 5))
        ToolTip(btn_open, "Abrir Carpeta Inteligente")
            
        lbl_path = ctk.CTkLabel(frame, text=f"Ruta: {path}", font=FONT_MONO, text_color=TEXT_DIM, anchor="w")
        lbl_path.pack(side="left", fill="x", expand=True, padx=(5 if index == 0 else 0, 0))
        
        self.smart_tab_widgets[tab_name] = {'lbl_path': lbl_path, 'index': index}

    def add_new_smart_folder_from_tab(self):
        if len(self.smart_folders) >= 5:
            messagebox.showinfo("Límite alcanzado", "Puedes tener un máximo de 5 carpetas inteligentes conectadas.")
            if hasattr(self, 'last_active_tab') and self.last_active_tab != "+":
                self.tabs.set(self.last_active_tab)
            else:
                self.tabs.set("CARPETA INTELIGENTE")
            return
            
        d = filedialog.askdirectory()
        if d:
            self.smart_folders.append(d)
            self.save_config()
            self.after(10, lambda: self._build_tabs_completely(startup=False))
        else:
            if hasattr(self, 'last_active_tab') and self.last_active_tab != "+":
                self.tabs.set(self.last_active_tab)
            else:
                self.tabs.set("CARPETA INTELIGENTE")

    def remove_smart_folder(self, idx):
        if messagebox.askyesno("Quitar Carpeta", "¿Estás seguro de que quieres desconectar y quitar esta carpeta inteligente de la vista? (Los archivos originales no se borrarán)"):
            self.stop_smart_folder()
            del self.smart_folders[idx]
            self.save_config()
            self.after(10, lambda: self._build_tabs_completely(startup=False))

    def _check_default_folder_startup(self):
        default_folder = self.smart_folders[0]
        if not self.first_run_completed:
            if not os.path.exists(default_folder):
                try:
                    os.makedirs(default_folder, exist_ok=True)
                    self.log_message("> Carpeta por defecto _ARCHIVOS_YEZKA_ creada automáticamente.")
                except Exception as e:
                    self.log_message(f"> Error al crear carpeta por defecto: {e}")
            self.first_run_completed = True
            self.save_config()
            
            if self.active_smart_path == default_folder and self.tabs.get() == "CARPETA INTELIGENTE" and not self.loaded_paths and not self.observer and not self.is_loading:
                self.start_smart_folder()
        else:
            if not os.path.exists(default_folder) and self.prompt_create_default_folder:
                resp = messagebox.askyesno("Carpeta Yezka no encontrada", f"No se encontró la carpeta por defecto de la aplicación:\n\n{default_folder}\n\n¿Deseas crearla nuevamente?")
                if resp:
                    try:
                        os.makedirs(default_folder, exist_ok=True)
                        self.log_message("> Carpeta por defecto _ARCHIVOS_YEZKA_ creada.")
                        if self.active_smart_path == default_folder and self.tabs.get() == "CARPETA INTELIGENTE" and not self.loaded_paths and not self.observer and not self.is_loading:
                            self.start_smart_folder()
                    except Exception as e:
                        self.log_message(f"> Error al crear carpeta por defecto: {e}")

    def on_format_change(self, new_fmt):
        self._sync_visible_rows_to_data()

        staged_count = 0
        for path, data in self.file_data.items():
            if new_fmt == "Añadir solo metadatos":
                target_name = data['orig_name']
            else:
                target_name = self._build_formatted_name(data['pure_name'], data['bpm'], data['key'], new_fmt)

            saved_bpm, saved_key = self.read_metadata(path)
            current_disk_name = os.path.splitext(os.path.basename(path))[0]
            pending_name = target_name != current_disk_name
            pending_metadata = data['bpm'].strip() != saved_bpm.strip() or data['key'].strip() != saved_key.strip()

            data['name'] = target_name

            if pending_name or pending_metadata:
                data['estado'] = COLOR_MODIFIED
                data['is_staged'] = True
                staged_count += 1
            else:
                data['estado'] = COLOR_SAVED if (data['is_custom'] or data['is_formatted']) else TEXT_MUTED
                data['is_staged'] = False

        if self.file_data:
            if staged_count > 0:
                self.log_message(f"> Formato preparado para aplicar en {staged_count} archivos.")
            else:
                self.log_message("> El formato seleccionado ya coincide con los archivos cargados.")

        self.update_apply_button_state()
        self.refresh_virtual_grid()

    def toggle_log(self):
        if self.btn_toggle_log.cget("text") == "+":
            self.btn_toggle_log.configure(text="-")
            self.textbox_log.pack(side="top", fill="x")
        else:
            self.btn_toggle_log.configure(text="+")
            self.textbox_log.pack_forget()

    def _raw_to_samples(self, raw, sampwidth, n_channels, big_endian=False):
        import numpy as np
        bo = '>' if big_endian else '<'
        if sampwidth == 1:
            s = np.frombuffer(raw, dtype='uint8').astype(np.float32) - 128.0
        elif sampwidth == 2:
            s = np.frombuffer(raw, dtype=f'{bo}i2').astype(np.float32)
        elif sampwidth == 3:
            n = len(raw) // 3
            b = np.frombuffer(raw[:n*3], dtype='uint8').reshape(-1, 3)
            if big_endian:
                s = (b[:,0].astype(np.int32)<<16) | (b[:,1].astype(np.int32)<<8) | b[:,2].astype(np.int32)
            else:
                s = b[:,0].astype(np.int32) | (b[:,1].astype(np.int32)<<8) | (b[:,2].astype(np.int32)<<16)
            s = np.where(s >= 0x800000, s - 0x1000000, s).astype(np.float32)
        elif sampwidth == 4:
            try:
                s = np.frombuffer(raw, dtype=f'{bo}f4').astype(np.float32)
                if np.max(np.abs(s)) > 1.5:
                    raise ValueError
            except Exception:
                s = np.frombuffer(raw, dtype=f'{bo}i4').astype(np.float32)
        else:
            return None
        if n_channels > 1:
            s = s[:len(s) - len(s) % n_channels].reshape(-1, n_channels).mean(axis=1)
        return s

    def _generate_waveform(self, filepath, num_bars=300):
        try:
            import numpy as np
            ext = os.path.splitext(filepath)[1].lower()
            samples = None

            if ext == '.wav':
                import wave as wave_mod
                with wave_mod.open(filepath, 'rb') as wf:
                    ch, sw, nf = wf.getnchannels(), wf.getsampwidth(), wf.getnframes()
                    raw = wf.readframes(nf)
                samples = self._raw_to_samples(raw, sw, ch, big_endian=False)

            elif ext in ('.aiff', '.aif'):
                import aifc as aifc_mod
                with aifc_mod.open(filepath, 'rb') as wf:
                    ch, sw, nf = wf.getnchannels(), wf.getsampwidth(), wf.getnframes()
                    raw = wf.readframes(nf)
                samples = self._raw_to_samples(raw, sw, ch, big_endian=True)

            else:
                temp_wav = os.path.join(tempfile.gettempdir(), "yeska_wf_temp.wav")
                converted = False

                # Strategy 1: afconvert (macOS built-in, no extra deps)
                try:
                    result = subprocess.run(
                        ['afconvert', '-f', 'WAVE', '-d', 'LEI16', '-c', '1', filepath, temp_wav],
                        capture_output=True, timeout=30
                    )
                    converted = result.returncode == 0
                except Exception:
                    pass

                # Strategy 2: pydub fallback
                if not converted:
                    try:
                        from pydub import AudioSegment
                        seg = AudioSegment.from_file(filepath).set_channels(1)
                        seg.export(temp_wav, format="wav")
                        converted = True
                    except ImportError:
                        pass
                    except Exception as e:
                        self.after(0, lambda err=e: self.log_message(f"> [WF] Error convirtiendo {os.path.basename(filepath)}: {err}"))
                        return []

                if not converted:
                    self.after(0, lambda: self.log_message(f"> [WF] No se pudo decodificar {os.path.basename(filepath)} (instala pydub o ffmpeg)"))
                    return []

                import wave as wave_mod
                with wave_mod.open(temp_wav, 'rb') as wf:
                    ch, sw, nf = wf.getnchannels(), wf.getsampwidth(), wf.getnframes()
                    raw = wf.readframes(nf)
                try: os.remove(temp_wav)
                except: pass
                samples = self._raw_to_samples(raw, sw, ch, big_endian=False)

            if samples is None:
                self.after(0, lambda: self.log_message(f"> [WF] Bit depth no soportado en: {os.path.basename(filepath)}"))
                return []
            total = len(samples)
            if total == 0: return []

            chunk_size = max(1, total // num_bars)
            trim = chunk_size * num_bars
            s    = samples[:trim] if trim <= total else np.pad(samples, (0, trim - total))
            rms  = np.sqrt(np.mean(s.reshape(num_bars, chunk_size) ** 2, axis=1))
            peak = rms.max()
            if peak == 0: return [0.0] * num_bars
            return ((rms / peak) ** 0.6).tolist()

        except Exception as e:
            self.after(0, lambda err=e: self.log_message(f"> [WF] Error: {err}"))
            return []

    def _start_waveform_spinner(self):
        """Show a loading spinner centered on the waveform canvas."""
        self._wf_spinner_active = True
        self._wf_spinner_idx = 0
        self._animate_waveform_spinner()

    def _animate_waveform_spinner(self):
        if not getattr(self, '_wf_spinner_active', False):
            return
        c = self.waveform_canvas
        c.delete("all")
        c.update_idletasks()
        w = c.winfo_width()
        h = c.winfo_height()
        spin_char = self.spinner_frames[self._wf_spinner_idx % len(self.spinner_frames)]
        c.create_text(w / 2, h / 2, text=f"{spin_char} CARGANDO FORMA DE ONDA", fill=TEXT_MUTED, font=("Menlo", 10))
        self._wf_spinner_idx += 1
        self._wf_spinner_loop_id = self.after(80, self._animate_waveform_spinner)

    def _stop_waveform_spinner(self):
        self._wf_spinner_active = False
        if getattr(self, '_wf_spinner_loop_id', None):
            self.after_cancel(self._wf_spinner_loop_id)
            self._wf_spinner_loop_id = None

    def _on_waveform_ready(self, data, path):
        self._stop_waveform_spinner()
        if self.current_playing_path == path and data:
            self._draw_waveform(data, 0.0)

    def _on_waveform_configure(self, event):
        """Fires when the canvas is first laid out or resized — guaranteed real dimensions."""
        w, h = event.width, event.height
        if w < 2 or h < 2:
            return
        if self.waveform_data:
            ratio = 0.0
            if self.current_track_length > 0 and self.is_playing:
                current = self.playback_offset + (pygame.mixer.music.get_pos() / 1000.0 if getattr(self, 'pygame_active', False) else 0)
                ratio = min(1.0, current / self.current_track_length)
            self._draw_waveform(progress_ratio=ratio)
        elif not getattr(self, '_wf_spinner_active', False):
            self.waveform_canvas.delete("all")
            self.waveform_canvas.create_image(w // 2, h // 2, image=self._ic_wf_idle, anchor="center")

    def _draw_waveform(self, data=None, progress_ratio=0.0):
        c = self.waveform_canvas
        c.delete("all")
        if data is not None:
            self.waveform_data = data
        bars = self.waveform_data
        if not bars:
            return

        w = c.winfo_width()
        h = c.winfo_height()
        if w < 2 or h < 2:
            return

        n = len(bars)
        bar_w = w / n
        gap = 1
        mid = h / 2

        for i, amp in enumerate(bars):
            x0 = i * bar_w
            x1 = x0 + bar_w - gap
            if x1 <= x0: x1 = x0 + 0.5
            bar_h = amp * (mid - 1)
            color = ACCENT if (i / n) < progress_ratio else "#333333"
            c.create_rectangle(x0, mid - bar_h, x1, mid + bar_h, fill=color, outline="")

    def on_waveform_click(self, event):
        """Seek audio when clicking on the waveform."""
        if not self.is_playing or self.current_track_length <= 0:
            return
        c = self.waveform_canvas
        w = c.winfo_width()
        if w <= 0:
            return
        ratio = event.x / w
        ratio = max(0.0, min(1.0, ratio))
        target = ratio * self.current_track_length
        self.playback_offset = target
        ext = os.path.splitext(self.current_playing_path)[1].lower()
        try:
            if ext == '.mp3':
                pygame.mixer.music.play()
                pygame.mixer.music.set_pos(target)
            else:
                pygame.mixer.music.play(start=target)
        except:
            self.log_message(f"> [AVISO] Búsqueda no admitida en este formato de audio.")
        self.slider_progress.set(target)

    def _clear_waveform(self):
        self._stop_waveform_spinner()
        self.waveform_data = []
        c = self.waveform_canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w > 2 and h > 2:
            c.create_image(w // 2, h // 2, image=self._ic_wf_idle, anchor="center")

    def get_audio_duration(self, filepath):
        try:
            from mutagen.wave import WAVE
            from mutagen.aiff import AIFF
            from mutagen.mp3 import MP3
            from mutagen.flac import FLAC
            ext = os.path.splitext(filepath)[1].lower()
            if ext == '.mp3': return MP3(filepath).info.length
            elif ext == '.wav': return WAVE(filepath).info.length
            elif ext in ('.aiff', '.aif'): return AIFF(filepath).info.length
            elif ext == '.flac': return FLAC(filepath).info.length
        except: return 0.0
        return 0.0

    def on_progress_press(self, event):
        self.is_dragging_progress = True

    def on_progress_drag(self, val):
        if self.current_track_length > 0:
            cur_m, cur_s = divmod(int(val), 60)
            tot_m, tot_s = divmod(int(self.current_track_length), 60)
            self.lbl_time.configure(text=f"{cur_m:02d}:{cur_s:02d} / {tot_m:02d}:{tot_s:02d}")

    def on_progress_release(self, event):
        self.is_dragging_progress = False
        if self.is_playing and getattr(self, 'pygame_active', False):
            val = self.slider_progress.get()
            self.playback_offset = float(val)
            ext = os.path.splitext(self.current_playing_path)[1].lower()
            try:
                if ext in ['.mp3', '.ogg']:
                    pygame.mixer.music.play()
                    pygame.mixer.music.set_pos(val)
                else:
                    pygame.mixer.music.play(start=val)
            except Exception as e:
                self.log_message(f"> [AVISO] Búsqueda no admitida en este formato de audio.")

    def _update_progress_loop(self):
        if not self.is_playing or not getattr(self, 'pygame_active', False): return
        
        current_time = self.playback_offset + (pygame.mixer.music.get_pos() / 1000.0)
        
        if self.current_track_length > 0 and current_time >= self.current_track_length:
            self.stop_audio()
            return
            
        if not self.is_dragging_progress:
            self.slider_progress.set(current_time)
            cur_m, cur_s = divmod(int(current_time), 60)
            tot_m, tot_s = divmod(int(self.current_track_length), 60)
            self.lbl_time.configure(text=f"{cur_m:02d}:{cur_s:02d} / {tot_m:02d}:{tot_s:02d}")

        if self.waveform_data and self.current_track_length > 0:
            ratio = current_time / self.current_track_length
            self._draw_waveform(progress_ratio=ratio)

        self.row_spinner_idx = (getattr(self, 'row_spinner_idx', 0) + 1) % len(self.spinner_frames)
        for i in range(self.NUM_VISIBLE_ROWS):
            if i < len(self.visible_paths) and self.visible_paths[i] == self.current_playing_path:
                self.row_widgets[i]['btn_play'].configure(image=self.ic_pause, text="", text_color=ACCENT)
                break
                
        self._progress_loop_id = self.after(100, self._update_progress_loop) 

    def _player_bar_toggle(self):
        """Play/pause button in the player bar."""
        if not self.is_playing or not self.current_playing_path:
            return
        # Find the row index of the current track and delegate to toggle_play
        path = self.current_playing_path
        for i, p in enumerate(self.visible_paths):
            if p == path:
                self.toggle_play(i)
                return
        # Track not visible in current view — handle pause/resume directly
        if self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            track_name = self.file_data[path]['name']
            trunc = (track_name[:25] + '..') if len(track_name) > 25 else track_name
            self.lbl_player_track.configure(text=f"⏸ {trunc}", text_color=ACCENT)
            self._update_progress_loop()
        else:
            pygame.mixer.music.pause()
            self.is_paused = True
            track_name = self.file_data[path]['name']
            trunc = (track_name[:25] + '..') if len(track_name) > 25 else track_name
            self.lbl_player_track.configure(text=f"▶ {trunc}", text_color=TEXT_MUTED)
            if getattr(self, '_progress_loop_id', None):
                self.after_cancel(self._progress_loop_id)
                self._progress_loop_id = None

    def set_volume(self, val):
        if PYGAME_AVAILABLE and getattr(self, 'pygame_active', False):
            pygame.mixer.music.set_volume(float(val))

    def stop_audio(self, force_release=False):
        if not PYGAME_AVAILABLE: return
        
        if getattr(self, '_progress_loop_id', None):
            self.after_cancel(self._progress_loop_id)
            self._progress_loop_id = None
            
        if getattr(self, 'pygame_active', False):
            if self.is_playing:
                pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()
            except AttributeError:
                pass
            
            if force_release:
                pygame.mixer.quit()
                self.pygame_active = False

        self.is_playing = False
        self.is_paused = False
        self.current_playing_path = None
        self.lbl_player_track.configure(text="▪ REPRODUCTOR EN ESPERA", text_color=TEXT_MUTED)
        self.slider_progress.set(0)
        self.lbl_time.configure(text="00:00 / 00:00")
        self._clear_waveform()
        self.refresh_virtual_grid()

    def toggle_play(self, row_idx):
        if not PYGAME_AVAILABLE:
            self.log_message("> [ERROR] Motor de audio no instalado. Ejecuta en terminal: pip install pygame")
            return

        path = self.visible_paths[row_idx]
        if not path or not os.path.exists(path): return

        if not getattr(self, 'pygame_active', False):
            pygame.mixer.init()
            pygame.mixer.music.set_volume(float(self.slider_vol.get()))
            self.pygame_active = True

        if self.current_playing_path == path and self.is_playing:
            if self.is_paused:
                pygame.mixer.music.unpause()
                self.is_paused = False
                track_name = self.file_data[path]['name']
                trunc_name = (track_name[:25] + '..') if len(track_name) > 25 else track_name
                self.lbl_player_track.configure(text=f"⏸ {trunc_name}", text_color=ACCENT)
                self.refresh_virtual_grid()
                self._update_progress_loop()
            else:
                pygame.mixer.music.pause()
                self.is_paused = True
                track_name = self.file_data[path]['name']
                trunc_name = (track_name[:25] + '..') if len(track_name) > 25 else track_name
                self.lbl_player_track.configure(text=f"▶ {trunc_name}", text_color=TEXT_MUTED)
                if getattr(self, '_progress_loop_id', None):
                    self.after_cancel(self._progress_loop_id)
                    self._progress_loop_id = None
                self.refresh_virtual_grid()
        else:
            self.stop_audio()
            try:
                self.current_track_length = self.get_audio_duration(path)
                self.slider_progress.configure(to=self.current_track_length if self.current_track_length > 0 else 100)
                self.slider_progress.set(0)
                self.playback_offset = 0.0

                ext = os.path.splitext(path)[1].lower()
                temp_audio_path = os.path.join(tempfile.gettempdir(), f"yezka_ghost_track{ext}")
                shutil.copy2(path, temp_audio_path)

                pygame.mixer.music.load(temp_audio_path)
                pygame.mixer.music.play()

                self.is_playing = True
                self.is_paused = False
                self.current_playing_path = path

                track_name = self.file_data[path]['name']
                trunc_name = (track_name[:25] + '..') if len(track_name) > 25 else track_name
                self.lbl_player_track.configure(text=f"⏸ {trunc_name}", text_color=ACCENT)

                self._start_waveform_spinner()

                def _gen_wf():
                    data = self._generate_waveform(path)
                    self.after(0, lambda d=data: self._on_waveform_ready(d, path))
                threading.Thread(target=_gen_wf, daemon=True).start()

                self.refresh_virtual_grid()
                self._update_progress_loop()
            except Exception as e:
                self.log_message(f"> [ERROR AUDIO] No se pudo crear el entorno de reproducción: {e}")

    def open_finder(self, path):
        if not path or not os.path.exists(path):
            self.log_message(f"> [AVISO] La ruta no existe o está vacía: {path}")
            return
        try:
            subprocess.run(["open", path])
        except Exception as e:
            self.log_message(f"> Error abriendo carpeta: {e}")

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.smart_folders = data.get("smart_folders", [self.default_smart_folder])
                    self.app_scale = data.get("app_scale", 1.0)
                    self.bpm_range = data.get("bpm_range", "Electrónica (90-170)")
                    self.show_log_default = data.get("show_log_default", False)
                    self.default_tab_pref = data.get("default_tab_pref", "CARPETA INTELIGENTE")
                    self.default_format_pref = data.get("default_format_pref", "►KEY ►BPM - TITULO")
                    self.meta_separator = data.get("meta_separator", "►")
                    self.prompt_create_default_folder = data.get("prompt_create_default_folder", True)
                    self.first_run_completed = data.get("first_run_completed", False)
            except: pass

    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump({
                    "smart_folders": self.smart_folders,
                    "app_scale": self.app_scale,
                    "bpm_range": self.bpm_range,
                    "show_log_default": self.show_log_default,
                    "default_tab_pref": self.default_tab_pref,
                    "default_format_pref": self.default_format_pref,
                    "meta_separator": self.meta_separator,
                    "prompt_create_default_folder": self.prompt_create_default_folder,
                    "first_run_completed": self.first_run_completed
                }, f)
        except Exception as e:
            self.log_message(f"> Error guardando configuración: {e}")

    def open_general_settings(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Ajustes Generales")
        dialog.geometry("400x520")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        
        ctk.CTkLabel(dialog, text="AJUSTES DE INTERFAZ Y ANÁLISIS", font=FONT_TITLE, text_color=TEXT_PURE).pack(pady=(20, 10))
        
        scale_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        scale_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(scale_frame, text="Tamaño UI:", font=FONT_MONO, text_color=TEXT_NORMAL, width=150, anchor="w").pack(side="left")
        current_scale_str = f"{int(self.app_scale * 100)}%"
        scale_menu = ctk.CTkOptionMenu(scale_frame, values=["80%", "90%", "100%", "110%", "120%"], fg_color=BG_ELEMENT, button_color=BG_ELEMENT, button_hover_color=BG_HOVER)
        scale_menu.set(current_scale_str)
        scale_menu.pack(side="right", fill="x", expand=True)
        
        tab_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        tab_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(tab_frame, text="Pestaña Inicial:", font=FONT_MONO, text_color=TEXT_NORMAL, width=150, anchor="w").pack(side="left")
        tab_options = ["MODO MANUAL"] + list(self.smart_tab_widgets.keys())
        tab_menu = ctk.CTkOptionMenu(tab_frame, values=tab_options, fg_color=BG_ELEMENT, button_color=BG_ELEMENT, button_hover_color=BG_HOVER)
        
        if self.default_tab_pref in tab_options:
            tab_menu.set(self.default_tab_pref)
        else:
            tab_menu.set("CARPETA INTELIGENTE")
            
        tab_menu.pack(side="right", fill="x", expand=True)

        fmt_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        fmt_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(fmt_frame, text="Filtro Normal:", font=FONT_MONO, text_color=TEXT_NORMAL, width=150, anchor="w").pack(side="left")
        fmt_menu = ctk.CTkOptionMenu(fmt_frame, values=self.format_options, fg_color=BG_ELEMENT, button_color=BG_ELEMENT, button_hover_color=BG_HOVER)
        fmt_menu.set(self.default_format_pref)
        fmt_menu.pack(side="right", fill="x", expand=True)
        
        sep_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        sep_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(sep_frame, text="Separador Meta:", font=FONT_MONO, text_color=TEXT_NORMAL, width=150, anchor="w").pack(side="left")
        sep_menu = ctk.CTkOptionMenu(sep_frame, values=self.meta_separator_options, fg_color=BG_ELEMENT, button_color=BG_ELEMENT, button_hover_color=BG_HOVER)
        sep_menu.set(self.meta_separator)
        sep_menu.pack(side="right", fill="x", expand=True)
        
        bpm_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        bpm_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(bpm_frame, text="Rango BPM:", font=FONT_MONO, text_color=TEXT_NORMAL, width=150, anchor="w").pack(side="left")
        bpm_options = ["Automático (Sin filtro)", "Electrónica (90-170)", "Urbano/Reggaeton (70-120)", "Drum & Bass (150-200)"]
        bpm_menu = ctk.CTkOptionMenu(bpm_frame, values=bpm_options, fg_color=BG_ELEMENT, button_color=BG_ELEMENT, button_hover_color=BG_HOVER)
        bpm_menu.set(self.bpm_range)
        bpm_menu.pack(side="right", fill="x", expand=True)

        log_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        log_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(log_frame, text="Registro al Inicio:", font=FONT_MONO, text_color=TEXT_NORMAL, width=150, anchor="w").pack(side="left")
        self.log_switch_var = ctk.BooleanVar(value=self.show_log_default)
        log_switch = ctk.CTkSwitch(log_frame, text="", variable=self.log_switch_var, onvalue=True, offvalue=False, width=40, progress_color=ACCENT)
        log_switch.pack(side="right", anchor="e")

        folder_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        folder_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(folder_frame, text="Avisar si falta carpeta:", font=FONT_MONO, text_color=TEXT_NORMAL, width=220, anchor="w").pack(side="left")
        self.folder_switch_var = ctk.BooleanVar(value=self.prompt_create_default_folder)
        folder_switch = ctk.CTkSwitch(folder_frame, text="", variable=self.folder_switch_var, onvalue=True, offvalue=False, width=40, progress_color=ACCENT)
        folder_switch.pack(side="right", anchor="e")
        
        def save_settings():
            new_scale = int(scale_menu.get().replace("%", "")) / 100.0
            scale_changed = (new_scale != self.app_scale)
            
            self.app_scale = new_scale
            self.bpm_range = bpm_menu.get()
            self.default_tab_pref = tab_menu.get()
            self.default_format_pref = fmt_menu.get()
            self.meta_separator = sep_menu.get()
            self.prompt_create_default_folder = self.folder_switch_var.get()
            
            new_show_log = self.log_switch_var.get()
            if new_show_log != self.show_log_default:
                self.show_log_default = new_show_log
                if self.show_log_default and self.btn_toggle_log.cget("text") == "+":
                    self.toggle_log()
                elif not self.show_log_default and self.btn_toggle_log.cget("text") == "-":
                    self.toggle_log()
            
            if scale_changed:
                ctk.set_widget_scaling(self.app_scale)
                ctk.set_window_scaling(self.app_scale)
                self.draw_headers()
            
            self.refresh_virtual_grid()
            self.save_config()
            self.log_message(f"> Ajustes guardados.")
            dialog.destroy()
            
        ctk.CTkButton(dialog, text="APLICAR Y CERRAR", command=save_settings, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=ACCENT, border_width=1, border_color=ACCENT).pack(pady=20)

    def animate_loading(self):
        if not self.is_loading: return
        if "¡" in self.loading_base_msg:
            icon = "✗" if "ERROR" in self.loading_base_msg else "✓"
            self.loading_spinner_label.configure(text=icon)
            self.loading_text_label.configure(text=self.loading_base_msg)
        else:
            spin_char = self.spinner_frames[self.spinner_idx]
            self.loading_spinner_label.configure(text=spin_char)
            self.loading_text_label.configure(text=self.loading_base_msg)
            self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_frames)
            
        self.after(100, self.animate_loading)

    def show_loading(self, message="> PROCESANDO..."):
        self.loading_id += 1 
        self.loading_base_msg = message
        if not self.is_loading:
            self.is_loading = True
            self.loading_frame.place(relx=0.5, rely=0.5, anchor="center")
            self.loading_frame.tkraise()
            self.animate_loading()

    def hide_loading(self):
        self.loading_id += 1
        current_id = self.loading_id
        def do_hide():
            if self.loading_id == current_id:
                self.is_loading = False
                self.loading_frame.place_forget()
                self.update()
        self.after(1000, do_hide)

    def on_tab_change(self):
        if not hasattr(self, '_init_done') or not self._init_done: return 
        
        try:
            current_tab = self.tabs.get()
        except ValueError:
            return 

        self._align_tabs_left()
        
        if current_tab == "+":
            self.after(10, self.add_new_smart_folder_from_tab)
            return
            
        self.last_active_tab = current_tab
        self.clear_all()
        
        if current_tab.startswith("CARPETA INTELIGENTE"):
            self.lbl_empty_instruction.configure(text="\n> AGREGA O DESCARGA ARCHIVOS EN TU CARPETA INTELIGENTE PARA SINCRONIZARLOS AUTOMÁTICAMENTE.")
            self.btn_clear.configure(image=self.ic_refresh, command=self.refresh_smart_folder)
            self.tooltip_clear.text = "Forzar escaneo de la Carpeta Inteligente"
            
            if current_tab in self.smart_tab_widgets:
                idx = self.smart_tab_widgets[current_tab]['index']
                self.active_smart_path = self.smart_folders[idx]
                self.start_smart_folder()
        else:
            self.lbl_empty_instruction.configure(text="\n> SELECCIONA CARPETA O ARCHIVO EN LA BARRA SUPERIOR.")
            self.btn_clear.configure(image=self.ic_trash, command=self.clear_all)
            self.tooltip_clear.text = "Vacía la lista de archivos y el registro"
            self.stop_smart_folder()

    def refresh_smart_folder(self):
        self.log_message(f"> Forzando escaneo de {self.tabs.get()}...")
        self.clear_all(); self.start_smart_folder()

    def change_smart_folder(self, idx):
        f = filedialog.askdirectory()
        if f:
            self.stop_smart_folder()
            self.smart_folders[idx] = f
            self.save_config()
            
            tab_name = "CARPETA INTELIGENTE" if idx == 0 else f"CARPETA INTELIGENTE {idx+1}"
            self.smart_tab_widgets[tab_name]['lbl_path'].configure(text=f"Ruta: {f}")
            self.log_message(f"> {tab_name} configurada en: {f}")
            
            if self.tabs.get() == tab_name:
                self.active_smart_path = f
                self.clear_all()
                self.start_smart_folder()

    def start_smart_folder(self):
        self.stop_smart_folder() 
        if not os.path.exists(self.active_smart_path):
            self.log_message(f"> [AVISO] Carpeta inteligente no existe: {self.active_smart_path}")
            return

        existing_files = [os.path.join(self.active_smart_path, f) for f in os.listdir(self.active_smart_path) if f.lower().endswith(('.wav', '.aiff', '.mp3', '.flac'))]
        if existing_files:
            self.show_loading("LEYENDO\nCARPETA...")
            threading.Thread(target=self._thread_start_smart, args=(existing_files,), daemon=True).start()
        else:
            self._start_smart_observer()

    def _thread_start_smart(self, existing_files):
        time.sleep(0.5)
        new_paths, new_data = self._prepare_files_data(existing_files)
        self.after(0, lambda: self._finish_start_smart(new_paths, new_data))

    def _finish_start_smart(self, new_paths, new_data):
        self._sync_files_data(new_paths, new_data)
        self.refresh_virtual_grid()
        self.loading_base_msg = "¡CARPETA\nSINCRONIZADA!"
        self.hide_loading()
        self.log_message(f"> {len(new_paths)} archivos encontrados en {os.path.basename(self.active_smart_path)}.")
        self._start_smart_observer()

    def _start_smart_observer(self):
        self.stop_smart_folder()
        self.observer = Observer()
        event_handler = SmartFolderHandler(self.queue_new_file, self.queue_remove_file)
        try:
            self.observer.schedule(event_handler, self.active_smart_path, recursive=False)
            self.observer.start()
            self.log_message(f"> [AUTO] Escuchando descargas en: {os.path.basename(self.active_smart_path)}")
        except Exception as e:
            self.log_message(f"> [AVISO] No se pudo iniciar la escucha automática: {e}")
            self.observer = None

    def stop_smart_folder(self):
        if self.observer:
            try:
                self.observer.unschedule_all()
                if self.observer.is_alive():
                    self.observer.stop()
                    self.observer.join(timeout=1.0)
            except Exception: pass
            self.observer = None
            self.log_message("> [AUTO] Escucha detenida.")

    def queue_new_file(self, filepath): 
        if "_BACKUP_ORIGINALES" in filepath: return
        self.after(100, lambda: self._add_smart_file(filepath))
        
    def queue_remove_file(self, filepath): 
        self.after(100, lambda: self._remove_smart_file(filepath))

    def _add_smart_file(self, filepath):
        if filepath in self.watchdog_shield:
            return
        if filepath not in self.loaded_paths and os.path.exists(filepath):
            threading.Thread(target=self._thread_add_smart_file, args=(filepath,), daemon=True).start()

    def _thread_add_smart_file(self, filepath):
        new_paths, new_data = self._prepare_files_data([filepath])
        if new_paths:
            self.after(0, lambda: self._finish_add_smart_file(new_paths, new_data, filepath))

    def _finish_add_smart_file(self, new_paths, new_data, filepath):
        self._sync_files_data(new_paths, new_data)
        self.refresh_virtual_grid()
        self.scrollbar.set(1, 1); self.on_scrollbar('moveto', '1.0')
        self.log_message(f"> [IMPORT] Automático: {os.path.basename(filepath)}")

    def _remove_smart_file(self, filepath):
        if filepath in self.watchdog_shield:
            return

        if filepath in self.loaded_paths:
            if self.current_playing_path == filepath and self.is_playing:
                self.stop_audio()
                
            self.loaded_paths.remove(filepath)
            self.file_data.pop(filepath, None); self.session_history.pop(filepath, None); self.metadata_cache.pop(filepath, None)
            self._update_loaded_count_display()
            self.refresh_virtual_grid(); self.update_apply_button_state(); self.update_wav_button_state()
            self.log_message(f"> [SISTEMA] Removido: {os.path.basename(filepath)}")

    def _extract_pure_name(self, name, tb, tk):
        # FIX v0.9.45: Sistema de pelado avanzado que no duplica BPM ni Key jamás.
        if not name: return ""
        res = name.strip()
        
        k_n = tk.replace(" ", "").upper().replace("MAJOR", "MAJ").replace("MINOR", "MIN") if tk else ""
        b_n = tb.strip().upper() if tb else ""
        
        b_variants = [b_n, f"{b_n} BPM", f"{b_n}BPM"] if b_n else []
        k_variants = [k_n] if k_n else []
        tokens = k_variants + b_variants
        tokens.sort(key=len, reverse=True)
        
        strip_chars = "►◄=+- _"
        
        changed = True
        while changed:
            changed = False
            
            for token in tokens:
                if not token: continue
                
                res_clean = res.lstrip(strip_chars)
                res_clean_upper = res_clean.upper()
                
                if res_clean_upper.startswith(token):
                    after_token_idx = len(token)
                    if after_token_idx == len(res_clean_upper) or res_clean_upper[after_token_idx] in strip_chars:
                        res = res_clean[after_token_idx:].lstrip(strip_chars)
                        changed = True
                        break
                        
                res_clean = res.rstrip(strip_chars)
                res_clean_upper = res_clean.upper()
                
                if res_clean_upper.endswith(token):
                    before_token_idx = len(res_clean_upper) - len(token) - 1
                    if before_token_idx < 0 or res_clean_upper[before_token_idx] in strip_chars:
                        res = res_clean[:before_token_idx + 1].rstrip(strip_chars)
                        changed = True
                        break
                        
            if changed: continue
            
            res_clean = res.strip(strip_chars)
            
            m_k = REGEX_KEY_START.match(res_clean)
            if m_k: 
                res = m_k.group(2).lstrip(strip_chars)
                changed = True; continue
                
            m_b = REGEX_BPM_START.match(res_clean)
            if m_b: 
                res = m_b.group(2).lstrip(strip_chars)
                changed = True; continue
                
            m_ke = REGEX_KEY_END.search(res_clean)
            if m_ke: 
                res = m_ke.group(1).rstrip(strip_chars)
                changed = True; continue
                
            m_be = REGEX_BPM_END.search(res_clean)
            if m_be: 
                res = m_be.group(1).rstrip(strip_chars)
                changed = True; continue
                
        return res.strip(strip_chars)

    def _build_formatted_name(self, pure_name, bp, ky, fmt):
        if fmt == "Añadir solo metadatos":
            return pure_name
            
        sep = getattr(self, 'meta_separator', '►')
        if sep == "Espacio en blanco":
            sep = " "
            
        kn = ky.replace(" ", "").upper().replace("MAJOR", "MAJ").replace("MINOR", "MIN") if ky else ""
        b_name = pure_name
        
        res = b_name
        prefix_parts = []
        suffix_parts = []
        
        if fmt == "►KEY ►BPM - TITULO":
            if kn: prefix_parts.append(kn)
            if bp: prefix_parts.append(bp)
        elif fmt == "►BPM ►KEY - TITULO":
            if bp: prefix_parts.append(bp)
            if kn: prefix_parts.append(kn)
        elif fmt == "►BPM - TITULO":
            if bp: prefix_parts.append(bp)
        elif fmt == "►KEY - TITULO":
            if kn: prefix_parts.append(kn)
        elif fmt == "TITULO - ◄BPM ◄KEY":
            if bp: suffix_parts.append(bp)
            if kn: suffix_parts.append(kn)
        elif fmt == "TITULO - ◄KEY ◄BPM":
            if kn: suffix_parts.append(kn)
            if bp: suffix_parts.append(bp)
        elif fmt == "TITULO - ◄BPM":
            if bp: suffix_parts.append(bp)
        elif fmt == "TITULO - ◄KEY":
            if kn: suffix_parts.append(kn)
            
        if prefix_parts:
            joined_prefix = sep.join(prefix_parts)
            if sep in ["►", "-►", "+", "="]: 
                joined_prefix = sep + joined_prefix
            res = joined_prefix + " - " + b_name if sep == " " else joined_prefix + "-" + b_name
            
        if suffix_parts:
            joined_suffix = sep.join(suffix_parts)
            if sep in ["►", "-►", "+", "="]:
                joined_suffix = sep + joined_suffix
            res = b_name + " - " + joined_suffix if sep == " " else b_name + "-" + joined_suffix
            
        res = res.replace("- -", "-").replace("  ", " ").strip()
        if res.startswith("-"): res = res[1:].strip()
        if res.endswith("-"): res = res[:-1].strip()
        
        return res

    def _update_loaded_count_display(self):
        if not self.label_loaded_count:
            return

        total = len(self.loaded_paths)

        try:
            self.label_loaded_count.configure(text=f"(ARCHIVOS CARGADOS: {total})", text_color=TEXT_MUTED)
        except Exception:
            pass

    def draw_headers(self):
        for widget in self.frame_headers.winfo_children(): widget.destroy()
        self.label_loaded_count = None
        
        for i, w in enumerate(self.COL_WIDTHS): 
            self.frame_headers.grid_columnconfigure(i, minsize=w + 10, weight=0)
            self.rows_frame.grid_columnconfigure(i, minsize=w + 10, weight=0)
            
        headers_texts = ["", "NOMBRE DE ARCHIVOS", "FORMATO", "TEMPO", "KEY", "ST", "ACCIONES"]
        for i, text in enumerate(headers_texts):
            hf = ctk.CTkFrame(self.frame_headers, fg_color="transparent", width=self.COL_WIDTHS[i], height=24)
            hf.grid_propagate(False)
            hf.grid(row=0, column=i, sticky="" if text == "ST" else "w", padx=5) 
            
            if text == "NOMBRE DE ARCHIVOS":
                header_content = ctk.CTkFrame(hf, fg_color="transparent")
                header_content.pack(fill="both", expand=True)

                arrow = " ↑" if self.current_sort_col == text and self.sort_asc else (" ↓" if self.current_sort_col == text else "")
                btn = ctk.CTkButton(
                    header_content,
                    text=text + arrow,
                    font=FONT_MONO_BOLD,
                    text_color=TEXT_MUTED,
                    fg_color="transparent",
                    hover_color=BG_HOVER,
                    border_width=0,
                    height=24,
                    anchor="w",
                    command=lambda t=text: self.sort_grid(t)
                )
                btn.pack(side="left")

                self.label_loaded_count = ctk.CTkLabel(
                    header_content,
                    text="",
                    font=FONT_MONO_BOLD_SMALL,
                    text_color=TEXT_MUTED,
                    anchor="e",
                    justify="right"
                )
                self.label_loaded_count.pack(side="right", padx=(8, 0))
                self._update_loaded_count_display()
            elif text and text != "ACCIONES":
                arrow = " ↑" if self.current_sort_col == text and self.sort_asc else (" ↓" if self.current_sort_col == text else "")
                btn = ctk.CTkButton(hf, text=text + arrow, font=FONT_MONO_BOLD, text_color=TEXT_MUTED, fg_color="transparent", hover_color=BG_HOVER, border_width=0, height=24, anchor="center" if text == "ST" else "w", command=lambda t=text: self.sort_grid(t))
                btn.place(relx=0.5 if text == "ST" else 0.0, rely=0.5, anchor="center" if text == "ST" else "w")
            elif text:
                lbl = ctk.CTkLabel(hf, text=text, font=FONT_MONO_BOLD, text_color=TEXT_MUTED)
                lbl.place(relx=0.5 if text == "ST" else 0.0, rely=0.5, anchor="center" if text == "ST" else "w")

    def build_virtual_rows(self):
        for i in range(self.NUM_VISIBLE_ROWS):
            row_widgets = {}
            
            btn_play = ctk.CTkButton(self.rows_frame, text="", image=self.ic_play, width=self.COL_WIDTHS[0], height=28, fg_color="transparent", hover_color=BG_HOVER, corner_radius=RADIUS)
            btn_play.grid(row=i, column=0, padx=5, pady=(2, 2), sticky="w")
            
            e_name = YezkaEntry(self.rows_frame, width=self.COL_WIDTHS[1], height=28, fg_color=BG_ELEMENT, border_width=0, font=FONT_NAME, corner_radius=RADIUS)
            e_name.grid(row=i, column=1, padx=5, pady=(2, 2), sticky="w")
            
            tag_lbl = ctk.CTkLabel(self.rows_frame, width=self.COL_WIDTHS[2], height=28, fg_color=BG_ELEMENT, corner_radius=RADIUS, font=FONT_MONO, text="")
            tag_lbl.grid(row=i, column=2, padx=5, pady=(2, 2), sticky="w")
            
            e_bpm = YezkaEntry(self.rows_frame, width=self.COL_WIDTHS[3], height=28, fg_color=BG_ELEMENT, border_width=0, corner_radius=RADIUS, font=FONT_MONO)
            e_bpm.grid(row=i, column=3, padx=5, pady=(2, 2), sticky="w")
            
            e_key = YezkaEntry(self.rows_frame, width=self.COL_WIDTHS[4], height=28, fg_color=BG_ELEMENT, border_width=0, corner_radius=RADIUS, font=FONT_MONO)
            e_key.grid(row=i, column=4, padx=5, pady=(2, 2), sticky="w")
            
            l_st = ctk.CTkLabel(self.rows_frame, text="●", width=self.COL_WIDTHS[5], font=("monospace", 14))
            l_st.grid(row=i, column=5, padx=5, pady=(2, 2)) 
            
            af = ctk.CTkFrame(self.rows_frame, fg_color="transparent", width=self.COL_WIDTHS[6], height=28)
            af.grid_propagate(False)
            af.grid(row=i, column=6, padx=5, pady=(2, 2), sticky="w")
            
            bt_u = ctk.CTkButton(af, text="", image=self.ic_undo_muted, width=32, height=28, fg_color=BG_ELEMENT, border_width=0, hover_color="#1E1E1E", corner_radius=RADIUS)
            bt_u.pack(side="left", padx=(0, 4))
            ToolTip(bt_u, "Reiniciar o abortar cambios")
            
            bt_web = ctk.CTkButton(af, text="", image=self.ic_web, width=32, height=28, fg_color=BG_ELEMENT, border_width=0, hover_color="#1E1E1E", corner_radius=RADIUS)
            bt_web.pack(side="left", padx=(0, 4))
            ToolTip(bt_web, "Buscar BPM/Key en navegador")
            
            bt_analyze = ctk.CTkButton(af, text="", image=self.ic_analyze, width=32, height=28, fg_color=BG_ELEMENT, border_width=0, hover_color="#1E1E1E", corner_radius=RADIUS)
            bt_analyze.pack(side="left", padx=(0, 4))
            ToolTip(bt_analyze, "Analizar Audio Localmente")
            
            bt_w = ctk.CTkButton(af, text="WAV", width=40, height=28, fg_color=BG_ELEMENT, border_width=0, hover_color="#1E1E1E", corner_radius=RADIUS, font=FONT_MONO)
            bt_w.pack(side="left")
            ToolTip(bt_w, "Convertir a WAV")

            e_name.bind("<KeyRelease>", lambda e, idx=i: self.visual_row_state(idx, True))
            e_bpm.bind("<KeyRelease>", lambda e, idx=i: self.visual_row_state(idx, False))
            e_key.bind("<KeyRelease>", lambda e, idx=i: self.visual_row_state(idx, False))
            e_name.bind("<Return>", lambda e, idx=i: self.stage_row_changes(idx))
            e_bpm.bind("<Return>", lambda e, idx=i: self.stage_row_changes(idx))
            e_key.bind("<Return>", lambda e, idx=i: self.stage_row_changes(idx))

            e_name.bind("<FocusOut>", lambda e, idx=i: self.stage_row_changes_if_needed(idx))
            e_bpm.bind("<FocusOut>", lambda e, idx=i: self.stage_row_changes_if_needed(idx))
            e_key.bind("<FocusOut>", lambda e, idx=i: self.stage_row_changes_if_needed(idx))

            btn_play.configure(command=lambda idx=i: self.toggle_play(idx))
            bt_u.configure(command=lambda idx=i: self.restart_single_file(idx))
            bt_web.configure(command=lambda idx=i: self.handle_web(idx))
            bt_analyze.configure(command=lambda idx=i: self.handle_analyze(idx))
            bt_w.configure(command=lambda idx=i: self.handle_wav(idx))
            
            for widget in [btn_play, e_name, tag_lbl, e_bpm, e_key, l_st]:
                widget.bind("<Enter>", lambda e, idx=i: self.hover_in_row(idx))
                widget.bind("<Leave>", lambda e, idx=i: self.hover_out_row(idx))

            row_widgets = {'btn_play': btn_play, 'name': e_name, 'tag_lbl': tag_lbl, 'bpm': e_bpm, 'key': e_key, 'estado': l_st, 'btn_undo': bt_u, 'btn_web': bt_web, 'btn_analyze': bt_analyze, 'btn_wav': bt_w, 'frame': af}
            self.row_widgets.append(row_widgets)
            self.hide_row(i)

    def hover_in_row(self, row_idx, event=None):
        if row_idx >= len(self.visible_paths) or not self.visible_paths[row_idx]: return
        w = self.row_widgets[row_idx]
        color = BG_HOVER
        w['btn_play'].configure(fg_color=color)
        w['name'].configure(fg_color=color)
        w['tag_lbl'].configure(fg_color=color)
        w['bpm'].configure(fg_color=color)
        w['key'].configure(fg_color=color)

    def hover_out_row(self, row_idx, event=None):
        if row_idx >= len(self.visible_paths) or not self.visible_paths[row_idx]: return
        w = self.row_widgets[row_idx]
        color = BG_ELEMENT
        w['btn_play'].configure(fg_color="transparent")
        w['name'].configure(fg_color=color)
        w['tag_lbl'].configure(fg_color=color)
        w['bpm'].configure(fg_color=color)
        w['key'].configure(fg_color=color)

    def handle_wav(self, row_idx):
        path = self.visible_paths[row_idx]
        if path:
            self.convert_to_wav(path, auto_update=True)

    def visual_row_state(self, row_idx, is_name):
        path = self.visible_paths[row_idx]
        if not path: return
        w = self.row_widgets[row_idx]
        w['estado'].configure(text_color=COLOR_MODIFIED)
        self.file_data[path]['estado'] = COLOR_MODIFIED
        w['name'].configure(text_color=TEXT_PURE)
        if not is_name:
            w['bpm'].configure(text_color=TEXT_PURE)
            w['key'].configure(text_color=TEXT_PURE)
        self.update_apply_button_state()

    def stage_row_changes_if_needed(self, row_idx):
        if row_idx >= len(self.visible_paths): return
        path = self.visible_paths[row_idx]
        if not path or path not in self.file_data: return
        
        w = self.row_widgets[row_idx]
        raw_name = w['name'].get().strip()
        bp = w['bpm'].get().strip()
        ky = w['key'].get().strip()
        
        if raw_name != self.file_data[path]['name'] or bp != self.file_data[path]['bpm'] or ky != self.file_data[path]['key']:
            self.stage_row_changes(row_idx)

    def stage_row_changes(self, row_idx):
        path = self.visible_paths[row_idx]
        if not path: return
        w = self.row_widgets[row_idx]
        raw_name = w['name'].get().strip()
        bp = w['bpm'].get().strip()
        ky = w['key'].get().strip()
        
        if raw_name != self.file_data[path]['name']:
            new_pure = self._extract_pure_name(raw_name, bp, ky)
            self.file_data[path]['pure_name'] = new_pure
            self.file_data[path]['orig_name'] = raw_name 
            
        self.file_data[path]['is_staged'] = True
        
        fmt = self.format_var.get()
        if fmt == "Añadir solo metadatos":
            new_formatted_name = self.file_data[path]['orig_name']
        else:
            new_formatted_name = self._build_formatted_name(self.file_data[path]['pure_name'], bp, ky, fmt)
        
        w['name'].delete(0, 'end'); w['name'].insert(0, new_formatted_name); w['name'].set_initial_state() 
        self.file_data[path]['name'] = new_formatted_name
        self.file_data[path]['bpm'] = bp
        self.file_data[path]['key'] = ky
        self.file_data[path]['estado'] = COLOR_MODIFIED
        w['estado'].configure(text_color=COLOR_MODIFIED)
        w['name'].configure(text_color=TEXT_PURE) 
        
        if fmt != "Añadir solo metadatos":
            self.log_message(f"> Preparado para guardar: {new_formatted_name}")
        else:
            self.log_message(f"> Metadatos actualizados (Nombre original conservado).")
            
        self.update_apply_button_state(); self.refresh_virtual_grid()

    def hide_row(self, index):
        for key, widget in self.row_widgets[index].items():
            if hasattr(widget, 'grid_remove') and key not in ['btn_undo', 'btn_web', 'btn_analyze', 'btn_wav']: widget.grid_remove()

    def show_row(self, index):
        for key, widget in self.row_widgets[index].items():
            if hasattr(widget, 'grid') and key not in ['btn_undo', 'btn_web', 'btn_analyze', 'btn_wav']: widget.grid()

    def on_scrollbar(self, *args):
        total = len(self.loaded_paths)
        if total <= self.NUM_VISIBLE_ROWS: return
        if args[0] == 'moveto': self.top_index = int(float(args[1]) * total)
        elif args[0] == 'scroll': self.top_index += int(args[1])
        self.top_index = max(0, min(self.top_index, total - self.NUM_VISIBLE_ROWS))
        self.refresh_virtual_grid()

    def on_mouse_wheel(self, event):
        total = len(self.loaded_paths)
        if total <= self.NUM_VISIBLE_ROWS: return
        if event.delta > 0: self.top_index -= 1
        else: self.top_index += 1
        self.top_index = max(0, min(self.top_index, total - self.NUM_VISIBLE_ROWS))
        self.refresh_virtual_grid()

    def refresh_virtual_grid(self):
        total = len(self.loaded_paths)
        self.visible_paths = [] 
        if total == 0:
            for i in range(self.NUM_VISIBLE_ROWS): self.hide_row(i)
            self.scrollbar.set(0, 1); self.empty_frame.place(relx=0.5, rely=0.5, anchor="center"); self.empty_frame.tkraise()
            return
        else: self.empty_frame.place_forget()

        if total > self.NUM_VISIBLE_ROWS:
            thumb_start = self.top_index / total; thumb_end = (self.top_index + self.NUM_VISIBLE_ROWS) / total
            self.scrollbar.set(thumb_start, thumb_end)
        else: self.scrollbar.set(0, 1)

        for i in range(self.NUM_VISIBLE_ROWS):
            data_index = self.top_index + i
            if data_index < total:
                path = self.loaded_paths[data_index]
                self.visible_paths.append(path)
                data = self.file_data[path]
                w = self.row_widgets[i]
                
                self.show_row(i)
                w['name'].delete(0, 'end'); w['name'].insert(0, data['name']); w['name'].set_initial_state() 
                
                is_staged = data['estado'] == COLOR_MODIFIED
                highlight = data['is_custom'] or data['is_formatted'] or is_staged
                
                w['name'].configure(text_color=TEXT_PURE if highlight else TEXT_PALE)
                w['tag_lbl'].configure(text=data['ext'], text_color=TEXT_MUTED if data['ext'] == 'WAV' else ACCENT)
                
                w['bpm'].delete(0, 'end')
                if data['bpm']: w['bpm'].insert(0, data['bpm'])
                w['bpm'].set_initial_state()
                w['bpm'].configure(text_color=TEXT_PURE if highlight else TEXT_PALE)
                
                w['key'].delete(0, 'end')
                if data['key']: w['key'].insert(0, data['key'])
                w['key'].set_initial_state()
                w['key'].configure(text_color=TEXT_PURE if highlight else TEXT_PALE)
                
                w['estado'].configure(text_color=data['estado'])
                
                can_undo = data['is_custom'] or data.get('is_staged', False)
                if can_undo: 
                    w['btn_undo'].configure(state="normal", image=self.ic_undo_accent if data['is_custom'] else self.ic_undo_red)
                else: 
                    w['btn_undo'].configure(state="disabled", image=self.ic_undo_muted)
                
                if data.get('converted_to_wav', False): w['btn_wav'].configure(state="disabled", text_color_disabled=COLOR_SAVED, text_color=COLOR_SAVED)
                elif data['ext'] == 'WAV': w['btn_wav'].configure(state="disabled", text_color_disabled=TEXT_MUTED, text_color=TEXT_MUTED)
                else: w['btn_wav'].configure(state="normal", text_color=ACCENT)
                
                if self.is_playing and self.current_playing_path == path:
                    if self.is_paused:
                        w['btn_play'].configure(image=self.ic_play, text="", text_color=ACCENT, fg_color="transparent")
                    else:
                        w['btn_play'].configure(image=self.ic_pause, text="", text_color=ACCENT, fg_color="transparent")
                else:
                    w['btn_play'].configure(image=self.ic_play, text="", text_color=TEXT_NORMAL, fg_color="transparent")
                    w['btn_play'].update_idletasks()
                    
            else:
                self.hide_row(i); self.visible_paths.append(None)
                
        self.update_apply_button_state(); self.update_wav_button_state()

    def update_wav_button_state(self):
        if getattr(self, 'is_wav_all_applied', False): self.btn_mass_wav.configure(text="[ RESTAURAR ]", state="normal", text_color=COLOR_MODIFIED)
        else:
            has_non_wav = any(d['ext'] != 'WAV' for d in self.file_data.values())
            if has_non_wav: self.btn_mass_wav.configure(text="[ WAV ALL ]", state="normal", text_color=ACCENT)
            else: self.btn_mass_wav.configure(text="[ WAV ALL ]", state="disabled", text_color=TEXT_MUTED)

    def toggle_wav_all(self):
        if getattr(self, 'is_wav_all_applied', False): self.restore_all_formats()
        else: self.convert_all_to_wav()

    def restart_single_file(self, row_idx):
        path = self.visible_paths[row_idx]
        if not path: return
        if path in self.session_history: self.undo_single_file(path, auto_update=True)
        elif self.file_data[path]['estado'] == COLOR_MODIFIED: self.abort_staging(path)

    def abort_staging(self, path):
        self.file_data[path]['orig_name'] = os.path.splitext(os.path.basename(path))[0]
        bn = self.file_data[path]['orig_name']
        s_bpm, s_key = self.read_metadata(path)
        pure_n = self._extract_pure_name(bn, s_bpm, s_key)
        self.file_data[path]['name'] = bn; self.file_data[path]['pure_name'] = pure_n; self.file_data[path]['bpm'] = s_bpm; self.file_data[path]['key'] = s_key; self.file_data[path]['estado'] = TEXT_MUTED; self.file_data[path]['is_custom'] = False; self.file_data[path]['is_staged'] = False
        self.refresh_virtual_grid(); self.update_apply_button_state()

    def handle_web(self, row_idx):
        path = self.visible_paths[row_idx]
        if path:
            track_name = self.file_data[path]['name'].strip()
            if track_name:
                query = urllib.parse.quote_plus(f"{track_name} bpm key")
                webbrowser.open(f"https://www.google.com/search?q={query}")

    def handle_analyze(self, row_idx):
        path = self.visible_paths[row_idx]
        if not path: return

        if not ESSENTIA_AVAILABLE:
            self.log_message("> [ERROR] Essentia no detectado. Abre tu terminal y ejecuta: pip install essentia")
            return

        pure_name = self.file_data[path]['pure_name'].strip()
        self.show_loading(f"ANALIZANDO AUDIO\n{pure_name[:20]}...")
        self.log_message(f"> [MOTOR LOCAL] Analizando: {os.path.basename(path)} (Rango: {self.bpm_range})")
        
        threading.Thread(target=self._do_analyze_essentia, args=(path, pure_name), daemon=True).start()

    def _do_analyze_essentia(self, path, pure_name):
        try:
            time.sleep(0.6) 
            
            audio = es.MonoLoader(filename=path)()
            bpm_estimator = es.PercivalBpmEstimator()
            bpm = bpm_estimator(audio)
            
            if self.bpm_range == "Electrónica (90-170)":
                if bpm < 90.0: 
                    bpm *= 2.0
                    self.after(0, lambda: self.log_message("> [FILTRO] BPM x2 (Rango Electrónica aplicado)"))
                elif bpm > 175.0: 
                    bpm /= 2.0
                    self.after(0, lambda: self.log_message("> [FILTRO] BPM /2 (Rango Electrónica aplicado)"))
                    
            elif self.bpm_range == "Urbano/Reggaeton (70-120)":
                if bpm > 130.0: 
                    bpm /= 2.0
                    self.after(0, lambda: self.log_message("> [FILTRO] BPM /2 (Rango Urbano aplicado)"))
                elif bpm < 60.0:
                    bpm *= 2.0
                    self.after(0, lambda: self.log_message("> [FILTRO] BPM x2 (Rango Urbano aplicado)"))
                    
            elif self.bpm_range == "Drum & Bass (150-200)":
                if bpm < 130.0: 
                    bpm *= 2.0
                    self.after(0, lambda: self.log_message("> [FILTRO] BPM x2 (Rango DnB aplicado)"))

            detected_bpm = str(int(round(bpm)))
            
            self.after(0, lambda: setattr(self, 'loading_base_msg', "ANALIZANDO\nTONALIDAD..."))
            key_extractor = es.KeyExtractor(profileType="edma")
            key_val, scale_val, _ = key_extractor(audio)
            
            scale_short = "maj" if scale_val.lower() == "major" else "min"
            detected_key = f"{key_val} {scale_short}"

            self.after(0, lambda: self._apply_analysis(path, detected_bpm, detected_key))

        except Exception as e:
            self.after(0, lambda: setattr(self, 'loading_base_msg', "¡ERROR EN\nANÁLISIS!"))
            self.after(0, self.hide_loading)
            self.after(0, lambda err=e: self.log_message(f"> [ERROR ESSENTIA]: {str(err)}"))

    def _apply_analysis(self, path, detected_bpm, detected_key):
        if path in self.file_data:
            self.file_data[path]['bpm'] = detected_bpm
            self.file_data[path]['key'] = detected_key
            self.file_data[path]['estado'] = COLOR_MODIFIED
            self.log_message(f"> [OK] Análisis completado -> BPM: {detected_bpm} | KEY: {detected_key}")
            self.refresh_virtual_grid()
            if path in self.visible_paths:
                idx = self.visible_paths.index(path)
                self.stage_row_changes(idx)
        
        self.loading_base_msg = "¡ANÁLISIS\nCOMPLETO!"
        self.hide_loading()

    def sort_grid(self, col):
        self.show_loading(f"ORDENANDO\n{col}")
        self.after(400, lambda: self._do_sort_grid(col))

    def _do_sort_grid(self, col):
        if self.current_sort_col == col: self.sort_asc = not self.sort_asc
        else: self.current_sort_col = col; self.sort_asc = False if col in ["TEMPO/BPM", "ST"] else True
        def get_sort_key(p):
            data = self.file_data[p]
            if col == "NOMBRE DE ARCHIVOS": return data['name'].lower()
            elif col == "FORMATO": return data['ext'].lower()
            elif col == "TEMPO/BPM":
                try: return float(data['bpm'])
                except: return 0.0 if not self.sort_asc else 999.0
            elif col == "KEY/TONO":
                match = REGEX_KEY_STRICT.match(data['key'].strip())
                if match: return (int(match.group(1)), match.group(2).upper())
                return (99, data['key'].upper())
            elif col == "ST": return data['is_custom']
            return ""
        self.loaded_paths.sort(key=get_sort_key, reverse=not self.sort_asc)
        self.top_index = 0
        self.draw_headers()
        self.refresh_virtual_grid()
        self.loading_base_msg = "¡ORDEN\nCOMPLETO!"
        self.hide_loading()

    def read_metadata(self, filepath):
        if filepath in self.metadata_cache: return self.metadata_cache[filepath]['bpm'], self.metadata_cache[filepath]['key']
        bpm, key = "", ""
        try:
            from mutagen.wave import WAVE
            from mutagen.aiff import AIFF
            from mutagen.mp3 import MP3
            from mutagen.flac import FLAC
            ext = os.path.splitext(filepath)[1].lower()
            if ext == '.mp3':
                audio = MP3(filepath)
                if audio.tags:
                    if 'TBPM' in audio.tags: bpm = str(audio.tags['TBPM'].text[0])
                    if 'TKEY' in audio.tags: key = str(audio.tags['TKEY'].text[0])
            elif ext == '.wav':
                audio = WAVE(filepath)
                if audio.tags:
                    if 'TBPM' in audio.tags: bpm = str(audio.tags['TBPM'].text[0])
                    if 'TKEY' in audio.tags: key = str(audio.tags['TKEY'].text[0])
            elif ext in ('.aiff', '.aif'):
                audio = AIFF(filepath)
                if audio.tags:
                    if 'TBPM' in audio.tags: bpm = str(audio.tags['TBPM'].text[0])
                    if 'TKEY' in audio.tags: key = str(audio.tags['TKEY'].text[0])
            elif ext == '.flac':
                audio = FLAC(filepath)
                if audio.tags:
                    if 'bpm' in audio: bpm = str(audio['bpm'][0])
                    if 'key' in audio: key = str(audio['key'][0])
        except: pass 
        self.metadata_cache[filepath] = {'bpm': bpm, 'key': key}
        return bpm, key

    def write_metadata(self, filepath, bpm, key):
        try:
            os.chmod(filepath, 0o666)
        except: pass

        try:
            from mutagen.id3 import ID3, TBPM, TKEY
            from mutagen.wave import WAVE
            from mutagen.aiff import AIFF
            from mutagen.mp3 import MP3
            from mutagen.flac import FLAC

            ext = os.path.splitext(filepath)[1].lower()
            
            def update_id3(audio):
                if audio.tags is None: audio.add_tags()
                if bpm: audio.tags.add(TBPM(encoding=3, text=bpm))
                else: audio.tags.pop('TBPM', None)
                if key: audio.tags.add(TKEY(encoding=3, text=key))
                else: audio.tags.pop('TKEY', None)
                
                saved = False
                for _ in range(4):
                    try:
                        audio.save()
                        saved = True
                        break
                    except Exception as exc:
                        if "Permission denied" in str(exc) or "Errno 13" in str(exc):
                            time.sleep(0.5)
                        else:
                            raise exc
                if not saved: audio.save()

            if ext == '.mp3': update_id3(MP3(filepath))
            elif ext == '.wav': update_id3(WAVE(filepath))
            elif ext in ('.aiff', '.aif'): update_id3(AIFF(filepath))
            elif ext == '.flac':
                audio = FLAC(filepath)
                if bpm: audio['bpm'] = bpm
                else: audio.pop('bpm', None)
                if key: audio['key'] = key
                else: audio.pop('key', None)
                
                saved = False
                for _ in range(4):
                    try:
                        audio.save()
                        saved = True
                        break
                    except Exception as exc:
                        if "Permission denied" in str(exc) or "Errno 13" in str(exc):
                            time.sleep(0.5)
                        else:
                            raise exc
                if not saved: audio.save()

        except Exception as e:
            self.after(0, lambda: self.log_message(f"> Advertencia ID3 en {os.path.basename(filepath)}: {e}"))

    def update_apply_button_state(self):
        any_active = any(d['estado'] == COLOR_MODIFIED for d in self.file_data.values())
        if any_active: self.btn_run.configure(fg_color=BG_MAIN, text_color=ACCENT, state="normal", hover_color="#1E1E1E", border_color=ACCENT)
        else: self.btn_run.configure(fg_color=BG_MAIN, text_color=TEXT_MUTED, state="disabled", border_color="#222")

    def _sync_visible_rows_to_data(self):
        """Conserva cambios escritos en filas visibles antes de recalcular el formato global."""
        for row_idx in range(self.NUM_VISIBLE_ROWS):
            if row_idx >= len(self.visible_paths):
                break

            path = self.visible_paths[row_idx]
            if not path or path not in self.file_data:
                continue

            w = self.row_widgets[row_idx]
            raw_name = w['name'].get().strip()
            bpm = w['bpm'].get().strip()
            key = w['key'].get().strip()
            data = self.file_data[path]

            if raw_name != data['name']:
                data['orig_name'] = raw_name
                data['pure_name'] = self._extract_pure_name(raw_name, bpm, key)

            data['bpm'] = bpm
            data['key'] = key

    def log_message(self, message):
        self.textbox_log.configure(state="normal"); self.textbox_log.insert("end", message + "\n"); self.textbox_log.see("end"); self.textbox_log.configure(state="disabled")

    def clear_all(self):
        self.show_loading("LIMPIANDO...")
        self.stop_audio(force_release=True)
        self.after(500, self._do_clear_all)

    def _do_clear_all(self):
        self.csv_path = ""; self.loaded_paths.clear(); self.file_data.clear(); self.session_history.clear(); self.metadata_cache.clear()
        self.current_sort_col = "NOMBRE DE ARCHIVOS"
        self.sort_asc = True; self.top_index = 0
        self.is_wav_all_applied = False
        self.current_local_dir = ""
        self.lbl_local_path.configure(text="Ruta: Ninguna")
        self.draw_headers(); self._update_loaded_count_display(); self.refresh_virtual_grid() 
        self.textbox_log.configure(state="normal"); self.textbox_log.delete("1.0", "end"); self.log_message("> Reset de sistema."); self.textbox_log.configure(state="disabled")
        self.update_apply_button_state(); self.update_wav_button_state()
        self.loading_base_msg = "¡MEMORIA\nLIMPIA!"
        self.hide_loading()

    def _prepare_files_data(self, paths):
        new_paths = []
        new_data = {}
        for p in paths:
            if p not in self.loaded_paths:
                bn, ext = os.path.splitext(os.path.basename(p))
                ep = ext.replace('.', '').upper()
                cu = p in self.session_history
                s_bpm, s_key = self.read_metadata(p) 
                pure_n = self._extract_pure_name(bn, s_bpm, s_key)
                
                is_formatted = False
                if not cu and s_bpm and s_key:
                    for fmt in self.format_options:
                        if fmt == "Añadir solo metadatos": continue
                        pos_name = self._build_formatted_name(pure_n, s_bpm, s_key, fmt)
                        if bn == pos_name:
                            is_formatted = True
                            break
                            
                new_paths.append(p)
                new_data[p] = {
                    'name': bn, 'pure_name': pure_n, 'orig_name': bn, 'bpm': s_bpm, 'key': s_key, 
                    'ext': ep, 'estado': COLOR_SAVED if (cu or is_formatted) else TEXT_MUTED, 
                    'is_custom': cu, 
                    'is_formatted': is_formatted,
                    'is_staged': False,
                    'converted_to_wav': False
                }
        return new_paths, new_data

    def _sync_files_data(self, new_paths, new_data):
        for p in new_paths:
            if p not in self.loaded_paths:
                self.loaded_paths.append(p)
                self.file_data[p] = new_data[p]
        self._update_loaded_count_display()

    def select_folder(self):
        f = filedialog.askdirectory()
        self.focus_force() 
        if f:
            self.current_local_dir = f
            self.lbl_local_path.configure(text=f"Ruta: {f}")
            self.show_loading("LEYENDO\nMETADATOS...")
            threading.Thread(target=self._thread_select_folder, args=(f,), daemon=True).start()

    def _thread_select_folder(self, f):
        time.sleep(0.5) 
        paths = [os.path.join(f, x) for x in os.listdir(f) if x.lower().endswith(('.wav','.aiff','.mp3','.flac'))]
        new_paths, new_data = self._prepare_files_data(paths)
        self.after(0, lambda: self._finish_select_folder(f, new_paths, new_data))

    def _finish_select_folder(self, f, new_paths, new_data):
        self._sync_files_data(new_paths, new_data)
        self.log_message("-" * 30); self.log_message(f"Carpeta cargada: {f}")
        self.top_index = 0; self.draw_headers(); self._update_loaded_count_display(); self.refresh_virtual_grid()
        self.loading_base_msg = "¡ARCHIVOS\nCARGADOS!"
        self.hide_loading()

    def select_files(self):
        f = filedialog.askopenfilenames(filetypes=[("Audio Files", "*.wav *.aiff *.mp3 *.flac")])
        self.focus_force() 
        if f:
            self.current_local_dir = os.path.dirname(f[0])
            self.lbl_local_path.configure(text=f"Ruta: {self.current_local_dir}")
            self.show_loading("LEYENDO\nMETADATOS...")
            threading.Thread(target=self._thread_select_files, args=(f,), daemon=True).start()

    def _thread_select_files(self, f):
        time.sleep(0.5)
        new_paths, new_data = self._prepare_files_data(f)
        self.after(0, lambda: self._finish_select_files(new_paths, new_data))

    def _finish_select_files(self, new_paths, new_data):
        self._sync_files_data(new_paths, new_data)
        self.log_message("-" * 30); self.log_message(f"Archivos añadidos: {len(new_paths)} elementos.")
        self._update_loaded_count_display()
        self.top_index = 0; self.refresh_virtual_grid()
        self.loading_base_msg = "¡ARCHIVOS\nCARGADOS!"
        self.hide_loading()

    def select_csv(self):
        f = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        self.focus_force() 
        if f: 
            self.csv_path = f
            self.log_message("-" * 30); self.log_message(f"CSV vinculado: {os.path.basename(f)}")

    def convert_to_wav(self, current_path, auto_update=True):
        if self.current_playing_path == current_path and self.is_playing: 
            self.stop_audio(force_release=True)
        
        d, fn = os.path.dirname(current_path), os.path.basename(current_path)
        ext_orig = os.path.splitext(fn)[1].replace('.', '').upper()
        b = os.path.join(d, "_BACKUP_ORIGINALES")
        n = os.path.splitext(current_path)[0] + ".wav"
        
        self.watchdog_shield.add(current_path)
        self.watchdog_shield.add(n)
        
        if auto_update: self.show_loading(f"CONVIRTIENDO\n{fn[:15]}...")
        self.log_message(f"--- INICIANDO CONVERSIÓN: {ext_orig} -> WAV ({fn}) ---")
        try:
            if not os.path.exists(b): os.makedirs(b)
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@44100", current_path, n], check=True)
            bk = os.path.join(b, fn); shutil.move(current_path, bk)
            self.session_history[n] = bk
            self.loaded_paths[self.loaded_paths.index(current_path)] = n
            if current_path in self.metadata_cache: self.metadata_cache[n] = self.metadata_cache.pop(current_path)
            if current_path in self.file_data:
                data = self.file_data.pop(current_path)
                data['ext'] = 'WAV'; data['is_custom'] = True; data['converted_to_wav'] = True 
                self.file_data[n] = data
            if auto_update: self.refresh_virtual_grid()
        except Exception as e: self.log_message(f"> Error en {fn}: {e}")
        
        self.after(3000, lambda cp=current_path, np=n: self._clear_shield(cp, np))
        
        if auto_update:
            self.loading_base_msg = "¡CONVERSIÓN\nCOMPLETA!"
            self.hide_loading()

    def convert_all_to_wav(self):
        to_convert = [p for p in self.loaded_paths if not p.lower().endswith('.wav')]
        if not to_convert: return
        
        self.stop_smart_folder()
        self.show_loading(f"COLA WAV\n0/{len(to_convert)}")
        self.process_next_conversion(to_convert, 0)

    def process_next_conversion(self, file_list, index):
        if index >= len(file_list):
            self.is_wav_all_applied = True
            self.show_loading("ACTUALIZANDO\nCARPETA...")
            self.after(1500, self._finalize_mass_conversion)
            return
        p = file_list[index]
        self.loading_base_msg = f"CONVIRTIENDO\n{index+1}/{len(file_list)}"
        self.update()
        self.convert_to_wav(p, auto_update=False)
        self.after(50, lambda: self.process_next_conversion(file_list, index + 1))
        
    def _finalize_mass_conversion(self):
        existing_paths = []
        for p in self.loaded_paths:
            if os.path.exists(p):
                existing_paths.append(p)
            else:
                self.file_data.pop(p, None)
                self.session_history.pop(p, None)
                self.metadata_cache.pop(p, None)
        self.loaded_paths = existing_paths
        self._update_loaded_count_display()
        
        self.update_wav_button_state()
        self.refresh_virtual_grid()
        self.loading_base_msg = "¡TODOS\nCONVERTIDOS!"
        
        if self.tabs.get().startswith("CARPETA INTELIGENTE"):
            self._start_smart_observer()
            
        self.hide_loading()

    def restore_all_formats(self):
        to_restore = []
        for p in self.loaded_paths:
            if p in self.session_history:
                old_path = self.session_history[p]
                if os.path.splitext(old_path)[1].lower() != '.wav' and os.path.splitext(p)[1].lower() == '.wav':
                    to_restore.append(p)
        if not to_restore:
            self.is_wav_all_applied = False
            self.update_wav_button_state()
            return
            
        self.stop_smart_folder()
        self.show_loading(f"RESTAURANDO\n0/{len(to_restore)}")
        self.process_next_restore(to_restore, 0)

    def process_next_restore(self, file_list, index):
        if index >= len(file_list):
            self.is_wav_all_applied = False
            self.update_wav_button_state(); self.refresh_virtual_grid()
            self.loading_base_msg = "¡FORMATOS\nRESTAURADOS!"
            if self.tabs.get().startswith("CARPETA INTELIGENTE"):
                self._start_smart_observer()
            self.hide_loading()
            return
        p = file_list[index]
        self.loading_base_msg = f"RESTAURANDO\n{index+1}/{len(file_list)}"
        self.update()
        self.undo_single_file(p, auto_update=False)
        self.after(50, lambda: self.process_next_restore(file_list, index + 1))

    def undo_single_file(self, current_path, auto_update=True):
        if current_path not in self.session_history: return
        if self.current_playing_path == current_path and self.is_playing: 
            self.stop_audio(force_release=True)
        
        if auto_update: self.show_loading("RESTAURANDO\nORIGINAL...")
        op = self.session_history[current_path]
        try:
            if "_BACKUP_ORIGINALES" in op:
                rp = os.path.join(os.path.dirname(os.path.dirname(op)), os.path.basename(op))
                self.watchdog_shield.add(current_path)
                self.watchdog_shield.add(rp)
                
                shutil.move(op, rp); os.remove(current_path) if os.path.exists(current_path) else None
                bd = os.path.dirname(op)
                if os.path.exists(bd) and not os.listdir(bd): os.rmdir(bd)
                self.loaded_paths[self.loaded_paths.index(current_path)] = rp
                if current_path in self.metadata_cache: self.metadata_cache[rp] = self.metadata_cache.pop(current_path)
                new_path = rp
            else:
                self.watchdog_shield.add(current_path)
                self.watchdog_shield.add(op)
                
                shutil.move(current_path, op)
                self.loaded_paths[self.loaded_paths.index(current_path)] = op
                if current_path in self.metadata_cache: self.metadata_cache[op] = self.metadata_cache.pop(current_path)
                new_path = op
                
            del self.session_history[current_path]
            if current_path in self.file_data:
                data = self.file_data.pop(current_path)
                final_name = os.path.splitext(os.path.basename(new_path))[0]
                
                data['orig_name'] = final_name
                
                old_bpm, old_key = self.read_metadata(new_path)
                pure_n = self._extract_pure_name(final_name, old_bpm, old_key)
                data['name'] = final_name; data['pure_name'] = pure_n; data['bpm'] = old_bpm; data['key'] = old_key; data['is_custom'] = False; data['is_staged'] = False; data['estado'] = TEXT_MUTED; data['ext'] = os.path.splitext(new_path)[1].replace('.', '').upper(); data['converted_to_wav'] = False 
                self.file_data[new_path] = data
        except Exception as e: self.log_message(f"> Error Undo: {e}")
        
        self.after(3000, lambda cp=current_path, np=new_path: self._clear_shield(cp, np))
        
        if auto_update:
            self.refresh_virtual_grid(); self.update_wav_button_state()
            self.loading_base_msg = "¡ARCHIVO\nRESTAURADO!"
            self.hide_loading()

    def run_rename_all(self):
        for i in range(self.NUM_VISIBLE_ROWS):
            self.stage_row_changes_if_needed(i)
            
        paths_to_process = [p for p, d in self.file_data.items() if d['estado'] == COLOR_MODIFIED]
        if not paths_to_process: return
        if not messagebox.askyesno("Confirmar", f"Se aplicarán a {len(paths_to_process)} archivos. ¿Continuar?"): return

        self.stop_audio(force_release=True) 
        
        self.stop_smart_folder()
        self.show_loading("GUARDANDO\nMETADATOS...")
        threading.Thread(target=self._thread_run_rename_all, args=(paths_to_process,), daemon=True).start()

    def _thread_run_rename_all(self, paths_to_process):
        time.sleep(0.2) 
        
        rc = 0; fmt = self.format_var.get()
        success_updates = [] 
        
        for p in paths_to_process:
            if p not in self.file_data: continue
                
            data = self.file_data[p].copy() 
            cn, bp, ky, ex = data['name'].strip(), data['bpm'].strip(), data['key'].strip(), f".{data['ext'].lower()}"
            if cn: 
                old_bpm, old_key = self.read_metadata(p)
                pure_n = data['pure_name']
                
                if fmt == "Añadir solo metadatos":
                    final_name = data['orig_name']
                else:
                    final_name = self._build_formatted_name(pure_n, bp, ky, fmt)
                    
                nf = f"{final_name}{ex}"
                np = os.path.join(os.path.dirname(p), nf)
                try:
                    self.watchdog_shield.add(p)
                    self.watchdog_shield.add(np)
                    
                    temp_path = os.path.join(tempfile.gettempdir(), f"yezka_atomic_{int(time.time()*1000)}{ex}")
                    shutil.copy2(p, temp_path)
                    
                    self.write_metadata(temp_path, bp, ky)
                    
                    shutil.move(temp_path, np)
                    
                    if p != np:
                        try:
                            os.remove(p)
                        except Exception:
                            subprocess.run(["rm", "-f", p])
                            
                    data['name'] = final_name
                    data['estado'] = COLOR_SAVED
                    data['is_custom'] = True
                    data['is_staged'] = False
                    
                    success_updates.append((p, np, data))
                    rc += 1
                    self.after(0, lambda fn=final_name: self.log_message(f"> Metadatos inyectados con éxito en ID3 de {fn}"))
                except Exception as e:
                    self.after(0, lambda err=e, bad_p=p: self.log_message(f"> Error procesando {os.path.basename(bad_p)}: {err}"))
        
        self.after(0, lambda: self._finish_run_rename_all(rc, success_updates))

    def _finish_run_rename_all(self, rc, success_updates):
        for old_p, new_p, new_data in success_updates:
            if old_p in self.file_data: self.file_data.pop(old_p)
            if old_p in self.loaded_paths: self.loaded_paths[self.loaded_paths.index(old_p)] = new_p
            
            self.file_data[new_p] = new_data
            if old_p != new_p:
                h = self.session_history.pop(old_p) if old_p in self.session_history else old_p
                self.session_history[new_p] = h
                if old_p in self.metadata_cache: self.metadata_cache[new_p] = self.metadata_cache.pop(old_p)
                
            self.after(3000, lambda op=old_p, np=new_p: self._clear_shield(op, np))
            
        self.show_loading("ACTUALIZANDO\nCARPETA...")
        self.after(1500, self._finalize_mass_conversion)

    def _clear_shield(self, p1, p2):
        self.watchdog_shield.discard(p1)
        self.watchdog_shield.discard(p2)

if __name__ == "__main__":
    app = YezkaApp()
    app.mainloop()