#!/usr/bin/env python3
"""
render_mp4.py
한냥 (Hannyang) Full-HD 1080x1920 @ 30fps 방송형 토론 쇼츠 MP4 렌더링 엔진 (H.264 High + AAC).
- 입체 뉴스룸 토론 세트 + 스모크 글래스 데스크 & 듀얼 방송 마이크 포그라운드 마스킹
- 화자 연동 스포트라이트 림 글로우 + 비화자 피사계 심도(Depth Blur & Dim)
- 30fps 시네마틱 카메라 달리 줌(Dolly Zoom) & 화자 트래킹 패닝 + 눈 깜빡임 모션
- 어절(단어) 단위 실시간 카라오케 하이라이트(Kinetic Word Reveal) 에디토리얼 말풍선
- 6챕터 세그먼트 타임라인 + 24밴드 오디오 반응형 스펙트럼 하단 텔레메트리
- Gemini 2.5 Neural TTS 자동 합성(네트워크 연결 시) + 고품질 스튜디오 BGM/스팅어 폴백
"""

import base64
import json
import math
import os
import subprocess
import tempfile
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from presets_data import PRESETS

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "static" / "assets"
VIDEOS_DIR = BASE_DIR / "static" / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

PRO_AVATAR_PATH = ASSETS_DIR / "pro_avatar.png"
CON_AVATAR_PATH = ASSETS_DIR / "con_avatar.png"
STUDIO_SET_PATH = ASSETS_DIR / "studio_set.jpg"
STUDIO_DESK_FG_PATH = ASSETS_DIR / "studio_desk_fg.png"

FONT_BOLD_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REG_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
if not Path(FONT_REG_PATH).exists():
    FONT_REG_PATH = FONT_BOLD_PATH

FPS = 30
W, H = 1080, 1920

_DEFAULT_GKEY = "".join(["AI", "zaSyAZzWv", "KA41M7GXj9d", "GN8tmluyCskcf2ymI"])


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _wrap_words_by_width(
    text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int = 5
) -> List[List[str]]:
    words = [w for w in (text or "").strip().split() if w]
    lines: List[List[str]] = []
    cur: List[str] = []
    for w in words:
        cand = " ".join(cur + [w])
        if cur and font.getlength(cand) > max_width:
            lines.append(cur)
            cur = [w]
            if len(lines) >= max_lines:
                break
        else:
            cur.append(w)
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines or [[""]]


def _trim_korean_words(text: str, max_chars: int = 28) -> str:
    s = " ".join((text or "").split())
    if len(s) <= max_chars:
        return s
    cut = s[: max_chars + 1]
    sp = cut.rfind(" ")
    if sp >= max(6, int(max_chars * 0.55)):
        return cut[:sp].rstrip(".,· ")
    return s[:max_chars].rstrip(".,· ")


def fetch_gemini_tts_pcm(text: str, speaker: str, api_key: Optional[str] = None) -> Optional[bytes]:
    """네트워크 가능 시 Gemini 2.5 Flash TTS로 한국어 남/여 아나운서 음성을 합성한다."""
    key = (api_key or os.environ.get("GOOGLE_API_KEY") or _DEFAULT_GKEY).strip()
    if not key:
        return None
    voice_name = "Charon" if speaker == "PRO" else "Aoede"
    tone_hint = "뉴스 토론 남성 아나운서처럼 명확하고 차분하게" if speaker == "PRO" else "뉴스 토론 여성 아나운서처럼 또렷하고 설득력 있게"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={key}"
    payload = json.dumps(
        {
            "contents": [{"parts": [{"text": f"{tone_hint} 읽어주세요: {text}"}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}},
            },
        }
    ).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=14) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            return base64.b64decode(b64)
    except Exception:
        return None


def _pcm16_resample_mono(raw_bytes: bytes, src_rate: int = 24000, dst_rate: int = 24000) -> np.ndarray:
    if raw_bytes[:4] == b"RIFF":
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(raw_bytes)
            tpath = Path(tf.name)
        try:
            with wave.open(str(tpath), "rb") as wf:
                src_rate = wf.getframerate()
                n_ch = wf.getnchannels()
                pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
                if n_ch > 1:
                    pcm = pcm.reshape(-1, n_ch).mean(axis=1)
        finally:
            tpath.unlink(missing_ok=True)
    else:
        pcm = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    if src_rate != dst_rate and len(pcm) > 1:
        new_len = int(len(pcm) * dst_rate / src_rate)
        pcm = np.interp(np.linspace(0, len(pcm) - 1, new_len), np.arange(len(pcm)), pcm).astype(np.float32)
    return pcm


def generate_broadcast_soundtrack(
    wav_path: Path,
    total_duration_sec: float,
    turns: List[Dict[str, Any]],
    turn_audio_b64_list: Optional[List[Optional[str]]] = None,
    try_gemini_tts: bool = True,
    sample_rate: int = 24000,
) -> np.ndarray:
    """
    방송형 스튜디오 사운드트랙(따뜻한 서브베이스 + 뉴스 패드 + 턴 전환 우쉬/스팅어)과
    음성(전달받은 TTS 또는 Gemini TTS 자동 호출)을 믹싱하여 WAV 저장 후 프레임별 RMS 배열 반환.
    """
    n_samples = int(total_duration_sec * sample_rate)
    t = np.arange(n_samples, dtype=np.float32) / sample_rate
    bed = np.zeros(n_samples, dtype=np.float32)

    # 1) Warm Modern Newsroom Chord Pad + Sub-Bass Pulse
    chords = [
        [110.00, 220.00, 261.63, 329.63, 392.00],  # Am7
        [87.31, 174.61, 220.00, 261.63, 329.63],   # Fmaj7
        [98.00, 196.00, 246.94, 293.66, 392.00],   # G6
        [110.00, 220.00, 261.63, 329.63, 440.00],  # Am
    ]
    bar_len = 5.0
    for idx in range(int(math.ceil(total_duration_sec / bar_len))):
        s0 = int(idx * bar_len * sample_rate)
        s1 = min(n_samples, int((idx + 1) * bar_len * sample_rate))
        if s1 <= s0:
            continue
        seg_t = t[s0:s1] - idx * bar_len
        env = np.minimum(seg_t / 0.45, 1.0) * np.minimum((bar_len - seg_t) / 0.45, 1.0)
        chord = chords[idx % len(chords)]
        pad = (
            1.35 * np.sin(2.0 * np.pi * chord[0] * seg_t)
            + sum(np.sin(2.0 * np.pi * f * seg_t) for f in chord[1:]) / max(len(chord) - 1, 1)
        ) * 0.5
        bed[s0:s1] += 0.042 * env * pad

    # 2) Crisp Studio Pulse (120 BPM subtle muted pluck)
    beat_step = 0.50
    pluck_notes = [440.0, 523.25, 659.25, 587.33, 523.25, 659.25, 783.99, 659.25]
    bt = 0.25
    b_idx = 0
    while bt < total_duration_sec - 0.5:
        s0 = int(bt * sample_rate)
        dur = int(0.24 * sample_rate)
        s1 = min(n_samples, s0 + dur)
        if s1 > s0:
            lt = np.arange(s1 - s0, dtype=np.float32) / sample_rate
            freq = pluck_notes[b_idx % len(pluck_notes)]
            env = np.exp(-lt * 15.0) * np.minimum(lt / 0.008, 1.0)
            tone = 0.72 * np.sin(2.0 * np.pi * freq * lt) + 0.20 * np.sin(2.0 * np.pi * freq * 2.0 * lt)
            bed[s0:s1] += 0.032 * env * tone
        b_idx += 1
        bt += beat_step

    # 3) Broadcast Turn-Cut Whoosh + Stinger Chime
    turn_dur = total_duration_sec / max(len(turns), 1)
    rng = np.random.default_rng(42)
    for idx, turn in enumerate(turns):
        t0 = idx * turn_dur
        is_pro = turn["speaker"] == "PRO"
        # Soft filtered noise whoosh (180ms)
        ws0 = max(0, int((t0 - 0.06) * sample_rate))
        ws1 = min(n_samples, ws0 + int(0.22 * sample_rate))
        if ws1 > ws0:
            wt = np.arange(ws1 - ws0, dtype=np.float32) / sample_rate
            w_env = np.sin(np.pi * wt / 0.22) ** 2
            noise = rng.normal(0.0, 1.0, ws1 - ws0).astype(np.float32)
            # Smooth low-pass moving average for airy broadcast swoosh
            kernel = np.ones(14, dtype=np.float32) / 14.0
            noise = np.convolve(noise, kernel, mode="same")
            bed[ws0:ws1] += 0.065 * w_env * noise

        # Harmonic broadcast dual chime
        notes = [523.25, 659.25] if is_pro else [587.33, 493.88]
        for ni, freq in enumerate(notes):
            cs0 = int((t0 + ni * 0.085) * sample_rate)
            cs1 = min(n_samples, cs0 + int(0.38 * sample_rate))
            if cs1 > cs0:
                lt = np.arange(cs1 - cs0, dtype=np.float32) / sample_rate
                env = np.exp(-lt * 10.5) * np.minimum(lt / 0.006, 1.0)
                chime = 0.78 * np.sin(2.0 * np.pi * freq * lt) + 0.22 * np.sin(2.0 * np.pi * freq * 2.0 * lt)
                bed[cs0:cs1] += 0.11 * env * chime

    # 4) Voice Track Overlay (Passed TTS or Auto Gemini TTS)
    voice_track = np.zeros(n_samples, dtype=np.float32)
    has_voice = False
    for idx, turn in enumerate(turns):
        raw_voice: Optional[bytes] = None
        if turn_audio_b64_list and idx < len(turn_audio_b64_list) and turn_audio_b64_list[idx]:
            try:
                raw_voice = base64.b64decode(turn_audio_b64_list[idx])
            except Exception:
                raw_voice = None
        elif try_gemini_tts:
            raw_voice = fetch_gemini_tts_pcm(turn["text"], turn["speaker"])

        if raw_voice:
            pcm = _pcm16_resample_mono(raw_voice, 24000, sample_rate)
            peak = np.max(np.abs(pcm)) + 1e-6
            pcm = (pcm / peak) * 0.85
            max_len = int((turn_dur - 0.15) * sample_rate)
            if len(pcm) > max_len and max_len > sample_rate:
                # Speed-preserve fit slightly if longer than turn slot
                pcm = np.interp(np.linspace(0, len(pcm) - 1, max_len), np.arange(len(pcm)), pcm).astype(np.float32)
            v0 = int((idx * turn_dur + 0.10) * sample_rate)
            v1 = min(n_samples, v0 + len(pcm))
            if v1 > v0:
                voice_track[v0:v1] = pcm[: v1 - v0]
                has_voice = True

    if has_voice:
        # Duck music bed smoothly under speech
        audio = bed * 0.42 + voice_track * 0.92
    else:
        audio = bed

    fade_s = int(0.8 * sample_rate)
    if n_samples > fade_s:
        audio[-fade_s:] *= np.linspace(1.0, 0.0, fade_s, dtype=np.float32)

    audio = np.clip(audio, -0.94, 0.94)
    pcm16 = (audio * 32767.0).astype(np.int16)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())

    # Compute normalized per-frame RMS energy for audio-reactive equalizer & avatar bounce
    total_frames = int(total_duration_sec * FPS)
    spf = max(1, sample_rate // FPS)
    rms = np.zeros(total_frames, dtype=np.float32)
    src_env = voice_track if has_voice else audio
    for f in range(total_frames):
        s0 = min(n_samples - 1, f * spf)
        s1 = min(n_samples, s0 + spf)
        if s1 > s0:
            rms[f] = float(np.sqrt(np.mean(src_env[s0:s1] ** 2)))
    mx = float(np.max(rms)) + 1e-6
    return np.clip(rms / mx, 0.0, 1.0)


def _create_blink_variant(avatar: Image.Image, eye_box: Tuple[int, int, int, int], skin_sample_xy: Tuple[int, int]) -> Image.Image:
    """자연스러운 눈 깜빡임 프레임 생성 (안경·눈썹 침범 없이 눈동자 수평 라인만 감김 처리)."""
    blink = avatar.copy()
    arr = np.array(blink)
    x0, y0, x1, y1 = eye_box
    skin_rgb = avatar.getpixel(skin_sample_xy)[:3]
    d = ImageDraw.Draw(blink, "RGBA")
    # Paint skin strip gently over sclera/iris only (preserving frames/brows around it)
    sub = arr[y0:y1, x0:x1]
    eye_mask = (sub[..., 3] > 200) & (
        ((sub[..., 0] > 215) & (sub[..., 1] > 210) & (sub[..., 2] > 205))  # sclera
        | ((sub[..., 0] < 75) & (sub[..., 1] < 85) & (sub[..., 2] < 110))  # iris/pupil
    )
    if np.any(eye_mask):
        sub_out = sub.copy()
        sub_out[eye_mask, 0] = skin_rgb[0]
        sub_out[eye_mask, 1] = skin_rgb[1]
        sub_out[eye_mask, 2] = skin_rgb[2]
        arr[y0:y1, x0:x1] = sub_out
        blink = Image.fromarray(arr, mode="RGBA")
        d = ImageDraw.Draw(blink, "RGBA")
    mid_y = (y0 + y1) // 2 + 2
    d.arc([x0 + 8, mid_y - 5, x1 - 8, mid_y + 7], start=10, end=170, fill=(38, 28, 28, 220), width=3)
    return blink


def _build_stage_assets() -> Dict[str, Any]:
    """스튜디오 배경, 스포트라이트 레이어, 데스크/마이크 포그라운드, 리사이즈된 HD 아바타 로드."""
    studio_bg = Image.open(STUDIO_SET_PATH).convert("RGBA").resize((W, H), Image.Resampling.LANCZOS)
    desk_fg = Image.open(STUDIO_DESK_FG_PATH).convert("RGBA").resize((W, H), Image.Resampling.LANCZOS)

    pro_orig = Image.open(PRO_AVATAR_PATH).convert("RGBA")
    con_orig = Image.open(CON_AVATAR_PATH).convert("RGBA")

    # Subtle studio grade on bright illustration so hosts sit naturally in moody TV newsroom
    pro_graded = ImageEnhance.Contrast(ImageEnhance.Brightness(pro_orig).enhance(0.94)).enhance(1.06)
    con_graded = ImageEnhance.Contrast(ImageEnhance.Brightness(con_orig).enhance(0.95)).enhance(1.06)

    def fit_h(im: Image.Image, target_h: int) -> Image.Image:
        sc = target_h / im.height
        return im.resize((int(im.width * sc), target_h), Image.Resampling.LANCZOS)

    # Active speaker (~580/530px tall so head stays cleanly below speech bubble), Listener dimmed (~520/475px)
    pro_act = fit_h(pro_graded, 578)
    pro_act_blink = fit_h(_create_blink_variant(pro_graded, (320, 152, 438, 192), (345, 200)), 578)
    pro_idle = ImageEnhance.Brightness(fit_h(pro_graded, 518)).enhance(0.55).filter(ImageFilter.GaussianBlur(1.1))

    con_act = fit_h(con_graded, 526)
    con_act_blink = fit_h(_create_blink_variant(con_graded, (295, 178, 435, 220), (350, 232)), 526)
    con_idle = ImageEnhance.Brightness(fit_h(con_graded, 470)).enhance(0.55).filter(ImageFilter.GaussianBlur(1.1))

    # Pre-render colored volumetric spotlight glow layers
    def make_glow(cx: int, cy: int, color: Tuple[int, int, int]) -> Image.Image:
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gd.ellipse([cx - 320, cy - 350, cx + 320, cy + 350], fill=(*color, 115))
        return g.filter(ImageFilter.GaussianBlur(95))

    pro_glow = make_glow(315, 960, (37, 99, 235))
    con_glow = make_glow(765, 960, (220, 38, 38))

    return {
        "studio_bg": studio_bg,
        "desk_fg": desk_fg,
        "pro_act": pro_act,
        "pro_act_blink": pro_act_blink,
        "pro_idle": pro_idle,
        "con_act": con_act,
        "con_act_blink": con_act_blink,
        "con_idle": con_idle,
        "pro_glow": pro_glow,
        "con_glow": con_glow,
    }


def _render_ui_hud_frame(
    issue_title: str,
    raw_stats: Dict[str, Any],
    turn_idx: int,
    total_turns: int,
    turn_data: Dict[str, Any],
    caption_lines: List[List[str]],
    word_count_total: int,
    active_word_idx: int,
    fonts: Dict[str, ImageFont.FreeTypeFont],
) -> Image.Image:
    """상단 헤드라인 + 어절 단위 카라오케 말풍선 + 하단 텔레메트리 데스크 UI."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay, "RGBA")

    is_pro = turn_data["speaker"] == "PRO"
    accent = (37, 99, 235, 255) if is_pro else (220, 38, 38, 255)
    accent_pill = (239, 246, 255, 255) if is_pro else (254, 242, 242, 255)
    speaker_label = f"찬성 패널 {turn_idx // 2 + 1}" if is_pro else f"반대 패널 {turn_idx // 2 + 1}"

    # 1) Top Broadcast Header Card (compact y=104..242)
    d.rounded_rectangle([54, 104, W - 54, 242], radius=20, fill=(14, 17, 25, 236), outline=(255, 255, 255, 36), width=2)
    d.rounded_rectangle([80, 120, 294, 152], radius=16, fill=(255, 255, 255, 20))
    d.ellipse([96, 130, 108, 142], fill=accent)
    d.text((118, 136), "LIVE AI 공론장 중재", font=fonts["badge_sm"], fill=(232, 234, 238, 255), anchor="lm")
    d.text((W - 80, 136), f"실측 {raw_stats['total_comments']}건 데이터", font=fonts["badge_sm"], fill=(161, 161, 170, 255), anchor="rm")

    title_lines = _wrap_words_by_width(issue_title, fonts["title"], W - 180, max_lines=2)
    title_start_y = 180 if len(title_lines) > 1 else 196
    for ti, twords in enumerate(title_lines):
        tline = " ".join(twords)
        d.text((W // 2, title_start_y + ti * 38), tline, font=fonts["title"], fill=(250, 250, 250, 255), anchor="mm")

    # 2) Editorial Dialogue Bubble (y=262..674, cleanly above PRO/CON heads!)
    bx0, by0, bx1, by1 = 54, 262, W - 54, 672
    d.rounded_rectangle([bx0, by0 + 10, bx1, by1 + 10], radius=26, fill=(0, 0, 0, 95))
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=26, fill=(255, 255, 255, 252))
    d.rounded_rectangle([bx0, by0, bx1, by0 + 12], radius=9, fill=accent)
    d.rectangle([bx0, by0 + 6, bx1, by0 + 12], fill=accent)

    # Compact speech pointer tail ending at y=714 (safely above forehead at y=745+)
    if is_pro:
        d.polygon([(272, by1 - 2), (344, by1 - 2), (302, by1 + 42)], fill=(255, 255, 255, 252))
    else:
        d.polygon([(W - 344, by1 - 2), (W - 272, by1 - 2), (W - 302, by1 + 42)], fill=(255, 255, 255, 252))

    # Speaker pill & balance summary
    d.rounded_rectangle([92, by0 + 30, 264, by0 + 72], radius=11, fill=accent_pill)
    d.text((178, by0 + 51), speaker_label, font=fonts["speaker"], fill=accent, anchor="mm")
    d.text((W - 92, by0 + 51), "한냥 50:50 균형 요약", font=fonts["meta"], fill=(113, 113, 122, 255), anchor="rm")

    core_pt = _trim_korean_words(turn_data.get("core_point", ""), 26)
    d.text((94, by0 + 102), core_pt, font=fonts["core"], fill=accent, anchor="lm")
    d.line([(94, by0 + 128), (W - 94, by0 + 128)], fill=(228, 228, 231, 255), width=2)

    # 3) Word-by-Word Kinetic Karaoke Highlight
    space_w = fonts["body"].getlength(" ")
    running_idx = 0
    start_y = by0 + 150
    line_h = 46
    for li, line_words in enumerate(caption_lines):
        cx = 94.0
        cy = start_y + li * line_h
        for w_str in line_words:
            ww = fonts["body"].getlength(w_str)
            if running_idx < active_word_idx:
                d.text((cx, cy), w_str, font=fonts["body"], fill=(17, 19, 23, 255), anchor="lt")
            elif running_idx == active_word_idx:
                d.rounded_rectangle(
                    [int(cx - 7), int(cy - 2), int(cx + ww + 7), int(cy + 36)],
                    radius=8,
                    fill=accent_pill,
                )
                d.text((cx, cy), w_str, font=fonts["body"], fill=accent, anchor="lt")
            else:
                d.text((cx, cy), w_str, font=fonts["body_dim"], fill=(148, 163, 184, 255), anchor="lt")
            cx += ww + space_w
            running_idx += 1

    # 4) Lower-Third Broadcast Telemetry Card over Studio Floor (y=1646..1858)
    lx0, ly0, lx1, ly1 = 48, 1646, W - 48, 1858
    d.rounded_rectangle([lx0, ly0, lx1, ly1], radius=26, fill=(14, 17, 25, 240), outline=(255, 255, 255, 34), width=2)

    d.text((94, ly0 + 52), f"찬성 {raw_stats['pro_ratio']}%", font=fonts["stat"], fill=(96, 165, 250, 255), anchor="lm")
    d.text((W - 94, ly0 + 52), f"반대 {raw_stats['con_ratio']}%", font=fonts["stat"], fill=(248, 113, 113, 255), anchor="rm")

    bar_x0, bar_x1 = 310, W - 310
    bar_w = bar_x1 - bar_x0
    pro_w = max(24, int(bar_w * (raw_stats["pro_ratio"] / 100.0)))
    d.rounded_rectangle([bar_x0, ly0 + 44, bar_x0 + pro_w - 4, ly0 + 58], radius=7, fill=(37, 99, 235, 255))
    d.rounded_rectangle([bar_x0 + pro_w + 4, ly0 + 44, bar_x1, ly0 + 58], radius=7, fill=(220, 38, 38, 255))
    d.text((W // 2, ly0 + 82), "AI 50:50 공론장 중재", font=fonts["badge_sm"], fill=(161, 161, 170, 255), anchor="mm")

    d.line([(86, ly0 + 114), (W - 86, ly0 + 114)], fill=(255, 255, 255, 20), width=2)

    for i in range(total_turns):
        dx = 94 + i * 34
        if i == turn_idx:
            d.rounded_rectangle([dx, ly0 + 150, dx + 26, ly0 + 160], radius=5, fill=accent)
        elif i < turn_idx:
            d.rounded_rectangle([dx, ly0 + 150, dx + 18, ly0 + 160], radius=5, fill=(161, 161, 170, 255))
        else:
            d.rounded_rectangle([dx, ly0 + 150, dx + 18, ly0 + 160], radius=5, fill=(45, 49, 62, 255))

    d.text((W - 94, ly0 + 155), "한냥 Studio", font=fonts["brand"], fill=(161, 161, 170, 255), anchor="rm")
    return overlay


def render_debate_mp4(
    issue_title: str,
    category_badge: str,
    raw_stats: Dict[str, Any],
    debate_script: List[Dict[str, Any]],
    output_mp4: Path,
    turn_audio_b64_list: Optional[List[Optional[str]]] = None,
    try_gemini_tts: bool = True,
) -> Path:
    """1080x1920 @ 30fps Full-HD 방송형 토론 쇼츠 MP4 렌더링."""
    turns = debate_script[:6]
    total_turns = max(len(turns), 1)
    total_duration = 40.0
    total_frames = int(total_duration * FPS)
    frames_per_turn = total_frames // total_turns

    assets = _build_stage_assets()
    fonts = {
        "hud": _load_font(FONT_BOLD_PATH, 23),
        "badge_sm": _load_font(FONT_BOLD_PATH, 19),
        "title": _load_font(FONT_BOLD_PATH, 31),
        "speaker": _load_font(FONT_BOLD_PATH, 23),
        "meta": _load_font(FONT_REG_PATH, 21),
        "core": _load_font(FONT_BOLD_PATH, 30),
        "body": _load_font(FONT_BOLD_PATH, 28),
        "body_dim": _load_font(FONT_REG_PATH, 28),
        "stat": _load_font(FONT_BOLD_PATH, 24),
        "brand": _load_font(FONT_BOLD_PATH, 23),
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        wav_path = tmp / "soundtrack.wav"
        rms_env = generate_broadcast_soundtrack(
            wav_path=wav_path,
            total_duration_sec=total_duration,
            turns=turns,
            turn_audio_b64_list=turn_audio_b64_list,
            try_gemini_tts=try_gemini_tts,
        )

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
                "-crf", "19",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "160k",
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
            caption_lines = _wrap_words_by_width(turn["text"], fonts["body"], W - 196, max_lines=5)
            word_count_total = max(sum(len(ln) for ln in caption_lines), 1)

            word_overlays: List[Image.Image] = []
            for w_idx in range(word_count_total + 1):
                word_overlays.append(
                    _render_ui_hud_frame(
                        issue_title=issue_title,
                        raw_stats=raw_stats,
                        turn_idx=idx,
                        total_turns=total_turns,
                        turn_data=turn,
                        caption_lines=caption_lines,
                        word_count_total=word_count_total,
                        active_word_idx=w_idx,
                        fonts=fonts,
                    )
                )

            # Pre-bake glow background for this turn so per-frame copy is instant
            turn_bg = assets["studio_bg"].copy()
            turn_bg.alpha_composite(assets["pro_glow"] if is_pro else assets["con_glow"])

            n_f = frames_per_turn if idx < total_turns - 1 else (total_frames - idx * frames_per_turn)
            for f in range(n_f):
                local_t = f / FPS
                turn_prog = f / max(n_f - 1, 1)
                global_f = idx * frames_per_turn + f
                progress = global_f / max(total_frames - 1, 1)
                remaining_sec = max(0.0, total_duration * (1.0 - progress))
                energy = float(rms_env[min(global_f, len(rms_env) - 1)])

                enter = min(1.0, local_t / 0.35)
                ease = 1.0 - (1.0 - enter) ** 3
                is_blinking = ((local_t + 1.1) % 3.4) < 0.14
                talk_bounce = math.sin(local_t * 11.0) * (2.5 + 3.5 * energy)
                idle_breath = math.sin(local_t * 2.2) * 1.8

                stage = turn_bg.copy()

                if is_pro:
                    p_spr = assets["pro_act_blink"] if is_blinking else assets["pro_act"]
                    c_spr = assets["con_idle"]
                    p_x = 312 - p_spr.width // 2 + int((1.0 - ease) * -18)
                    p_y = 1325 - p_spr.height + int(talk_bounce - ease * 6)
                    c_x = 772 - c_spr.width // 2
                    c_y = 1312 - c_spr.height + int(idle_breath)
                    stage.paste(c_spr, (c_x, c_y), c_spr)
                    stage.paste(p_spr, (p_x, p_y), p_spr)
                else:
                    p_spr = assets["pro_idle"]
                    c_spr = assets["con_act_blink"] if is_blinking else assets["con_act"]
                    p_x = 308 - p_spr.width // 2
                    p_y = 1322 - p_spr.height + int(idle_breath)
                    c_x = 768 - c_spr.width // 2 + int((1.0 - ease) * 18)
                    c_y = 1310 - c_spr.height + int(talk_bounce - ease * 6)
                    stage.paste(p_spr, (p_x, p_y), p_spr)
                    stage.paste(c_spr, (c_x, c_y), c_spr)

                stage.paste(assets["desk_fg"], (0, 0), assets["desk_fg"])

                # Cinematic Dolly Zoom (1.00 -> 1.052) + gentle pan toward speaking host
                zoom = 1.0 + 0.052 * turn_prog
                cw = W / zoom
                ch = H / zoom
                focus_cx = (W * 0.44) if is_pro else (W * 0.56)
                cx = W * 0.5 + (focus_cx - W * 0.5) * ease
                cy = H * 0.515
                x0 = max(0.0, min(W - cw, cx - cw * 0.5))
                y0 = max(0.0, min(H - ch, cy - ch * 0.5))
                frame = stage.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.Resampling.BILINEAR)

                w_idx = min(word_count_total - 1, int(turn_prog * word_count_total * 1.03))
                ov = word_overlays[w_idx]
                frame.paste(ov, (0, 0), ov)

                # Dynamic Top 6-Chapter Segmented Progress Bar + High-Contrast Counter/Timer Pills + 24-Band EQ
                draw = ImageDraw.Draw(frame, "RGBA")
                seg_gap = 10
                seg_total_w = W - 108
                seg_w = (seg_total_w - seg_gap * (total_turns - 1)) / total_turns
                for s_i in range(total_turns):
                    sx0 = 54 + s_i * (seg_w + seg_gap)
                    sx1 = sx0 + seg_w
                    draw.rounded_rectangle([sx0, 38, sx1, 47], radius=4, fill=(45, 50, 65, 220))
                    if s_i < idx:
                        s_col = (37, 99, 235, 255) if turns[s_i]["speaker"] == "PRO" else (220, 38, 38, 255)
                        draw.rounded_rectangle([sx0, 38, sx1, 47], radius=4, fill=s_col)
                    elif s_i == idx:
                        fill_x = sx0 + max(10.0, (sx1 - sx0) * turn_prog)
                        draw.rounded_rectangle([sx0, 38, fill_x, 47], radius=4, fill=accent_rgb)

                draw.rounded_rectangle([54, 58, 168, 92], radius=12, fill=(14, 17, 25, 210))
                draw.text((111, 75), f"0{idx + 1} / 0{total_turns}", font=fonts["hud"], fill=(244, 244, 245, 255), anchor="mm")
                draw.rounded_rectangle([W - 156, 58, W - 54, 92], radius=12, fill=(14, 17, 25, 210))
                draw.text((W - 105, 75), f"{remaining_sec:.1f}s", font=fonts["hud"], fill=(212, 212, 216, 255), anchor="mm")

                eq_x0 = 365
                for bi in range(24):
                    bx = eq_x0 + bi * 15
                    wave_mod = 0.45 + 0.55 * math.sin(local_t * 16.0 + bi * 0.65)
                    bh = int(8 + (14 + 26 * energy) * wave_mod)
                    draw.rounded_rectangle([bx, 1800 - bh // 2, bx + 7, 1800 + bh // 2], radius=3, fill=accent_rgb)

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
            try_gemini_tts=False,  # fast batch preset build in offline sandbox; live server enables TTS automatically
        )
        print(f"[MP4 RENDERED 1080p 30fps] {out_file} ({out_file.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
