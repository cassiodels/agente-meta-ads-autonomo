"""
Utilitário de Vídeo para o MVP.
Extrai obrigatoriamente o 1º frame (usado como capa oficial na Meta e preview no Telegram)
mais até 2 frames ao longo do vídeo para análise multimodal econômica no Gemini.
"""
from pathlib import Path
from typing import List, Tuple
from PIL import Image

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi"}


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def extract_video_frames(video_path: Path, max_px: int = 768) -> Tuple[Path, List[Image.Image]]:
    """
    Retorna (caminho_do_primeiro_frame_png, [frame_1, frame_meio, frame_fim]).
    O 1º frame é salvo em alta resolução como PNG de capa para Meta Ads e Telegram.
    Os frames retornados na lista já vêm redimensionados (<= max_px) para economizar tokens.
    """
    import cv2  # opencv-python-headless

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Não foi possível abrir o vídeo: {video_path.name}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    # Sempre 1º frame (índice 0) + 2 pontos ao longo do vídeo (45% e 80%)
    if total_frames >= 10:
        indices = [0, int(total_frames * 0.45), int(total_frames * 0.80)]
    elif total_frames >= 3:
        indices = [0, total_frames // 2, total_frames - 1]
    else:
        indices = [0]

    extracted_full: List[Image.Image] = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if ok and frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            extracted_full.append(Image.fromarray(rgb))
    cap.release()

    if not extracted_full:
        raise RuntimeError(f"Nenhum frame pôde ser extraído do vídeo: {video_path.name}")

    # Salvar o 1º frame como capa oficial (PNG)
    thumbs_dir = video_path.parent / ".thumbs"
    thumbs_dir.mkdir(exist_ok=True)
    thumb_path = thumbs_dir / f"{video_path.stem}_frame1.png"
    extracted_full[0].save(thumb_path, format="PNG")

    # Versões redimensionadas em memória para análise econômica no Gemini
    vision_frames: List[Image.Image] = []
    for img in extracted_full:
        copy_img = img.copy()
        if max(copy_img.size) > max_px:
            copy_img.thumbnail((max_px, max_px))
        vision_frames.append(copy_img)

    return thumb_path, vision_frames
