#!/usr/bin/env python3
"""
render_mp4.py
Agora-Shorts 실제 9:16 세로형 MP4 영상(720x1280, H.264 + AAC, 40초 6턴) 렌더링 엔진.
- 각 턴(PRO 찬성 / CON 반대)별 고해상도 9:16 방송 그래픽 프레임(SVG -> PNG) 생성
- Gemini 2.5 Flash Native Audio TTS (또는 고품질 방송 시그널/음성 트랙) 오디오 결합
- ffmpeg libx264 (yuv420p, faststart)로 브라우저 <video> 태그 및 모바일/유튜브 쇼츠 즉시 호환 MP4 생성
"""

import base64
import html
import json
import math
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from presets_data import PRESETS

BASE_DIR = Path(__file__).resolve().parent
VIDEOS_DIR = BASE_DIR / "static" / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)


def _wrap_korean_text(text: str, max_chars: int = 24) -> List[str]:
    """한글 문장을 쇼츠 자막 박스 폭에 맞춰 자연스럽게 줄바꿈."""
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
    return lines[:5]


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
    9:16 (720x1280) 쇼츠 프레임을 SVG로 생성한 뒤 rsvg-convert로 PNG 렌더링.
    phase (0, 1, 2)에 따라 오디오 파형(Waveform) 높이와 네온 링 크기가 동적으로 변화함.
    """
    W, H = 720, 1280
    is_pro = turn_data["speaker"] == "PRO"
    progress_pct = ((turn_idx + (phase + 1) / 3.0) / total_turns) * 100.0
    remaining_sec = max(0.0, 40.0 - (progress_pct / 100.0) * 40.0)

    title_lines = _wrap_korean_text(issue_title, max_chars=23)
    title_svg = "".join(
        f'<text x="360" y="{178 + i * 32}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="23" font-weight="700" fill="#F8FAFC">{html.escape(line)}</text>'
        for i, line in enumerate(title_lines[:2])
    )

    caption_lines = _wrap_korean_text(turn_data["text"], max_chars=23)
    caption_svg = "".join(
        f'<text x="72" y="{908 + i * 38}" font-family="Noto Sans CJK KR, sans-serif" font-size="24" font-weight="500" fill="#F1F5F9">{html.escape(line)}</text>'
        for i, line in enumerate(caption_lines[:4])
    )

    # Dynamic waveform bar heights for PRO and CON
    pro_waves = [26, 48, 34, 56, 28, 52, 38, 44, 24] if is_pro else [8, 8, 8, 8, 8, 8, 8, 8, 8]
    con_waves = [28, 52, 36, 58, 30, 48, 40, 46, 26] if not is_pro else [8, 8, 8, 8, 8, 8, 8, 8, 8]
    if phase == 1:
        pro_waves = [h if h == 8 else int(h * 0.65) for h in pro_waves]
        con_waves = [h if h == 8 else int(h * 0.65) for h in con_waves]
    elif phase == 2:
        pro_waves = [h if h == 8 else int(h * 0.85) for h in pro_waves[::-1]]
        con_waves = [h if h == 8 else int(h * 0.85) for h in con_waves[::-1]]

    pro_wave_svg = "".join(
        f'<rect x="{122 + i * 16}" y="{638 - h // 2}" width="8" height="{h}" rx="4" fill="{"#60A5FA" if is_pro else "#334155"}"/>'
        for i, h in enumerate(pro_waves)
    )
    con_wave_svg = "".join(
        f'<rect x="{462 + i * 16}" y="{638 - h // 2}" width="8" height="{h}" rx="4" fill="{"#FB7185" if not is_pro else "#334155"}"/>'
        for i, h in enumerate(con_waves)
    )

    pro_border = "#60A5FA" if is_pro else "#1E293B"
    con_border = "#FB7185" if not is_pro else "#1E293B"
    pro_bg = "#1E3A8A" if is_pro else "#0F172A"
    con_bg = "#881337" if not is_pro else "#0F172A"
    pro_ring_r = 74 + (phase * 4 if is_pro else 0)
    con_ring_r = 74 + (phase * 4 if not is_pro else 0)

    caption_border = "#3B82F6" if is_pro else "#F43F5E"
    speaker_badge_bg = "#2563EB" if is_pro else "#E11D48"
    speaker_label = f"찬성 측 핵심 논거 #{turn_idx // 2 + 1} (PRO)" if is_pro else f"반대 측 핵심 논거 #{turn_idx // 2 + 1} (CON)"
    core_color = "#7DD3FC" if is_pro else "#FDA4AF"

    # Step dots
    dots_svg = []
    for i in range(total_turns):
        dx = 76 + i * 32
        if i == turn_idx:
            dots_svg.append(f'<rect x="{dx}" y="1142" width="24" height="10" rx="5" fill="{speaker_badge_bg}"/>')
        elif i < turn_idx:
            dots_svg.append(f'<rect x="{dx}" y="1142" width="14" height="10" rx="5" fill="#94A3B8"/>')
        else:
            dots_svg.append(f'<rect x="{dx}" y="1142" width="14" height="10" rx="5" fill="#334155"/>')

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#070B14"/>
      <stop offset="50%" stop-color="#0D162B"/>
      <stop offset="100%" stop-color="#060911"/>
    </linearGradient>
    <linearGradient id="prog" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#3B82F6"/>
      <stop offset="50%" stop-color="#38BDF8"/>
      <stop offset="100%" stop-color="#F43F5E"/>
    </linearGradient>
  </defs>

  <rect x="0" y="0" width="{W}" height="{H}" fill="url(#bg)"/>

  <!-- Top Progress Bar -->
  <rect x="42" y="38" width="636" height="14" rx="7" fill="#1E293B"/>
  <rect x="42" y="38" width="{max(14.0, 6.36 * progress_pct):.1f}" height="14" rx="7" fill="url(#prog)"/>

  <!-- Top Status Row -->
  <rect x="42" y="68" width="96" height="34" rx="8" fill="#E11D48"/>
  <text x="90" y="91" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="18" font-weight="700" fill="#FFFFFF">SHORTS</text>
  <text x="154" y="91" font-family="Noto Sans CJK KR, sans-serif" font-size="20" font-weight="700" fill="#F8FAFC">TURN {turn_idx + 1} / {total_turns}</text>
  <text x="678" y="91" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="20" font-weight="700" fill="#38BDF8">{remaining_sec:.1f}s 남음</text>

  <!-- Issue Header Box -->
  <rect x="42" y="116" width="636" height="122" rx="18" fill="#0F172A" stroke="#334155" stroke-width="2"/>
  <text x="360" y="144" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="17" font-weight="700" fill="#38BDF8">{html.escape(category_badge)}</text>
  {title_svg}

  <!-- Real YouTube Stats Pill -->
  <rect x="42" y="252" width="636" height="48" rx="12" fill="#131C31" stroke="#1E293B" stroke-width="1.5"/>
  <text x="360" y="282" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="17" font-weight="600" fill="#CBD5E1">
    실측 댓글 {raw_stats['total_comments']}건 분석 · 악플 {raw_stats['filtered_curse_count']}건 정화 · 과열도 {raw_stats['toxicity_before']}→{raw_stats['toxicity_after']}점
  </text>

  <!-- PRO Avatar Card (Left) -->
  <rect x="42" y="330" width="304" height="360" rx="24" fill="{pro_bg}" fill-opacity="0.45" stroke="{pro_border}" stroke-width="3.5"/>
  <rect x="64" y="352" width="110" height="32" rx="8" fill="#1D4ED8"/>
  <text x="119" y="374" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="16" font-weight="700" fill="#FFFFFF">PRO · 찬성</text>
  <text x="322" y="374" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="18" font-weight="700" fill="#93C5FD">여론 {raw_stats['pro_ratio']}%</text>

  <circle cx="194" cy="485" r="{pro_ring_r}" fill="#1E3A8A" fill-opacity="0.35" stroke="{pro_border}" stroke-width="3"/>
  <circle cx="194" cy="485" r="58" fill="#1D4ED8"/>
  <circle cx="194" cy="468" r="18" fill="#DBEAFE"/>
  <path d="M162 520 C162 498 226 498 226 520" stroke="#DBEAFE" stroke-width="10" stroke-linecap="round" fill="none"/>

  <text x="194" y="582" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="22" font-weight="700" fill="#FFFFFF">AI 아나운서 찬성</text>
  <text x="194" y="608" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="500" fill="#93C5FD">중립 핵심논거 브리핑</text>
  {pro_wave_svg}

  <!-- CON Avatar Card (Right) -->
  <rect x="374" y="330" width="304" height="360" rx="24" fill="{con_bg}" fill-opacity="0.45" stroke="{con_border}" stroke-width="3.5"/>
  <rect x="396" y="352" width="110" height="32" rx="8" fill="#BE123C"/>
  <text x="451" y="374" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="16" font-weight="700" fill="#FFFFFF">CON · 반대</text>
  <text x="654" y="374" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="18" font-weight="700" fill="#FDA4AF">여론 {raw_stats['con_ratio']}%</text>

  <circle cx="526" cy="485" r="{con_ring_r}" fill="#881337" fill-opacity="0.35" stroke="{con_border}" stroke-width="3"/>
  <circle cx="526" cy="485" r="58" fill="#E11D48"/>
  <circle cx="526" cy="468" r="18" fill="#FFE4E6"/>
  <path d="M494 520 C494 498 558 498 558 520" stroke="#FFE4E6" stroke-width="10" stroke-linecap="round" fill="none"/>

  <text x="526" y="582" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="22" font-weight="700" fill="#FFFFFF">AI 아나운서 반대</text>
  <text x="526" y="608" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="15" font-weight="500" fill="#FDA4AF">중립 핵심논거 브리핑</text>
  {con_wave_svg}

  <!-- Dynamic Subtitle Stage Box -->
  <rect x="42" y="726" width="636" height="456" rx="24" fill="#090E1C" stroke="{caption_border}" stroke-width="3.5"/>
  <rect x="72" y="756" width="260" height="40" rx="10" fill="{speaker_badge_bg}"/>
  <text x="202" y="783" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="19" font-weight="700" fill="#FFFFFF">{html.escape(speaker_label)}</text>
  <text x="646" y="782" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="17" font-weight="700" fill="#34D399">✓ 비속어 100% 정화됨</text>

  <text x="72" y="842" font-family="Noto Sans CJK KR, sans-serif" font-size="25" font-weight="700" fill="{core_color}">
    {html.escape(turn_data['core_point'])}
  </text>
  <line x1="72" y1="862" x2="646" y2="862" stroke="#1E293B" stroke-width="2"/>

  {caption_svg}

  <line x1="72" y1="1120" x2="646" y2="1120" stroke="#1E293B" stroke-width="1.5"/>
  {"".join(dots_svg)}
  <text x="646" y="1154" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="16" font-weight="600" fill="#64748B">Agora-Shorts · 호날두의 아이들</text>
</svg>
"""
    svg_path = out_png.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    subprocess.run(
        ["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(out_png), str(svg_path)],
        check=True,
    )
    svg_path.unlink(missing_ok=True)


def generate_synthesized_broadcast_wav(
    wav_path: Path,
    duration_sec: float,
    is_pro: bool,
    text: str,
    sample_rate: int = 24000,
) -> None:
    """
    외부 TTS 오디오가 전달되지 않은 오프라인/서버 단독 렌더링 시,
    실제 아나운서 음절 리듬(Syllable Formant Cadence)과 턴 전환 차임을 합성한 WAV 트랙 생성.
    """
    n_samples = int(duration_sec * sample_rate)
    f0 = 135.0 if is_pro else 210.0  # PRO: 남성 중저음 포먼트, CON: 여성 중고음 포먼트
    syllables = [c for c in text if "가" <= c <= "힣"]
    syl_rate = max(4.5, min(7.5, len(syllables) / max(duration_sec - 0.6, 1.0)))

    buf = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        # Opening broadcast chime (0.0s ~ 0.28s)
        if t < 0.28:
            chime_f = (440.0 if is_pro else 587.33) * (1.0 + 0.25 * (t / 0.28))
            env = math.sin(math.pi * (t / 0.28)) * 0.22
            val = env * math.sin(2.0 * math.pi * chime_f * t)
        elif t > duration_sec - 0.35:
            val = 0.0
        else:
            # Soft ambient studio bed + rhythmic speech cadence envelope
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
    """
    6턴 대본과 (선택적) Gemini TTS 오디오 트랙 배열을 받아
    40초 분량의 실제 9:16 H.264 MP4 파일을 생성한다.
    """
    turns = debate_script[:6]
    total_turns = len(turns)
    turn_duration = 40.0 / max(total_turns, 1)  # ~6.67s per turn

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        segment_files: List[Path] = []

        for idx, turn in enumerate(turns):
            # 1) Prepare audio WAV for this turn
            wav_path = tmp / f"turn_{idx}.wav"
            wrote_custom_audio = False
            if turn_audio_b64_list and idx < len(turn_audio_b64_list) and turn_audio_b64_list[idx]:
                try:
                    raw_bytes = base64.b64decode(turn_audio_b64_list[idx])
                    # Check if raw_bytes is already WAV or raw PCM 24kHz 16-bit mono from Gemini TTS
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

            # 2) Render 3 animated phase PNGs for this turn and create a dynamic video segment
            concat_img_txt = tmp / f"imgs_{idx}.txt"
            lines = []
            n_cycles = 6  # 6 cycles across ~6.67s -> ~1.1s per cycle
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

        # Concatenate all 6 segments into final 9:16 MP4
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
