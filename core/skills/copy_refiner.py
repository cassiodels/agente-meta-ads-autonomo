"""
Skill 3: CopyRefiner (O Redator com Visão Multimodal, Suporte a Vídeo, Persona Optimizer e Loop de Feedback).
Gera e refina copys utilizando a memória rankeada e permite ao usuário sugerir edições via Telegram.
"""
from pathlib import Path
from typing import Any, Dict, List, Tuple
from PIL import Image

from core.model_manager import ModelManager, AIUnavailableError  # noqa: F401
from core.video_utils import is_video_file, extract_video_frames


class CopyRefiner:
    def __init__(self, persona_text: str, memory_data: Dict[str, Any], api_key: str):
        self.persona_text = persona_text
        self.memory_data = memory_data
        self.models = ModelManager(api_key)

    def _generate_json(self, contents) -> Dict[str, Any]:
        """Delega ao ModelManager (modelo preferido, retries e fallback)."""
        return self.models.generate_json(contents)

    def _prepare_image_for_vision(self, image_path: Path, max_px: int = 768) -> Image.Image:
        """Redimensiona cópia em memória para economizar tokens de visão sem alterar o arquivo original."""
        img = Image.open(image_path)
        if max(img.size) > max_px:
            img = img.copy()
            img.thumbnail((max_px, max_px))
        return img

    def create_proposal_from_media(
        self,
        media_path: Path,
        top_insights: List[str] = None,
        mandatory_notes: str = "",
        default_cta: str = "APPLY_NOW",
    ) -> Dict[str, Any]:
        """Analisa imagem ou vídeo (1º frame + até 2 frames) e gera proposta de anúncio."""
        winners = self.memory_data.get("angulos_testados", {})
        if top_insights is None:
            ranked = sorted(
                self.memory_data.get("insights_rankeados", []),
                key=lambda x: x.get("score", 5),
                reverse=True,
            )[:10]
            top_insights = [i.get("text", "") for i in ranked] or self.memory_data.get("insights_aprendidos", [])[:10]
        insights = "\n".join(top_insights)

        is_video = is_video_file(media_path)
        if is_video:
            thumb_path, vision_media = extract_video_frames(media_path)
            media_hint = (
                "MÍDIA: VÍDEO. As imagens anexadas são frames extraídos do vídeo: "
                "a 1ª imagem é obrigatoriamente o 1º frame (capa escolhida pelo usuário) "
                "e as seguintes mostram a evolução do vídeo."
            )
        else:
            thumb_path = None
            vision_media = [self._prepare_image_for_vision(media_path)]
            media_hint = "MÍDIA: IMAGEM ESTÁTICA anexada."

        notes_block = f"\nOBSERVAÇÕES E REGRAS OBRIGATÓRIAS DO NEGÓCIO:\n{mandatory_notes}\n" if mandatory_notes else ""

        prompt = f"""
Você é um estrategista sênior de Meta Ads e Copywriter.
Analise a mídia anexada e gere uma proposta de anúncio em JSON seguindo rigorosamente a persona da marca.

{media_hint}

DIRETRIZES DA MARCA (PERSONA):
{self.persona_text}
{notes_block}
MEMÓRIA DE APRENDIZADO DA CONTA (TOP 10 POR IMPORTÂNCIA):
{insights}
Ângulos com histórico de sucesso: {winners}

REGRAS:
1. Siga exatamente o tom de voz, público-alvo e diferenciais descritos na Persona da marca.
2. Cumpra todas as observações/regras obrigatórias da marca e todas as políticas da Meta (sem promessas garantidas ou enganosas).
3. Responda em formato JSON estrito:
{{
  "visual_analysis": "O que você viu na mídia (imagem ou sequência de frames do vídeo)",
  "angle": "Ângulo persuasivo escolhido",
  "headline": "Título curto de alto impacto",
  "primary_text": "Texto principal completo do anúncio respeitando a persona e observações obrigatórias",
  "call_to_action": "{default_cta}",
  "compliance_status": "CONFORME"
}}
"""
        result = self._generate_json([*vision_media, prompt])
        result["media_type"] = "video" if is_video else "image"
        if thumb_path:
            result["preview_image_path"] = str(thumb_path)
        return result

    def create_proposal_from_image(self, image_path: Path, top_insights: List[str] = None) -> Dict[str, Any]:
        """Alias compatível com chamadas legadas."""
        return self.create_proposal_from_media(image_path, top_insights=top_insights)

    def refine_with_feedback(self, current_copy: Dict[str, Any], user_feedback: str) -> Dict[str, Any]:
        """Ajusta a copy com base no feedback e atribui nota de importância (1-10) ao aprendizado."""
        prompt = f"""
O usuário solicitou um ajuste na seguinte copy de anúncio:
TÍTULO ATUAL: {current_copy.get('headline')}
TEXTO ATUAL: {current_copy.get('primary_text')}

DIRETRIZES E REGRAS DA MARCA (PERSONA):
{self.persona_text}

FEEDBACK DO USUÁRIO: "{user_feedback}"

Reescreva a copy atendendo estritamente ao feedback do usuário e mantendo todas as diretrizes e regras obrigatórias da persona da marca.
Avalie também de 1 a 10 a importância desse feedback como aprendizado duradouro para futuros anúncios desta conta.
Responda em formato JSON:
{{
  "headline": "Novo título ajustado",
  "primary_text": "Novo texto ajustado respeitando a persona",
  "call_to_action": "{current_copy.get('call_to_action', 'APPLY_NOW')}",
  "notes": "Explicação do que foi ajustado com base no feedback",
  "importance_score": 7,
  "learning_summary": "Resumo curto da regra/preferência aprendida com este feedback"
}}
"""
        data = self._generate_json(prompt)
        current_copy["headline"] = data.get("headline", current_copy["headline"])
        current_copy["primary_text"] = data.get("primary_text", current_copy["primary_text"])
        current_copy["refined_note"] = data.get("notes", "Ajustado com sucesso.")
        current_copy["importance_score"] = int(data.get("importance_score", 7))
        current_copy["learning_summary"] = data.get("learning_summary", user_feedback)
        return current_copy

    def optimize_persona(self, form_data: Dict[str, Any]) -> Tuple[str, bool]:
        """
        Estrutura os campos preenchidos pelo usuário no painel em um persona.md otimizado.
        Retorna (markdown_gerado, used_ai). Nunca sobrescreve arquivos sozinho.
        """
        prompt = f"""
Você é um especialista em posicionamento de marca e tráfego pago Meta Ads.
Com base EXCLUSIVAMENTE nas respostas preenchidas abaixo pelo usuário (não invente fatos novos),
estruture um documento claro e objetivo de Persona em Markdown para guiar um agente de anúncios.
Preserve integralmente todas as observações e regras obrigatórias informadas.

RESPOSTAS DO USUÁRIO:
- Empresa / Nicho: {form_data.get('niche', '')}
- Diferencial / Motivo para clicar agora: {form_data.get('differential', '')}
- Objetivo das campanhas: {form_data.get('objective', '')}
- Público-alvo: {form_data.get('audience', '')}
- Região de atendimento: {form_data.get('region', '')}
- Principais dores / objeções: {form_data.get('pains', '')}
- Tom de voz e referências: {form_data.get('tone', '')}
- Observações e Regras Obrigatórias: {form_data.get('mandatory_notes', '')}
- Link de destino: {form_data.get('destination_url', '')}
- CTA preferido: {form_data.get('default_cta', '')}

Responda em JSON: {{"persona_markdown": "# Persona e Diretrizes da Marca..."}}
"""
        try:
            res = self._generate_json(prompt)
            md = (res.get("persona_markdown") or "").strip()
            if md:
                return md, True
        except AIUnavailableError:
            pass

        # Fallback determinístico em Python caso a IA esteja indisponível
        fallback_md = (
            f"# 🎯 Persona e Diretrizes da Marca — {form_data.get('account_name', 'Cliente')}\n\n"
            f"## 1. Sobre o Negócio\n"
            f"- **O que faz / Nicho:** {form_data.get('niche', '')}\n"
            f"- **Diferencial (Por que clicar agora):** {form_data.get('differential', '')}\n"
            f"- **Objetivo das Campanhas:** {form_data.get('objective', '')}\n"
            f"- **CTA Preferido:** {form_data.get('default_cta', 'APPLY_NOW')}\n"
            f"- **Link de Destino:** {form_data.get('destination_url', 'Não aplicável (Formulário nativo)')}\n\n"
            f"## 2. Público-Alvo e Região\n"
            f"- **Público:** {form_data.get('audience', '')}\n"
            f"- **Região de Atendimento:** {form_data.get('region', '')}\n"
            f"- **Principais Dores e Objeções:** {form_data.get('pains', '')}\n\n"
            f"## 3. Tom de Voz\n"
            f"- **Estilo e Referências:** {form_data.get('tone', '')}\n\n"
            f"## 4. Observações e Regras Obrigatórias do Negócio\n"
            f"{form_data.get('mandatory_notes', 'Seguir as políticas de publicidade da Meta.')}\n"
        )
        return fallback_md, False
