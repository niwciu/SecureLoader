"""Lightweight i18n layer.

We use a minimal in-process translation dictionary rather than compiled
.mo files: the string set is tiny, and shipping editable Python
dictionaries keeps the toolchain free from gettext build steps (``msgfmt``
is not always available on Windows build agents).

The module exposes :func:`set_language`, :func:`get_language`, and the
canonical short-aliased :func:`_` function. Translators add a new language
by appending an entry to :data:`TRANSLATIONS`.
"""

from __future__ import annotations

import locale
import logging
import os
from typing import Literal

log = logging.getLogger(__name__)

Language = Literal["en", "de", "fr", "es", "it", "pl"]
SUPPORTED: tuple[Language, ...] = ("en", "de", "fr", "es", "it", "pl")

TRANSLATIONS: dict[Language, dict[str, str]] = {
    "en": {},
    "de": {
        # Window / menu
        "Language": "Sprache",
        "&Help": "&Hilfe",
        "Credentials": "Anmeldedaten",
        "Set login and password": "Login und Passwort setzen",
        "Update instruction...": "Updateanleitung...",
        "&About...": "&Über...",
        "About {name}": "Über {name}",
        "Version info": "Versionsinformation",
        # Form labels
        "Port": "Port",
        "Baud": "Baud",
        "Parity": "Parität",
        "Stop bits": "Stoppbits",
        "Status": "Status",
        "Product ID": "Produkt-ID",
        "Bootloader Version": "Bootloader-Version",
        "Firmware file": "Firmware-Datei",
        "Firmware download": "Firmware-Download",
        "App Version": "App-Version",
        "Previous App Ver.": "Vorherige Version",
        "Protocol": "Protokoll",
        "File Size": "Dateigröße",
        "Update progress": "Aktualisierungsfortschritt",
        # Buttons
        "Connect": "Verbinden",
        "Disconnect": "Trennen",
        "Refresh ports": "Ports aktualisieren",
        "Select file...": "Datei auswählen...",
        "Fetch from server": "Vom Server laden",
        "Get Previous Firmware": "Vorherige Firmware laden",
        "Update": "Aktualisieren",
        "Show password": "Passwort anzeigen",
        "Login:": "Login:",
        "Password:": "Passwort:",
        "OK": "OK",
        "Cancel": "Abbrechen",
        # Messages
        "Cannot read file {path}: {err}": "Datei {path} kann nicht gelesen werden: {err}",
        "Update completed successfully": "Aktualisierung erfolgreich abgeschlossen",
        "Firmware download from server completed": "Firmware-Download vom Server abgeschlossen",
        "Device must be connected before downloading.": (
            "Das Gerät muss vor dem Herunterladen verbunden sein."
        ),
        "Previous version requires a firmware file loaded.": (
            "Die vorherige Version erfordert eine geladene Firmware-Datei."
        ),
        "Server connection problem": "Serververbindungsproblem",
        "Idle": "Bereit",
        "Connecting": "Verbinde",
        "Connected": "Verbunden",
        "Download": "Übertragung",
        "Version {version}": "Version {version}",
        # CLI
        "No serial ports found.": "Keine seriellen Ports gefunden.",
        "Connected to device:": "Mit Gerät verbunden:",
        "Firmware header:": "Firmware-Header:",
        "Device does not match firmware ({reason}).": (
            "Gerät passt nicht zur Firmware ({reason})."
        ),
        "Downloaded file is not a valid firmware image.": (
            "Die heruntergeladene Datei ist kein gültiges Firmware-Image."
        ),
        "Starting transfer...": "Übertragung wird gestartet...",
        "Update finished.": "Aktualisierung abgeschlossen.",
    },
    "fr": {
        # Window / menu
        "Language": "Langue",
        "&Help": "&Aide",
        "Credentials": "Identifiants",
        "Set login and password": "Définir login et mot de passe",
        "Update instruction...": "Instructions de mise à jour...",
        "&About...": "&À propos...",
        "About {name}": "À propos de {name}",
        "Version info": "Informations de version",
        # Form labels
        "Port": "Port",
        "Baud": "Baud",
        "Parity": "Parité",
        "Stop bits": "Bits d'arrêt",
        "Status": "Statut",
        "Product ID": "ID produit",
        "Bootloader Version": "Version du bootloader",
        "Firmware file": "Fichier firmware",
        "Firmware download": "Téléchargement firmware",
        "App Version": "Version de l'application",
        "Previous App Ver.": "Version précédente",
        "Protocol": "Protocole",
        "File Size": "Taille du fichier",
        "Update progress": "Progression de la mise à jour",
        # Buttons
        "Connect": "Connecter",
        "Disconnect": "Déconnecter",
        "Refresh ports": "Actualiser les ports",
        "Select file...": "Sélectionner un fichier...",
        "Fetch from server": "Récupérer du serveur",
        "Get Previous Firmware": "Obtenir le firmware précédent",
        "Update": "Mettre à jour",
        "Show password": "Afficher le mot de passe",
        "Login:": "Login :",
        "Password:": "Mot de passe :",
        "OK": "OK",
        "Cancel": "Annuler",
        # Messages
        "Cannot read file {path}: {err}": "Impossible de lire le fichier {path} : {err}",
        "Update completed successfully": "Mise à jour réussie",
        "Firmware download from server completed": (
            "Téléchargement du firmware depuis le serveur terminé"
        ),
        "Device must be connected before downloading.": (
            "L'appareil doit être connecté avant de télécharger."
        ),
        "Previous version requires a firmware file loaded.": (
            "La version précédente nécessite un fichier firmware chargé."
        ),
        "Server connection problem": "Problème de connexion au serveur",
        "Idle": "Inactif",
        "Connecting": "Connexion",
        "Connected": "Connecté",
        "Download": "Téléchargement",
        "Version {version}": "Version {version}",
        # CLI
        "No serial ports found.": "Aucun port série trouvé.",
        "Connected to device:": "Connecté à l'appareil :",
        "Firmware header:": "En-tête firmware :",
        "Device does not match firmware ({reason}).": (
            "L'appareil ne correspond pas au firmware ({reason})."
        ),
        "Downloaded file is not a valid firmware image.": (
            "Le fichier téléchargé n'est pas une image firmware valide."
        ),
        "Starting transfer...": "Démarrage du transfert...",
        "Update finished.": "Mise à jour terminée.",
    },
    "es": {
        # Window / menu
        "Language": "Idioma",
        "&Help": "&Ayuda",
        "Credentials": "Credenciales",
        "Set login and password": "Configurar usuario y contraseña",
        "Update instruction...": "Instrucciones de actualización...",
        "&About...": "&Acerca de...",
        "About {name}": "Acerca de {name}",
        "Version info": "Información de versión",
        # Form labels
        "Port": "Puerto",
        "Baud": "Baud",
        "Parity": "Paridad",
        "Stop bits": "Bits de parada",
        "Status": "Estado",
        "Product ID": "ID de producto",
        "Bootloader Version": "Versión del bootloader",
        "Firmware file": "Archivo de firmware",
        "Firmware download": "Descarga de firmware",
        "App Version": "Versión de la aplicación",
        "Previous App Ver.": "Versión anterior",
        "Protocol": "Protocolo",
        "File Size": "Tamaño del archivo",
        "Update progress": "Progreso de actualización",
        # Buttons
        "Connect": "Conectar",
        "Disconnect": "Desconectar",
        "Refresh ports": "Actualizar puertos",
        "Select file...": "Seleccionar archivo...",
        "Fetch from server": "Obtener del servidor",
        "Get Previous Firmware": "Obtener firmware anterior",
        "Update": "Actualizar",
        "Show password": "Mostrar contraseña",
        "Login:": "Usuario:",
        "Password:": "Contraseña:",
        "OK": "OK",
        "Cancel": "Cancelar",
        # Messages
        "Cannot read file {path}: {err}": "No se puede leer el archivo {path}: {err}",
        "Update completed successfully": "Actualización completada con éxito",
        "Firmware download from server completed": ("Descarga de firmware del servidor completada"),
        "Device must be connected before downloading.": (
            "El dispositivo debe estar conectado antes de descargar."
        ),
        "Previous version requires a firmware file loaded.": (
            "La versión anterior requiere un archivo de firmware cargado."
        ),
        "Server connection problem": "Problema de conexión al servidor",
        "Idle": "Inactivo",
        "Connecting": "Conectando",
        "Connected": "Conectado",
        "Download": "Descargando",
        "Version {version}": "Versión {version}",
        # CLI
        "No serial ports found.": "No se encontraron puertos serie.",
        "Connected to device:": "Conectado al dispositivo:",
        "Firmware header:": "Cabecera de firmware:",
        "Device does not match firmware ({reason}).": (
            "El dispositivo no coincide con el firmware ({reason})."
        ),
        "Downloaded file is not a valid firmware image.": (
            "El archivo descargado no es una imagen de firmware válida."
        ),
        "Starting transfer...": "Iniciando transferencia...",
        "Update finished.": "Actualización terminada.",
    },
    "it": {
        # Window / menu
        "Language": "Lingua",
        "&Help": "&Aiuto",
        "Credentials": "Credenziali",
        "Set login and password": "Imposta login e password",
        "Update instruction...": "Istruzioni per l'aggiornamento...",
        "&About...": "&Informazioni...",
        "About {name}": "Informazioni su {name}",
        "Version info": "Informazioni sulla versione",
        # Form labels
        "Port": "Porta",
        "Baud": "Baud",
        "Parity": "Parità",
        "Stop bits": "Bit di stop",
        "Status": "Stato",
        "Product ID": "ID prodotto",
        "Bootloader Version": "Versione bootloader",
        "Firmware file": "File firmware",
        "Firmware download": "Download firmware",
        "App Version": "Versione app",
        "Previous App Ver.": "Versione precedente",
        "Protocol": "Protocollo",
        "File Size": "Dimensione file",
        "Update progress": "Avanzamento aggiornamento",
        # Buttons
        "Connect": "Connetti",
        "Disconnect": "Disconnetti",
        "Refresh ports": "Aggiorna porte",
        "Select file...": "Seleziona file...",
        "Fetch from server": "Scarica dal server",
        "Get Previous Firmware": "Ottieni firmware precedente",
        "Update": "Aggiorna",
        "Show password": "Mostra password",
        "Login:": "Login:",
        "Password:": "Password:",
        "OK": "OK",
        "Cancel": "Annulla",
        # Messages
        "Cannot read file {path}: {err}": "Impossibile leggere il file {path}: {err}",
        "Update completed successfully": "Aggiornamento completato con successo",
        "Firmware download from server completed": ("Download firmware dal server completato"),
        "Device must be connected before downloading.": (
            "Il dispositivo deve essere connesso prima di scaricare."
        ),
        "Previous version requires a firmware file loaded.": (
            "La versione precedente richiede un file firmware caricato."
        ),
        "Server connection problem": "Problema di connessione al server",
        "Idle": "Inattivo",
        "Connecting": "Connessione",
        "Connected": "Connesso",
        "Download": "Download",
        "Version {version}": "Versione {version}",
        # CLI
        "No serial ports found.": "Nessuna porta seriale trovata.",
        "Connected to device:": "Connesso al dispositivo:",
        "Firmware header:": "Intestazione firmware:",
        "Device does not match firmware ({reason}).": (
            "Il dispositivo non corrisponde al firmware ({reason})."
        ),
        "Downloaded file is not a valid firmware image.": (
            "Il file scaricato non è un'immagine firmware valida."
        ),
        "Starting transfer...": "Avvio trasferimento...",
        "Update finished.": "Aggiornamento completato.",
    },
    "pl": {
        # Window / menu
        "Language": "Język",
        "&Help": "&Pomoc",
        "Credentials": "Dane Logowania",
        "Set login and password": "Ustaw Login i Hasło",
        "Update instruction...": "Instrukcja aktualizacji...",
        "&About...": "O &programie...",
        "About {name}": "O programie {name}",
        "Version info": "Info o wersji",
        # Form labels
        "Port": "Port",
        "Baud": "Baud",
        "Parity": "Parzystość",
        "Stop bits": "Bity stopu",
        "Status": "Status",
        "Product ID": "Product ID",
        "Bootloader Version": "Wersja bootloadera",
        "Firmware file": "Plik z firmware",
        "Firmware download": "Pobieranie firmware",
        "App Version": "Wersja aplikacji",
        "Previous App Ver.": "Poprzednia wersja",
        "Protocol": "Protokół",
        "File Size": "Rozmiar pliku",
        "Update progress": "Progres aktualizacji",
        # Buttons
        "Connect": "Połącz",
        "Disconnect": "Rozłącz",
        "Refresh ports": "Odśwież porty",
        "Select file...": "Wybierz plik...",
        "Fetch from server": "Ściągnij plik z serwera",
        "Get Previous Firmware": "Pobierz poprzedni firmware",
        "Update": "Aktualizuj",
        "Show password": "Pokaż hasło",
        "Login:": "Login:",
        "Password:": "Hasło:",
        "OK": "OK",
        "Cancel": "Anuluj",
        # Messages
        "Cannot read file {path}: {err}": "Nie można odczytać pliku {path}: {err}",
        "Update completed successfully": "Aktualizacja zakończona powodzeniem",
        "Firmware download from server completed": (
            "Pobieranie firmware z serwera zakończone powodzeniem"
        ),
        "Device must be connected before downloading.": (
            "Urządzenie musi być podłączone przed pobieraniem."
        ),
        "Previous version requires a firmware file loaded.": (
            "Poprzednia wersja wymaga załadowanego pliku firmware."
        ),
        "Server connection problem": "Problem z połączeniem do serwera",
        "Idle": "Bezczynny",
        "Connecting": "Łączenie",
        "Connected": "Połączono",
        "Download": "Pobieranie",
        "Downloaded file is not a valid firmware image.": (
            "Pobrany plik nie jest prawidłowym obrazem firmware."
        ),
        "Version {version}": "Wersja {version}",
        # CLI
        "No serial ports found.": "Nie znaleziono portów szeregowych.",
        "Connected to device:": "Połączono z urządzeniem:",
        "Firmware header:": "Nagłówek firmware:",
        "Device does not match firmware ({reason}).": (
            "Urządzenie nie pasuje do firmware ({reason})."
        ),
        "Starting transfer...": "Rozpoczynanie transferu...",
        "Update finished.": "Aktualizacja zakończona.",
    },
}

_current: Language = "en"


def available_languages() -> tuple[Language, ...]:
    return SUPPORTED


def detect_language() -> Language:
    """Guess the user's preferred language from environment variables."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        val = os.environ.get(var)
        if val:
            code = val.split("_", 1)[0].split(".", 1)[0].lower()
            if code in SUPPORTED:
                return code
    try:
        code = (locale.getlocale()[0] or "").split("_", 1)[0].lower()
        if code in SUPPORTED:
            return code
    except (AttributeError, ValueError):
        pass
    return "en"


def set_language(lang: str) -> Language:
    """Switch the active translation. ``lang='auto'`` triggers detection."""
    global _current
    if lang == "auto":
        _current = detect_language()
    elif lang in SUPPORTED:
        _current = lang
    else:
        log.warning("unsupported language %r, falling back to en", lang)
        _current = "en"
    return _current


def get_language() -> Language:
    return _current


def _(msgid: str, **kwargs: object) -> str:
    """Translate ``msgid`` into the active language, then apply ``str.format``."""
    translated = TRANSLATIONS.get(_current, {}).get(msgid, msgid)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError):
            log.exception("translation formatting failed for %r", msgid)
            return translated
    return translated


set_language("en")
