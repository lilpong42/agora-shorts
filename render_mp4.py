#!/usr/bin/env python3
"""
render_mp4.py
Agora-Shorts 실제 9:16 세로형 MP4 영상(720x1280, H.264 + AAC, 40초 6턴) 고퀄리티 렌더링 엔진.
- 2인 웹툰·모션그래픽 캐릭터(pro_avatar.png / con_avatar.png) 마주보기 배치
- 화자 줌인·발화 바운스·비화자 디밍 + 방향성 말풍선(Speech Bubble Tail) 팝업 애니메이션
- ffmpeg libx264 (yuv420p, faststart)로 유튜브 쇼츠/릴스 즉시 업로드 가능한 MP4 생성
"""

import base64
import html
import math
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageEnhance
from presets_data import PRESETS

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "static" / "assets"
VIDEOS_DIR = BASE_DIR / "static" / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

PRO_AVATAR_PATH = ASSETS_DIR / "pro_avatar.png"
CON_AVATAR_PATH = ASSETS_DIR / "con_avatar.png"


def _wrap_korean_text(text: str, max_chars: int = 26, max_lines: int = 6) -> List[str]:
    """한글 문장을 말풍선 폭에 맞춰 자연스럽게 줄바꿈."""
    words = text.split()
    lines: List[str] = []
    current = ""
    for w in words:
        if not current:
            current = w
        elif len(current) + 1 + len(w) <= max_chars:
            current += " " + w
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines[:max_lines]


def create_turn_frame_png(
    issue_title: str,
    category_badge: str,
    raw_stats: Dict[str, Any],
    turn_idx: int,
    total_turns: int,
    turn_data: Dict[str, Any],
    phase: int,
    out_png: Path,
) -> None:
    """
    9:16 (720x1280) 웹툰 말풍선 + 2인 캐릭터 대립 프레임을 렌더링.
    phase (0, 1, 2)에 따라 화자 바운스, 오디오 이퀄라이저, 말풍선 팝업이 동적으로 변화.
    """
    W, H = 720, 1280
    is_pro = turn_data["speaker"] == "PRO"
    progress_pct = ((turn_idx + (phase + 1) / 3.0) / total_turns) * 100.0
    remaining_sec = max(0.0, 40.0 - (progress_pct / 100.0) * 40.0)

    title_lines = _wrap_korean_text(issue_title, max_chars=22, max_lines=2)
    title_svg = "".join(
        f'<text x="360" y="{152 + i * 32}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="24" font-weight="800" fill="#F8FAFC">{html.escape(line)}</text>'
        for i, line in enumerate(title_lines)
    )

    caption_lines = _wrap_korean_text(turn_data["text"], max_chars=26, max_lines=6)
    caption_svg = "".join(
        f'<text x="76" y="{380 + i * 32}" font-family="Noto Sans CJK KR, sans-serif" font-size="21.5" font-weight="600" fill="#0F172A">{html.escape(line)}</text>'
        for i, line in enumerate(caption_lines)
    )

    bubble_border = "#3B82F6" if is_pro else "#F43F5E"
    badge_bg = "#2563EB" if is_pro else "#E11D48"
    core_color = "#1D4ED8" if is_pro else "#BE123C"
    speaker_label = f"찬성 #{turn_idx // 2 + 1}" if is_pro else f"반대 #{turn_idx // 2 + 1}"

    # Speech bubble tail pointing down-left toward PRO (x=190) or down-right toward CON (x=530)
    if is_pro:
        tail_svg = f"""
        <polygon points="165,576 225,576 178,632" fill="#F8FAFC"/>
        <polyline points="165,577 178,632 225,577" fill="none" stroke="{bubble_border}" stroke-width="5" stroke-linejoin="round"/>
        <line x1="167" y1="576" x2="223" y2="576" stroke="#F8FAFC" stroke-width="8"/>
        """
    else:
        tail_svg = f"""
        <polygon points="495,576 555,576 542,632" fill="#F8FAFC"/>
        <polyline points="495,577 542,632 555,577" fill="none" stroke="{bubble_border}" stroke-width="5" stroke-linejoin="round"/>
        <line x1="497" y1="576" x2="553" y2="576" stroke="#F8FAFC" stroke-width="8"/>
        """

    # Animated equalizer bars near active speaker
    eq_heights = [
        [22, 42, 28, 48, 24],
        [38, 24, 46, 26, 36],
        [26, 46, 32, 40, 30],
    ][phase % 3]
    eq_x = 52 if is_pro else 606
    eq_color = "#60A5FA" if is_pro else "#FB7185"
    eq_svg = "".join(
        f'<rect x="{eq_x + i * 13}" y="{675 - h // 2}" width="7" height="{h}" rx="3.5" fill="{eq_color}"/>'
        for i, h in enumerate(eq_heights)
    )

    # Spotlight glow behind active speaker
    spot_cx = 195 if is_pro else 525
    spot_color = "#2563EB" if is_pro else "#E11D48"

    # Layer 1: Background + Top Title + Speech Bubble SVG -> PNG
    bg_svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#070A12"/>
      <stop offset="55%" stop-color="#0C1324"/>
      <stop offset="100%" stop-color="#06080E"/>
    </linearGradient>
    <radialGradient id="spot" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{spot_color}" stop-opacity="0.48"/>
      <stop offset="100%" stop-color="{spot_color}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="prog" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#3B82F6"/>
      <stop offset="100%" stop-color="#F43F5E"/>
    </linearGradient>
  </defs>

  <rect x="0" y="0" width="{W}" height="{H}" fill="url(#bg)"/>
  <circle cx="{spot_cx}" cy="870" r="290" fill="url(#spot)"/>

  <!-- Top Progress & Status -->
  <rect x="40" y="34" width="640" height="10" rx="5" fill="#1E293B"/>
  <rect x="40" y="34" width="{max(12.0, 6.40 * progress_pct):.1f}" height="10" rx="5" fill="url(#prog)"/>

  <rect x="40" y="60" width="92" height="32" rx="8" fill="#1E293B"/>
  <text x="86" y="82" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="16" font-weight="800" fill="#FFFFFF">SHORTS</text>
  <text x="148" y="82" font-family="Noto Sans CJK KR, sans-serif" font-size="18" font-weight="700" fill="#94A3B8">TURN {turn_idx + 1}/{total_turns}</text>
  <text x="680" y="82" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="18" font-weight="700" fill="#E2E8F0">{remaining_sec:.1f}s</text>

  <!-- Issue Headline -->
  <rect x="40" y="108" width="640" height="104" rx="18" fill="#111827" fill-opacity="0.85" stroke="#1F2937" stroke-width="1.5"/>
  {title_svg}

  <!-- Comic / Broadcast Speech Bubble -->
  <rect x="40" y="232" width="640" height="346" rx="28" fill="#F8FAFC" stroke="{bubble_border}" stroke-width="5"/>
  {tail_svg}

  <!-- Speech Bubble Header -->
  <rect x="74" y="256" width="124" height="34" rx="10" fill="{badge_bg}"/>
  <text x="136" y="279" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="17" font-weight="800" fill="#FFFFFF">{html.escape(speaker_label)}</text>
  <text x="646" y="279" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="700" fill="#64748B">실측 {raw_stats['total_comments']}개 댓글 핵심 요약</text>

  <!-- Core Argument Headline inside Bubble -->
  <text x="76" y="330" font-family="Noto Sans CJK KR, sans-serif" font-size="24" font-weight="800" fill="{core_color}">
    {html.escape(turn_data['core_point'][:26])}
  </text>
  <line x1="76" y1="348" x2="644" y2="348" stroke="#E2E8F0" stroke-width="2"/>

  {caption_svg}

  <!-- Active Voice Equalizer -->
  {eq_svg}
</svg>
"""
    svg_path = out_png.with_suffix(".svg")
    svg_path.write_text(bg_svg, encoding="utf-8")
    subprocess.run(
        ["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(out_png), str(svg_path)],
        check=True,
    )
    svg_path.unlink(missing_ok=True)

    # Layer 2: Composite Webtoon Characters onto Frame with Speaking Zoom, Bob & Listening Dim
    canvas = Image.open(out_png).convert("RGBA")
    pro_img = Image.open(PRO_AVATAR_PATH).convert("RGBA")
    con_img = Image.open(CON_AVATAR_PATH).convert("RGBA")

    bob_offsets = [0, -10, -4]
    pro_bob = bob_offsets[phase % 3] if is_pro else 6
    con_bob = bob_offsets[phase % 3] if not is_pro else 6

    pro_scale = 0.90 if is_pro else 0.78
    con_scale = 0.90 if not is_pro else 0.78

    if not is_pro:
        pro_img = ImageEnhance.Brightness(pro_img).enhance(0.55)
    else:
        con_img = ImageEnhance.Brightness(con_img).enhance(0.55)

    pro_w, pro_h = int(pro_img.width * pro_scale), int(pro_img.height * pro_scale)
    con_w, con_h = int(con_img.width * con_scale), int(con_img.height * con_scale)
    pro_resized = pro_img.resize((pro_w, pro_h), Image.Resampling.LANCZOS)
    con_resized = con_img.resize((con_w, con_h), Image.Resampling.LANCZOS)

    # Position side-by-side behind bottom studio podium (y=1120)
    pro_x = 195 - pro_w // 2
    pro_y = 1150 - pro_h + pro_bob
    con_x = 525 - con_w // 2
    con_y = 1150 - con_h + con_bob

    # Draw listener first, active speaker on top
    if is_pro:
        canvas.paste(con_resized, (con_x, con_y), con_resized)
        canvas.paste(pro_resized, (pro_x, pro_y), pro_resized)
    else:
        canvas.paste(pro_resized, (pro_x, pro_y), pro_resized)
        canvas.paste(con_resized, (con_x, con_y), con_resized)

    # Layer 3: Crisp Studio Podium / Footer Overlay (SVG -> PNG alpha composited cleanly)
    dots_svg = []
    for i in range(total_turns):
        dx = 68 + i * 30
        if i == turn_idx:
            dots_svg.append(f'<rect x="{dx}" y="1192" width="22" height="8" rx="4" fill="{badge_bg}"/>')
        elif i < turn_idx:
            dots_svg.append(f'<rect x="{dx}" y="1192" width="14" height="8" rx="4" fill="#94A3B8"/>')
        else:
            dots_svg.append(f'<rect x="{dx}" y="1192" width="14" height="8" rx="4" fill="#334155"/>')

    fg_svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <!-- Sleek Studio Podium Table -->
  <rect x="28" y="1108" width="664" height="140" rx="22" fill="#0B111E" stroke="#1E293B" stroke-width="2"/>
  <rect x="48" y="1126" width="130" height="30" rx="8" fill="#1E3A8A" fill-opacity="0.75"/>
  <text x="113" y="1147" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="800" fill="#93C5FD">찬성 {raw_stats['pro_ratio']}%</text>

  <text x="360" y="1147" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="700" fill="#E2E8F0">50 : 50 공론장 중재</text>

  <rect x="542" y="1126" width="130" height="30" rx="8" fill="#881337" fill-opacity="0.75"/>
  <text x="607" y="1147" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="800" fill="#FDA4AF">반대 {raw_stats['con_ratio']}%</text>

  <line x1="56" y1="1172" x2="664" y2="1172" stroke="#1E293B" stroke-width="1.5"/>
  {"".join(dots_svg)}
  <text x="664" y="1202" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="600" fill="#64748B">Agora-Shorts Studio</text>
</svg>
"""
    fg_svg_path = out_png.with_suffix(".fg.svg")
    fg_png_path = out_png.with_suffix(".fg.png")
    fg_svg_path.write_text(fg_svg, encoding="utf-8")
    subprocess.run(
        ["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(fg_png_path), str(fg_svg_path)],
        check=True,
    )
    fg_img = Image.open(fg_png_path).convert("RGBA")
    canvas.alpha_composite(fg_img)
    canvas.convert("RGB").save(out_png)
    fg_svg_path.unlink(missing_ok=True)
    fg_png_path.unlink(missing_ok=True)


def generate_synthesized_broadcast_wav(
    wav_path: Path,
    duration_sec: float,
    is_pro: bool,
    text: str,
    sample_rate: int = 24000,
) -> None:
    """아나운서 음절 리듬과 턴 전환 차임을 합성한 WAV 오디오 트랙 생성."""
    n_samples = int(duration_sec * sample_rate)
    f0 = 135.0 if is_pro else 210.0
    syllables = [c for c in text if "가" <= c <= "힣"]
    syl_rate = max(4.5, min(7.5, len(syllables) / max(duration_sec - 0.6, 1.0)))

    buf = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        if t < 0.28:
            chime_f = (440.0 if is_pro else 587.33) * (1.0 + 0.25 * (t / 0.28))
            env = math.sin(math.pi * (t / 0.28)) * 0.22
            val = env * math.sin(2.0 * math.pi * chime_f * t)
        elif t > duration_sec - 0.35:
            val = 0.0
        else:
            speech_t = t - 0.32
            syl_env = max(0.0, math.sin(math.pi * ((speech_t * syl_rate) % 1.0))) ** 0.6
            pause_mod = 0.15 if int(speech_t * 1.4) % 5 == 4 else 1.0
            pitch_mod = f0 * (1.0 + 0.06 * math.sin(2.0 * math.pi * 1.8 * speech_t))
            harmonic = (
                0.55 * math.sin(2.0 * math.pi * pitch_mod * t)
                + 0.28 * math.sin(2.0 * math.pi * (pitch_mod * 2.0) * t)
                + 0.12 * math.sin(2.0 * math.pi * (pitch_mod * 3.0) * t)
            )
            val = 0.08 * syl_env * pause_mod * harmonic

        sample_int = max(-32767, min(32767, int(val * 32767)))
        buf += struct.pack("<h", sample_int)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(buf))


def render_debate_mp4(
    issue_title: str,
    category_badge: str,
    raw_stats: Dict[str, Any],
    debate_script: List[Dict[str, Any]],
    output_mp4: Path,
    turn_audio_b64_list: Optional[List[str]] = None,
) -> Path:
    """6턴 대본을 2인 캐릭터 + 말풍선 애니메이션 40초 9:16 H.264 MP4로 렌더링."""
    turns = debate_script[:6]
    total_turns = len(turns)
    turn_duration = 40.0 / max(total_turns, 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        segment_files: List[Path] = []

        for idx, turn in enumerate(turns):
            wav_path = tmp / f"turn_{idx}.wav"
            wrote_custom_audio = False
            if turn_audio_b64_list and idx < len(turn_audio_b64_list) and turn_audio_b64_list[idx]:
                try:
                    raw_bytes = base64.b64decode(turn_audio_b64_list[idx])
                    if raw_bytes[:4] == b"RIFF":
                        wav_path.write_bytes(raw_bytes)
                    else:
                        with wave.open(str(wav_path), "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(24000)
                            wf.writeframes(raw_bytes)
                    wrote_custom_audio = True
                except Exception:
                    wrote_custom_audio = False

            if not wrote_custom_audio:
                generate_synthesized_broadcast_wav(
                    wav_path,
                    duration_sec=turn_duration,
                    is_pro=(turn["speaker"] == "PRO"),
                    text=turn["text"],
                )

            concat_img_txt = tmp / f"imgs_{idx}.txt"
            lines = []
            n_cycles = 8
            step_dur = turn_duration / (n_cycles * 3)
            phase_pngs = []
            for ph in range(3):
                p_png = tmp / f"turn_{idx}_ph_{ph}.png"
                create_turn_frame_png(
                    issue_title=issue_title,
                    category_badge=category_badge,
                    raw_stats=raw_stats,
                    turn_idx=idx,
                    total_turns=total_turns,
                    turn_data=turn,
                    phase=ph,
                    out_png=p_png,
                )
                phase_pngs.append(p_png)

            for _ in range(n_cycles):
                for ph in range(3):
                    lines.append(f"file '{phase_pngs[ph]}'")
                    lines.append(f"duration {step_dur:.4f}")
            lines.append(f"file '{phase_pngs[2]}'")
            concat_img_txt.write_text("\n".join(lines), encoding="utf-8")

            seg_mp4 = tmp / f"seg_{idx}.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_img_txt),
                    "-i", str(wav_path),
                    "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
                    "-pix_fmt", "yuv420p", "-r", "24",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "24000",
                    "-shortest",
                    str(seg_mp4),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            segment_files.append(seg_mp4)

        full_list_txt = tmp / "segments.txt"
        full_list_txt.write_text(
            "\n".join(f"file '{s}'" for s in segment_files),
            encoding="utf-8",
        )
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(full_list_txt),
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_mp4),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    return output_mp4


def main():
    for pid, data in PRESETS.items():
        out_file = VIDEOS_DIR / f"{pid}.mp4"
        render_debate_mp4(
            issue_title=data["issue_title"],
            category_badge=data["category_badge"],
            raw_stats=data["raw_stats"],
            debate_script=data["debate_script"],
            output_mp4=out_file,
        )
        print(f"[MP4 RENDERED] {out_file} ({out_file.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
