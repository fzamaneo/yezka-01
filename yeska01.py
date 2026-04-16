# -*- coding: utf-8 -*-
import os
import sys
import csv
import shutil
import webbrowser
import urllib.parse
import re
import threading
import time
import json 
import base64
import requests 
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pytablericons import TablerIcons, OutlineIcon 

# --- CREDENCIALES DE SPOTIFY API ---
SPOTIFY_CLIENT_ID = "CLAVES_OCULTAS"
SPOTIFY_CLIENT_SECRET = "CLAVES_OCULTAS"

# --- CONFIGURACIÓN GLOBAL (MINIMALISMO YEZKA-01) ---
ctk.set_appearance_mode("dark")

FONT_MONO = ("Menlo", 12)  
FONT_MONO_BOLD = ("Menlo", 12, "bold")
FONT_TITLE = ("Menlo", 17, "bold")
FONT_NAME = ("Menlo", 13, "normal") 

BG_MAIN = "#000000"      
BG_HOVER = "#1E1E1E"     
BG_ELEMENT = "#141414"   
ACCENT = "#DCE038"       

COLOR_MODIFIED = "#E93B35" 
COLOR_SAVED = "#35E93B"    

TEXT_NORMAL = "#DFDFDF"  
TEXT_PURE = "#FFFFFF"    
TEXT_PALE = "#C0C0C0"    
TEXT_MUTED = "#555555"   

RADIUS = 4 

REGEX_KEY_START = re.compile(r'^(\d{1,2}[A-Za-z]{1,3})\s*[-_ ]\s*(.*)')
REGEX_BPM_START = re.compile(r'^(\d{2,3}(?:\.\d+)?)\s*(?:BPM)?\s*[-_ ]\s*(.*)', re.IGNORECASE)
REGEX_KEY_END = re.compile(r'(.*?)\s*[-_ ]\s*(\d{1,2}[A-Za-z]{1,3})$')
REGEX_BPM_END = re.compile(r'(.*?)\s*[-_ ]\s*(\d{2,3}(?:\.\d+)?)\s*(?:BPM)?$', re.IGNORECASE)
REGEX_KEY_STRICT = re.compile(r'^(\d{1,2})([A-Za-z]+)$')

class YezkaEntry(ctk.CTkEntry):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.undo_stack = []
        self.redo_stack = []
        self._entry.bind("<KeyRelease>", self.save_state)
        self._entry.bind("<Command-z>", self.undo)
        self._entry.bind("<Command-y>", self.redo)
        self._entry.bind("<Command-Z>", self.redo) 
        self._entry.bind("<Control-z>", self.undo) 
        self._entry.bind("<Control-y>", self.redo)
        self._entry.bind("<Control-Z>", self.redo)

    def set_initial_state(self):
        self.undo_stack = [self.get()]
        self.redo_stack = []

    def save_state(self, event):
        if event.keysym in ("z", "y", "Z", "Command_L", "Command_R", "Control_L", "Control_R", "Shift_L", "Shift_R", "Return", "Meta_L", "Meta_R"): 
            return
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
        self.widget.bind("<ButtonPress>", self.leave) 

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
        label = tk.Label(tw, text=self.text, justify='left', background=BG_ELEMENT, foreground=TEXT_NORMAL, relief='flat', borderwidth=0, font=FONT_MONO)
        label.pack(ipadx=6, ipady=3)

    def hidetip(self):
        if self.tooltip_window: self.tooltip_window.destroy(); self.tooltip_window = None

class SmartFolderHandler(FileSystemEventHandler):
    def __init__(self, add_callback, remove_callback):
        self.add_callback = add_callback; self.remove_callback = remove_callback
        self.valid_extensions = ('.wav', '.aiff', '.mp3', '.flac')

    def on_created(self, event):
        if not event.is_directory:
            filepath = event.src_path
            if filepath.lower().endswith(self.valid_extensions):
                time.sleep(0.5); self.add_callback(filepath)

    def on_deleted(self, event):
        if not event.is_directory:
            filepath = event.src_path
            if filepath.lower().endswith(self.valid_extensions): self.remove_callback(filepath)
                
    def on_moved(self, event):
        if not event.is_directory:
            if event.src_path.lower().endswith(self.valid_extensions): self.remove_callback(event.src_path)
            if event.dest_path.lower().endswith(self.valid_extensions):
                time.sleep(0.5); self.add_callback(event.dest_path)

class YezkaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._init_done = False 
        
        self.title("YEZKA-01 - v0.8.36 (Spotify API Connection Fixed)") 
        self.geometry("1134x780") 
        self.resizable(False, False)
        self.configure(fg_color=BG_MAIN)

        self.csv_path = ""
        self.loaded_paths = [] 
        self.metadata_cache = {} 
        self.file_data = {} 
        self.session_history = {} 

        self.current_sort_col = "NOMBRE DE ARCHIVOS"
        self.sort_asc = True
        self.is_wav_all_applied = False

        self.config_file = os.path.expanduser("~/.yezka_config.json")
        self.default_smart_folder = os.path.expanduser("~/Documents/DESCARGAS YESKA")
        self.smart_folder_path = self.load_config()
        self.observer = None

        self.NUM_VISIBLE_ROWS = 11 
        self.top_index = 0
        self.row_widgets = [] 
        self.visible_paths = [] 
        self.COL_WIDTHS = [640, 85, 70, 70, 50, 180]

        self.ic_trash = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.TRASH, color=TEXT_NORMAL, size=24, stroke_width=1), dark_image=TablerIcons.load(OutlineIcon.TRASH, color=TEXT_NORMAL, size=24, stroke_width=1), size=(20, 20))
        self.ic_refresh = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.REFRESH, color=ACCENT, size=24, stroke_width=1), dark_image=TablerIcons.load(OutlineIcon.REFRESH, color=ACCENT, size=24, stroke_width=1), size=(20, 20))
        self.ic_web = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.WORLD_SEARCH, color=TEXT_NORMAL, size=24, stroke_width=1), dark_image=TablerIcons.load(OutlineIcon.WORLD_SEARCH, color=TEXT_NORMAL, size=24, stroke_width=1), size=(18, 18))
        self.ic_analyze = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.WAND, color=ACCENT, size=24, stroke_width=1), dark_image=TablerIcons.load(OutlineIcon.WAND, color=ACCENT, size=24, stroke_width=1), size=(18, 18))
        self.ic_undo_muted = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.ARROW_BACK_UP, color=TEXT_MUTED, size=24, stroke_width=1), dark_image=TablerIcons.load(OutlineIcon.ARROW_BACK_UP, color=TEXT_MUTED, size=24, stroke_width=1), size=(18, 18))
        self.ic_undo_accent = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.ARROW_BACK_UP, color=ACCENT, size=24, stroke_width=1), dark_image=TablerIcons.load(OutlineIcon.ARROW_BACK_UP, color=ACCENT, size=24, stroke_width=1), size=(18, 18))
        self.ic_undo_red = ctk.CTkImage(light_image=TablerIcons.load(OutlineIcon.ARROW_BACK_UP, color=COLOR_MODIFIED, size=24, stroke_width=1), dark_image=TablerIcons.load(OutlineIcon.ARROW_BACK_UP, color=COLOR_MODIFIED, size=24, stroke_width=1), size=(18, 18))

        self.label_title = ctk.CTkLabel(self, text="YEZKA-01  //  v0.8.36", font=FONT_TITLE, text_color=TEXT_NORMAL)
        self.label_title.pack(pady=(15, 5), anchor="w", padx=20)

        self.frame_toolbar = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0, height=50) 
        self.frame_toolbar.pack(pady=(5, 10), padx=20, fill="x")
        
        self.tabs = ctk.CTkTabview(self.frame_toolbar, height=60, fg_color="transparent", bg_color="transparent", segmented_button_fg_color=BG_ELEMENT, segmented_button_selected_color="#2A2A2A", segmented_button_unselected_color=BG_ELEMENT, text_color=TEXT_NORMAL, command=self.on_tab_change)
        self.tabs.pack(side="left", fill="y")
        
        self.tab_local = self.tabs.add("MODO MANUAL")
        self.tab_smart = self.tabs.add("CARPETA INTELIGENTE")
        
        self.btn_folder = ctk.CTkButton(self.tab_local, text="SELECCIONAR CARPETA", command=self.select_folder, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=0, width=160, height=32)
        self.btn_folder.pack(side="left", padx=(0, 10), pady=0)
        
        self.btn_files = ctk.CTkButton(self.tab_local, text="SELECCIONAR ARCHIVO", command=self.select_files, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=0, width=160, height=32)
        self.btn_files.pack(side="left", padx=(0, 10), pady=0)

        self.label_loaded = ctk.CTkLabel(self.tab_local, text="NINGÚN ARCHIVO CARGADO", font=FONT_MONO, text_color=TEXT_MUTED)
        self.label_loaded.pack(side="left", padx=(10, 0))

        self.btn_change_smart = ctk.CTkButton(self.tab_smart, text="CAMBIAR RUTA", command=self.change_smart_folder, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=0, width=110, height=32)
        self.btn_change_smart.pack(side="left", padx=(0, 10), pady=0)
        
        self.lbl_smart_path = ctk.CTkLabel(self.tab_smart, text=f"Ruta: ...{os.path.basename(self.smart_folder_path)}", font=FONT_MONO, text_color=TEXT_PALE, width=150, anchor="w")
        self.lbl_smart_path.pack(side="left", padx=(0, 15))

        self.frame_global_tools = ctk.CTkFrame(self.frame_toolbar, fg_color="transparent")
        self.frame_global_tools.pack(side="right", fill="y", pady=(28,0)) 
        
        self.btn_clear = ctk.CTkButton(self.frame_global_tools, text="", image=self.ic_trash, width=36, height=32, fg_color=BG_ELEMENT, hover_color="#1E1E1E", corner_radius=RADIUS, command=self.clear_all, border_width=0)
        self.btn_clear.pack(side="right", padx=(10, 0))
        self.tooltip_clear = ToolTip(self.btn_clear, "Vacía la lista de archivos y el registro")

        self.btn_csv = ctk.CTkButton(self.frame_global_tools, text="CSV", width=60, height=32, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO, command=self.select_csv, border_width=0)
        self.btn_csv.pack(side="right", padx=(10, 0))
        ToolTip(self.btn_csv, "Aplica etiquetas desde un archivo CSV")
        
        self.menu_format = ctk.CTkOptionMenu(self.frame_global_tools, values=["►KEY ►BPM - TITULO", "►BPM ►KEY - TITULO", "►BPM - TITULO", "►KEY - TITULO", "TITULO - ◄BPM ◄KEY", "TITULO - ◄KEY ◄BPM", "TITULO - ◄BPM", "TITULO - ◄KEY"], variable=ctk.StringVar(value="►BPM ►KEY - TITULO"), width=200, height=32, fg_color=BG_ELEMENT, button_color=BG_ELEMENT, button_hover_color=BG_HOVER, dropdown_fg_color=BG_ELEMENT, font=FONT_MONO, text_color=TEXT_NORMAL)
        self.format_var = self.menu_format._variable
        self.menu_format.pack(side="right", padx=(10, 0))
        
        self.btn_mass_wav = ctk.CTkButton(self.frame_global_tools, text="[ WAV ALL ]", width=90, height=32, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_MUTED, state="disabled", corner_radius=RADIUS, font=FONT_MONO_BOLD, command=self.toggle_wav_all, border_width=0)
        self.btn_mass_wav.pack(side="right", padx=(10, 0))

        self.table_container = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0)
        self.table_container.pack(padx=20, fill="both", expand=True, pady=(5, 5))

        self.frame_headers = ctk.CTkFrame(self.table_container, fg_color="transparent", corner_radius=0)
        self.frame_headers.pack(fill="x", pady=(0, 2), padx=(0, 16)) 
        
        self.scroll_container = ctk.CTkFrame(self.table_container, fg_color="transparent", height=420)
        self.scroll_container.pack(fill="x", pady=(0, 0))
        self.scroll_container.pack_propagate(False)

        self.scrollbar = ctk.CTkScrollbar(self.scroll_container, command=self.on_scrollbar, fg_color=BG_MAIN, button_color=TEXT_MUTED, button_hover_color=TEXT_PALE)
        self.scrollbar.pack(side="right", fill="y")

        self.rows_frame = ctk.CTkFrame(self.scroll_container, fg_color="transparent")
        self.rows_frame.pack(side="left", fill="both", expand=True)

        for i, w in enumerate(self.COL_WIDTHS):
            self.rows_frame.grid_columnconfigure(i, minsize=w, weight=0)

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
        ctk.CTkLabel(self.empty_frame, text="\n> SELECCIONA CARPETA O ARCHIVO EN LA BARRA SUPERIOR.", font=("Menlo", 10), text_color=TEXT_MUTED, justify="center").pack(pady=(10, 0))
        
        self.frame_footer = ctk.CTkFrame(self.table_container, fg_color="transparent")
        self.frame_footer.pack(fill="x", pady=(5, 5), padx=(0, 16))
        self.btn_run = ctk.CTkButton(self.frame_footer, text="APLICAR CAMBIOS", height=32, command=self.run_rename_all, fg_color=BG_ELEMENT, text_color=TEXT_MUTED, state="disabled", corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=0)
        self.btn_run.pack(side="right")
        
        self.label_log = ctk.CTkLabel(self, text="REGISTRO", font=FONT_MONO_BOLD, text_color=TEXT_MUTED)
        self.label_log.pack(padx=20, anchor="w", pady=(5,0))
        self.textbox_log = ctk.CTkTextbox(self, height=98, state="disabled", fg_color="transparent", text_color="#e93b35", border_width=0, corner_radius=0, font=FONT_MONO)
        self.textbox_log.pack(pady=(0, 15), padx=20, fill="x")

        self.loading_frame = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0)
        self.loading_label = ctk.CTkLabel(self.loading_frame, text="> PROCESANDO...", font=("Menlo", 20, "bold"), text_color=ACCENT)
        self.loading_label.place(relx=0.5, rely=0.5, anchor="center")

        self.draw_headers()
        self.build_virtual_rows()
        self.refresh_virtual_grid() 
        
        self._init_done = True 
        self.focus_force() 

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    return data.get("smart_folder", self.default_smart_folder)
            except: pass
        return self.default_smart_folder

    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump({"smart_folder": self.smart_folder_path}, f)
        except Exception as e:
            self.log_message(f"> Error guardando configuración: {e}")

    def on_tab_change(self):
        if not hasattr(self, '_init_done') or not self._init_done: return 
        current_tab = self.tabs.get()
        self.clear_all()
        if current_tab == "CARPETA INTELIGENTE":
            self.btn_clear.configure(image=self.ic_refresh, command=self.refresh_smart_folder)
            self.tooltip_clear.text = "Forzar escaneo de la Carpeta Inteligente"
            self.start_smart_folder()
        else:
            self.btn_clear.configure(image=self.ic_trash, command=self.clear_all)
            self.tooltip_clear.text = "Vacía la lista de archivos y el registro"
            self.stop_smart_folder()

    def refresh_smart_folder(self):
        self.log_message("> Forzando escaneo de la Carpeta Inteligente...")
        self.clear_all(); self.start_smart_folder()

    def change_smart_folder(self):
        f = filedialog.askdirectory()
        if f:
            self.stop_smart_folder()
            self.smart_folder_path = f
            self.save_config()
            self.lbl_smart_path.configure(text=f"Ruta: ...{os.path.basename(f)}")
            self.log_message(f"> Carpeta Inteligente configurada en: {f}")
            self.clear_all(); self.start_smart_folder()

    def start_smart_folder(self):
        self.stop_smart_folder() 
        if not os.path.exists(self.smart_folder_path):
            try: os.makedirs(self.smart_folder_path, exist_ok=True)
            except Exception: return

        existing_files = [os.path.join(self.smart_folder_path, f) for f in os.listdir(self.smart_folder_path) if f.lower().endswith(('.wav', '.aiff', '.mp3', '.flac'))]
        if existing_files:
            self.show_loading("> LEYENDO CARPETA INTELIGENTE...")
            self.process_new_files(existing_files)
            self.refresh_virtual_grid(); self.hide_loading()
            self.log_message(f"> {len(existing_files)} archivos encontrados en la Carpeta Inteligente.")

        self.observer = Observer()
        event_handler = SmartFolderHandler(self.queue_new_file, self.queue_remove_file)
        self.observer.schedule(event_handler, self.smart_folder_path, recursive=False)
        self.observer.start()
        self.log_message(f"> [AUTO] Escuchando descargas en: {os.path.basename(self.smart_folder_path)}")

    def stop_smart_folder(self):
        if self.observer:
            self.observer.stop(); self.observer.join(); self.observer = None
            self.log_message("> [AUTO] Escucha detenida.")

    def queue_new_file(self, filepath): self.after(100, lambda: self._add_smart_file(filepath))
    def queue_remove_file(self, filepath): self.after(100, lambda: self._remove_smart_file(filepath))

    def _add_smart_file(self, filepath):
        if filepath not in self.loaded_paths and os.path.exists(filepath):
            self.process_new_files([filepath])
            self.refresh_virtual_grid(); self.scrollbar.set(1, 1); self.on_scrollbar('moveto', '1.0')
            self.log_message(f"> [IMPORT] Automático: {os.path.basename(filepath)}")

    def _remove_smart_file(self, filepath):
        if filepath in self.loaded_paths:
            self.loaded_paths.remove(filepath)
            self.file_data.pop(filepath, None); self.session_history.pop(filepath, None); self.metadata_cache.pop(filepath, None)
            self.refresh_virtual_grid(); self.update_apply_button_state(); self.update_wav_button_state()
            self.log_message(f"> [SISTEMA] Removido: {os.path.basename(filepath)}")

    def _extract_pure_name(self, name, tb, tk):
        if not name: return ""
        k_n = tk.replace(" ", "").upper().replace("MAJOR", "MAJ").replace("MINOR", "MIN") if tk else ""
        b_n = tb.strip().upper() if tb else ""
        parts = [x.strip() for x in name.split('-')]
        while parts:
            fst = parts[0].upper()
            if (k_n and fst == k_n) or (b_n and fst == b_n) or fst == f"{b_n} BPM" or fst == f"{b_n}BPM": parts.pop(0)
            else: break
        while parts:
            lst = parts[-1].upper()
            if (k_n and lst == k_n) or (b_n and lst == b_n) or lst == f"{b_n} BPM" or lst == f"{b_n}BPM": parts.pop()
            else: break
        res = "-".join(parts) if parts else name
        while True:
            m_k = REGEX_KEY_START.match(res)
            if m_k: res = m_k.group(2); continue
            m_b = REGEX_BPM_START.match(res)
            if m_b: res = m_b.group(2); continue
            break
        while True:
            m_ke = REGEX_KEY_END.search(res)
            if m_ke: res = m_ke.group(1); continue
            m_be = REGEX_BPM_END.search(res)
            if m_be: res = m_be.group(1); continue
            break
        return res

    def _build_formatted_name(self, pure_name, bp, ky, fmt):
        kn = ky.replace(" ", "").upper().replace("MAJOR", "MAJ").replace("MINOR", "MIN") if ky else ""
        pt = []
        b_name = pure_name
        if fmt == "►KEY ►BPM - TITULO":
            if kn: pt.append(kn)
            if bp: pt.append(bp)
            pt.append(b_name)
        elif fmt == "►BPM ►KEY - TITULO":
            if bp: pt.append(bp)
            if kn: pt.append(kn)
            pt.append(b_name)
        elif fmt == "►BPM - TITULO":
            if bp: pt.append(bp)
            pt.append(b_name)
        elif fmt == "►KEY - TITULO":
            if kn: pt.append(kn)
            pt.append(b_name)
        elif fmt == "TITULO - ◄BPM ◄KEY":
            pt.append(b_name)
            if bp: pt.append(bp)
            if kn: pt.append(kn)
        elif fmt == "TITULO - ◄KEY ◄BPM":
            pt.append(b_name)
            if kn: pt.append(kn)
            if bp: pt.append(bp)
        elif fmt == "TITULO - ◄BPM":
            pt.append(b_name)
            if bp: pt.append(bp)
        elif fmt == "TITULO - ◄KEY":
            pt.append(b_name)
            if kn: pt.append(kn)
        return "-".join([x for x in pt if x])

    def build_virtual_rows(self):
        for i in range(self.NUM_VISIBLE_ROWS):
            row_widgets = {}
            e_name = YezkaEntry(self.rows_frame, width=625, height=28, fg_color=BG_ELEMENT, border_width=0, font=FONT_NAME, corner_radius=RADIUS)
            e_name.grid(row=i, column=0, padx=5, pady=(4, 3), sticky="w")
            tag_lbl = ctk.CTkLabel(self.rows_frame, width=75, height=28, fg_color=BG_ELEMENT, corner_radius=RADIUS, font=FONT_MONO, text="")
            tag_lbl.grid(row=i, column=1, padx=5, pady=(4, 3), sticky="w")
            e_bpm = YezkaEntry(self.rows_frame, width=60, height=28, fg_color=BG_ELEMENT, border_width=0, corner_radius=RADIUS, font=FONT_MONO)
            e_bpm.grid(row=i, column=2, padx=5, pady=(4, 3), sticky="w")
            e_key = YezkaEntry(self.rows_frame, width=60, height=28, fg_color=BG_ELEMENT, border_width=0, corner_radius=RADIUS, font=FONT_MONO)
            e_key.grid(row=i, column=3, padx=5, pady=(4, 3), sticky="w")
            l_st = ctk.CTkLabel(self.rows_frame, text="●", width=40, font=("monospace", 14))
            l_st.grid(row=i, column=4, padx=5, pady=(4, 3))
            af = ctk.CTkFrame(self.rows_frame, fg_color="transparent")
            af.grid(row=i, column=5, padx=5, pady=(4, 3), sticky="w")
            
            bt_u = ctk.CTkButton(af, text="", image=self.ic_undo_muted, width=36, height=28, fg_color=BG_ELEMENT, border_width=0, hover_color="#1E1E1E", corner_radius=RADIUS)
            bt_u.pack(side="left", padx=(0, 2))
            ToolTip(bt_u, "Reiniciar o abortar cambios")
            
            bt_web = ctk.CTkButton(af, text="", image=self.ic_web, width=36, height=28, fg_color=BG_ELEMENT, border_width=0, hover_color="#1E1E1E", corner_radius=RADIUS)
            bt_web.pack(side="left", padx=(0, 2))
            ToolTip(bt_web, "Buscar BPM/Key en navegador")
            
            bt_analyze = ctk.CTkButton(af, text="", image=self.ic_analyze, width=36, height=28, fg_color=BG_ELEMENT, border_width=0, hover_color="#1E1E1E", corner_radius=RADIUS)
            bt_analyze.pack(side="left", padx=(0, 2))
            ToolTip(bt_analyze, "Conectar a Spotify API (Búsqueda Inteligente)")
            
            bt_w = ctk.CTkButton(af, text="WAV", width=42, height=28, fg_color=BG_ELEMENT, border_width=0, hover_color="#1E1E1E", corner_radius=RADIUS, font=FONT_MONO)
            bt_w.pack(side="left")
            ToolTip(bt_w, "Convertir a WAV")

            e_name.bind("<KeyRelease>", lambda e, idx=i: self.visual_row_state(idx, True))
            e_bpm.bind("<KeyRelease>", lambda e, idx=i: self.visual_row_state(idx, False))
            e_key.bind("<KeyRelease>", lambda e, idx=i: self.visual_row_state(idx, False))
            e_name.bind("<Return>", lambda e, idx=i: self.stage_row_changes(idx))
            e_bpm.bind("<Return>", lambda e, idx=i: self.stage_row_changes(idx))
            e_key.bind("<Return>", lambda e, idx=i: self.stage_row_changes(idx))

            bt_u.configure(command=lambda idx=i: self.restart_single_file(idx))
            bt_web.configure(command=lambda idx=i: self.handle_web(idx))
            bt_analyze.configure(command=lambda idx=i: self.handle_analyze(idx))
            bt_w.configure(command=lambda idx=i: self.handle_wav(idx))

            row_widgets = {'name': e_name, 'tag_lbl': tag_lbl, 'bpm': e_bpm, 'key': e_key, 'estado': l_st, 'btn_undo': bt_u, 'btn_web': bt_web, 'btn_analyze': bt_analyze, 'btn_wav': bt_w, 'frame': af}
            self.row_widgets.append(row_widgets)
            self.hide_row(i)

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

    def stage_row_changes(self, row_idx):
        path = self.visible_paths[row_idx]
        if not path: return
        w = self.row_widgets[row_idx]
        raw_name = w['name'].get().strip()
        bp = w['bpm'].get().strip()
        ky = w['key'].get().strip()
        
        if raw_name != self.file_data[path]['name']:
            new_pure = self._extract_pure_name(raw_name, self.file_data[path]['bpm'], self.file_data[path]['key'])
            self.file_data[path]['pure_name'] = new_pure
        
        fmt = self.format_var.get()
        new_formatted_name = self._build_formatted_name(self.file_data[path]['pure_name'], bp, ky, fmt)
        
        w['name'].delete(0, 'end'); w['name'].insert(0, new_formatted_name); w['name'].set_initial_state() 
        self.file_data[path]['name'] = new_formatted_name
        self.file_data[path]['bpm'] = bp
        self.file_data[path]['key'] = ky
        self.file_data[path]['estado'] = COLOR_MODIFIED
        w['estado'].configure(text_color=COLOR_MODIFIED)
        w['name'].configure(text_color=TEXT_PURE) 
        
        self.log_message(f"> Preparado para guardar: {new_formatted_name}")
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
                w['name'].configure(text_color=TEXT_PURE if (data['is_custom'] or is_staged) else TEXT_PALE)
                w['tag_lbl'].configure(text=data['ext'], text_color=TEXT_MUTED if data['ext'] == 'WAV' else ACCENT)
                w['bpm'].delete(0, 'end')
                if data['bpm']: w['bpm'].insert(0, data['bpm'])
                w['bpm'].set_initial_state()
                w['bpm'].configure(text_color=TEXT_PURE if data['is_custom'] else TEXT_PALE)
                w['key'].delete(0, 'end')
                if data['key']: w['key'].insert(0, data['key'])
                w['key'].set_initial_state()
                w['key'].configure(text_color=TEXT_PURE if data['is_custom'] else TEXT_PALE)
                w['estado'].configure(text_color=data['estado'])
                
                if data['is_custom'] or is_staged: w['btn_undo'].configure(state="normal", image=self.ic_undo_accent if data['is_custom'] else self.ic_undo_red)
                else: w['btn_undo'].configure(state="disabled", image=self.ic_undo_muted)
                
                if data.get('converted_to_wav', False): w['btn_wav'].configure(state="disabled", text_color_disabled=COLOR_SAVED, text_color=COLOR_SAVED)
                elif data['ext'] == 'WAV': w['btn_wav'].configure(state="disabled", text_color_disabled=TEXT_MUTED, text_color=TEXT_MUTED)
                else: w['btn_wav'].configure(state="normal", text_color=ACCENT)
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
        bn = os.path.splitext(os.path.basename(path))[0]
        s_bpm, s_key = self.read_metadata(path)
        pure_n = self._extract_pure_name(bn, s_bpm, s_key)
        self.file_data[path]['name'] = bn; self.file_data[path]['pure_name'] = pure_n; self.file_data[path]['bpm'] = s_bpm; self.file_data[path]['key'] = s_key; self.file_data[path]['estado'] = TEXT_MUTED; self.file_data[path]['is_custom'] = False
        self.refresh_virtual_grid(); self.update_apply_button_state()

    def handle_web(self, row_idx):
        path = self.visible_paths[row_idx]
        if path:
            track_name = self.file_data[path]['name'].strip()
            if track_name:
                query = urllib.parse.quote_plus(f"{track_name} bpm key")
                webbrowser.open(f"https://www.google.com/search?q={query}")

    # --- LA MAGIA EN LA NUBE (SPOTIFY API) ---
    def handle_analyze(self, row_idx):
        path = self.visible_paths[row_idx]
        if not path: return
        
        # Validar credenciales
        if SPOTIFY_CLIENT_ID == "PEGA_TU_CLIENT_ID_AQUI" or SPOTIFY_CLIENT_SECRET == "PEGA_TU_CLIENT_SECRET_AQUI":
            messagebox.showerror("Faltan Credenciales", "Por favor, pega tu Client ID y Client Secret de Spotify en las líneas 24 y 25 del código.")
            return

        pure_name = self.file_data[path]['pure_name'].strip()
        if not pure_name:
            self.log_message("> [ERROR] No hay un nombre válido para buscar en Spotify.")
            return

        self.show_loading(f"> CONECTANDO A SPOTIFY...\n[{pure_name}]")
        self.log_message(f"> [API] Buscando huella de: {pure_name}...")
        
        threading.Thread(target=self._do_analyze_spotify, args=(path, pure_name), daemon=True).start()

    def _do_analyze_spotify(self, path, pure_name):
        try:
            # 1. Autenticación con Spotify (URLs Reales escritas directamente)
            auth_str = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
            b64_auth_str = base64.b64encode(auth_str.encode()).decode()
            
            auth_headers = {
                "Authorization": f"Basic {b64_auth_str}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            auth_data = {"grant_type": "client_credentials"}
            
            # URL real de cuentas
            auth_response = requests.post("https://accounts.spotify.com/api/token", headers=auth_headers, data=auth_data)
            
            if auth_response.status_code != 200:
                raise Exception("Error de Autenticación. Revisa que tus claves de Spotify sean correctas.")
            
            token = auth_response.json()["access_token"]
            search_headers = {"Authorization": f"Bearer {token}"}

            # 2. Búsqueda Inteligente (Sanitizamos el nombre)
            clean_query = pure_name.replace('-', ' ').replace('_', ' ').replace(',', ' ').replace('‑', ' ')
            clean_query = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean_query) # CamelCase a espacios
            clean_query = re.sub(r'(?i)\b\d{2,3}\s*BPM\b', '', clean_query)
            clean_query = re.sub(r'(?i)\b\d{1,2}[AB]\b', '', clean_query)
            clean_query = re.sub(r'(?i)\b[A-G][#b]?(MAJ|MIN)\b', '', clean_query)
            clean_query = " ".join(clean_query.split())

            queries_to_try = [clean_query, pure_name.replace('-', ' ')]
            valid_features = None
            
            for q in queries_to_try:
                if not q.strip(): continue
                self.after(0, lambda q_str=q: self.loading_label.configure(text=f"> BUSCANDO TRACK...\n[{q_str[:30]}]"))
                query_encoded = urllib.parse.quote(q)
                
                # URL real de búsqueda de API
                search_url = f"https://api.spotify.com/v1/search?q={query_encoded}&type=track&limit=5"
                
                search_res = requests.get(search_url, headers=search_headers)
                search_data = search_res.json()
                
                tracks = search_data.get("tracks", {}).get("items", [])
                
                for track in tracks:
                    track_id = track["id"]
                    
                    # 3. Obtener Audio Features (URL real)
                    features_url = f"https://api.spotify.com/v1/audio-features/{track_id}"
                    features_res = requests.get(features_url, headers=search_headers)
                    
                    if features_res.status_code == 200:
                        features_data = features_res.json()
                        if features_data and features_data.get("tempo"):
                            valid_features = features_data
                            break 
                            
                if valid_features:
                    break

            if not valid_features:
                raise Exception("Spotify no encontró la canción o sus versiones no tienen BPM/Tono.")

            # 4. Traducción de datos
            detected_bpm = str(int(round(valid_features["tempo"])))
            
            key_map = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            mode_map = ['min', 'maj']
            
            key_index = valid_features.get("key", -1)
            mode_index = valid_features.get("mode", 0)
            
            if key_index == -1:
                detected_key = "---"
            else:
                detected_key = f"{key_map[key_index]} {mode_map[mode_index]}"

            self.after(0, lambda: self.loading_label.configure(text=f"> FINALIZANDO...\n[{pure_name[:30]}]"))
            time.sleep(0.3)

            self.after(0, lambda: self._apply_analysis(path, detected_bpm, detected_key))

        except Exception as e:
            self.after(0, self.hide_loading)
            self.after(0, lambda err=e: self.log_message(f"> [API ERROR]: {str(err)}"))

    def _apply_analysis(self, path, detected_bpm, detected_key):
        self.hide_loading()
        if path in self.file_data:
            self.file_data[path]['bpm'] = detected_bpm
            self.file_data[path]['key'] = detected_key
            self.file_data[path]['estado'] = COLOR_MODIFIED
            self.log_message(f"> [SPOTIFY] Precisión 100% -> BPM: {detected_bpm} | KEY: {detected_key}")
            self.refresh_virtual_grid()
            if path in self.visible_paths:
                idx = self.visible_paths.index(path)
                self.stage_row_changes(idx)

    def show_loading(self, message="> PROCESANDO..."):
        self.loading_label.configure(text=message)
        self.loading_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.loading_frame.tkraise(); self.update() 

    def hide_loading(self):
        self.loading_frame.place_forget(); self.update()

    def draw_headers(self):
        for widget in self.frame_headers.winfo_children(): widget.destroy()
        for i, w in enumerate(self.COL_WIDTHS): self.frame_headers.grid_columnconfigure(i, minsize=w, weight=0)
        headers_texts = ["NOMBRE DE ARCHIVOS", "FORMATO", "TEMPO/BPM", "KEY/TONO", "ST", "ACCIONES"]
        for i, text in enumerate(headers_texts):
            hf = ctk.CTkFrame(self.frame_headers, fg_color="transparent")
            hf.grid(row=0, column=i, sticky="" if text in ["ST", "ACCIONES"] else "w", padx=5) 
            if text != "ACCIONES":
                arrow = " ↑" if self.current_sort_col == text and self.sort_asc else (" ↓" if self.current_sort_col == text else "")
                btn = ctk.CTkButton(hf, text=text + arrow, font=FONT_MONO_BOLD, text_color=TEXT_MUTED, fg_color="transparent", hover_color=BG_HOVER, border_width=0, width=0, height=20, anchor="center" if text == "ST" else "w", command=lambda t=text: self.sort_grid(t))
                btn.pack(anchor="center" if text == "ST" else "w", pady=(0, 2))
            else:
                ctk.CTkLabel(hf, text=text, font=FONT_MONO_BOLD, text_color=TEXT_MUTED).pack(anchor="center", pady=(0, 2))

    def sort_grid(self, col):
        self.show_loading(f"> ORDENANDO POR {col}...")
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
        self.top_index = 0; self.draw_headers(); self.refresh_virtual_grid(); self.hide_loading()

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
        self.metadata_cache[filepath] = {'bpm': bpm, 'key': key}
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
                audio.save()

            if ext == '.mp3': update_id3(MP3(filepath))
            elif ext == '.wav': update_id3(WAVE(filepath))
            elif ext in ('.aiff', '.aif'): update_id3(AIFF(filepath))
            elif ext == '.flac':
                audio = FLAC(filepath)
                if bpm: 
                    audio['bpm'] = bpm
                else: 
                    audio.pop('bpm', None)
                if key: 
                    audio['key'] = key
                else: 
                    audio.pop('key', None)
                audio.save()
            self.log_message(f"> Metadatos inyectados con éxito en ID3 de {os.path.basename(filepath)}")
        except Exception as e:
            self.log_message(f"> Advertencia ID3 en {os.path.basename(filepath)}: {e}")

    def update_apply_button_state(self):
        any_active = any(d['estado'] == COLOR_MODIFIED for d in self.file_data.values())
        if any_active: self.btn_run.configure(fg_color=BG_ELEMENT, text_color=ACCENT, state="normal", hover_color="#1E1E1E")
        else: self.btn_run.configure(fg_color=BG_ELEMENT, text_color=TEXT_MUTED, state="disabled")

    def log_message(self, message):
        self.textbox_log.configure(state="normal"); self.textbox_log.insert("end", message + "\n"); self.textbox_log.see("end"); self.textbox_log.configure(state="disabled")

    def clear_all(self):
        self.show_loading("> LIMPIANDO MEMORIA...")
        self.csv_path = ""; self.loaded_paths.clear(); self.file_data.clear(); self.session_history.clear(); self.metadata_cache.clear()
        self.current_sort_col = "NOMBRE DE ARCHIVOS"
        self.sort_asc = True; self.top_index = 0
        self.is_wav_all_applied = False
        self.label_loaded.configure(text="NINGÚN ARCHIVO CARGADO", text_color=TEXT_MUTED)
        self.draw_headers(); self.refresh_virtual_grid() 
        self.textbox_log.configure(state="normal"); self.textbox_log.delete("1.0", "end"); self.log_message("> Reset de sistema."); self.textbox_log.configure(state="disabled")
        self.update_apply_button_state(); self.update_wav_button_state(); self.hide_loading()

    def process_new_files(self, paths):
        for p in paths:
            if p not in self.loaded_paths:
                self.loaded_paths.append(p)
                bn, ext = os.path.splitext(os.path.basename(p))
                ep = ext.replace('.', '').upper()
                cu = p in self.session_history
                s_bpm, s_key = self.read_metadata(p)
                pure_n = self._extract_pure_name(bn, s_bpm, s_key)
                self.file_data[p] = {'name': bn, 'pure_name': pure_n, 'bpm': s_bpm, 'key': s_key, 'ext': ep, 'estado': COLOR_SAVED if cu else TEXT_MUTED, 'is_custom': cu, 'converted_to_wav': False}

    def select_folder(self):
        f = filedialog.askdirectory()
        self.focus_force() 
        if f:
            self.show_loading("> ESCANEANDO CARPETA Y LEYENDO METADATOS ID3...")
            paths = [os.path.join(f, x) for x in os.listdir(f) if x.lower().endswith(('.wav','.aiff','.mp3','.flac'))]
            self.process_new_files(paths)
            self.label_loaded.configure(text=f"ARCHIVOS CARGADOS: {len(self.loaded_paths)}", text_color=TEXT_NORMAL)
            self.log_message("-" * 30); self.log_message(f"Carpeta cargada: {f}")
            self.top_index = 0; self.draw_headers(); self.refresh_virtual_grid(); self.hide_loading()

    def select_files(self):
        f = filedialog.askopenfilenames(filetypes=[("Audio Files", "*.wav *.aiff *.mp3 *.flac")])
        self.focus_force() 
        if f:
            self.show_loading("> LEYENDO METADATOS ID3...")
            self.process_new_files(f)
            self.label_loaded.configure(text=f"ARCHIVOS CARGADOS: {len(self.loaded_paths)}", text_color=TEXT_NORMAL)
            self.log_message("-" * 30); self.log_message(f"Archivos añadidos: {len(f)} elementos.")
            self.top_index = 0; self.refresh_virtual_grid(); self.hide_loading()

    def select_csv(self):
        f = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        self.focus_force() 
        if f: 
            self.csv_path = f
            self.log_message("-" * 30); self.log_message(f"CSV vinculado: {os.path.basename(f)}")

    def convert_to_wav(self, current_path, auto_update=True):
        d, fn = os.path.dirname(current_path), os.path.basename(current_path)
        ext_orig = os.path.splitext(fn)[1].replace('.', '').upper()
        b = os.path.join(d, "_BACKUP_ORIGINALES")
        n = os.path.splitext(current_path)[0] + ".wav"
        if auto_update: self.show_loading(f"> CONVIRTIENDO A WAV: {fn}...")
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
        if auto_update: self.hide_loading()

    def convert_all_to_wav(self):
        to_convert = [p for p in self.loaded_paths if not p.lower().endswith('.wav')]
        if not to_convert: return
        self.show_loading(f"> INICIANDO COLA: 0/{len(to_convert)}...")
        self.process_next_conversion(to_convert, 0)

    def process_next_conversion(self, file_list, index):
        if index >= len(file_list):
            self.is_wav_all_applied = True
            self.update_wav_button_state(); self.refresh_virtual_grid(); self.hide_loading()
            return
        p = file_list[index]
        self.loading_label.configure(text=f"> CONVIRTIENDO: {index+1}/{len(file_list)}...")
        self.update()
        self.convert_to_wav(p, auto_update=False)
        self.after(50, lambda: self.process_next_conversion(file_list, index + 1))

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
        self.show_loading(f"> RESTAURANDO {len(to_restore)} FORMATOS...")
        self.process_next_restore(to_restore, 0)

    def process_next_restore(self, file_list, index):
        if index >= len(file_list):
            self.is_wav_all_applied = False
            self.update_wav_button_state(); self.refresh_virtual_grid(); self.hide_loading()
            return
        p = file_list[index]
        self.loading_label.configure(text=f"> RESTAURANDO: {index+1}/{len(file_list)}...")
        self.update()
        self.undo_single_file(p, auto_update=False)
        self.after(50, lambda: self.process_next_restore(file_list, index + 1))

    def undo_single_file(self, current_path, auto_update=True):
        if current_path not in self.session_history: return
        if auto_update: self.show_loading("> RESTAURANDO ORIGINAL...")
        op = self.session_history[current_path]
        try:
            if "_BACKUP_ORIGINALES" in op:
                rp = os.path.join(os.path.dirname(os.path.dirname(op)), os.path.basename(op))
                shutil.move(op, rp); os.remove(current_path) if os.path.exists(current_path) else None
                bd = os.path.dirname(op)
                if os.path.exists(bd) and not os.listdir(bd): os.rmdir(bd)
                self.loaded_paths[self.loaded_paths.index(current_path)] = rp
                if current_path in self.metadata_cache: self.metadata_cache[rp] = self.metadata_cache.pop(current_path)
                new_path = rp
            else:
                shutil.move(current_path, op)
                self.loaded_paths[self.loaded_paths.index(current_path)] = op
                if current_path in self.metadata_cache: self.metadata_cache[op] = self.metadata_cache.pop(current_path)
                new_path = op
            del self.session_history[current_path]
            if current_path in self.file_data:
                data = self.file_data.pop(current_path)
                final_name = os.path.splitext(os.path.basename(new_path))[0]
                old_bpm, old_key = self.read_metadata(new_path)
                pure_n = self._extract_pure_name(final_name, old_bpm, old_key)
                data['name'] = final_name; data['pure_name'] = pure_n; data['bpm'] = old_bpm; data['key'] = old_key; data['is_custom'] = False; data['estado'] = TEXT_MUTED; data['ext'] = os.path.splitext(new_path)[1].replace('.', '').upper(); data['converted_to_wav'] = False 
                self.file_data[new_path] = data
        except Exception as e: self.log_message(f"> Error Undo: {e}")
        if auto_update: self.refresh_virtual_grid(); self.update_wav_button_state(); self.hide_loading()

    def run_rename_all(self):
        paths_to_process = [p for p, d in self.file_data.items() if d['estado'] == COLOR_MODIFIED]
        if not paths_to_process: return
        if not messagebox.askyesno("Confirmar", f"Se aplicarán a {len(paths_to_process)} archivos. ¿Continuar?"): return

        self.show_loading("> PROCESANDO Y GUARDANDO METADATOS...")
        rc = 0; fmt = self.format_var.get()
        for p in paths_to_process:
            data = self.file_data[p]
            cn, bp, ky, ex = data['name'].strip(), data['bpm'].strip(), data['key'].strip(), f".{data['ext'].lower()}"
            if cn: 
                old_bpm, old_key = self.read_metadata(p)
                pure_n = data['pure_name']
                final_name = self._build_formatted_name(pure_n, bp, ky, fmt)
                nf = f"{final_name}{ex}"
                np = os.path.join(os.path.dirname(p), nf)
                try:
                    data = self.file_data.pop(p)
                    if p != np:
                        shutil.move(p, np)
                        h = self.session_history.pop(p) if p in self.session_history else p
                        self.session_history[np] = h
                        self.loaded_paths[self.loaded_paths.index(p)] = np
                        if p in self.metadata_cache: self.metadata_cache[np] = self.metadata_cache.pop(p)
                        data['name'] = final_name; self.file_data[np] = data; target_p = np
                    else:
                        data['name'] = final_name; self.file_data[p] = data; target_p = p
                    self.write_metadata(target_p, bp, ky)
                    self.file_data[target_p]['estado'] = COLOR_SAVED; self.file_data[target_p]['is_custom'] = True
                    self.log_message(f"> Renombrado exitosamente: {data['name']}")
                    rc += 1
                except Exception as e: self.log_message(f"> Error procesando {os.path.basename(p)}: {e}")
        if rc > 0: self.log_message(f"> {rc} archivos procesados.")
        self.refresh_virtual_grid(); self.hide_loading()

if __name__ == "__main__":
    app = YezkaApp()
    app.mainloop()