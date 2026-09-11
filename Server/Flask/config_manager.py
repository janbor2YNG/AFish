"""Central configuration & path helper for the whole AFish project.

This module is imported by the Flask app *and* by the engine scripts in
``Python/`` (data_creator, mail_sender, mail_reader, campaign_runner). It is the
single source of truth for:

* all filesystem paths (so no script has to guess relative locations anymore),
* the currently active campaign YAML (``active_config.txt``),
* the sender profiles per template category (``sender_profiles.yaml``),
* the persisted application settings (``settings.json`` – SMTP/IMAP credentials,
  dry-run flag, admin password, …).

NOTE: Per project decision the admin password and mail credentials are stored in
plain text (no hashing/encryption). This is intentional for this internal tool -
it never leaves the school's own server and settings.json is excluded from
version control (see .gitignore).
"""

import os
import json
import yaml

# --- Paths -----------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))               # Server/Flask
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))      # repo root (AFish)

DATENBANKEN_DIR = os.path.join(REPO_ROOT, "Server", "Datenbanken")   # YAML configs + CSV
MAILS_DIR = os.path.join(REPO_ROOT, "Server", "Mails")               # mail templates
DATABASES_DIR = os.path.join(REPO_ROOT, "Python", "databases")       # campaign*.db files

CSV_PATH = os.path.join(DATENBANKEN_DIR, "current_user_list.csv")    # teacher/user list
SETTINGS_PATH = os.path.join(DATENBANKEN_DIR, "settings.json")       # app settings
ACTIVE_CONFIG_FILE = os.path.join(BASE_DIR, "active_config.txt")     # active YAML name
SENDER_PROFILES_PATH = os.path.join(DATENBANKEN_DIR, "sender_profiles.yaml")

# Status values stored per mail event (English, per project requirement).
# Ordered roughly by "how far the recipient got" - reported is the best outcome.
STATUS_PENDING = "pending"          # wave not sent yet (only used for display/counting)
STATUS_SENT = "sent"                # mail was handed to the mail server, no reaction yet
STATUS_CLICKED = "clicked"          # teacher clicked the phishing link    -> failed
STATUS_REPORTED = "reported"        # teacher forwarded/reported the mail  -> success
STATUS_VALUES = (STATUS_PENDING, STATUS_SENT, STATUS_CLICKED, STATUS_REPORTED)

# Default settings used when settings.json does not exist yet.
# NOTE: the mail subject is intentionally not a setting here - it comes from
# each template's own <title> tag (see mail_sender.extract_subject), so a new
# template's subject just works without anyone having to remember to also
# update it in Settings.
DEFAULT_SETTINGS = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "",
    "sender_password": "",
    "imap_server": "imap.gmail.com",
    "tracking_base_url": "http://127.0.0.1:5000",
    "dry_run": True,            # default: simulate, do NOT send/read real mail
    "admin_password": "admin",  # plain text, change via settings UI
}


# --- Active campaign config ------------------------------------------------
def set_active_config(filename):
    """Persist which YAML config is the active one."""
    with open(ACTIVE_CONFIG_FILE, "w") as f:
        f.write(filename)


def get_active_config_name():
    # Prefer the explicitly chosen config if it still exists on disk.
    if os.path.exists(ACTIVE_CONFIG_FILE):
        with open(ACTIVE_CONFIG_FILE) as f:
            name = f.read().strip()
        if name and os.path.exists(os.path.join(DATENBANKEN_DIR, name)):
            return name
    # Fallback for a fresh checkout: first available YAML.
    files = list_config_files()
    return files[0] if files else "beispiel-kampagne.yaml"


def get_config():
    """Backwards-compatible: return the active config filename."""
    return get_active_config_name()


def load_config(filename=None):
    """Load and parse a campaign YAML into a dict. Uses active config if None."""
    filename = filename or get_active_config_name()
    path = os.path.join(DATENBANKEN_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_config_files():
    """Return all available campaign YAML files in the Datenbanken folder.

    Excludes sender_profiles.yaml, which lives in the same folder but is not
    a campaign config.
    """
    if not os.path.isdir(DATENBANKEN_DIR):
        return []
    return sorted(
        f for f in os.listdir(DATENBANKEN_DIR)
        if f.endswith((".yml", ".yaml")) and f != os.path.basename(SENDER_PROFILES_PATH)
    )


# --- Sender profiles ---------------------------------------------------------
DEFAULT_SENDER_PROFILES = {
    "office": {"name": "IT-Support", "email": "it-support@simulation.schule-intern.example"},
    "google": {"name": "Konto-Sicherheitsdienst", "email": "sicherheit@simulation.schule-intern.example"},
    "schulleitung": {"name": "Schulleitung", "email": "verwaltung@simulation.schule-intern.example"},
}


def get_sender_profiles():
    """Return {category: {name, email}}. Falls back to built-in defaults."""
    if os.path.exists(SENDER_PROFILES_PATH):
        try:
            with open(SENDER_PROFILES_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if data:
                return data
        except (yaml.YAMLError, OSError):
            pass
    return DEFAULT_SENDER_PROFILES


def get_sender_for_template(template_name):
    """Derive the category from the template filename (part before the first '-')
    and return its sender profile, e.g. 'office-login' -> profiles['office'].
    Falls back to the globally configured sender_email/name if no profile matches.
    """
    category = template_name.split("-")[0]
    profiles = get_sender_profiles()
    profile = profiles.get(category)
    if profile:
        return category, profile
    settings = get_settings()
    return category, {"name": "Absender", "email": settings.get("sender_email", "")}


# --- Application settings ---------------------------------------------------
def get_settings():
    """Return the merged settings dict (defaults + persisted values)."""
    settings = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                settings.update(json.load(f) or {})
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(new_values: dict):
    """Merge ``new_values`` into the persisted settings and return the result."""
    settings = get_settings()
    for key, value in new_values.items():
        if key in DEFAULT_SETTINGS:
            settings[key] = value
    os.makedirs(DATENBANKEN_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    return settings


def get_setting(key, default=None):
    return get_settings().get(key, default)
