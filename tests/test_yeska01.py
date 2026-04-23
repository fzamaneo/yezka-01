# -*- coding: utf-8 -*-
"""
Suite de pruebas para YEZKA-01
Cubre: expresiones regulares, SmartFolderHandler,
       _extract_pure_name, _build_formatted_name,
       _raw_to_samples y _prepare_files_data.
"""

import re
import sys
import os
import types
import struct
import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# 1. SIMULAR MÓDULOS DE INTERFAZ GRÁFICA Y EXTERNOS ANTES DE IMPORTAR YESKA01
# ---------------------------------------------------------------------------

def _make_mock_module(name, **attrs):
    mod = types.ModuleType(name)
    for attr_name, attr_value in attrs.items():
        setattr(mod, attr_name, attr_value)
    return mod

# tkinter
_tk_mock = MagicMock()
sys.modules.setdefault('tkinter', _tk_mock)
sys.modules.setdefault('tkinter.filedialog', MagicMock())
sys.modules.setdefault('tkinter.messagebox', MagicMock())

# customtkinter
_ctk_mock = MagicMock()
_ctk_mock.set_appearance_mode = MagicMock()
_ctk_mock.CTk = MagicMock
_ctk_mock.CTkEntry = MagicMock
_ctk_mock.CTkFrame = MagicMock
_ctk_mock.CTkLabel = MagicMock
_ctk_mock.CTkButton = MagicMock
_ctk_mock.CTkTabview = MagicMock
_ctk_mock.CTkScrollbar = MagicMock
_ctk_mock.CTkTextbox = MagicMock
_ctk_mock.CTkSlider = MagicMock
_ctk_mock.CTkOptionMenu = MagicMock
_ctk_mock.CTkSwitch = MagicMock
_ctk_mock.CTkToplevel = MagicMock
_ctk_mock.CTkImage = MagicMock
_ctk_mock.BooleanVar = MagicMock
_ctk_mock.StringVar = MagicMock
_ctk_mock.set_widget_scaling = MagicMock()
_ctk_mock.set_window_scaling = MagicMock()
sys.modules.setdefault('customtkinter', _ctk_mock)

# pygame
_pygame_mock = MagicMock()
_pygame_mock.mixer = MagicMock()
sys.modules.setdefault('pygame', _pygame_mock)

# watchdog
_wd_mock = _make_mock_module('watchdog')
_wd_obs = _make_mock_module('watchdog.observers')
_wd_obs.Observer = MagicMock
_wd_ev = _make_mock_module('watchdog.events')
_wd_ev.FileSystemEventHandler = object  # clase base real vacía
sys.modules.setdefault('watchdog', _wd_mock)
sys.modules.setdefault('watchdog.observers', _wd_obs)
sys.modules.setdefault('watchdog.events', _wd_ev)

# pytablericons
_tabler_mock = _make_mock_module('pytablericons')
_tabler_mock.TablerIcons = MagicMock()
_tabler_mock.OutlineIcon = MagicMock()
sys.modules.setdefault('pytablericons', _tabler_mock)

# PIL
_pil_mock = _make_mock_module('PIL')
_pil_imagetk = _make_mock_module('PIL.ImageTk')
_pil_imagetk.PhotoImage = MagicMock
sys.modules.setdefault('PIL', _pil_mock)
sys.modules.setdefault('PIL.ImageTk', _pil_imagetk)

# mutagen (submódulos usados en importaciones inline)
for _mod in ['mutagen', 'mutagen.wave', 'mutagen.aiff', 'mutagen.mp3',
             'mutagen.flac', 'mutagen.id3']:
    sys.modules.setdefault(_mod, MagicMock())

# essentia (opcional)
sys.modules.setdefault('essentia', MagicMock())
sys.modules.setdefault('essentia.standard', MagicMock())

# ---------------------------------------------------------------------------
# 2. IMPORTAR LAS CONSTANTES Y CLASES NECESARIAS DE YESKA01
# ---------------------------------------------------------------------------

# Ajustamos el path para que Python encuentre yeska01.py
_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_DIR not in sys.path:
    sys.path.insert(0, _REPO_DIR)

import yeska01  # noqa: E402  (el import va después del bloque de mocks)

# Alias de comodidad
REGEX_KEY_START  = yeska01.REGEX_KEY_START
REGEX_BPM_START  = yeska01.REGEX_BPM_START
REGEX_KEY_END    = yeska01.REGEX_KEY_END
REGEX_BPM_END    = yeska01.REGEX_BPM_END
REGEX_KEY_STRICT = yeska01.REGEX_KEY_STRICT

SmartFolderHandler = yeska01.SmartFolderHandler


# ---------------------------------------------------------------------------
# 3. CLASE AUXILIAR: INSTANCIA MÍNIMA DE YezkaApp PARA PROBAR MÉTODOS PUROS
# ---------------------------------------------------------------------------

class _MinimalApp:
    """
    Simula sólo los atributos que necesitan _extract_pure_name
    y _build_formatted_name.  No inicializa ningún widget.
    """
    meta_separator = "►"
    format_options = [
        "Añadir solo metadatos",
        "►KEY ►BPM - TITULO",
        "►BPM ►KEY - TITULO",
        "►BPM - TITULO",
        "►KEY - TITULO",
        "TITULO - ◄BPM ◄KEY",
        "TITULO - ◄KEY ◄BPM",
        "TITULO - ◄BPM",
        "TITULO - ◄KEY",
    ]

    # Métodos reales extraídos directamente de YezkaApp
    _extract_pure_name  = yeska01.YezkaApp._extract_pure_name
    _build_formatted_name = yeska01.YezkaApp._build_formatted_name


# ============================================================================
# GRUPO 1: EXPRESIONES REGULARES
# ============================================================================

class TestRegexPatterns(unittest.TestCase):
    """Pruebas para las expresiones regulares del módulo."""

    # ---- REGEX_KEY_START ----

    def test_key_start_formato_clasico(self):
        """Detecta clave Camelot al inicio: '8A - My Track'."""
        m = REGEX_KEY_START.match("8A - My Track")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "8A")
        self.assertEqual(m.group(2), "My Track")

    def test_key_start_con_guion_bajo(self):
        """Acepta guiones bajos como separador."""
        m = REGEX_KEY_START.match("11B_Cool Loop")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "11B")

    def test_key_start_con_espacio(self):
        """Acepta un espacio simple como separador."""
        m = REGEX_KEY_START.match("3Am  Hard Bass")
        self.assertIsNotNone(m)

    def test_key_start_no_coincide_sin_clave(self):
        """No debe coincidir con texto que no comienza con clave Camelot."""
        m = REGEX_KEY_START.match("My Track - 128 BPM")
        self.assertIsNone(m)

    def test_key_start_clave_minuscula(self):
        """Acepta claves en minúsculas."""
        m = REGEX_KEY_START.match("4b - Smooth Groove")
        self.assertIsNotNone(m)

    # ---- REGEX_BPM_START ----

    def test_bpm_start_formato_clasico(self):
        """Detecta BPM al inicio: '128 BPM - Track Name'."""
        m = REGEX_BPM_START.match("128 BPM - Track Name")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "128")
        self.assertEqual(m.group(2), "Track Name")

    def test_bpm_start_sin_sufijo_bpm(self):
        """Detecta número de BPM al inicio sin la palabra 'BPM'."""
        m = REGEX_BPM_START.match("140 - Energetic Drop")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "140")

    def test_bpm_start_decimal(self):
        """Acepta BPM con decimales."""
        m = REGEX_BPM_START.match("128.5 BPM - Groove")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "128.5")

    def test_bpm_start_no_coincide_con_numero_corto(self):
        """Un número de un solo dígito no debe ser detectado como BPM."""
        m = REGEX_BPM_START.match("9 - Something")
        self.assertIsNone(m)

    def test_bpm_start_insensible_a_mayusculas(self):
        """La palabra 'bpm' debe ser reconocida en minúsculas."""
        m = REGEX_BPM_START.match("120 bpm - Lo-fi Beat")
        self.assertIsNotNone(m)

    # ---- REGEX_KEY_END ----

    def test_key_end_formato_clasico(self):
        """Detecta clave Camelot al final: 'Track Name - 8A'."""
        m = REGEX_KEY_END.search("Track Name - 8A")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "8A")

    def test_key_end_con_guion_bajo(self):
        """Acepta guiones bajos como separador al final."""
        m = REGEX_KEY_END.search("Deep Bass_12B")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "12B")

    def test_key_end_no_coincide_sin_clave(self):
        """No debe coincidir cuando no hay clave Camelot al final."""
        m = REGEX_KEY_END.search("Track Name - 128")
        self.assertIsNone(m)

    # ---- REGEX_BPM_END ----

    def test_bpm_end_formato_clasico(self):
        """Detecta BPM al final: 'Track - 128 BPM'."""
        m = REGEX_BPM_END.search("Track - 128 BPM")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "128")

    def test_bpm_end_sin_sufijo_bpm(self):
        """Detecta número al final como BPM aunque no lleve el sufijo."""
        m = REGEX_BPM_END.search("Groove Track - 140")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "140")

    def test_bpm_end_insensible_a_mayusculas(self):
        """Acepta 'BPM' en cualquier combinación de mayúsculas/minúsculas."""
        m = REGEX_BPM_END.search("Chill - 90 Bpm")
        self.assertIsNotNone(m)

    # ---- REGEX_KEY_STRICT ----

    def test_key_strict_valido(self):
        """Detecta correctamente '8A' como número=8, letra=A."""
        m = REGEX_KEY_STRICT.match("8A")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "8")
        self.assertEqual(m.group(2), "A")

    def test_key_strict_dos_digitos(self):
        """Acepta claves con dos dígitos, como '12B'."""
        m = REGEX_KEY_STRICT.match("12B")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "12")

    def test_key_strict_no_coincide_solo_letras(self):
        """Una cadena sin número inicial no debe coincidir."""
        m = REGEX_KEY_STRICT.match("Amaj")
        self.assertIsNone(m)

    def test_key_strict_no_coincide_solo_numeros(self):
        """Un número sin letras no debe coincidir."""
        m = REGEX_KEY_STRICT.match("128")
        self.assertIsNone(m)


# ============================================================================
# GRUPO 2: SmartFolderHandler
# ============================================================================

class TestSmartFolderHandler(unittest.TestCase):
    """Pruebas de filtrado de eventos del sistema de archivos."""

    def setUp(self):
        self.added = []
        self.removed = []
        self.handler = SmartFolderHandler(
            add_callback=self.added.append,
            remove_callback=self.removed.append,
        )

    def _make_event(self, path, is_directory=False):
        """Crea un evento simulado de creación o eliminación."""
        ev = MagicMock()
        ev.src_path = path
        ev.is_directory = is_directory
        return ev

    # ---- on_created ----

    def test_created_ignora_directorios(self):
        """No debe registrar eventos de creación de directorios."""
        ev = self._make_event("/ruta/carpeta/", is_directory=True)
        with patch('time.sleep'):
            self.handler.on_created(ev)
        self.assertEqual(self.added, [])

    def test_created_ignora_extensiones_no_validas(self):
        """Archivos con extensión desconocida no deben registrarse."""
        ev = self._make_event("/ruta/archivo.txt")
        with patch('time.sleep'):
            self.handler.on_created(ev)
        self.assertEqual(self.added, [])

    def test_created_ignora_carpeta_backup(self):
        """Archivos dentro de _BACKUP_ORIGINALES no deben registrarse."""
        ev = self._make_event("/ruta/_BACKUP_ORIGINALES/track.wav")
        with patch('time.sleep'):
            self.handler.on_created(ev)
        self.assertEqual(self.added, [])

    @patch('time.sleep')
    def test_created_wav_registrado(self, _sleep):
        """Un archivo .wav válido debe invocar add_callback."""
        ev = self._make_event("/ruta/track.wav")
        self.handler.on_created(ev)
        self.assertEqual(self.added, ["/ruta/track.wav"])

    @patch('time.sleep')
    def test_created_mp3_registrado(self, _sleep):
        """Un archivo .mp3 válido debe invocar add_callback."""
        ev = self._make_event("/musica/beat.mp3")
        self.handler.on_created(ev)
        self.assertEqual(self.added, ["/musica/beat.mp3"])

    @patch('time.sleep')
    def test_created_aiff_registrado(self, _sleep):
        """Un archivo .aiff válido debe invocar add_callback."""
        ev = self._make_event("/musica/loop.aiff")
        self.handler.on_created(ev)
        self.assertEqual(self.added, ["/musica/loop.aiff"])

    @patch('time.sleep')
    def test_created_flac_registrado(self, _sleep):
        """Un archivo .flac válido debe invocar add_callback."""
        ev = self._make_event("/musica/stem.flac")
        self.handler.on_created(ev)
        self.assertEqual(self.added, ["/musica/stem.flac"])

    # ---- on_deleted ----

    def test_deleted_ignora_directorios(self):
        """No debe registrar eventos de eliminación de directorios."""
        ev = self._make_event("/ruta/carpeta/", is_directory=True)
        self.handler.on_deleted(ev)
        self.assertEqual(self.removed, [])

    def test_deleted_ignora_backup(self):
        """Archivos del backup no deben activar remove_callback."""
        ev = self._make_event("/ruta/_BACKUP_ORIGINALES/track.wav")
        self.handler.on_deleted(ev)
        self.assertEqual(self.removed, [])

    def test_deleted_wav_registrado(self):
        """Eliminación de .wav válido debe invocar remove_callback."""
        ev = self._make_event("/ruta/track.wav")
        self.handler.on_deleted(ev)
        self.assertEqual(self.removed, ["/ruta/track.wav"])

    def test_deleted_ignora_extension_no_valida(self):
        """Eliminación de archivo sin extensión válida no debe registrarse."""
        ev = self._make_event("/ruta/nota.txt")
        self.handler.on_deleted(ev)
        self.assertEqual(self.removed, [])

    # ---- on_moved ----

    @patch('time.sleep')
    def test_moved_origen_valido_y_destino_valido(self, _sleep):
        """Un movimiento de .wav a .wav registra remove del origen y add del destino."""
        ev = MagicMock()
        ev.is_directory = False
        ev.src_path = "/ruta/viejo.wav"
        ev.dest_path = "/ruta/nuevo.wav"
        self.handler.on_moved(ev)
        self.assertIn("/ruta/viejo.wav", self.removed)
        self.assertIn("/ruta/nuevo.wav", self.added)

    @patch('time.sleep')
    def test_moved_origen_backup_ignorado(self, _sleep):
        """Origen en _BACKUP_ORIGINALES no debe invocar remove_callback."""
        ev = MagicMock()
        ev.is_directory = False
        ev.src_path = "/ruta/_BACKUP_ORIGINALES/viejo.wav"
        ev.dest_path = "/ruta/nuevo.wav"
        self.handler.on_moved(ev)
        self.assertEqual(self.removed, [])
        self.assertIn("/ruta/nuevo.wav", self.added)

    @patch('time.sleep')
    def test_moved_destino_backup_ignorado(self, _sleep):
        """Destino en _BACKUP_ORIGINALES no debe invocar add_callback."""
        ev = MagicMock()
        ev.is_directory = False
        ev.src_path = "/ruta/track.wav"
        ev.dest_path = "/ruta/_BACKUP_ORIGINALES/track.wav"
        self.handler.on_moved(ev)
        self.assertIn("/ruta/track.wav", self.removed)
        self.assertEqual(self.added, [])


# ============================================================================
# GRUPO 3: _extract_pure_name
# ============================================================================

class TestExtractPureName(unittest.TestCase):
    """Pruebas de extracción del nombre puro de un archivo de audio."""

    def setUp(self):
        self.app = _MinimalApp()

    def _extract(self, name, bpm="", key=""):
        return self.app._extract_pure_name(name, bpm, key)

    # ---- Casos básicos ----

    def test_nombre_sin_metadata(self):
        """Un nombre sin metadatos debe devolverse intacto."""
        self.assertEqual(self.app._extract_pure_name("Mi Track", "", ""), "Mi Track")

    def test_nombre_vacio(self):
        """Cadena vacía debe devolver cadena vacía."""
        self.assertEqual(self.app._extract_pure_name("", "", ""), "")

    # ---- Eliminación de prefijo de clave Camelot ----

    def test_elimina_prefijo_key(self):
        """Debe eliminar la clave Camelot del inicio."""
        result = self._extract("8A - Cool Loop", "", "8A")
        self.assertEqual(result, "Cool Loop")

    def test_elimina_prefijo_key_con_bpm(self):
        """Debe eliminar prefijo KEY►BPM cuando ambos se pasan como metadatos."""
        result = self._extract("8A►128 - Cool Loop", "128", "8A")
        self.assertEqual(result, "Cool Loop")

    # ---- Eliminación de sufijo de clave Camelot ----

    def test_elimina_sufijo_key(self):
        """Debe eliminar la clave Camelot del final."""
        result = self._extract("Cool Loop - 8A", "", "8A")
        self.assertEqual(result, "Cool Loop")

    # ---- Eliminación de prefijo de BPM ----

    def test_elimina_prefijo_bpm(self):
        """Debe eliminar el BPM del inicio del nombre."""
        result = self._extract("128 - My Beat", "128", "")
        self.assertEqual(result, "My Beat")

    def test_elimina_prefijo_bpm_con_sufijo_bpm_literal(self):
        """Debe eliminar '128 BPM' del inicio."""
        result = self._extract("128 BPM - My Beat", "128", "")
        self.assertEqual(result, "My Beat")

    # ---- Eliminación de sufijo de BPM ----

    def test_elimina_sufijo_bpm(self):
        """Debe eliminar el BPM del final del nombre."""
        result = self._extract("My Beat - 128", "128", "")
        self.assertEqual(result, "My Beat")

    def test_elimina_sufijo_bpm_literal(self):
        """Debe eliminar '128 BPM' del final del nombre."""
        result = self._extract("My Beat - 128 BPM", "128", "")
        self.assertEqual(result, "My Beat")

    # ---- Extracción con regex cuando no hay metadatos explícitos ----

    def test_regex_key_start_extrae_nombre(self):
        """El regex de clave inicial debe limpiar el nombre sin metadatos."""
        result = self._extract("11B - Deep House Loop", "", "")
        self.assertEqual(result, "Deep House Loop")

    def test_regex_bpm_start_extrae_nombre(self):
        """El regex de BPM inicial debe limpiar el nombre sin metadatos."""
        result = self._extract("140 - Energetic Drop", "", "")
        self.assertEqual(result, "Energetic Drop")

    def test_regex_key_end_extrae_nombre(self):
        """El regex de clave final debe limpiar el nombre sin metadatos."""
        result = self._extract("Acid Bass - 3A", "", "")
        self.assertEqual(result, "Acid Bass")

    def test_regex_bpm_end_extrae_nombre(self):
        """El regex de BPM final debe limpiar el nombre sin metadatos."""
        result = self._extract("Bassline - 130", "", "")
        self.assertEqual(result, "Bassline")

    # ---- Casos de borde ----

    def test_nombre_con_solo_key(self):
        """Un nombre que es solo la clave debe devolver cadena vacía."""
        result = self._extract("8A", "", "8A")
        self.assertEqual(result, "")

    def test_preserva_nombre_complejo(self):
        """Nombre complejo sin metadatos no debe ser modificado."""
        result = self._extract("Dark Minimal (Original Mix)", "", "")
        self.assertEqual(result, "Dark Minimal (Original Mix)")

    def test_no_duplica_eliminacion(self):
        """
        Cuando el nombre contiene tanto la clave metadato (8A) como otra
        secuencia que parece una clave (3B al final), el algoritmo elimina
        ambas porque REGEX_KEY_END también actúa sobre 3B.
        El nombre puro resultante debe al menos conservar las palabras
        intermedias que no son clave ni BPM.
        """
        result = self._extract("Track 8A vs 3B", "128", "8A")
        # "Track 8A vs 3B": primero se elimina "8A" del token conocido,
        # luego REGEX_KEY_END elimina "3B" del final.
        # El texto que debe mantenerse es la parte que no es clave/BPM.
        self.assertIn("Track", result)

    def test_key_en_mayusculas_y_minusculas(self):
        """La clave en minúsculas debe eliminarse igual que en mayúsculas."""
        result_upper = self._extract("8A - Track", "", "8A")
        result_lower = self._extract("8a - Track", "", "8a")
        self.assertEqual(result_upper, "Track")
        self.assertEqual(result_lower, "Track")


# ============================================================================
# GRUPO 4: _build_formatted_name
# ============================================================================

class TestBuildFormattedName(unittest.TestCase):
    """Pruebas de construcción del nombre de archivo formateado."""

    def setUp(self):
        self.app = _MinimalApp()

    def _build(self, name, bpm, key, fmt):
        return self.app._build_formatted_name(name, bpm, key, fmt)

    # ---- Formatos de prefijo ----

    def test_formato_key_bpm_titulo(self):
        """Formato '►KEY ►BPM - TITULO': la clave y el BPM preceden al título."""
        result = self._build("My Track", "128", "8A", "►KEY ►BPM - TITULO")
        self.assertTrue(result.startswith("►8A"))
        self.assertIn("128", result)
        self.assertIn("My Track", result)

    def test_formato_bpm_key_titulo(self):
        """Formato '►BPM ►KEY - TITULO': el BPM precede a la clave."""
        result = self._build("My Track", "128", "8A", "►BPM ►KEY - TITULO")
        self.assertTrue(result.startswith("►128"))
        self.assertIn("8A", result)
        self.assertIn("My Track", result)

    def test_formato_solo_bpm_titulo(self):
        """Formato '►BPM - TITULO': solo el BPM como prefijo."""
        result = self._build("My Track", "140", "8A", "►BPM - TITULO")
        self.assertTrue(result.startswith("►140"))
        self.assertIn("My Track", result)

    def test_formato_solo_key_titulo(self):
        """Formato '►KEY - TITULO': solo la clave como prefijo."""
        result = self._build("My Track", "128", "3B", "►KEY - TITULO")
        self.assertTrue(result.startswith("►3B"))
        self.assertIn("My Track", result)

    # ---- Formatos de sufijo ----

    def test_formato_titulo_bpm_key(self):
        """Formato 'TITULO - ◄BPM ◄KEY': BPM y clave van al final."""
        result = self._build("My Track", "128", "8A", "TITULO - ◄BPM ◄KEY")
        self.assertTrue(result.startswith("My Track"))
        self.assertIn("128", result)
        self.assertIn("8A", result)

    def test_formato_titulo_key_bpm(self):
        """Formato 'TITULO - ◄KEY ◄BPM': clave y BPM van al final."""
        result = self._build("My Track", "128", "8A", "TITULO - ◄KEY ◄BPM")
        self.assertTrue(result.startswith("My Track"))
        self.assertIn("8A", result)
        self.assertIn("128", result)

    def test_formato_titulo_solo_bpm(self):
        """Formato 'TITULO - ◄BPM': solo el BPM va al final."""
        result = self._build("My Track", "128", "8A", "TITULO - ◄BPM")
        self.assertTrue(result.startswith("My Track"))
        self.assertIn("128", result)

    def test_formato_titulo_solo_key(self):
        """Formato 'TITULO - ◄KEY': solo la clave va al final."""
        result = self._build("My Track", "128", "8A", "TITULO - ◄KEY")
        self.assertTrue(result.startswith("My Track"))
        self.assertIn("8A", result)

    # ---- Formato especial: solo metadatos ----

    def test_formato_solo_metadatos_devuelve_nombre_puro(self):
        """'Añadir solo metadatos' devuelve el nombre sin modificar."""
        result = self._build("My Track", "128", "8A", "Añadir solo metadatos")
        self.assertEqual(result, "My Track")

    # ---- Casos con metadatos vacíos ----

    def test_bpm_vacio_omitido_en_prefijo(self):
        """Si el BPM está vacío, no debe aparecer en el resultado."""
        result = self._build("My Track", "", "8A", "►KEY ►BPM - TITULO")
        self.assertNotIn("BPM", result)
        self.assertIn("8A", result)

    def test_key_vacio_omitido_en_prefijo(self):
        """Si la clave está vacía, no debe aparecer en el resultado."""
        result = self._build("My Track", "128", "", "►KEY ►BPM - TITULO")
        self.assertNotIn("KEY", result)
        self.assertIn("128", result)

    def test_ambos_vacios_devuelve_nombre(self):
        """Con BPM y clave vacíos en formato de prefijo, devuelve el nombre."""
        result = self._build("My Track", "", "", "►KEY ►BPM - TITULO")
        self.assertEqual(result, "My Track")

    # ---- Separadores ----

    def test_separador_espacio_en_blanco(self):
        """El separador 'Espacio en blanco' usa un espacio."""
        self.app.meta_separator = "Espacio en blanco"
        result = self._build("My Track", "128", "8A", "►KEY ►BPM - TITULO")
        # Los metadatos deben aparecer separados por espacio, no por ►
        self.assertNotIn("►", result)
        self.app.meta_separator = "►"  # restaurar

    def test_separador_guion(self):
        """El separador '-' genera un nombre con guiones."""
        self.app.meta_separator = "-"
        result = self._build("My Track", "128", "8A", "►KEY ►BPM - TITULO")
        self.assertIn("8A", result)
        self.assertIn("128", result)
        self.app.meta_separator = "►"  # restaurar

    # ---- Normalización de clave ----

    def test_key_major_normalizado(self):
        """'MAJOR' debe ser reemplazado por 'MAJ' en el resultado."""
        result = self._build("My Track", "128", "C MAJOR", "►KEY - TITULO")
        self.assertIn("CMAJ", result)
        self.assertNotIn("MAJOR", result)

    def test_key_minor_normalizado(self):
        """'MINOR' debe ser reemplazado por 'MIN' en el resultado."""
        result = self._build("My Track", "128", "A MINOR", "►KEY - TITULO")
        self.assertIn("AMIN", result)
        self.assertNotIn("MINOR", result)

    # ---- Limpieza del resultado ----

    def test_sin_dobles_guiones(self):
        """El resultado no debe contener '- -' ni guiones duplicados."""
        result = self._build("My Track", "128", "8A", "►KEY ►BPM - TITULO")
        self.assertNotIn("- -", result)

    def test_no_empieza_ni_termina_con_guion(self):
        """El resultado no debe comenzar ni terminar con un guión suelto."""
        result = self._build("My Track", "", "", "►KEY ►BPM - TITULO")
        self.assertFalse(result.startswith("-"))
        self.assertFalse(result.endswith("-"))


# ============================================================================
# GRUPO 5: _raw_to_samples
# ============================================================================

class TestRawToSamples(unittest.TestCase):
    """Pruebas de conversión de bytes de audio crudo a muestras flotantes."""

    def setUp(self):
        self.app = _MinimalApp()
        self.app._raw_to_samples = yeska01.YezkaApp._raw_to_samples.__get__(
            self.app, _MinimalApp
        )

    # ---- 8 bits ----

    def test_8bit_mono_convierte(self):
        """Audio de 8 bits mono debe generar muestras centradas en 0."""
        import numpy as np
        # Valor 128 = silencio en PCM 8-bit unsigned
        raw = bytes([128, 200, 50])
        samples = self.app._raw_to_samples(raw, sampwidth=1, n_channels=1)
        self.assertIsNotNone(samples)
        self.assertAlmostEqual(float(samples[0]), 0.0, places=3)

    # ---- 16 bits ----

    def test_16bit_mono_convierte(self):
        """Audio de 16 bits mono debe generar el número correcto de muestras."""
        import numpy as np
        # 4 samples, little-endian int16
        data = [1000, -1000, 32767, -32768]
        raw = struct.pack('<4h', *data)
        samples = self.app._raw_to_samples(raw, sampwidth=2, n_channels=1)
        self.assertIsNotNone(samples)
        self.assertEqual(len(samples), 4)
        self.assertAlmostEqual(float(samples[0]), 1000.0, places=1)

    def test_16bit_estereo_promedia_canales(self):
        """Audio de 16 bits estéreo debe promediar ambos canales en uno mono."""
        import numpy as np
        # 2 pares de muestras estéreo: (100, 200) y (300, 400)
        raw = struct.pack('<4h', 100, 200, 300, 400)
        samples = self.app._raw_to_samples(raw, sampwidth=2, n_channels=2)
        self.assertIsNotNone(samples)
        self.assertEqual(len(samples), 2)
        self.assertAlmostEqual(float(samples[0]), 150.0, places=1)  # (100+200)/2
        self.assertAlmostEqual(float(samples[1]), 350.0, places=1)  # (300+400)/2

    # ---- 24 bits ----

    def test_24bit_mono_convierte(self):
        """Audio de 24 bits mono debe generar muestras correctas."""
        import numpy as np
        # Muestra 0 como tres bytes en little-endian: 0x00 0x00 0x00
        raw = bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00])
        samples = self.app._raw_to_samples(raw, sampwidth=3, n_channels=1)
        self.assertIsNotNone(samples)
        self.assertEqual(len(samples), 2)
        self.assertAlmostEqual(float(samples[0]), 0.0, places=1)
        self.assertAlmostEqual(float(samples[1]), 1.0, places=1)

    # ---- Ancho de muestra no soportado ----

    def test_sampwidth_no_soportado_devuelve_none(self):
        """Un ancho de muestra desconocido debe devolver None."""
        result = self.app._raw_to_samples(b'\x00' * 8, sampwidth=5, n_channels=1)
        self.assertIsNone(result)

    # ---- Big-endian ----

    def test_16bit_big_endian(self):
        """Audio de 16 bits big-endian debe interpretarse correctamente."""
        import numpy as np
        raw = struct.pack('>2h', 1000, -500)
        samples = self.app._raw_to_samples(raw, sampwidth=2, n_channels=1, big_endian=True)
        self.assertIsNotNone(samples)
        self.assertAlmostEqual(float(samples[0]), 1000.0, places=1)
        self.assertAlmostEqual(float(samples[1]), -500.0, places=1)


# ============================================================================
# GRUPO 6: _prepare_files_data
# ============================================================================

class TestPrepareFilesData(unittest.TestCase):
    """Pruebas de la preparación del diccionario de datos por archivo."""

    def setUp(self):
        # Creamos un objeto mínimo que replique los atributos necesarios
        self.app = MagicMock()
        self.app.loaded_paths = []
        self.app.session_history = {}
        self.app.format_options = _MinimalApp.format_options
        self.app.meta_separator = "►"

        # Sustituimos los métodos por las implementaciones reales
        self.app.read_metadata = MagicMock(return_value=("128", "8A"))
        self.app._extract_pure_name = (
            yeska01.YezkaApp._extract_pure_name.__get__(self.app, type(self.app))
        )
        self.app._build_formatted_name = (
            yeska01.YezkaApp._build_formatted_name.__get__(self.app, type(self.app))
        )
        self.app._prepare_files_data = (
            yeska01.YezkaApp._prepare_files_data.__get__(self.app, type(self.app))
        )

    def _mock_path(self, filename, tmpdir="/tmp"):
        """Construye una cadena de ruta bajo tmpdir sin crear el archivo."""
        return os.path.join(tmpdir, filename)

    def test_prepara_datos_basicos(self):
        """Cada archivo debe generar una entrada con los campos esperados."""
        path = "/tmp/Cool Loop.wav"
        new_paths, new_data = self.app._prepare_files_data([path])

        self.assertIn(path, new_paths)
        data = new_data[path]
        self.assertIn('name', data)
        self.assertIn('bpm', data)
        self.assertIn('key', data)
        self.assertIn('ext', data)
        self.assertIn('estado', data)
        self.assertIn('is_custom', data)
        self.assertIn('is_formatted', data)
        self.assertIn('is_staged', data)

    def test_extension_convertida_a_mayusculas(self):
        """La extensión en el campo 'ext' debe estar en MAYÚSCULAS."""
        path = "/tmp/track.mp3"
        _, new_data = self.app._prepare_files_data([path])
        self.assertEqual(new_data[path]['ext'], 'MP3')

    def test_archivo_ya_cargado_no_se_duplica(self):
        """Un archivo ya presente en loaded_paths no debe re-añadirse."""
        path = "/tmp/track.wav"
        self.app.loaded_paths = [path]
        new_paths, new_data = self.app._prepare_files_data([path])
        self.assertEqual(new_paths, [])
        self.assertEqual(new_data, {})

    def test_is_staged_siempre_false_al_cargar(self):
        """Los archivos recién cargados no deben estar en estado 'staged'."""
        path = "/tmp/new_track.flac"
        _, new_data = self.app._prepare_files_data([path])
        self.assertFalse(new_data[path]['is_staged'])

    def test_converted_to_wav_false_al_cargar(self):
        """El campo converted_to_wav debe ser False para nuevos archivos."""
        path = "/tmp/new_track.aiff"
        _, new_data = self.app._prepare_files_data([path])
        self.assertFalse(new_data[path]['converted_to_wav'])

    def test_multiples_archivos_se_preparan(self):
        """Múltiples rutas deben generar múltiples entradas."""
        paths = ["/tmp/a.wav", "/tmp/b.mp3", "/tmp/c.flac"]
        new_paths, new_data = self.app._prepare_files_data(paths)
        self.assertEqual(len(new_paths), 3)
        self.assertEqual(len(new_data), 3)


# ============================================================================
# GRUPO 7: INTEGRACIÓN — combinando _extract_pure_name + _build_formatted_name
# ============================================================================

class TestIntegracionNombres(unittest.TestCase):
    """
    Pruebas de integración: extraer el nombre puro de un archivo y luego
    reconstruirlo con otro formato debe producir un resultado coherente.
    """

    def setUp(self):
        self.app = _MinimalApp()

    def _ciclo(self, nombre_original, bpm, key, fmt):
        """Extrae el nombre puro y luego lo formatea con el formato dado."""
        pure = self.app._extract_pure_name(nombre_original, bpm, key)
        return self.app._build_formatted_name(pure, bpm, key, fmt)

    def test_ciclo_completo_prefijo_key_bpm(self):
        """Un nombre con clave y BPM en el nombre debe regenerarse correctamente."""
        result = self._ciclo("8A►128-Cool Loop", "128", "8A", "►KEY ►BPM - TITULO")
        self.assertIn("Cool Loop", result)
        self.assertIn("128", result)
        self.assertIn("8A", result)

    def test_ciclo_cambia_formato_a_sufijo(self):
        """Cambiar del formato prefijo al sufijo mantiene el nombre puro."""
        nombre = "►8A►128-Deep Bass"
        pure = self.app._extract_pure_name(nombre, "128", "8A")
        resultado_sufijo = self.app._build_formatted_name(
            pure, "128", "8A", "TITULO - ◄BPM ◄KEY"
        )
        self.assertTrue(resultado_sufijo.startswith("Deep Bass"))
        self.assertIn("128", resultado_sufijo)
        self.assertIn("8A", resultado_sufijo)

    def test_ciclo_con_nombre_complejo(self):
        """Nombre con paréntesis y espacios no se corrompe en el ciclo."""
        result = self._ciclo("Acid Rain (Original Mix)", "140", "3A", "►KEY - TITULO")
        self.assertIn("Acid Rain (Original Mix)", result)
        self.assertIn("3A", result)

    def test_ciclo_nombre_solo_devuelve_nombre(self):
        """Formato 'Añadir solo metadatos' devuelve el nombre puro sin cambios."""
        pure = self.app._extract_pure_name("8A - My Track", "", "8A")
        result = self.app._build_formatted_name(pure, "128", "8A", "Añadir solo metadatos")
        self.assertEqual(result, "My Track")


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == '__main__':
    unittest.main(verbosity=2)
