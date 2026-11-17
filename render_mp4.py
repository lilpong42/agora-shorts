#!/usr/bin/env python3
"""
render_mp4.py
Agora 고퀄리티 24fps 9:16 방송형 토론 쇼츠 MP4 렌더링 엔진 (720x1280, H.264 + AAC).
- 건축적 뉴스룸 스튜디오 배경 + 데스크 퍼스펙티브 라인
- 24fps 부드러운 Ease-out 화자 줌인/리액션 모션 & 비화자 디밍
- 실시간 단어/어절 하이라이트(Kinetic Caption Reveal)가 적용된 에디토리얼 말풍선
- 12밴드 반응형 오디오 스펙트럼 + 여론 비율 하단 데스크
- Numpy 합성 뉴스룸 마림바·패드 BGM + 턴 전환 스팅어 사운드 (외부 TTS 오버레이 지원)
"""

import base64
import html
import math
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
from presets_data import PRESETS

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "static" / "assets"
VIDEOS_DIR = BASE_DIR / "static" / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

PRO_AVATAR_PATH = ASSETS_DIR / "pro_avatar.png"
CON_AVATAR_PATH = ASSETS_DIR / "con_avatar.png"
FONT_BOLD_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

FPS = 24
W, H = 720, 1280


def _wrap_korean_text(text: str, max_chars: int = 25, max_lines: int = 6) -> List[str]:
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


def _svg_to_rgba(svg_str: str, tmp_dir: Path, name: str) -> Image.Image:
    svg_path = tmp_dir / f"{name}.svg"
    png_path = tmp_dir / f"{name}.png"
    svg_path.write_text(svg_str, encoding="utf-8")
    subprocess.run(
        ["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(png_path), str(svg_path)],
        check=True,
    )
    img = Image.open(png_path).convert("RGBA")
    svg_path.unlink(missing_ok=True)
    png_path.unlink(missing_ok=True)
    return img


def _render_studio_backdrop(tmp_dir: Path) -> Image.Image:
    """건축적 뉴스룸 스튜디오 배경 레이어 (1회 생성)."""
    pillars = []
    for x in range(48, W, 88):
        pillars.append(f'<rect x="{x}" y="0" width="2" height="1120" fill="#FFFFFF" fill-opacity="0.03"/>')
    floor_lines = []
    for i in range(6):
        y = 1040 + i * 24
        floor_lines.append(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="#FFFFFF" stroke-opacity="{0.04 - i * 0.005:.3f}" stroke-width="1"/>')

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0E1015"/>
      <stop offset="52%" stop-color="#141821"/>
      <stop offset="100%" stop-color="#0B0D12"/>
    </linearGradient>
    <radialGradient id="topLight" cx="50%" cy="28%" r="58%">
      <stop offset="0%" stop-color="#273043" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="#0E1015" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  <rect width="{W}" height="{H}" fill="url(#topLight)"/>
  {"".join(pillars)}
  {"".join(floor_lines)}
  <line x1="0" y1="1038" x2="{W}" y2="1038" stroke="#FFFFFF" stroke-opacity="0.08" stroke-width="1.5"/>
</svg>
"""
    return _svg_to_rgba(svg, tmp_dir, "studio_backdrop")


def _render_bubble_stage_overlay(
    tmp_dir: Path,
    issue_title: str,
    raw_stats: Dict[str, Any],
    turn_idx: int,
    total_turns: int,
    turn_data: Dict[str, Any],
    caption_lines: List[str],
    reveal_stage: int,
    total_stages: int,
) -> Image.Image:
    """헤드라인 + 키네틱 자막 하이라이트 말풍선 + 하단 데스크 오버레이."""
    is_pro = turn_data["speaker"] == "PRO"
    accent = "#2563EB" if is_pro else "#DC2626"
    badge_bg = "#EFF6FF" if is_pro else "#FEF2F2"
    speaker_label = f"찬성 {turn_idx // 2 + 1}" if is_pro else f"반대 {turn_idx // 2 + 1}"

    title_lines = _wrap_korean_text(issue_title, max_chars=23, max_lines=2)
    title_svg = "".join(
        f'<text x="360" y="{144 + i * 31}" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="22.5" font-weight="700" fill="#F4F4F5">{html.escape(line)}</text>'
        for i, line in enumerate(title_lines)
    )

    total_lines = max(len(caption_lines), 1)
    active_line_float = ((reveal_stage + 1) / max(total_stages, 1)) * total_lines
    caption_elems = []
    for i, line in enumerate(caption_lines):
        y = 376 + i * 33
        if i + 1 <= int(active_line_float):
            fill = "#111317"
            weight = "700"
        elif i < active_line_float:
            est_w = min(560, max(160, int(len(line) * 16.8)))
            caption_elems.append(
                f'<rect x="70" y="{y - 23}" width="{est_w}" height="29" rx="6" fill="{badge_bg}"/>'
            )
            fill = accent
            weight = "800"
        else:
            fill = "#94A3B8"
            weight = "500"
        caption_elems.append(
            f'<text x="76" y="{y}" font-family="Noto Sans CJK KR, sans-serif" font-size="21" font-weight="{weight}" fill="{fill}">{html.escape(line)}</text>'
        )

    tail_svg = (
        '<polygon points="168,574 218,574 182,616" fill="#FFFFFF"/>'
        if is_pro
        else '<polygon points="502,574 552,574 538,616" fill="#FFFFFF"/>'
    )

    pro_w_bar = max(14, int(220 * (raw_stats["pro_ratio"] / 100.0)))
    con_w_bar = 220 - pro_w_bar

    dots_svg = []
    for i in range(total_turns):
        dx = 64 + i * 28
        if i == turn_idx:
            dots_svg.append(f'<rect x="{dx}" y="1202" width="22" height="6" rx="3" fill="{accent}"/>')
        elif i < turn_idx:
            dots_svg.append(f'<rect x="{dx}" y="1202" width="12" height="6" rx="3" fill="#A1A1AA"/>')
        else:
            dots_svg.append(f'<rect x="{dx}" y="1202" width="12" height="6" rx="3" fill="#272A34"/>')

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <!-- Top Issue Card -->
  <rect x="38" y="102" width="644" height="96" rx="14" fill="#181B24" fill-opacity="0.92" stroke="#FFFFFF" stroke-opacity="0.08" stroke-width="1"/>
  {title_svg}

  <!-- Editorial Broadcast Speech Bubble -->
  <rect x="38" y="220" width="644" height="356" rx="20" fill="#FFFFFF"/>
  <rect x="38" y="220" width="644" height="6" rx="3" fill="{accent}"/>
  {tail_svg}

  <rect x="74" y="248" width="96" height="32" rx="8" fill="{badge_bg}"/>
  <text x="122" y="270" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="16" font-weight="800" fill="{accent}">{html.escape(speaker_label)}</text>
  <text x="646" y="270" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="14.5" font-weight="600" fill="#71717A">실측 {raw_stats['total_comments']}건 핵심 요약</text>

  <text x="76" y="324" font-family="Noto Sans CJK KR, sans-serif" font-size="23" font-weight="800" fill="{accent}">
    {html.escape(turn_data['core_point'][:26])}
  </text>
  <line x1="76" y1="342" x2="644" y2="342" stroke="#F4F4F5" stroke-width="2"/>

  {"".join(caption_elems)}

  <!-- Lower-Third Broadcast Desk Overlay -->
  <rect x="30" y="1116" width="660" height="130" rx="18" fill="#151821" fill-opacity="0.96" stroke="#FFFFFF" stroke-opacity="0.09" stroke-width="1"/>
  <text x="64" y="1152" font-family="Noto Sans CJK KR, sans-serif" font-size="15.5" font-weight="700" fill="#60A5FA">찬성 {raw_stats['pro_ratio']}%</text>

  <rect x="250" y="1142" width="{pro_w_bar}" height="8" rx="4" fill="#2563EB"/>
  <rect x="{250 + pro_w_bar + 4}" y="1142" width="{max(6, con_w_bar - 4)}" height="8" rx="4" fill="#DC2626"/>
  <text x="360" y="1172" text-anchor="middle" font-family="Noto Sans CJK KR, sans-serif" font-size="13" font-weight="600" fill="#A1A1AA">50:50 중재</text>

  <text x="656" y="1152" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="15.5" font-weight="700" fill="#F87171">반대 {raw_stats['con_ratio']}%</text>
  <line x1="60" y1="1184" x2="660" y2="1184" stroke="#FFFFFF" stroke-opacity="0.06" stroke-width="1"/>
  {"".join(dots_svg)}
  <text x="656" y="1210" text-anchor="end" font-family="Noto Sans CJK KR, sans-serif" font-size="14.5" font-weight="700" fill="#71717A">Agora Studio</text>
</svg>
"""
    return _svg_to_rgba(svg, tmp_dir, f"turn_{turn_idx}_st_{reveal_stage}")


def generate_newsroom_audio_bed(
    wav_path: Path,
    total_duration_sec: float,
    turns: List[Dict[str, Any]],
    sample_rate: int = 24000,
) -> None:
    """깔끔한 뉴스룸 스튜디오 마림바/코드 BGM + 턴 전환 차임 합성."""
    n_samples = int(total_duration_sec * sample_rate)
    t = np.arange(n_samples, dtype=np.float32) / sample_rate
    audio = np.zeros(n_samples, dtype=np.float32)

    chords = [
        [220.00, 261.63, 329.63],
        [174.61, 220.00, 261.63],
        [196.00, 246.94, 293.66],
        [220.00, 261.63, 329.63],
    ]
    bar_len = 5.0
    for idx in range(int(math.ceil(total_duration_sec / bar_len))):
        start_s = int(idx * bar_len * sample_rate)
        end_s = min(n_samples, int((idx + 1) * bar_len * sample_rate))
        if end_s <= start_s:
            continue
        seg_t = t[start_s:end_s] - idx * bar_len
        env = np.minimum(seg_t / 0.4, 1.0) * np.minimum((bar_len - seg_t) / 0.4, 1.0)
        chord = chords[idx % len(chords)]
        pad = sum(np.sin(2.0 * np.pi * f * seg_t) for f in chord) / len(chord)
        audio[start_s:end_s] += 0.045 * env * pad

    beat_step = 0.4166
    scale_notes = [440.0, 523.25, 659.25, 587.33, 440.0, 523.25, 659.25, 783.99]
    beat_idx = 0
    bt = 0.15
    while bt < total_duration_sec - 0.5:
        start_s = int(bt * sample_rate)
        dur_s = int(0.28 * sample_rate)
        end_s = min(n_samples, start_s + dur_s)
        seg_len = end_s - start_s
        if seg_len > 0:
            lt = np.arange(seg_len, dtype=np.float32) / sample_rate
            freq = scale_notes[beat_idx % len(scale_notes)]
            env = np.exp(-lt * 14.0) * np.minimum(lt / 0.008, 1.0)
            note = 0.7 * np.sin(2.0 * np.pi * freq * lt) + 0.3 * np.sin(2.0 * np.pi * freq * 2.0 * lt)
            audio[start_s:end_s] += 0.042 * env * note
        beat_idx += 1
        bt += beat_step

    turn_dur = total_duration_sec / max(len(turns), 1)
    for idx, turn in enumerate(turns):
        t0 = idx * turn_dur
        is_pro = turn["speaker"] == "PRO"
        notes = [523.25, 659.25] if is_pro else [587.33, 493.88]
        for ni, freq in enumerate(notes):
            start_s = int((t0 + ni * 0.09) * sample_rate)
            dur_s = int(0.32 * sample_rate)
            end_s = min(n_samples, start_s + dur_s)
            seg_len = end_s - start_s
            if seg_len > 0:
                lt = np.arange(seg_len, dtype=np.float32) / sample_rate
                env = np.exp(-lt * 11.0) * np.minimum(lt / 0.006, 1.0)
                chime = 0.75 * np.sin(2.0 * np.pi * freq * lt) + 0.25 * np.sin(2.0 * np.pi * freq * 2.0 * lt)
                audio[start_s:end_s] += 0.12 * env * chime

    fade_s = int(1.0 * sample_rate)
    if n_samples > fade_s:
        audio[-fade_s:] *= np.linspace(1.0, 0.0, fade_s, dtype=np.float32)

    audio = np.clip(audio, -0.92, 0.92)
    pcm = (audio * 32767.0).astype(np.int16)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def render_debate_mp4(
    issue_title: str,
    category_badge: str,
    raw_stats: Dict[str, Any],
    debate_script: List[Dict[str, Any]],
    output_mp4: Path,
    turn_audio_b64_list: Optional[List[str]] = None,
) -> Path:
    """24fps 브로드캐스트 모션그래픽 + 키네틱 자막 9:16 H.264 MP4 렌더링."""
    turns = debate_script[:6]
    total_turns = max(len(turns), 1)
    total_duration = 40.0
    total_frames = int(total_duration * FPS)
    frames_per_turn = total_frames // total_turns

    pro_orig = Image.open(PRO_AVATAR_PATH).convert("RGBA")
    con_orig = Image.open(CON_AVATAR_PATH).convert("RGBA")
    pro_dim_orig = ImageEnhance.Brightness(pro_orig).enhance(0.48)
    con_dim_orig = ImageEnhance.Brightness(con_orig).enhance(0.48)

    try:
        hud_font = ImageFont.truetype(FONT_BOLD_PATH, 19)
    except Exception:
        hud_font = ImageFont.load_default()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        backdrop = _render_studio_backdrop(tmp)

        wav_path = tmp / "soundtrack.wav"
        has_custom_audio = bool(turn_audio_b64_list and any(turn_audio_b64_list))
        if has_custom_audio:
            seg_wavs: List[Path] = []
            turn_dur = total_duration / total_turns
            for idx in range(total_turns):
                sw = tmp / f"t_{idx}.wav"
                raw_b64 = turn_audio_b64_list[idx] if idx < len(turn_audio_b64_list) else None
                if raw_b64:
                    raw_bytes = base64.b64decode(raw_b64)
                    if raw_bytes[:4] == b"RIFF":
                        sw.write_bytes(raw_bytes)
                    else:
                        with wave.open(str(sw), "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(24000)
                            wf.writeframes(raw_bytes)
                else:
                    generate_newsroom_audio_bed(sw, turn_dur, [turns[idx]])
                seg_wavs.append(sw)
            list_txt = tmp / "wavs.txt"
            list_txt.write_text("\n".join(f"file '{w}'" for w in seg_wavs), encoding="utf-8")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_txt), "-c:a", "pcm_s16le", str(wav_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            generate_newsroom_audio_bed(wav_path, total_duration, turns)

        pro_active = pro_orig.resize((int(pro_orig.width * 0.92), int(pro_orig.height * 0.92)), Image.Resampling.LANCZOS)
        pro_idle = pro_dim_orig.resize((int(pro_dim_orig.width * 0.78), int(pro_dim_orig.height * 0.78)), Image.Resampling.LANCZOS)
        con_active = con_orig.resize((int(con_orig.width * 0.92), int(con_orig.height * 0.92)), Image.Resampling.LANCZOS)
        con_idle = con_dim_orig.resize((int(con_dim_orig.width * 0.78), int(con_dim_orig.height * 0.78)), Image.Resampling.LANCZOS)

        proc = subprocess.Popen(
            [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-s", f"{W}x{H}",
                "-pix_fmt", "rgba",
                "-r", str(FPS),
                "-i", "pipe:0",
                "-i", str(wav_path),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                "-ar", "24000",
                "-shortest",
                "-movflags", "+faststart",
                str(output_mp4),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert proc.stdin is not None

        for idx, turn in enumerate(turns):
            is_pro = turn["speaker"] == "PRO"
            accent_rgb = (37, 99, 235, 255) if is_pro else (220, 38, 38, 255)
            caption_lines = _wrap_korean_text(turn["text"], max_chars=25, max_lines=6)
            total_stages = max(len(caption_lines) * 2, 6)

            stage_overlays: List[Image.Image] = []
            for st in range(total_stages):
                stage_overlays.append(
                    _render_bubble_stage_overlay(
                        tmp_dir=tmp,
                        issue_title=issue_title,
                        raw_stats=raw_stats,
                        turn_idx=idx,
                        total_turns=total_turns,
                        turn_data=turn,
                        caption_lines=caption_lines,
                        reveal_stage=st,
                        total_stages=total_stages,
                    )
                )

            n_f = frames_per_turn if idx < total_turns - 1 else (total_frames - idx * frames_per_turn)
            for f in range(n_f):
                local_t = f / FPS
                global_f = idx * frames_per_turn + f
                progress = global_f / max(total_frames - 1, 1)
                remaining_sec = max(0.0, total_duration * (1.0 - progress))

                enter = min(1.0, local_t / 0.35)
                ease = 1.0 - (1.0 - enter) ** 3

                speech_wave = math.sin(local_t * 10.5) * 3.5 + math.sin(local_t * 4.2) * 2.0
                breath_idle = math.sin(local_t * 2.1) * 1.5

                frame = backdrop.copy()

                if is_pro:
                    p_spr = pro_active
                    c_spr = con_idle
                    p_x = 192 - p_spr.width // 2 + int((1.0 - ease) * -14)
                    p_y = 1146 - p_spr.height + int(speech_wave - ease * 6)
                    c_x = 532 - c_spr.width // 2
                    c_y = 1152 - c_spr.height + int(breath_idle)
                    frame.paste(c_spr, (c_x, c_y), c_spr)
                    frame.paste(p_spr, (p_x, p_y), p_spr)
                else:
                    p_spr = pro_idle
                    c_spr = con_active
                    p_x = 188 - p_spr.width // 2
                    p_y = 1152 - p_spr.height + int(breath_idle)
                    c_x = 528 - c_spr.width // 2 + int((1.0 - ease) * 14)
                    c_y = 1146 - c_spr.height + int(speech_wave - ease * 6)
                    frame.paste(p_spr, (p_x, p_y), p_spr)
                    frame.paste(c_spr, (c_x, c_y), c_spr)

                st_idx = min(total_stages - 1, int((f / max(n_f, 1)) * total_stages))
                frame.alpha_composite(stage_overlays[st_idx])

                draw = ImageDraw.Draw(frame, "RGBA")
                draw.rounded_rectangle([38, 34, 682, 42], radius=4, fill=(39, 42, 52, 255))
                bar_right = max(48, int(38 + 644 * progress))
                draw.rounded_rectangle([38, 34, bar_right, 42], radius=4, fill=accent_rgb)

                draw.text((40, 56), f"{idx + 1} / {total_turns}", font=hud_font, fill=(228, 228, 231, 255))
                timer_txt = f"{remaining_sec:.1f}s"
                draw.text((680, 56), timer_txt, font=hud_font, fill=(161, 161, 170, 255), anchor="ra")

                eq_base_x = 294
                for bi in range(12):
                    bx = eq_base_x + bi * 11
                    bh = int(6 + 16 * (0.5 + 0.5 * math.sin(local_t * 14.0 + bi * 0.75)))
                    draw.rounded_rectangle(
                        [bx, 1205 - bh // 2, bx + 5, 1205 + bh // 2],
                        radius=2,
                        fill=accent_rgb,
                    )

                proc.stdin.write(frame.tobytes())

        proc.stdin.close()
        ret = proc.wait()
        if ret != 0:
            raise RuntimeError(f"ffmpeg exited with code {ret}")

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
        print(f"[MP4 RENDERED 24fps] {out_file} ({out_file.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
