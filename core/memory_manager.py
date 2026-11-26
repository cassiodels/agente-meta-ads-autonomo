"""
Gerenciador de Memória Rankeada por Importância.
Mantém os aprendizados e feedbacks organizados por nota (1 a 10),
garantindo que lições antigas valiosas nunca sejam descartadas por feedbacks recentes
e mantendo o prompt enxuto (Top 10).
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class MemoryManager:
    TOP_LIMIT = 10

    def __init__(self, memory_path: Path):
        self.memory_path = memory_path

    def load(self) -> Dict[str, Any]:
        if not self.memory_path.exists():
            return {"insights_rankeados": [], "angulos_testados": {}, "historico_feedbacks": []}
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {"insights_rankeados": [], "angulos_testados": {}, "historico_feedbacks": []}

        # Migração suave do formato antigo (insights_aprendidos -> insights_rankeados)
        if "insights_rankeados" not in data:
            legacy = data.get("insights_aprendidos", [])
            data["insights_rankeados"] = [
                {"text": item, "score": 8, "category": "legado", "created_at": data.get("created_at", "")}
                for item in legacy
            ]
        return data

    def save(self, data: Dict[str, Any]) -> None:
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add_learning(self, text: str, score: int = 7, category: str = "feedback") -> None:
        """Adiciona um aprendizado/feedback com nota de importância (1 a 10)."""
        score = max(1, min(10, int(score)))
        data = self.load()
        items = data.setdefault("insights_rankeados", [])

        # Evita duplicatas exatas, atualizando a nota se já existir
        for item in items:
            if item.get("text", "").strip().lower() == text.strip().lower():
                item["score"] = max(item.get("score", 5), score)
                item["updated_at"] = datetime.now().isoformat()
                self.save(data)
                return

        items.append({
            "text": text.strip(),
            "score": score,
            "category": category,
            "created_at": datetime.now().isoformat(),
        })
        if category == "feedback":
            data.setdefault("historico_feedbacks", []).append({
                "data": datetime.now().isoformat(),
                "feedback": text.strip(),
                "score": score,
            })
        self.save(data)

    def get_top_insights(self, limit: int = TOP_LIMIT) -> List[str]:
        """Retorna apenas os N aprendizados mais importantes (ordenados por score desc)."""
        data = self.load()
        items = data.get("insights_rankeados", [])
        ranked = sorted(items, key=lambda x: (x.get("score", 5), x.get("created_at", "")), reverse=True)
        return [f"[Nota {i.get('score', 5)}/10] {i.get('text', '')}" for i in ranked[:limit]]
