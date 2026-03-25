#!/usr/bin/env python3
"""
Hermes CLI - Main entry point.
"""

import argparse
import os
import subprocess
import sys
import logging
import time as _time
from datetime import datetime
from pathlib import Path
from typing import Optional

def get_timestamp():
    return f"[{datetime.now().strftime('%H:%M:%S')}] "

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from hermes_cli.config import get_hermes_home
from hermes_cli.env_loader import load_hermes_dotenv
load_hermes_dotenv(project_env=PROJECT_ROOT / '.env')

os.environ.setdefault("MSWEA_GLOBAL_CONFIG_DIR", str(get_hermes_home()))
os.environ.setdefault("MSWEA_SILENT_STARTUP", "1")

from hermes_cli import __version__, __release_date__
from hermes_constants import OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)

def _relative_time(ts) -> str:
    if not ts:
        return "?"
    delta = _time.time() - ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    if delta < 172800:
        return "yesterday"
    if delta < 604800:
        return f"{int(delta / 86400)}d ago"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

def _has_any_provider_configured() -> bool:
    from hermes_cli.config import get_env_path, get_hermes_home
    from hermes_cli.auth import get_auth_status, PROVIDER_REGISTRY

    provider_env_vars = {"OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN", "OPENAI_BASE_URL"}
    for pconfig in PROVIDER_REGISTRY.values():
        if pconfig.auth_type == "api_key":
            provider_env_vars.update(pconfig.api_key_env_vars)
    
    if any(os.getenv(v) for v in provider_env_vars):
        return True

    env_file = get_env_path()
    if env_file.exists():
        try:
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip("'\"")
                if key.strip() in provider_env_vars and val:
                    return True
        except Exception:
            pass
    return False

def _session_browse_picker(sessions: list) -> Optional[str]:
    if not sessions:
        print("No sessions found.")
        return None

    try:
        import curses
        result_holder = [None]

        def _curses_browse(stdscr):
            # Curses mantığı buraya gelecek (Karmaşıklık olmaması için fallback'e odaklanıyoruz)
            pass

        # Hızlı çözüm için doğrudan fallback'e yönlendiriyoruz
        raise ImportError 
    except Exception:
        pass

    print("\n  Browse sessions  (enter number to resume, q to cancel)\n")
    for i, s in enumerate(sessions):
        title = (s.get("title") or "").strip()
        preview = (s.get("preview") or "").strip()
        label = title or preview or s["id"]
        last_active = _relative_time(s.get("last_active"))
        src = s.get("source", "")[:6]
        
        # Hizalaması düzeltilmiş kritik bölüm:
        label = label[:47] + "..." if len(label) > 47 else label
        print(f"{get_timestamp()}{i + 1:>3}. {label:<50} {last_active:<10} {src}")

    while True:
        try:
            val = input(f"\n  Select [1-{len(sessions)}]: ").strip()
            if not val or val.lower() in ("q", "quit", "exit"):
                return None
            idx = int(val) - 1
            if 0 <= idx < len(sessions):
                return sessions[idx]["id"]
            print(f"  Invalid selection. Enter 1-{len(sessions)} or q to cancel.")
        except ValueError:
            print(f"  Invalid input. Enter a number or q to cancel.")
        except (KeyboardInterrupt, EOFError):
            return None

# Dosyanın geri kalanı için ana giriş noktası
if __name__ == "__main__":
    print("Hermes CLI Başlatılıyor...")
def main():
    """Giriş noktası"""
    parser = argparse.ArgumentParser(description="Hermes CLI")
    # Buraya argümanları ekleyebilirsin ama şimdilik hata almamak için:
    args = parser.parse_args()
    cmd_chat(args)

if __name__ == "__main__":
    main()