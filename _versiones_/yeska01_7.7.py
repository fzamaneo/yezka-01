# -*- coding: utf-8 -*-
import os
import csv
import shutil
import subprocess
import webbrowser
import urllib.parse
import re
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox

# --- CONFIGURACIÓN GLOBAL (MINIMALISMO YEZKA-01) ---
ctk.set_appearance_mode("dark")

FONT_MONO = ("Menlo", 12)  
FONT_MONO_BOLD = ("Menlo", 12, "bold")
FONT_TITLE = ("Menlo", 17, "bold")
FONT_NAME = ("Menlo", 12, "normal") 

BG_MAIN = "#000000"      
BG_HOVER = "#1E1E1E"     
BG_ELEMENT = "#141414"   
ACCENT = "#DCE038"       

# NUEVOS COLORES DE ESTADO (ST)
COLOR_MODIFIED = "#E93B35" # Rojo: Modificado, pendiente de aplicar
COLOR_SAVED = "#35E93B"    # Verde: Cambios guardados con éxito

TEXT_NORMAL = "#DFDFDF"  
TEXT_PURE = "#FFFFFF"    
TEXT_PALE = "#C0C0C0"    
TEXT_MUTED = "#555555"   
PLACEHOLDER_COLOR = "#333333" 

RADIUS = 4 

# --- MOTOR DE TEXTO AVANZADO ---
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
        if not self.undo_stack:
            self.undo_stack.append("")
        if current_text != self.undo_stack[-1]:
            self.undo_stack.append(current_text)
            self.redo_stack.clear()

    def undo(self, event):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self.delete(0, 'end')
            self.insert(0, self.undo_stack[-1])
        return "break"

    def redo(self, event):
        if self.redo_stack:
            text = self.redo_stack.pop()
            self.undo_stack.append(text)
            self.delete(0, 'end')
            self.insert(0, text)
        return "break"

# --- MOTOR DE TOOLTIPS ---
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave) 

    def enter(self, event=None):
        self.unschedule()
        self.id = self.widget.after(400, self.showtip) 

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def showtip(self):
        if self.tooltip_window: return
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try: tw.tk.call("::tk::unsupported::MacWindowStyle", "style", tw._w, "help", "none")
        except: pass
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left', background=BG_ELEMENT, foreground=TEXT_NORMAL, relief='flat', borderwidth=0, font=FONT_MONO)
        label.pack(ipadx=6, ipady=3)

    def hidetip(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

# --- APLICACIÓN PRINCIPAL ---
class YezkaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YEZKA-01 - v7.7 Pro") 
        self.geometry("1134x780") 
        self.resizable(False, False)
        self.configure(fg_color=BG_MAIN)

        self.csv_path = ""
        self.file_rows = {} 
        self.session_history = {} 
        self.loaded_paths = [] 
        
        self.metadata_cache = {} 
        self.current_sort_col = "NOMBRE DE ARCHIVOS"
        self.sort_asc = True

        # Paginación
        self.items_displayed = 0
        self.page_size = 50
        self.COL_WIDTHS = [625, 85, 90, 90, 50, 145]

        self.label_title = ctk.CTkLabel(self, text="YEZKA-01  //  v7.7 Pro", font=FONT_TITLE, text_color=TEXT_NORMAL)
        self.label_title.pack(pady=(15, 5), anchor="w", padx=20)

        # --- BARRA DE HERRAMIENTAS ---
        self.frame_toolbar = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0) 
        self.frame_toolbar.pack(pady=(5, 10), padx=20, fill="x")
        
        self.btn_folder = ctk.CTkButton(self.frame_toolbar, text="SELECCIONAR CARPETA", command=self.select_folder, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=0, width=165, height=36)
        self.btn_folder.pack(side="left", padx=(0, 10), pady=10)
        ToolTip(self.btn_folder, "Carga todos los audios dentro de una carpeta")

        self.btn_files = ctk.CTkButton(self.frame_toolbar, text="SELECCIONAR ARCHIVO", command=self.select_files, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=0, width=165, height=36)
        self.btn_files.pack(side="left", padx=(5, 20), pady=10)
        ToolTip(self.btn_files, "Añade archivos individuales de audio")

        self.label_loaded = ctk.CTkLabel(self.frame_toolbar, text="NINGÚN ARCHIVO CARGADO", font=FONT_MONO, text_color=TEXT_MUTED)
        self.label_loaded.pack(side="left")

        self.btn_clear = ctk.CTkButton(self.frame_toolbar, text="↺", width=36, height=32, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=("Arial", 17, "bold"), command=self.clear_all, border_width=0)
        self.btn_clear.pack(side="right", padx=(10, 0))
        ToolTip(self.btn_clear, "Vacía la lista de archivos y el registro")
        
        self.btn_csv = ctk.CTkButton(self.frame_toolbar, text="CSV", width=60, height=32, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=FONT_MONO, command=self.select_csv, border_width=0)
        self.btn_csv.pack(side="right", padx=(10, 0))
        ToolTip(self.btn_csv, "Aplica etiquetas desde un archivo CSV")

        # --- SELECTOR DE FORMATO ---
        self.format_var = ctk.StringVar(value="►BPM ►KEY - TITULO")
        self.menu_format = ctk.CTkOptionMenu(
            self.frame_toolbar, 
            values=[
                "►KEY ►BPM - TITULO", 
                "►BPM ►KEY - TITULO", 
                "►BPM - TITULO", 
                "►KEY - TITULO",
                "TITULO - ◄BPM ◄KEY", 
                "TITULO - ◄KEY ◄BPM",
                "TITULO - ◄BPM",
                "TITULO - ◄KEY"
            ],
            variable=self.format_var,
            width=230, height=32,
            fg_color=BG_ELEMENT, button_color=BG_ELEMENT, button_hover_color=BG_HOVER, dropdown_fg_color=BG_ELEMENT,
            font=FONT_MONO, text_color=TEXT_NORMAL
        )
        self.menu_format.pack(side="right", padx=(10, 0))
        ToolTip(self.menu_format, "Elige el estilo de renombrado para los archivos")

        # --- BOTÓN CONVERSIÓN MASIVA WAV ---
        self.btn_mass_wav = ctk.CTkButton(self.frame_toolbar, text="[ WAV ALL ]", width=90, height=32, fg_color=BG_ELEMENT, hover_color="#1E1E1E", text_color=ACCENT, corner_radius=RADIUS, font=FONT_MONO_BOLD, command=self.convert_all_to_wav, border_width=0)
        self.btn_mass_wav.pack(side="right", padx=(10, 0))
        ToolTip(self.btn_mass_wav, "Convierte todos los MP3/FLAC/AIFF a WAV")

        # --- TABLA CONTENEDOR ---
        self.table_container = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0)
        self.table_container.pack(padx=20, fill="both", expand=True, pady=(5, 5))

        self.frame_headers = ctk.CTkFrame(self.table_container, fg_color="transparent", corner_radius=0)
        self.frame_headers.pack(fill="x", pady=(0, 2), padx=(0, 16)) 
        
        self.scroll_frame = ctk.CTkScrollableFrame(self.table_container, height=400, fg_color="transparent", corner_radius=0, scrollbar_button_color=BG_MAIN, scrollbar_button_hover_color=BG_MAIN)
        self.scroll_frame.pack(fill="both", expand=True, pady=(0, 0)) 
        
        # --- FOOTER (BOTÓN APLICAR) ---
        self.frame_footer = ctk.CTkFrame(self.table_container, fg_color="transparent")
        self.frame_footer.pack(fill="x", pady=(5, 5), padx=(0, 16))
        
        self.btn_run = ctk.CTkButton(self.frame_footer, text="APLICAR CAMBIOS", height=32, command=self.run_rename, fg_color=BG_ELEMENT, text_color=TEXT_MUTED, state="disabled", corner_radius=RADIUS, font=FONT_MONO_BOLD, border_width=0)
        self.btn_run.pack(side="right")
        ToolTip(self.btn_run, "Aplica el renombrado a los archivos modificados en la tabla")

        # --- REGISTRO ---
        self.label_log = ctk.CTkLabel(self, text="REGISTRO", font=FONT_MONO_BOLD, text_color=TEXT_MUTED)
        self.label_log.pack(padx=20, anchor="w", pady=(5,0))
        self.textbox_log = ctk.CTkTextbox(self, height=95, state="disabled", fg_color="transparent", text_color="#e93b35", border_width=0, corner_radius=0, font=FONT_MONO)
        self.textbox_log.pack(pady=(0, 15), padx=20, fill="x")

        # --- PANTALLA DE CARGA (OVERLAY) ---
        self.loading_frame = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0)
        self.loading_label = ctk.CTkLabel(self.loading_frame, text="> PROCESANDO...", font=("Menlo", 20, "bold"), text_color=ACCENT)
        self.loading_label.place(relx=0.5, rely=0.5, anchor="center")

        self.draw_headers()
        self.populate_grid()
        self.focus_force() 

    # --- CONTROL DE PANTALLA DE CARGA ---
    def show_loading(self, message="> PROCESANDO..."):
        self.loading_label.configure(text=message)
        self.loading_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.loading_frame.tkraise()
        self.update() 

    def hide_loading(self):
        self.loading_frame.place_forget()
        self.update()

    # --- DIBUJADO DINÁMICO DE CABECERAS ---
    def draw_headers(self):
        for widget in self.frame_headers.winfo_children():
            widget.destroy()
            
        for i, w in enumerate(self.COL_WIDTHS):
            self.frame_headers.grid_columnconfigure(i, minsize=w, weight=0)

        headers_texts = ["NOMBRE DE ARCHIVOS", "FORMATO", "TEMPO/BPM", "KEY/TONO", "ST", "ACCIONES"]
        for i, text in enumerate(headers_texts):
            hf = ctk.CTkFrame(self.frame_headers, fg_color="transparent")
            hf.grid(row=0, column=i, sticky="" if text in ["ST", "ACCIONES"] else "w", padx=5) 
            
            if text != "ACCIONES":
                arrow = ""
                if self.current_sort_col == text:
                    arrow = " ↑" if self.sort_asc else " ↓"
                
                btn = ctk.CTkButton(hf, text=text + arrow, font=FONT_MONO_BOLD, text_color=TEXT_MUTED,
                                    fg_color="transparent", hover_color=BG_HOVER, border_width=0,
                                    width=0, height=20, anchor="center" if text == "ST" else "w",
                                    command=lambda t=text: self.sort_grid(t))
                btn.pack(anchor="center" if text == "ST" else "w", pady=(0, 2))
                ToolTip(btn, f"Ordenar por {text}")
            else:
                ctk.CTkLabel(hf, text=text, font=FONT_MONO_BOLD, text_color=TEXT_MUTED).pack(anchor="center", pady=(0, 2))

    # --- MOTOR DE ORDENAMIENTO ---
    def sort_grid(self, col):
        self.show_loading(f"> ORDENANDO POR {col}...")
        if self.current_sort_col == col:
            self.sort_asc = not self.sort_asc
        else:
            self.current_sort_col = col
            self.sort_asc = False if col in ["TEMPO/BPM", "ST"] else True
            
        self.apply_sort()
        self.hide_loading()

    def apply_sort(self):
        def get_sort_key(p):
            if self.current_sort_col == "NOMBRE DE ARCHIVOS":
                return os.path.basename(p).lower()
            elif self.current_sort_col == "FORMATO":
                return os.path.splitext(p)[1].lower()
            elif self.current_sort_col == "TEMPO/BPM":
                bpm, _ = self.read_metadata(p)
                try: return float(bpm)
                except: return 0.0 if not self.sort_asc else 999.0
            elif self.current_sort_col == "KEY/TONO":
                _, key = self.read_metadata(p)
                match = re.match(r'^(\d{1,2})([A-Za-z]+)$', key.strip())
                if match: return (int(match.group(1)), match.group(2).upper())
                return (99, key.upper())
            elif self.current_sort_col == "ST":
                return p in self.session_history
            return ""

        self.loaded_paths.sort(key=get_sort_key, reverse=not self.sort_asc)
        self.items_displayed = 0
        self.draw_headers()
        self.populate_grid()

    # --- LECTURA DE METADATOS ---
    def read_metadata(self, filepath):
        if filepath in self.metadata_cache:
            return self.metadata_cache[filepath]['bpm'], self.metadata_cache[filepath]['key']
            
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
        except Exception:
            pass 
            
        self.metadata_cache[filepath] = {'bpm': bpm, 'key': key}
        return bpm, key

    # --- INYECCIÓN Y BORRADO DE METADATOS ---
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
                if bpm: audio['bpm'] = bpm
                else: audio.pop('bpm', None)
                if key: audio['key'] = key
                else: audio.pop('key', None)
                audio.save()
                
            self.log_message(f"> Metadatos guardados -> BPM: [{bpm or 'Vacío'}] | KEY: [{key or 'Vacío'}]")
        except Exception as e:
            self.log_message(f"> Advertencia ID3 en {os.path.basename(filepath)}: {e}")

    def update_apply_button_state(self):
        # Ahora se activa si hay al menos una fila con el color ROJO (COLOR_MODIFIED)
        any_active = any(et['estado'].cget("text_color") == COLOR_MODIFIED for et in self.file_rows.values())
        if any_active:
            self.btn_run.configure(fg_color=BG_ELEMENT, text_color=ACCENT, state="normal", hover_color="#1E1E1E")
        else:
            self.btn_run.configure(fg_color=BG_ELEMENT, text_color=TEXT_MUTED, state="disabled")

    def log_message(self, message):
        self.textbox_log.configure(state="normal"); self.textbox_log.insert("end", message + "\n"); self.textbox_log.see("end"); self.textbox_log.configure(state="disabled")

    def clear_all(self):
        self.show_loading("> LIMPIANDO MEMORIA...")
        self.csv_path = ""; self.file_rows.clear(); self.session_history.clear(); self.loaded_paths.clear()
        self.metadata_cache.clear()
        self.current_sort_col = "NOMBRE DE ARCHIVOS"
        self.sort_asc = True
        self.items_displayed = 0
        self.label_loaded.configure(text="NINGÚN ARCHIVO CARGADO", text_color=TEXT_MUTED)
        self.draw_headers()
        self.populate_grid() 
        self.textbox_log.configure(state="normal"); self.textbox_log.delete("1.0", "end"); self.log_message("> Reset de sistema."); self.textbox_log.configure(state="disabled")
        self.update_apply_button_state()
        self.hide_loading()

    def select_folder(self):
        f = filedialog.askdirectory()
        self.focus_force() 
        if f:
            self.show_loading("> ESCANEANDO CARPETA Y LEYENDO METADATOS ID3...")
            self.loaded_paths = [os.path.join(f, x) for x in os.listdir(f) if x.lower().endswith(('.wav','.aiff','.mp3','.flac'))]
            for p in self.loaded_paths: self.read_metadata(p)
            self.label_loaded.configure(text=f"ARCHIVOS CARGADOS: {len(self.loaded_paths)}", text_color=TEXT_NORMAL)
            self.log_message("-" * 30); self.log_message(f"Carpeta cargada: {f}")
            self.items_displayed = 0
            self.apply_sort()
            self.hide_loading()

    def select_files(self):
        f = filedialog.askopenfilenames(filetypes=[("Audio Files", "*.wav *.aiff *.mp3 *.flac")])
        self.focus_force() 
        if f:
            self.show_loading("> LEYENDO METADATOS ID3...")
            for x in f: 
                if x not in self.loaded_paths: 
                    self.loaded_paths.append(x)
                    self.read_metadata(x)
            self.label_loaded.configure(text=f"ARCHIVOS CARGADOS: {len(self.loaded_paths)}", text_color=TEXT_NORMAL)
            self.log_message("-" * 30); self.log_message(f"Archivos añadidos: {len(f)} elementos.")
            self.items_displayed = 0
            self.apply_sort()
            self.hide_loading()

    def select_csv(self):
        f = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        self.focus_force() 
        if f: 
            self.csv_path = f
            self.log_message("-" * 30); self.log_message(f"CSV vinculado: {os.path.basename(f)}")

    # --- EVENTOS DESACOPLADOS DE UI ---
    def mark_as_edited(self, widget, is_name):
        for et in self.file_rows.values():
            if widget in (et['name'], et['bpm'], et['key']):
                # Se pinta de ROJO (pendiente de guardar)
                et['estado'].configure(text_color=COLOR_MODIFIED)
                self.update_apply_button_state()
                if is_name: widget.configure(text_color=TEXT_NORMAL)
                else: widget.configure(text_color=TEXT_PURE)
                break

    def force_apply_and_run(self, widget):
        self.mark_as_edited(widget, False)
        self.run_rename()

    def open_web_search(self, current_path):
        track_name = ""
        for et in self.file_rows.values():
            if et['current_path'] == current_path:
                track_name = et['name'].get().strip()
                break
        if not track_name: return
        query = urllib.parse.quote_plus(f"{track_name} bpm key")
        webbrowser.open(f"https://www.google.com/search?q={query}")

    # --- LÓGICA DE CONVERSIÓN ---
    def convert_to_wav(self, current_path, auto_update=True):
        d, fn = os.path.dirname(current_path), os.path.basename(current_path)
        ext_orig = os.path.splitext(fn)[1].replace('.', '').upper()
        b = os.path.join(d, "_BACKUP_ORIGINALES")
        n = os.path.splitext(current_path)[0] + ".wav"
        
        if auto_update: self.show_loading(f"> CONVIRTIENDO A WAV: {fn}...")
        self.log_message(f"--- INICIANDO CONVERSIÓN: {ext_orig} -> WAV ---")
        
        try:
            if not os.path.exists(b): os.makedirs(b)
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@44100", current_path, n], check=True)
            bk = os.path.join(b, fn); shutil.move(current_path, bk)
            
            self.session_history[n] = bk
            self.loaded_paths[self.loaded_paths.index(current_path)] = n
            if current_path in self.metadata_cache: self.metadata_cache[n] = self.metadata_cache.pop(current_path)
            
            # Reasignamos path en el diccionario
            if current_path in self.file_rows:
                et = self.file_rows.pop(current_path)
                et['current_path'] = n
                self.file_rows[n] = et
            
            if auto_update: 
                self.items_displayed = 0
                self.apply_sort()
        except Exception as e: 
            self.log_message(f"> Error en {fn}: {e}")
            
        if auto_update: self.hide_loading()

    def convert_all_to_wav(self):
        to_convert = [p for p in self.loaded_paths if not p.lower().endswith('.wav')]
        if not to_convert:
            self.log_message("> Ningún archivo pendiente de conversión a WAV.")
            return
            
        self.show_loading(f"> INICIANDO COLA: 0/{len(to_convert)}...")
        self.process_next_conversion(to_convert, 0)

    def process_next_conversion(self, file_list, index):
        if index >= len(file_list):
            self.log_message(f"> {len(file_list)} ARCHIVOS CONVERTIDOS A WAV EXITOSAMENTE.")
            self.items_displayed = 0
            self.apply_sort()
            self.hide_loading()
            return
            
        p = file_list[index]
        self.loading_label.configure(text=f"> CONVIRTIENDO: {index+1}/{len(file_list)}...")
        self.update()
        self.convert_to_wav(p, auto_update=False)
        
        self.after(50, lambda: self.process_next_conversion(file_list, index + 1))

    # --- DESHACER ---
    def undo_single_file(self, current_path):
        if current_path not in self.session_history: return
        self.show_loading("> RESTAURANDO ORIGINAL...")
        op = self.session_history[current_path]
        try:
            self.log_message("-" * 30)
            self.log_message(f"Restaurado: {os.path.basename(op)}")
            
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
            
            # Reasignamos path visualmente in-place (sin saltos)
            if current_path in self.file_rows:
                et = self.file_rows.pop(current_path)
                et['current_path'] = new_path
                self.file_rows[new_path] = et
                
                final_name = os.path.splitext(os.path.basename(new_path))[0]
                et['name'].delete(0, 'end')
                et['name'].insert(0, final_name)
                et['name'].configure(text_color=TEXT_PALE)
                
                old_bpm, old_key = self.read_metadata(new_path)
                et['bpm'].delete(0, 'end')
                if old_bpm: et['bpm'].insert(0, old_bpm)
                et['bpm'].configure(text_color=PLACEHOLDER_COLOR)
                
                et['key'].delete(0, 'end')
                if old_key: et['key'].insert(0, old_key)
                et['key'].configure(text_color=PLACEHOLDER_COLOR)
                
                et['estado'].configure(text_color=TEXT_MUTED)
                et['btn_undo'].configure(state="disabled", text="-", text_color=TEXT_MUTED)

        except Exception as e: 
            self.log_message(f"> Error Undo: {e}")
        self.update_apply_button_state()
        self.hide_loading()

    # --- MOTOR PRINCIPAL DE RENOMBRADO ---
    def run_rename(self, event=None):
        self.show_loading("> PROCESANDO Y GUARDANDO METADATOS...")
        rc = 0
        fmt = self.format_var.get()
        
        for p, et in list(self.file_rows.items()):
            # Solo procesa las filas que estén en estado ROJO (pendientes de guardar)
            if et['estado'].cget("text_color") != COLOR_MODIFIED: continue
            
            cn, bp, ky, ex = et['name'].get().strip(), et['bpm'].get().strip(), et['key'].get().strip(), et['ext']
            if cn: 
                old_bpm, old_key = self.read_metadata(p)
                base_name = cn
                
                # 1. PODA ACTIVA
                def strip_metadata(name, tb, tk):
                    if not name: return ""
                    k_n = tk.replace(" ", "").upper().replace("MAJOR", "MAJ").replace("MINOR", "MIN") if tk else ""
                    b_n = tb.strip().upper() if tb else ""
                    parts = [x.strip() for x in name.split('-')]
                    while parts:
                        fst = parts[0].upper()
                        if (k_n and fst == k_n) or (b_n and fst == b_n) or fst == f"{b_n} BPM" or fst == f"{b_n}BPM":
                            parts.pop(0)
                        else: break
                    while parts:
                        lst = parts[-1].upper()
                        if (k_n and lst == k_n) or (b_n and lst == b_n) or lst == f"{b_n} BPM" or lst == f"{b_n}BPM":
                            parts.pop()
                        else: break
                    return "-".join(parts) if parts else name

                base_name = strip_metadata(base_name, old_bpm, old_key)
                base_name = strip_metadata(base_name, bp, ky)

                # Fallback de limpieza Regex
                while True:
                    m_k = re.match(r'^(\d{1,2}[A-Za-z]{1,3})\s*[-_ ]\s*(.*)', base_name)
                    if m_k: base_name = m_k.group(2); continue
                    m_b = re.match(r'^(\d{2,3}(?:\.\d+)?)\s*(?:BPM)?\s*[-_ ]\s*(.*)', base_name, re.IGNORECASE)
                    if m_b: base_name = m_b.group(2); continue
                    break
                while True:
                    m_ke = re.search(r'(.*?)\s*[-_ ]\s*(\d{1,2}[A-Za-z]{1,3})$', base_name)
                    if m_ke: base_name = m_ke.group(1); continue
                    m_be = re.search(r'(.*?)\s*[-_ ]\s*(\d{2,3}(?:\.\d+)?)\s*(?:BPM)?$', base_name, re.IGNORECASE)
                    if m_be: base_name = m_be.group(1); continue
                    break

                kn = ky.replace(" ", "").upper().replace("MAJOR", "MAJ").replace("MINOR", "MIN")
                pt = []; b_name = base_name if base_name else cn
                
                # 2. ENSAMBLE SEGÚN FORMATO
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

                nf = f"{'-'.join([x for x in pt if x])}{ex}"
                np = os.path.join(os.path.dirname(p), nf)
                
                try:
                    if p != np:
                        shutil.move(p, np)
                        h = self.session_history.pop(p) if p in self.session_history else p
                        self.session_history[np] = h
                        self.loaded_paths[self.loaded_paths.index(p)] = np
                        if p in self.metadata_cache:
                            self.metadata_cache[np] = self.metadata_cache.pop(p)
                        
                        # Actualiza el diccionario in-place
                        et = self.file_rows.pop(p)
                        et['current_path'] = np
                        self.file_rows[np] = et
                        
                    self.write_metadata(np, bp, kn)
                    
                    # 3. REFRESCADO VISUAL "IN-PLACE"
                    # El punto pasa a VERDE (Guardado exitoso)
                    et['estado'].configure(text_color=COLOR_SAVED)
                    
                    final_name = os.path.splitext(os.path.basename(np))[0]
                    et['name'].delete(0, 'end')
                    et['name'].insert(0, final_name)
                    et['name'].configure(text_color=TEXT_NORMAL)
                    
                    # 4. FIX: ENCENDIDO DEL BOTÓN DE REVERTIR
                    if np in self.session_history:
                        et['btn_undo'].configure(state="normal", text="↩", text_color=ACCENT)
                    
                    rc += 1
                except Exception as e:
                    self.log_message(f"> Error procesando {os.path.basename(p)}: {e}")
                
        if rc > 0: 
            self.log_message(f"> {rc} archivos procesados y actualizados con éxito.")
        self.update_apply_button_state()
        self.hide_loading()

    # --- CONSTRUCCIÓN DE LA TABLA CON PAGINACIÓN ---
    def populate_grid(self, append=False):
        if not append:
            for widget in self.scroll_frame.winfo_children(): widget.destroy()
            self.file_rows.clear()
            self.items_displayed = 0
            if len(self.loaded_paths) > 11:
                self.scroll_frame.configure(scrollbar_button_color=TEXT_MUTED, scrollbar_button_hover_color=TEXT_PALE)
            else:
                self.scroll_frame.configure(scrollbar_button_color=BG_MAIN, scrollbar_button_hover_color=BG_MAIN)
        else:
            for widget in self.scroll_frame.winfo_children():
                if isinstance(widget, ctk.CTkButton) and "MOSTRAR MÁS" in widget.cget("text"):
                    widget.destroy()

        if not self.loaded_paths: 
            self.update_apply_button_state()
            
            empty_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            empty_frame.pack(pady=80)
            
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
            
            ctk.CTkLabel(empty_frame, text=empty_ascii, font=("Menlo", 10), text_color=TEXT_MUTED, justify="left").pack()
            ctk.CTkLabel(empty_frame, text="\n> SELECCIONA CARPETA O ARCHIVO EN LA BARRA SUPERIOR.", font=("Menlo", 10), text_color=TEXT_MUTED, justify="center").pack(pady=(10, 0))
            return

        start = self.items_displayed
        end = min(start + self.page_size, len(self.loaded_paths))

        for i in range(start, end):
            path = self.loaded_paths[i]
            bn, ext = os.path.splitext(os.path.basename(path))
            ep = ext.replace('.', '').upper()
            
            cu = path in self.session_history
            s_bpm, s_key = self.read_metadata(path)
            
            name_color = TEXT_NORMAL if cu else TEXT_PALE
            row_idx = i + 1
            
            e_name = ctk.CTkEntry(self.scroll_frame, width=610, height=28, fg_color=BG_ELEMENT, border_width=0, font=FONT_NAME, text_color=name_color, corner_radius=RADIUS)
            e_name.insert(0, bn)
            e_name.grid(row=row_idx, column=0, padx=5, pady=4, sticky="w")
            
            is_wav = ext.lower() == '.wav'
            tag_color = TEXT_MUTED if is_wav else ACCENT
            tag_frame = ctk.CTkFrame(self.scroll_frame, width=75, height=25, fg_color=BG_ELEMENT, border_width=0, corner_radius=RADIUS)
            tag_frame.grid(row=row_idx, column=1, padx=5, pady=4, sticky="w")
            tag_frame.pack_propagate(False)
            ctk.CTkLabel(tag_frame, text=ep, text_color=tag_color, font=FONT_MONO).place(relx=0.5, rely=0.5, anchor="center")
            
            e_bpm = ctk.CTkEntry(self.scroll_frame, width=80, fg_color=BG_ELEMENT, border_width=0, corner_radius=RADIUS, font=FONT_MONO, text_color=TEXT_PURE if cu else PLACEHOLDER_COLOR, placeholder_text="--- BPM", placeholder_text_color=PLACEHOLDER_COLOR)
            if s_bpm: e_bpm.insert(0, s_bpm)
            e_bpm.grid(row=row_idx, column=2, padx=5, pady=4, sticky="w")
            
            e_key = ctk.CTkEntry(self.scroll_frame, width=80, fg_color=BG_ELEMENT, border_width=0, corner_radius=RADIUS, font=FONT_MONO, text_color=TEXT_PURE if cu else PLACEHOLDER_COLOR, placeholder_text="--- KEY", placeholder_text_color=PLACEHOLDER_COLOR)
            if s_key: e_key.insert(0, s_key)
            e_key.grid(row=row_idx, column=3, padx=5, pady=4, sticky="w")
            
            # El estado (Punto) inicia gris por defecto o verde si ya fue guardado en esta sesión.
            st_color = COLOR_SAVED if cu else TEXT_MUTED
            l_st = ctk.CTkLabel(self.scroll_frame, text="●", width=40, text_color=st_color, font=("monospace", 14))
            l_st.grid(row=row_idx, column=4, padx=5, pady=4)
            
            af = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            af.grid(row=row_idx, column=5, padx=5, pady=4, sticky="w")
            
            # Conexión dinámica del botón de revertir
            et = {'name': e_name, 'bpm': e_bpm, 'key': e_key, 'ext': ext, 'estado': l_st, 'current_path': path}
            
            tx_u = ACCENT if cu else TEXT_MUTED
            bt_u = ctk.CTkButton(af, text="↩" if cu else "-", width=36, height=28, fg_color=BG_ELEMENT, border_width=0, state="normal" if cu else "disabled", hover_color="#1E1E1E", text_color=tx_u, corner_radius=RADIUS, font=("monospace", 14), command=lambda r=et: self.undo_single_file(r['current_path']))
            bt_u.pack(side="left", padx=(0, 2))
            
            ToolTip(bt_u, "Restaurar original")
            
            et['btn_undo'] = bt_u # Añadido al diccionario interno
            
            bt_web = ctk.CTkButton(af, text="⌕", width=36, height=28, fg_color=BG_ELEMENT, border_width=0, hover_color="#1E1E1E", text_color=TEXT_NORMAL, corner_radius=RADIUS, font=("Menlo", 21, "bold"), command=lambda r=et: self.open_web_search(r['current_path']))
            bt_web.pack(side="left", padx=(0, 2))
            ToolTip(bt_web, "Buscar BPM/Key en navegador")
            
            tx_w = ACCENT if not is_wav else TEXT_MUTED
            bt_w = ctk.CTkButton(af, text="WAV", width=42, height=28, fg_color=BG_ELEMENT, border_width=0, state="disabled" if is_wav else "normal", hover_color="#1E1E1E", text_color=tx_w, corner_radius=RADIUS, font=FONT_MONO, command=lambda r=et: self.convert_to_wav(r['current_path']))
            bt_w.pack(side="left")
            ToolTip(bt_w, "Convertir a WAV")
            
            # --- BINDS ---
            e_name.bind("<Enter>", lambda e, w=e_name: w.configure(fg_color=BG_HOVER))
            e_name.bind("<Leave>", lambda e, w=e_name: w.configure(fg_color=BG_ELEMENT))
            
            e_name.bind("<KeyRelease>", lambda e, w=e_name: self.mark_as_edited(w, True))
            e_bpm.bind("<KeyRelease>", lambda e, w=e_bpm: self.mark_as_edited(w, False))
            e_key.bind("<KeyRelease>", lambda e, w=e_key: self.mark_as_edited(w, False))

            e_name.bind("<Return>", lambda e, w=e_name: self.force_apply_and_run(w))
            e_bpm.bind("<Return>", lambda e, w=e_bpm: self.force_apply_and_run(w))
            e_key.bind("<Return>", lambda e, w=e_key: self.force_apply_and_run(w))

            self.file_rows[path] = et
        
        self.items_displayed = end

        if self.items_displayed < len(self.loaded_paths):
            restantes = len(self.loaded_paths) - self.items_displayed
            btn_more = ctk.CTkButton(self.scroll_frame, text=f"[ + MOSTRAR MÁS ARCHIVOS ({restantes} PENDIENTES) ]", fg_color=BG_MAIN, hover_color=BG_ELEMENT, text_color=ACCENT, font=FONT_MONO_BOLD, command=lambda: self.populate_grid(append=True))
            btn_more.grid(row=self.items_displayed + 1, column=0, columnspan=6, pady=20, sticky="ew")

        self.update_apply_button_state()

if __name__ == "__main__":
    app = YezkaApp()
    app.mainloop()
    app.mainloop()