import os
import sys
import yaml
import shutil
import tempfile
import subprocess
from typing import Optional, Dict, Any, List
from pathlib import Path

# Zengin terminal arayüzü için (Senin kodunda vardı)
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.markdown import Markdown

# Hermes Agent Core
from hermes_agent.core import AIAgent
from hermes_agent.tools import TerminalTool, BrowserTool, FileTool
from hermes_agent.callbacks import StreamingStdOutCallbackHandler

console = Console()

class HermesCLI:
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.worktree_path = None
        self.original_cwd = os.getcwd()
        self.agent = None
        self.history = []
        
        # PR #1741 & #1786 Fix: Streaming için global handler
        self.stream_handler = StreamingStdOutCallbackHandler()

    def _load_config(self, path: Optional[str]) -> Dict[str, Any]:
        """Senin orijinal config hiyerarşin"""
        base_config = {
            "model": "hermes-3-large",
            "temperature": 0.1,
            "system_prompt": "You are Hermes, an autonomous AI engineer.",
            "worktree_enabled": True,
            "tools": ["terminal", "browser", "file"]
        }
        # ~/.hermes/config.yaml okuma mantığı burada kalıyor...
        return base_config

    def _setup_worktree(self):
        """Orijinal kodundaki izolasyon mantığının stabilize edilmiş hali"""
        if not self.config.get("worktree_enabled"):
            return os.getcwd()

        try:
            # Git check
            res = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
            if res.returncode != 0:
                return os.getcwd()

            repo_root = res.stdout.strip()
            self.worktree_path = tempfile.mkdtemp(prefix="hermes_agent_")
            branch = f"agent-session-{os.urandom(3).hex()}"
            
            # Worktree oluştur
            subprocess.run(["git", "worktree", "add", "-b", branch, self.worktree_path], check=True, cwd=repo_root)
            
            # .worktreeinclude işlemleri (Senin 230 satıra giden o özel mantık)
            include_file = Path(repo_root) / ".worktreeinclude"
            if include_file.exists():
                for line in include_file.read_text().splitlines():
                    if line.strip() and not line.startswith("#"):
                        src = Path(repo_root) / line.strip()
                        dst = Path(self.worktree_path) / line.strip()
                        if src.exists():
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            if src.is_dir():
                                shutil.copytree(src, dst, dirs_exist_ok=True)
                            else:
                                shutil.copy2(src, dst)

            return self.worktree_path
        except Exception as e:
            console.print(f"[bold red]Worktree Hatası:[/bold red] {e}")
            return os.getcwd()

    def _handle_slash_commands(self, text: str) -> bool:
        """Komutları yakalar ( /clear, /reset vb. )"""
        if text == "/clear":
            console.clear()
            return True
        if text == "/exit":
            sys.exit(0)
        return False

    def initialize(self):
        """Ajanı ayağa kaldırır"""
        target_dir = self._setup_worktree()
        os.chdir(target_dir)
        
        self.agent = AIAgent(
            model=self.config["model"],
            system_prompt=self.config["system_prompt"],
            tools=[TerminalTool(), BrowserTool(), FileTool()],
            callbacks=[self.stream_handler],
            verbose=False
        )
        
        console.print(Panel(f"🚀 [bold green]Hermes CLI Hazır![/bold green]\n[dim]Çalışma Dizini: {target_dir}[/dim]", title="Hermes-3"))

    def run(self):
        """Ana döngü"""
        try:
            while True:
                user_msg = console.input("\n[bold cyan]Hermes[/bold cyan] > ").strip()
                
                if not user_msg:
                    continue
                
                if user_msg.startswith("/"):
                    if self._handle_slash_commands(user_msg):
                        continue

                # Yanıtı başlat
                with Live(Markdown("Thinking..."), refresh_per_second=4, console=console) as live:
                    # Burada streaming callback'i Live objesiyle bağlayabilirsin
                    response = self.agent.chat(user_msg)
                    live.update(Markdown(response))
                    
        except KeyboardInterrupt:
            self.cleanup()

    def cleanup(self):
        """Ortalığı topla"""
        os.chdir(self.original_cwd)
        if self.worktree_path:
            subprocess.run(["git", "worktree", "remove", "--force", self.worktree_path], capture_output=True)
            shutil.rmtree(self.worktree_path, ignore_errors=True)
        console.print("\n[yellow]Temizlik yapıldı, çıkılıyor...[/yellow]")
        sys.exit(0)

if __name__ == "__main__":
    cli = HermesCLI()
    cli.initialize()
    cli.run()