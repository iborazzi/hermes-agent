#!/usr/bin/env python3
"""
Hermes CLI - Main entry point.
"""

import argparse
import os
import sys
import logging
import time as _time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Proje kök dizinini yola ekle
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from hermes_cli.config import get_hermes_home, get_env_path
from hermes_cli.env_loader import load_hermes_dotenv

# Yapılandırma dizinlerini ayarla
os.environ.setdefault("MSWEA_GLOBAL_CONFIG_DIR", str(get_hermes_home()))
os.environ.setdefault("MSWEA_SILENT_STARTUP", "1")

# .env yükle
load_hermes_dotenv(project_env=PROJECT_ROOT / '.env')

# Versiyon bilgileri
try:
    from hermes_cli import __version__, __release_date__
except ImportError:
    __version__ = "0.4.0"
    __release_date__ = "2026-03-25"

logger = logging.getLogger(__name__)

def get_timestamp():
    return f"[{datetime.now().strftime('%H:%M:%S')}] "

def main():
    """Hermes CLI Ana Giriş Fonksiyonu"""
    parser = argparse.ArgumentParser(
        description="Hermes CLI - AI Assistant for Web3 & Automation",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument("-v", "--version", action="version", 
                        version=f"Hermes CLI {__version__} ({__release_date__})")
    
    parser.add_argument("--chat", action="store_true", help="Start an interactive chat session")
    parser.add_argument("--cron-toggle", action="store_true", help="Toggle conversational responses for cron tasks")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.chat:
        print(f"{get_timestamp()} Chat session starting...")
        # Buraya chat modülü import edilip çağrılabilir.
    
    if args.cron_toggle:
        env_path = Path(get_env_path())
        
        # Klasör ve dosya güvenliği
        env_path.parent.mkdir(parents=True, exist_ok=True)
        if not env_path.exists():
            env_path.touch()

        # Dosyayı oku ve temizle (Boş satırları ve boşlukları atla)
        content = env_path.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        
        # Mevcut ayarı kontrol et (True mu?)
        is_currently_true = any(line == "HERMES_CRON_CONVERSATIONAL=true" for line in lines)
        new_val = not is_currently_true
        
        # Eskileri temizle ve yenisini ekle (Duplication engelleme)
        new_lines = [line for line in lines if not line.startswith("HERMES_CRON_CONVERSATIONAL=")]
        new_lines.append(f"HERMES_CRON_CONVERSATIONAL={'true' if new_val else 'false'}")

        # Dosyaya tertemiz yaz
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        
        status = "ENABLED (Konuşkan)" if new_val else "DISABLED (Sessiz)"
        print(f"{get_timestamp()} Cron responses are now {status}")
        print(f"{get_timestamp()} Config updated at: {env_path}")

if __name__ == "__main__":
    main()