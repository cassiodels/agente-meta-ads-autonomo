"""
Gerenciador de Ativos (Assets & Criativos).
Escaneia a pasta de criativos de cada cliente, identifica novos materiais
e armazena histórico de uso no state.json para não repetir materiais sem necessidade.
"""
from pathlib import Path
from typing import List, Dict, Any
import json

class AssetManager:
    def __init__(self, account_dir: Path):
        self.account_dir = account_dir
        self.assets_dir = account_dir / "assets"
        self.state_file = account_dir / "state.json"
        self.supported_extensions = {".png", ".jpg", ".jpeg", ".mp4", ".mov"}

    def get_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {"used_assets": [], "pending_creatives": []}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"used_assets": [], "pending_creatives": []}

    def save_state(self, state: Dict[str, Any]):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def scan_new_assets(self) -> List[Path]:
        """Localiza imagens e vídeos na pasta de criativos que ainda não foram publicados."""
        if not self.assets_dir.exists():
            return []

        state = self.get_state()
        used = set(state.get("used_assets", []))

        new_files = []
        for file in self.assets_dir.iterdir():
            if file.is_file() and file.suffix.lower() in self.supported_extensions:
                if file.name not in used:
                    new_files.append(file)

        return new_files
