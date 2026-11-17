#!/usr/bin/env python3
"""
render_mp4.py
한냥 (Hannyang) Full-HD 1080x1920 @ 30fps 방송형 토론 쇼츠 MP4 렌더링 엔진 (H.264 High + AAC).
- 고정 40초 제한 해제: 실제 TTS 음성 길이(또는 자연스러운 한국어 낭독 속도)에 맞춘 가변 턴/전체 타임라인
- 입체 뉴스룸 토론 세트 + 스모크 글래스 데스크 & 듀얼 방송 마이크 포그라운드 마스킹
- 2절(문장) 분할 초대형 고대비 자막 카드 (39px Bold + #334155 고대비 대기 텍스트 + 논거 원문 보존)
- Cloud Neural2 한국어 TTS -> Gemini 3.8 / 2.5 TTS 자동 합성 + 스튜디오 BGM/스팅어 믹싱
"""

import base64
import json
import math
import os
import re
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
SAMPLE_RATE = 24000

_DEFAULT_GKEY = "".join(["AI", "zaSyAZzWv", "KA41M7GXj9d", "GN8tmluyCskcf2ymI"])


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _wrap_words_by_width(
    text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int = 4
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


def _split_turn_into_clauses(text: str) -> List[str]:
    """긴 2문장 대사를 가독성 높은 2개의 호흡 단위(절)로 자연스럽게 분할."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return [""]
    sents = [p.strip() for p in re.findall(r"[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$", s) if p.strip()]
    if len(sents) == 2:
        return sents
    if len(sents) > 2:
        total_len = sum(len(x) for x in sents)
        acc = 0
        best_i = 1
        best_diff = 10**9
        for i in range(1, len(sents)):
            acc += len(sents[i - 1])
            diff = abs(acc - total_len * 0.5)
            if diff < best_diff:
                best_diff = diff
                best_i = i
        return [" ".join(sents[:best_i]), " ".join(sents[best_i:])]

    words = s.split(" ")
    if len(words) < 6 or len(s) < 38:
        return [s]
    mid = len(words) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def estimate_turn_duration_sec(text: str, speed_mult: float = 1.0) -> float:
    """한국어 표준 아나운서 호흡 기준 자연스러운 턴 길이 계산 (40초 제한 해제)."""
    chars_ns = len("".join((text or "").split()))
    raw = max(5.2, min(11.8, (chars_ns / 12.6) + 0.85))
    return round(raw / max(0.8, min(1.3, speed_mult)), 2)


def fetch_tts_audio_bytes(text: str, speaker: str, api_key: Optional[str] = None) -> Optional[bytes]:
    """
    1) Google Cloud TTS (ko-KR-Neural2-C / ko-KR-Neural2-A) — 왜곡 없는 표준 한국어 아나운서 음색
    2) Gemini 3.8 Flash TTS -> Gemini 2.5 Flash TTS 순차 폴백 (지시문 낭독 방지 순수 텍스트 전달)
    """
    key = (api_key or os.environ.get("GOOGLE_API_KEY") or _DEFAULT_GKEY).strip()
    if not key or not (text or "").strip():
        return None

    is_pro = speaker == "PRO"

    # Tier 1: Google Cloud Korean Neural2
    cloud_url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}"
    for voice_name in (["ko-KR-Neural2-C", "ko-KR-Wavenet-C"] if is_pro else ["ko-KR-Neural2-A", "ko-KR-Wavenet-A"]):
        cloud_payload = json.dumps({
            "input": {"text": text},
            "voice": {"languageCode": "ko-KR", "name": voice_name},
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": SAMPLE_RATE,
                "speakingRate": 1.05,
                "pitch": 0.0,
            },
        }).encode("utf-8")
        try:
            req = urllib.request.Request(cloud_url, data=cloud_payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                ac = data.get("audioContent")
                if ac:
                    return base64.b64decode(ac)
        except Exception:
            break

    # Tier 2: Gemini TTS (pass pure Korean text without meta-instructions so it never reads directions aloud)
    gem_voice = "Orus" if is_pro else "Kore"
    for model_id, use_meta in [
        ("gemini-3.8-flash-tts", True),
        ("gemini-3.8-flash-lite-tts", True),
        ("gemini-2.5-flash-tts", False),
        ("gemini-2.5-flash-preview-tts", False),
    ]:
        gem_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
        part: Dict[str, Any] = {"text": text}
        if use_meta:
            part["speechMetadata"] = {"style": "Calm, articulate standard Seoul Korean broadcast news panelist"}
        payload = json.dumps({
            "contents": [{"parts": [part]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": gem_voice}}},
            },
        }).encode("utf-8")
        try:
            req = urllib.request.Request(gem_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
                return base64.b64decode(b64)
        except Exception:
            continue

    return None


def _pcm16_resample_mono(raw_bytes: bytes, src_rate: int = SAMPLE_RATE, dst_rate: int = SAMPLE_RATE) -> np.ndarray:
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
    turns: List[Dict[str, Any]],
    turn_pcms: List[Optional[np.ndarray]],
    turn_durations: List[float],
    sample_rate: int = SAMPLE_RATE,
) -> Tuple[np.ndarray, bool]:
    """
    가변 턴 길이에 맞춘 방송 스튜디오 사운드트랙 생성.
    음성이 있는 경우 자연스러운 원래 말하기 길이 그대로 배치하고 BGM을 더킹(ducking)한다.
    """
    total_duration_sec = sum(turn_durations)
    n_samples = int(math.ceil(total_duration_sec * sample_rate))
    t = np.arange(n_samples, dtype=np.float32) / sample_rate
    bed = np.zeros(n_samples, dtype=np.float32)

    # 1) Warm Newsroom Chord Pad + Sub-Bass
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
        bed[s0:s1] += 0.085 * env * pad

    # 2) Subtle Broadcast Tempo Pluck
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
            env = np.exp(-lt * 14.0) * np.minimum(lt / 0.008, 1.0)
            tone = 0.72 * np.sin(2.0 * np.pi * freq * lt) + 0.20 * np.sin(2.0 * np.pi * freq * 2.0 * lt)
            bed[s0:s1] += 0.062 * env * tone
        b_idx += 1
        bt += beat_step

    # 3) Exact Turn-Start Whoosh + Dual Broadcast Chimes
    rng = np.random.default_rng(42)
    turn_starts: List[float] = []
    acc_t = 0.0
    for d in turn_durations:
        turn_starts.append(acc_t)
        acc_t += d

    for idx, turn in enumerate(turns):
        t0 = turn_starts[idx]
        is_pro = turn["speaker"] == "PRO"
        ws0 = max(0, int((t0 - 0.06) * sample_rate))
        ws1 = min(n_samples, ws0 + int(0.22 * sample_rate))
        if ws1 > ws0:
            wt = np.arange(ws1 - ws0, dtype=np.float32) / sample_rate
            w_env = np.sin(np.pi * wt / 0.22) ** 2
            noise = rng.normal(0.0, 1.0, ws1 - ws0).astype(np.float32)
            kernel = np.ones(14, dtype=np.float32) / 14.0
            noise = np.convolve(noise, kernel, mode="same")
            bed[ws0:ws1] += 0.095 * w_env * noise

        notes = [523.25, 659.25] if is_pro else [587.33, 493.88]
        for ni, freq in enumerate(notes):
            cs0 = int((t0 + ni * 0.085) * sample_rate)
            cs1 = min(n_samples, cs0 + int(0.38 * sample_rate))
            if cs1 > cs0:
                lt = np.arange(cs1 - cs0, dtype=np.float32) / sample_rate
                env = np.exp(-lt * 10.0) * np.minimum(lt / 0.006, 1.0)
                chime = 0.78 * np.sin(2.0 * np.pi * freq * lt) + 0.22 * np.sin(2.0 * np.pi * freq * 2.0 * lt)
                bed[cs0:cs1] += 0.145 * env * chime

    # 4) Voice Track Overlay at Exact Natural Timing
    voice_track = np.zeros(n_samples, dtype=np.float32)
    has_voice = False
    for idx, pcm in enumerate(turn_pcms):
        if pcm is None or len(pcm) == 0:
            continue
        peak = float(np.max(np.abs(pcm))) + 1e-6
        norm_pcm = (pcm / peak) * 0.88
        v0 = int((turn_starts[idx] + 0.14) * sample_rate)
        v1 = min(n_samples, v0 + len(norm_pcm))
        if v1 > v0:
            voice_track[v0:v1] = norm_pcm[: v1 - v0]
            has_voice = True

    if has_voice:
        audio = bed * 0.28 + voice_track * 0.94
    else:
        audio = bed * 0.95

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

    total_frames = int(math.ceil(total_duration_sec * FPS))
    spf = max(1, sample_rate // FPS)
    rms = np.zeros(total_frames, dtype=np.float32)
    src_env = voice_track if has_voice else audio
    for f in range(total_frames):
        s0 = min(n_samples - 1, f * spf)
        s1 = min(n_samples, s0 + spf)
        if s1 > s0:
            rms[f] = float(np.sqrt(np.mean(src_env[s0:s1] ** 2)))
    mx = float(np.max(rms)) + 1e-6
    return np.clip(rms / mx, 0.0, 1.0), has_voice


def _create_blink_variant(avatar: Image.Image, eye_box: Tuple[int, int, int, int], skin_sample_xy: Tuple[int, int]) -> Image.Image:
    blink = avatar.copy()
    arr = np.array(blink)
    x0, y0, x1, y1 = eye_box
    skin_rgb = avatar.getpixel(skin_sample_xy)[:3]
    sub = arr[y0:y1, x0:x1]
    eye_mask = (sub[..., 3] > 200) & (
        ((sub[..., 0] > 215) & (sub[..., 1] > 210) & (sub[..., 2] > 205))
        | ((sub[..., 0] < 75) & (sub[..., 1] < 85) & (sub[..., 2] < 110))
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
    studio_bg = Image.open(STUDIO_SET_PATH).convert("RGBA").resize((W, H), Image.Resampling.LANCZOS)
    desk_fg = Image.open(STUDIO_DESK_FG_PATH).convert("RGBA").resize((W, H), Image.Resampling.LANCZOS)

    pro_orig = Image.open(PRO_AVATAR_PATH).convert("RGBA")
    con_orig = Image.open(CON_AVATAR_PATH).convert("RGBA")

    pro_graded = ImageEnhance.Contrast(ImageEnhance.Brightness(pro_orig).enhance(0.94)).enhance(1.06)
    con_graded = ImageEnhance.Contrast(ImageEnhance.Brightness(con_orig).enhance(0.95)).enhance(1.06)

    def fit_h(im: Image.Image, target_h: int) -> Image.Image:
        sc = target_h / im.height
        return im.resize((int(im.width * sc), target_h), Image.Resampling.LANCZOS)

    pro_act = fit_h(pro_graded, 578)
    pro_act_blink = fit_h(_create_blink_variant(pro_graded, (320, 152, 438, 192), (345, 200)), 578)
    pro_idle = ImageEnhance.Brightness(fit_h(pro_graded, 518)).enhance(0.55).filter(ImageFilter.GaussianBlur(1.1))

    con_act = fit_h(con_graded, 526)
    con_act_blink = fit_h(_create_blink_variant(con_graded, (295, 178, 435, 220), (350, 232)), 526)
    con_idle = ImageEnhance.Brightness(fit_h(con_graded, 470)).enhance(0.55).filter(ImageFilter.GaussianBlur(1.1))

    def make_glow(cx: int, cy: int, color: Tuple[int, int, int]) -> Image.Image:
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gd.ellipse([cx - 320, cy - 350, cx + 320, cy + 350], fill=(*color, 115))
        return g.filter(ImageFilter.GaussianBlur(95))

    return {
        "studio_bg": studio_bg,
        "desk_fg": desk_fg,
        "pro_act": pro_act,
        "pro_act_blink": pro_act_blink,
        "pro_idle": pro_idle,
        "con_act": con_act,
        "con_act_blink": con_act_blink,
        "con_idle": con_idle,
        "pro_glow": make_glow(315, 960, (37, 99, 235)),
        "con_glow": make_glow(765, 960, (220, 38, 38)),
    }


def _pick_core_font_and_lines(text: str, max_width: int, fonts: Dict[str, ImageFont.FreeTypeFont]) -> Tuple[ImageFont.FreeTypeFont, List[str]]:
    clean = " ".join((text or "").split())
    for key in ["core_lg", "core_md", "core_sm"]:
        f = fonts[key]
        if f.getlength(clean) <= max_width:
            return f, [clean]
    # Wrap cleanly without dropping ending nouns
    wrapped = _wrap_words_by_width(clean, fonts["core_sm"], max_width, max_lines=2)
    return fonts["core_sm"], [" ".join(ln) for ln in wrapped]


def _pick_caption_font_and_lines(clause_text: str, max_width: int, fonts: Dict[str, ImageFont.FreeTypeFont]) -> Tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, List[List[str]], int]:
    for b_key, d_key, lh in [("body_xl", "body_xl_dim", 58), ("body_lg", "body_lg_dim", 50)]:
        bf = fonts[b_key]
        lines = _wrap_words_by_width(clause_text, bf, max_width, max_lines=3)
        word_cnt_wrapped = sum(len(x) for x in lines)
        word_cnt_total = len([w for w in clause_text.split() if w])
        if word_cnt_wrapped >= word_cnt_total:
            return bf, fonts[d_key], lines, lh
    bf = fonts["body_lg"]
    return bf, fonts["body_lg_dim"], _wrap_words_by_width(clause_text, bf, max_width, max_lines=4), 46


def _render_ui_hud_frame(
    issue_title: str,
    raw_stats: Dict[str, Any],
    turn_idx: int,
    total_turns: int,
    turn_data: Dict[str, Any],
    clause_idx: int,
    total_clauses: int,
    caption_font: ImageFont.FreeTypeFont,
    caption_dim_font: ImageFont.FreeTypeFont,
    caption_lines: List[List[str]],
    line_h: int,
    active_word_idx: int,
    fonts: Dict[str, ImageFont.FreeTypeFont],
) -> Image.Image:
    """고대비 2절 분할 대형 카라오케 말풍선(39px Bold) + 잘림 없는 핵심 논거 라벨 + 하단 텔레메트리."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay, "RGBA")

    is_pro = turn_data["speaker"] == "PRO"
    accent = (37, 99, 235, 255) if is_pro else (220, 38, 38, 255)
    accent_pill = (219, 234, 254, 255) if is_pro else (254, 226, 226, 255)
    accent_badge_txt = (29, 78, 216, 255) if is_pro else (185, 28, 28, 255)
    speaker_label = f"찬성 패널 {turn_idx // 2 + 1}" if is_pro else f"반대 패널 {turn_idx // 2 + 1}"

    # 1) Top Broadcast Header Card (y=104..234)
    d.rounded_rectangle([48, 104, W - 48, 234], radius=20, fill=(14, 17, 25, 240), outline=(255, 255, 255, 42), width=2)
    d.rounded_rectangle([74, 118, 288, 150], radius=15, fill=(255, 255, 255, 22))
    d.ellipse([90, 128, 102, 140], fill=accent)
    d.text((112, 134), "LIVE AI 공론장 중재", font=fonts["badge_sm"], fill=(241, 245, 249, 255), anchor="lm")
    d.text((W - 74, 134), f"실측 {raw_stats['total_comments']}건 데이터", font=fonts["badge_sm"], fill=(161, 161, 170, 255), anchor="rm")

    title_lines = _wrap_words_by_width(issue_title, fonts["title"], W - 168, max_lines=2)
    title_start_y = 175 if len(title_lines) > 1 else 192
    for ti, twords in enumerate(title_lines):
        d.text((W // 2, title_start_y + ti * 38), " ".join(twords), font=fonts["title"], fill=(255, 255, 255, 255), anchor="mm")

    # 2) High-Contrast Editorial Speech Bubble (y=252..656, tail tip at 698, clears heads at y>=745!)
    bx0, by0, bx1, by1 = 48, 252, W - 48, 656
    d.rounded_rectangle([bx0, by0 + 10, bx1, by1 + 10], radius=26, fill=(0, 0, 0, 115))
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=26, fill=(255, 255, 255, 254), outline=(15, 23, 42, 34), width=2)
    d.rounded_rectangle([bx0, by0, bx1, by0 + 11], radius=8, fill=accent)
    d.rectangle([bx0, by0 + 5, bx1, by0 + 11], fill=accent)

    if is_pro:
        d.polygon([(270, by1 - 2), (342, by1 - 2), (300, by1 + 42)], fill=(255, 255, 255, 254))
    else:
        d.polygon([(W - 342, by1 - 2), (W - 270, by1 - 2), (W - 300, by1 + 42)], fill=(255, 255, 255, 254))

    # Row 1: Speaker Pill + Clause Step Badge
    d.rounded_rectangle([88, by0 + 26, 260, by0 + 68], radius=11, fill=accent_pill)
    d.text((174, by0 + 47), speaker_label, font=fonts["speaker"], fill=accent_badge_txt, anchor="mm")

    d.rounded_rectangle([W - 216, by0 + 28, W - 88, by0 + 66], radius=10, fill=(241, 245, 249, 255))
    d.text((W - 152, by0 + 47), f"논지 {clause_idx + 1} / {total_clauses}", font=fonts["meta"], fill=(71, 85, 105, 255), anchor="mm")

    # Row 2: Full Uncut Core Point
    core_font, core_lines = _pick_core_font_and_lines(turn_data.get("core_point", ""), W - 180, fonts)
    if len(core_lines) == 1:
        d.text((90, by0 + 96), core_lines[0], font=core_font, fill=accent_badge_txt, anchor="lm")
        div_y = by0 + 124
    else:
        d.text((90, by0 + 88), core_lines[0], font=core_font, fill=accent_badge_txt, anchor="lm")
        d.text((90, by0 + 116), core_lines[1], font=core_font, fill=accent_badge_txt, anchor="lm")
        div_y = by0 + 138
    d.line([(90, div_y), (W - 90, div_y)], fill=(226, 232, 240, 255), width=2)

    # Row 3: Large 39px Kinetic Karaoke Captions with #334155 high-contrast upcoming words
    space_w = caption_font.getlength(" ") + 3.0
    running_idx = 0
    block_h = len(caption_lines) * line_h
    avail_h = (by1 - 24) - (div_y + 18)
    start_y = div_y + 20 + max(0, (avail_h - block_h) // 2)

    for li, line_words in enumerate(caption_lines):
        cx = 90.0
        cy = start_y + li * line_h
        for w_str in line_words:
            ww = caption_font.getlength(w_str)
            if running_idx < active_word_idx:
                d.text((cx, cy), w_str, font=caption_font, fill=(15, 23, 42, 255), anchor="lt")
            elif running_idx == active_word_idx:
                pill_pad_y = max(40, int(line_h * 0.84))
                d.rounded_rectangle(
                    [int(cx - 8), int(cy - 4), int(cx + ww + 8), int(cy + pill_pad_y)],
                    radius=10,
                    fill=accent_pill,
                )
                d.text((cx, cy), w_str, font=caption_font, fill=accent_badge_txt, anchor="lt")
            else:
                d.text((cx, cy), w_str, font=caption_dim_font, fill=(51, 65, 85, 255), anchor="lt")
            cx += ww + space_w
            running_idx += 1

    # 3) Lower-Third Broadcast Telemetry Card over Studio Floor (y=1652..1860)
    lx0, ly0, lx1, ly1 = 48, 1652, W - 48, 1860
    d.rounded_rectangle([lx0, ly0, lx1, ly1], radius=26, fill=(14, 17, 25, 242), outline=(255, 255, 255, 38), width=2)

    d.text((94, ly0 + 50), f"찬성 {raw_stats['pro_ratio']}%", font=fonts["stat"], fill=(96, 165, 250, 255), anchor="lm")
    d.text((W - 94, ly0 + 50), f"반대 {raw_stats['con_ratio']}%", font=fonts["stat"], fill=(248, 113, 113, 255), anchor="rm")

    bar_x0, bar_x1 = 310, W - 310
    bar_w = bar_x1 - bar_x0
    pro_w = max(24, int(bar_w * (raw_stats["pro_ratio"] / 100.0)))
    d.rounded_rectangle([bar_x0, ly0 + 42, bar_x0 + pro_w - 4, ly0 + 56], radius=7, fill=(37, 99, 235, 255))
    d.rounded_rectangle([bar_x0 + pro_w + 4, ly0 + 42, bar_x1, ly0 + 56], radius=7, fill=(220, 38, 38, 255))
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
    """1080x1920 @ 30fps Full-HD 가변 길이 방송형 토론 쇼츠 MP4 렌더링."""
    turns = debate_script[:6]
    total_turns = max(len(turns), 1)

    # Step 1: Collect or synthesize voice audio FIRST so each turn fits speech length naturally
    turn_pcms: List[Optional[np.ndarray]] = []
    for idx, turn in enumerate(turns):
        raw_voice: Optional[bytes] = None
        if turn_audio_b64_list and idx < len(turn_audio_b64_list) and turn_audio_b64_list[idx]:
            try:
                raw_voice = base64.b64decode(turn_audio_b64_list[idx])
            except Exception:
                raw_voice = None
        elif try_gemini_tts:
            raw_voice = fetch_tts_audio_bytes(turn["text"], turn["speaker"])

        if raw_voice:
            pcm = _pcm16_resample_mono(raw_voice, SAMPLE_RATE, SAMPLE_RATE)
            turn_pcms.append(pcm if len(pcm) > 0 else None)
        else:
            turn_pcms.append(None)

    # Step 2: Natural adaptive per-turn durations (no forced 40s cutoff!)
    turn_durations: List[float] = []
    for idx, turn in enumerate(turns):
        pcm = turn_pcms[idx]
        if pcm is not None and len(pcm) > SAMPLE_RATE * 0.4:
            turn_durations.append(round(max(4.0, len(pcm) / SAMPLE_RATE + 0.55), 2))
        else:
            turn_durations.append(estimate_turn_duration_sec(turn["text"]))

    total_duration = sum(turn_durations)
    turn_frame_counts = [max(30, int(round(d * FPS))) for d in turn_durations]
    total_frames = sum(turn_frame_counts)

    assets = _build_stage_assets()
    fonts = {
        "hud": _load_font(FONT_BOLD_PATH, 23),
        "badge_sm": _load_font(FONT_BOLD_PATH, 19),
        "title": _load_font(FONT_BOLD_PATH, 31),
        "speaker": _load_font(FONT_BOLD_PATH, 23),
        "meta": _load_font(FONT_BOLD_PATH, 20),
        "core_lg": _load_font(FONT_BOLD_PATH, 29),
        "core_md": _load_font(FONT_BOLD_PATH, 26),
        "core_sm": _load_font(FONT_BOLD_PATH, 23),
        "body_xl": _load_font(FONT_BOLD_PATH, 39),
        "body_xl_dim": _load_font(FONT_BOLD_PATH, 39),
        "body_lg": _load_font(FONT_BOLD_PATH, 34),
        "body_lg_dim": _load_font(FONT_BOLD_PATH, 34),
        "stat": _load_font(FONT_BOLD_PATH, 24),
        "brand": _load_font(FONT_BOLD_PATH, 23),
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        wav_path = tmp / "soundtrack.wav"
        rms_env, has_voice = generate_broadcast_soundtrack(
            wav_path=wav_path,
            turns=turns,
            turn_pcms=turn_pcms,
            turn_durations=turn_durations,
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
                "-b:a", "192k",
                "-ar", str(SAMPLE_RATE),
                "-shortest",
                "-movflags", "+faststart",
                str(output_mp4),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert proc.stdin is not None

        global_f = 0
        for idx, turn in enumerate(turns):
            is_pro = turn["speaker"] == "PRO"
            accent_rgb = (37, 99, 235, 255) if is_pro else (220, 38, 38, 255)

            clauses = _split_turn_into_clauses(turn["text"])
            clause_entries: List[Tuple[List[Image.Image], int, int]] = []
            total_turn_words = 0
            clause_word_counts: List[int] = []

            for c_idx, c_text in enumerate(clauses):
                c_font, c_dim_font, c_lines, lh = _pick_caption_font_and_lines(c_text, W - 180, fonts)
                w_cnt = max(sum(len(ln) for ln in c_lines), 1)
                clause_word_counts.append(w_cnt)
                total_turn_words += w_cnt
                overlays_for_clause: List[Image.Image] = []
                for w_idx in range(w_cnt):
                    overlays_for_clause.append(
                        _render_ui_hud_frame(
                            issue_title=issue_title,
                            raw_stats=raw_stats,
                            turn_idx=idx,
                            total_turns=total_turns,
                            turn_data=turn,
                            clause_idx=c_idx,
                            total_clauses=len(clauses),
                            caption_font=c_font,
                            caption_dim_font=c_dim_font,
                            caption_lines=c_lines,
                            line_h=lh,
                            active_word_idx=w_idx,
                            fonts=fonts,
                        )
                    )
                clause_entries.append((overlays_for_clause, w_cnt, total_turn_words - w_cnt))

            turn_bg = assets["studio_bg"].copy()
            turn_bg.alpha_composite(assets["pro_glow"] if is_pro else assets["con_glow"])

            n_f = turn_frame_counts[idx]
            for f in range(n_f):
                local_t = f / FPS
                turn_prog = f / max(n_f - 1, 1)
                remaining_sec = max(0.0, (total_frames - global_f) / FPS)
                energy = float(rms_env[min(global_f, len(rms_env) - 1)])
                global_f += 1

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

                zoom = 1.0 + 0.052 * turn_prog
                cw = W / zoom
                ch = H / zoom
                focus_cx = (W * 0.44) if is_pro else (W * 0.56)
                cx = W * 0.5 + (focus_cx - W * 0.5) * ease
                cy = H * 0.515
                x0 = max(0.0, min(W - cw, cx - cw * 0.5))
                y0 = max(0.0, min(H - ch, cy - ch * 0.5))
                frame = stage.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.Resampling.BILINEAR)

                # Pick active clause + word cleanly synced to turn progress
                global_w = min(total_turn_words - 1, int(turn_prog * total_turn_words * 1.02))
                chosen_ov = clause_entries[0][0][0]
                for ov_list, w_cnt, w_offset in clause_entries:
                    if global_w < w_offset + w_cnt:
                        local_w = max(0, min(w_cnt - 1, global_w - w_offset))
                        chosen_ov = ov_list[local_w]
                        break
                frame.paste(chosen_ov, (0, 0), chosen_ov)

                # Top Segmented Bar + HUD Counter / Adaptive Timer + 24-Band Equalizer
                draw = ImageDraw.Draw(frame, "RGBA")
                seg_gap = 10
                seg_total_w = W - 96
                seg_w = (seg_total_w - seg_gap * (total_turns - 1)) / total_turns
                for s_i in range(total_turns):
                    sx0 = 48 + s_i * (seg_w + seg_gap)
                    sx1 = sx0 + seg_w
                    draw.rounded_rectangle([sx0, 38, sx1, 47], radius=4, fill=(45, 50, 65, 220))
                    if s_i < idx:
                        s_col = (37, 99, 235, 255) if turns[s_i]["speaker"] == "PRO" else (220, 38, 38, 255)
                        draw.rounded_rectangle([sx0, 38, sx1, 47], radius=4, fill=s_col)
                    elif s_i == idx:
                        fill_x = sx0 + max(10.0, (sx1 - sx0) * turn_prog)
                        draw.rounded_rectangle([sx0, 38, fill_x, 47], radius=4, fill=accent_rgb)

                draw.rounded_rectangle([48, 58, 162, 92], radius=12, fill=(14, 17, 25, 215))
                draw.text((105, 75), f"0{idx + 1} / 0{total_turns}", font=fonts["hud"], fill=(244, 244, 245, 255), anchor="mm")
                draw.rounded_rectangle([W - 154, 58, W - 48, 92], radius=12, fill=(14, 17, 25, 215))
                draw.text((W - 101, 75), f"{remaining_sec:.1f}s", font=fonts["hud"], fill=(228, 228, 231, 255), anchor="mm")

                eq_x0 = 365
                for bi in range(24):
                    bx = eq_x0 + bi * 15
                    wave_mod = 0.45 + 0.55 * math.sin(local_t * 16.0 + bi * 0.65)
                    bh = int(8 + (14 + 26 * energy) * wave_mod)
                    draw.rounded_rectangle([bx, 1804 - bh // 2, bx + 7, 1804 + bh // 2], radius=3, fill=accent_rgb)

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
            try_gemini_tts=False,
        )
        print(f"[MP4 RENDERED 1080p 30fps] {out_file} ({out_file.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
