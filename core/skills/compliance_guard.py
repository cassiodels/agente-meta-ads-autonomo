"""
Skill 2: ComplianceGuard (O Auditor de Políticas Globais da Meta).
Valida apenas políticas globais da Meta de forma determinística.
Regras específicas de cada negócio vêm do campo 'Observações / Regras Obrigatórias' da Persona.
"""
import re
from typing import Dict, Any


class ComplianceGuard:
    def __init__(self):
        self.prohibited_patterns = [
            (r"ganhe\s+dinheiro\s+f[áa]cil", "Promessa de ganho fácil proibida"),
            (r"renda\s+(extra\s+)?garantida", "Promessa de renda garantida proibida"),
            (r"resultado[s]?\s+(100%\s+)?garantido[s]?", "Afirmação de resultado garantido proibida"),
            (r"cura\s+(definitiva|milagrosa)", "Promessa de cura milagrosa proibida"),
            (r"fique\s+rico", "Promessa financeira irrealista proibida"),
        ]

    def validate_ad(self, text: str, headline: str, mandatory_notes: str = "") -> Dict[str, Any]:
        full_text = f"{headline} {text}"
        violations = []

        for pattern, reason in self.prohibited_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                violations.append(reason)

        if violations:
            return {
                "compliant": False,
                "reasons": violations,
            }

        return {
            "compliant": True,
            "reasons": ["Conforme com as políticas globais da Meta."],
        }
