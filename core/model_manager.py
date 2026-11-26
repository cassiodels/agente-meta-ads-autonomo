"""
Gerenciador de modelos de IA (Gemini).

- Lê a ordem de preferência em config/models.json.
- Consulta a API de modelos (com cache) e ignora os que não existem mais.
- Tenta novamente em caso de sobrecarga (503) e cai para o próximo modelo.
- Nunca falha em silêncio: se tudo falhar, levanta AIUnavailableError.
- Registra o uso (chamadas e tokens) por modelo em config/.usage.json.
"""
import json
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List

from google import genai

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "models.json"
CACHE_FILE = BASE_DIR / "config" / ".models_cache.json"
USAGE_FILE = BASE_DIR / "config" / ".usage.json"


class AIUnavailableError(Exception):
    """Nenhum modelo conseguiu responder."""


def _read(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class ModelManager:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key) if api_key else None
        self.cfg = _read(CONFIG_FILE, {})
        self.warnings: List[str] = []

    # ---------------------------------------------------------- descoberta
    def available_models(self, force_refresh: bool = False) -> List[str]:
        hours = float(self.cfg.get("model_list_cache_hours", 24))
        cache = _read(CACHE_FILE, {})
        fresh = cache.get("fetched_at") and (
            (datetime.now() - datetime.fromisoformat(cache["fetched_at"])).total_seconds() < hours * 3600)
        if fresh and not force_refresh:
            return cache.get("models", [])
        try:
            names = []
            for m in self.client.models.list():
                if "generateContent" in (getattr(m, "supported_actions", None) or []):
                    names.append(m.name.replace("models/", ""))
            _write(CACHE_FILE, {"fetched_at": datetime.now().isoformat(), "models": names})
            return names
        except Exception:
            return cache.get("models", [])  # usa cache antigo se a listagem falhar

    def chain(self, force_refresh: bool = False) -> List[str]:
        wanted = list(self.cfg.get("preferred", [])) + list(self.cfg.get("fallback", []))
        available = self.available_models(force_refresh)
        if not available:  # não conseguiu listar: tenta a cadeia configurada mesmo assim
            return wanted
        self.warnings = [f"Modelo '{m}' não está mais disponível na API." for m in wanted if m not in available]
        return [m for m in wanted if m in available]

    # ---------------------------------------------------------- uso
    def _log_usage(self, model: str, resp) -> None:
        usage = _read(USAGE_FILE, {})
        today = date.today().isoformat()
        day = usage.setdefault(today, {}).setdefault(model, {"calls": 0, "tokens": 0})
        day["calls"] += 1
        meta = getattr(resp, "usage_metadata", None)
        day["tokens"] += int(getattr(meta, "total_token_count", 0) or 0)
        _write(USAGE_FILE, usage)

    # ---------------------------------------------------------- geração
    def generate_json(self, contents: Any) -> Dict[str, Any]:
        if not self.client:
            raise AIUnavailableError("GEMINI_API_KEY não configurada.")
        delays = self.cfg.get("retry_delays_seconds", [2, 5])
        config = {"response_mime_type": "application/json",
                  "max_output_tokens": int(self.cfg.get("max_output_tokens", 1500))}
        errors = []
        for model in self.chain():
            for attempt in range(len(delays) + 1):
                try:
                    resp = self.client.models.generate_content(model=model, contents=contents, config=config)
                    data = json.loads(resp.text)
                    if isinstance(data, list) and data and isinstance(data[0], dict):
                        data = data[0]
                    if not isinstance(data, dict):
                        raise ValueError("Resposta JSON não é um objeto.")
                    self._log_usage(model, resp)
                    return data
                except Exception as e:
                    msg = str(e)
                    errors.append(f"{model}: {msg[:80]}")
                    if "404" in msg or "NOT_FOUND" in msg:
                        break  # modelo inexistente: vai para o próximo
                    if attempt < len(delays):
                        time.sleep(delays[attempt])
        raise AIUnavailableError("; ".join(errors[-3:]) or "sem modelos disponíveis")
