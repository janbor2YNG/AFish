import yaml
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Ordner dieser Datei
UPLOAD_FOLDER = os.path.join(BASE_DIR, '..', 'Datenbanken')
ACTIVE_CONFIG_FILE = os.path.join(BASE_DIR, 'active_config.txt')

def set_active_config(filename):
    with open(ACTIVE_CONFIG_FILE, 'w') as f:
        f.write(filename)

def get_active_config_name():
    if os.path.exists(ACTIVE_CONFIG_FILE):
        with open(ACTIVE_CONFIG_FILE) as f:
            return f.read().strip()
    return 'default.yaml'

def get_config():
    filename = get_active_config_name()
    return filename
