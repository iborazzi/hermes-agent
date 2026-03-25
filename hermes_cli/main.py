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

from hermes_cli.config import get_hermes_home
from hermes_cli.env_loader import load_hermes_dotenv
load_hermes_dotenv(project_env=PROJECT_ROOT / '.env')

os.environ.setdefault("MSWEA_GLOBAL_CONFIG_DIR", str(get_hermes_home()))
os.environ.setdefault("MSWEA_SILENT_STARTUP", "1")

# Versiyon bilgilerini çek (Eğer hata verirse manuel string yazılabilir)
try:
    from hermes_cli import __version__, __release_date__
except ImportError:
    __version__ = "0.4.0"
    __release_date__ = "2026-03-25"

logger = logging.getLogger(__name__)

def get_timestamp():
    return f"[{datetime.now().strftime('%H:%M:%S')}] "

def _relative_time(ts) -> str:
    if not ts: return "?"
    delta = _time.time() - ts
    if delta < 60: return "just now"
    if delta < 3600: return f"{int(delta / 60)}m ago"
    if delta < 86400: return f"{int(delta / 3600)}h ago"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

def _session_browse_picker(sessions: list) -> Optional[str]:
    if not sessions:
        print("No sessions found.")
        return None

    print("\n  Browse sessions (enter number to resume, q to cancel)\n")
    for i, s in enumerate(sessions):
        title = (s.get("title") or "").strip()
        preview = (s.get("preview") or "").strip()
        label = title or preview or s["id"]
        last_active = _relative_time(s.get("last_active"))
        src = (s.get("source") or "")[:6]
        
        # Hizalaması düzeltilmiş kritik bölüm
        label_display = (label[:47] + "...") if len(label) > 47 else label
        print(f"{get_timestamp()}{i + 1:>3}. {label_display:<50} {last_active:<10} {src}")

    while True:
        try:
            val = input(f"\n  Select [1-{len(sessions)}]: ").strip()
            if not val or val.lower() in ("q", "quit", "exit"):
                return None
            idx = int(val) - 1
            if 0 <= idx < len(sessions):
                return sessions[idx]["id"]
            print(f"  Invalid selection. Enter 1-{len(sessions)} or q to cancel.")
        except (ValueError, KeyboardInterrupt, EOFError):
            return None

def main():
    """Hermes CLI Ana Giriş Fonksiyonu"""
    parser = argparse.ArgumentParser(
        description="Hermes CLI - AI Assistant for Web3 & Automation",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # Temel argümanlar
    parser.add_argument("-v", "--version", action="version", 
                        version=f"Hermes CLI {__version__} ({__release_date__})")
    
    # Cron ve Sohbet ayarları için eklenecek flag'ler buraya gelecek
    parser.add_argument("--chat", action="store_true", help="Start an interactive chat session")
    parser.add_argument("--cron-toggle", action="store_true", help="Toggle conversational responses for cron tasks")

    args = parser.parse_args()

    # Eğer hiçbir şey girilmezse yardım göster
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.chat:
        print(f"{get_timestamp()} Chat session starting...")
        # Buraya chat başlatma fonksiyonunu çağırabilirsin
    
    if args.cron_toggle:
        print(f"{get_timestamp()} Cron conversational toggle updated.")

if __name__ == "__main__":
    main()
# ... (argparse kısımları aynı kalıyor)
    
    args = parser.parse_args()

    if args.cron_toggle:
        from hermes_cli.config import get_env_path
        env_path = get_env_path()
        
        # Mevcut ayarı oku ve tersine çevir (Toggle mantığı)
        current_val = os.getenv("HERMES_CRON_CONVERSATIONAL", "false").lower() == "true"
        new_val = not current_val
        
        # .env dosyasını güncelleme fonksiyonu (basit sürüm)
        try:
            with open(env_path, "r") as f:
                lines = f.readlines()
            
            with open(env_path, "w") as f:
                found = False
                for line in lines:
                    if line.startswith("HERMES_CRON_CONVERSATIONAL="):
                        f.write(f"HERMES_CRON_CONVERSATIONAL={'true' if new_val else 'false'}\n")
                        found = True
                    else:
                        f.write(line)
                if not found:
                    f.write(f"HERMES_CRON_CONVERSATIONAL={'true' if new_val else 'false'}\n")
            
            status = "ENABLED (Konuşkan)" if new_val else "DISABLED (Sessiz)"
            print(f"{get_timestamp()} Cron responses are now {status}")
            
        except Exception as e:
            print(f"{get_timestamp()} Error updating config: {e}")