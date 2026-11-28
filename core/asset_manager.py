"""
Gerenciador de Ativos (Assets & Catálogo Pré-Analisado).
Escaneia mídias (imagens e vídeos), mantém catálogo em assets_catalog.json
para evitar reanálises caras na IA e gerencia remoção limpa de arquivos e thumbnails.
"""
from pathlib import Path
from typing import List, Dict, Any
import json


class AssetManager:
    def __init__(self, account_dir: Path):
        self.account_dir = account_dir
        self.assets_dir = account_dir / "assets"
        self.state_file = account_dir / "state.json"
        self.catalog_file = account_dir / "assets_catalog.json"
        self.supported_extensions = {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".m4v", ".avi"}

    def get_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {"used_assets": [], "pending_creatives": []}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"used_assets": [], "pending_creatives": []}

    def save_state(self, state: Dict[str, Any]) -> None:
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def load_catalog(self) -> Dict[str, Any]:
        if not self.catalog_file.exists():
            return {}
        try:
            with open(self.catalog_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_catalog(self, catalog: Dict[str, Any]) -> None:
        with open(self.catalog_file, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)

    def list_all_media(self) -> List[Path]:
        """Lista todos os arquivos de mídia existentes em assets/ ordenados por nome."""
        if not self.assets_dir.exists():
            return []
        files = [
            f for f in self.assets_dir.iterdir()
            if f.is_file() and f.suffix.lower() in self.supported_extensions
        ]
        return sorted(files, key=lambda p: p.name.lower())

    def scan_new_assets(self) -> List[Path]:
        """Localiza imagens e vídeos na pasta assets que ainda não foram publicados."""
        state = self.get_state()
        used = set(state.get("used_assets", []))
        return [f for f in self.list_all_media() if f.name not in used]

    def get_uncataloged_assets(self) -> List[Path]:
        """Retorna mídias em assets/ que ainda não possuem ficha no catálogo."""
        catalog = self.load_catalog()
        return [f for f in self.list_all_media() if not catalog.get(f.name)]

    def get_available_cataloged_entries(self) -> Dict[str, Any]:
        """Retorna fichas do catálogo para mídias que ainda existem em assets/ e não foram usadas."""
        catalog = self.load_catalog()
        available_names = {f.name for f in self.scan_new_assets()}
        return {
            name: entry for name, entry in catalog.items()
            if name in available_names and isinstance(entry, dict) and entry
        }

    def remove_asset(self, filename: str) -> None:
        """
        Remove o arquivo da pasta assets/, seu thumbnail em .thumbs/ (se houver)
        e sua ficha de assets_catalog.json. Propaga erros de I/O no arquivo principal.
        """
        target = self.assets_dir / filename
        if target.exists():
            target.unlink()

        thumb = self.assets_dir / ".thumbs" / f"{Path(filename).stem}_frame1.png"
        if thumb.exists():
            try:
                thumb.unlink()
            except OSError:
                pass

        catalog = self.load_catalog()
        if filename in catalog:
            catalog.pop(filename, None)
            self.save_catalog(catalog)
