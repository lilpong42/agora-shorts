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
    n = len(words)
    if n < 6 or len(s) < 36:
        return [s]

    lo = max(2, int(round(n * 0.33)))
    hi = min(n - 2, int(round(n * 0.68)))
    if lo > hi:
        mid = n // 2
        return [" ".join(words[:mid]), " ".join(words[mid:])]

    total_chars = sum(len(w) for w in words)
    best_idx = n // 2
    best_score = -10**9.0
    for i in range(lo, hi + 1):
        prev_w = words[i - 1]
        left_chars = sum(len(w) for w in words[:i])
        balance_pen = abs(left_chars - total_chars * 0.5) * 0.16
        sc = -balance_pen
        if prev_w.endswith(","):
            sc += 10.0
        elif re.search(r"(위해|보다|지만|으나|으며|므로|면서|도록|는데|거나|거든)$", prev_w):
            sc += 7.5
        elif len(prev_w) >= 2 and prev_w[-1] in ("은", "는"):
            sc += 3.5
        if sc > best_score:
            best_score = sc
            best_idx = i
    return [" ".join(words[:best_idx]), " ".join(words[best_idx:])]


def normalize_korean_for_tts(text: str) -> str:
    """TTS 발화 시 부호 오독·띄어쓰기 끊김을 방지하는 한국어 낭독 정규화."""
    s = text or ""
    s = re.sub(r"[·ㆍ]", " ", s)
    s = re.sub(r"([가-힣0-9A-Za-z])/([가-힣0-9A-Za-z])", r"\1 \2", s)
    s = re.sub(r'[“”"‘’\'「」『』\[\]]', "", s)
    s = re.sub(r"\(([^)]+)\)", r", \1, ", s)
    s = re.sub(r"\bPM\b", "피엠", s, flags=re.IGNORECASE)
    s = re.sub(r"\bGPS\b", "지피에스", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAI\b", "에이아이", s, flags=re.IGNORECASE)
    s = re.sub(r"\bSNS\b", "에스엔에스", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCCTV\b", "씨씨티비", s, flags=re.IGNORECASE)
    s = re.sub(r"(\d+)\s*%", r"\1퍼센트", s)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*pt\b", r"\1포인트", s, flags=re.IGNORECASE)
    s = re.sub(r"\.{2,}", ".", s)
    s = re.sub(r"\s*,\s*,\s*", ", ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _build_weighted_word_timeline(words: List[str]) -> List[Tuple[float, float]]:
    if not words:
        return [(0.0, 1.0)]
    weights: List[float] = []
    for w in words:
        core_len = max(1, len(re.sub(r"[^가-힣A-Za-z0-9]", "", w or "")))
        comma_pause = 1.5 if re.search(r"[,·]", w or "") else 0.0
        end_pause = 2.6 if re.search(r"[.!?]$", w or "") else 0.0
        weights.append(float(core_len) + comma_pause + end_pause)
    tot = sum(weights) or 1.0
    out: List[Tuple[float, float]] = []
    acc = 0.0
    for wt in weights:
        s0 = acc / tot
        acc += wt
        out.append((s0, acc / tot))
    return out


def _word_idx_for_ratio(timeline: List[Tuple[float, float]], ratio01: float) -> int:
    if not timeline:
        return 0
    clamped = max(0.0, min(0.9999, ratio01))
    for i, (_, end_r) in enumerate(timeline):
        if clamped < end_r or i == len(timeline) - 1:
            return i
    return 0


def _estimate_clause_duration_sec(clause_text: str, speed_mult: float = 1.0) -> float:
    spoken = normalize_korean_for_tts(clause_text)
    chars_ns = len(re.sub(r"\s+", "", spoken))
    pauses = len(re.findall(r"[,!?]", spoken)) * 0.16
    base = max(1.8, (chars_ns / 7.4) + 0.30 + pauses)
    return round(base / max(0.8, min(1.3, speed_mult)), 2)


def estimate_turn_duration_sec(text: str, speed_mult: float = 1.0) -> float:
    """한국어 표준 아나운서 호흡(약 7.4음절/초) 기준 자연스러운 턴 길이 계산."""
    clauses = _split_turn_into_clauses(text)
    tot = sum(_estimate_clause_duration_sec(c, speed_mult) for c in clauses) + 0.25
    return round(max(3.6, tot), 2)


def _analyze_pcm_clause_timing(
    pcm: Optional[np.ndarray],
    sample_rate: int,
    clauses: List[str],
    turn_dur_sec: float,
    lead_in_sec: float = 0.14,
) -> List[Tuple[float, float]]:
    """실제 음성 PCM의 20ms RMS 포락선과 무음 휴지 구간을 분석해 절(clause)별 [start, end] 시각을 반환."""
    safe_clauses = clauses or [""]
    n_clauses = len(safe_clauses)

    weights: List[float] = []
    for c in safe_clauses:
        sp = normalize_korean_for_tts(c)
        chars_ns = max(1, len(re.sub(r"\s+", "", sp)))
        pauses = len(re.findall(r"[,!?]", sp)) * 1.4
        weights.append(float(chars_ns) + pauses)
    tot_wt = sum(weights) or 1.0

    if pcm is None or len(pcm) < int(sample_rate * 0.25):
        usable_start = min(lead_in_sec, turn_dur_sec * 0.1)
        usable_end = max(usable_start + 0.5, turn_dur_sec - 0.18)
        span = usable_end - usable_start
        win_out: List[Tuple[float, float]] = []
        acc_w = 0.0
        for wt in weights:
            s0 = usable_start + (acc_w / tot_wt) * span
            acc_w += wt
            s1 = usable_start + (acc_w / tot_wt) * span
            win_out.append((s0, s1))
        return win_out

    dur_audio = len(pcm) / float(sample_rate)
    win_samples = max(1, int(sample_rate * 0.02))
    n_win = len(pcm) // win_samples
    if n_win < 12:
        win_out = []
        acc_w = 0.0
        for wt in weights:
            s0 = lead_in_sec + (acc_w / tot_wt) * dur_audio
            acc_w += wt
            s1 = lead_in_sec + (acc_w / tot_wt) * dur_audio
            win_out.append((s0, s1))
        return win_out

    trimmed = pcm[: n_win * win_samples].reshape(n_win, win_samples)
    rms = np.sqrt(np.mean(trimmed * trimmed, axis=1))
    peak_rms = float(np.max(rms)) if len(rms) else 0.0
    thr = max(peak_rms * 0.045, 0.004)

    first_w = 0
    while first_w < n_win - 1 and rms[first_w] < thr:
        first_w += 1
    last_w = n_win - 1
    while last_w > first_w + 1 and rms[last_w] < thr:
        last_w -= 1

    active_start = max(0.0, first_w * 0.02 - 0.04)
    active_end = min(dur_audio, max(active_start + 0.5, (last_w + 1) * 0.02 + 0.06))
    active_span = active_end - active_start

    if n_clauses == 1:
        return [(lead_in_sec + active_start, lead_in_sec + active_end)]

    boundaries = [active_start]
    cum_w = 0.0
    margin_sec = max(0.45, active_span * 0.16)
    for i in range(n_clauses - 1):
        cum_w += weights[i]
        expected_sec = active_start + (cum_w / tot_wt) * active_span
        lo_sec = max(boundaries[i] + 0.5, expected_sec - margin_sec)
        hi_sec = min(active_end - 0.5 * (n_clauses - 1 - i), expected_sec + margin_sec)
        w_lo = max(1, min(n_win - 2, int(math.floor(lo_sec / 0.02))))
        w_hi = max(w_lo, min(n_win - 2, int(math.ceil(hi_sec / 0.02))))
        exp_w = int(round(expected_sec / 0.02))

        best_w = exp_w
        best_sc = float("inf")
        for w in range(w_lo, w_hi + 1):
            local_mean = float(np.mean(rms[max(0, w - 2) : min(n_win, w + 3)]))
            dist_pen = abs(w - exp_w) * (peak_rms * 0.002)
            sc = local_mean + dist_pen
            if sc < best_sc:
                best_sc = sc
                best_w = w
        boundaries.append(max(boundaries[i] + 0.35, min(active_end - 0.35, best_w * 0.02)))
    boundaries.append(active_end)

    return [(lead_in_sec + boundaries[i], lead_in_sec + boundaries[i + 1]) for i in range(n_clauses)]


def _resolve_clause_and_word(
    local_t: float,
    word_timelines: List[List[Tuple[float, float]]],
    clause_windows: List[Tuple[float, float]],
) -> Tuple[int, int]:
    if not clause_windows:
        return 0, 0
    if local_t < clause_windows[0][0]:
        return 0, 0
    for ci, (s0, s1) in enumerate(clause_windows):
        next_s0 = clause_windows[ci + 1][0] if ci + 1 < len(clause_windows) else float("inf")
        tl = word_timelines[ci] if ci < len(word_timelines) else [(0.0, 1.0)]
        if local_t <= s1:
            r = (local_t - s0) / max(s1 - s0, 0.25)
            return ci, _word_idx_for_ratio(tl, r)
        if local_t < next_s0:
            return ci, max(0, len(tl) - 1)
    last_ci = len(clause_windows) - 1
    last_tl = word_timelines[last_ci] if last_ci < len(word_timelines) else [(0.0, 1.0)]
    return last_ci, max(0, len(last_tl) - 1)


_GEMINI_KO_VOICES_CACHE: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

PALETTE: Dict[str, Dict[str, Any]] = {
    "blue": {
        "accent": (37, 99, 235, 255),
        "pill": (219, 234, 254, 255),
        "txt": (29, 78, 216, 255),
        "glow": (37, 99, 235),
        "bar": (96, 165, 250, 255),
    },
    "red": {
        "accent": (220, 38, 38, 255),
        "pill": (254, 226, 226, 255),
        "txt": (185, 28, 28, 255),
        "glow": (220, 38, 38),
        "bar": (248, 113, 113, 255),
    },
    "violet": {
        "accent": (124, 58, 237, 255),
        "pill": (237, 233, 254, 255),
        "txt": (109, 40, 217, 255),
        "glow": (124, 58, 237),
        "bar": (167, 139, 250, 255),
    },
    "emerald": {
        "accent": (5, 150, 105, 255),
        "pill": (209, 250, 229, 255),
        "txt": (4, 120, 87, 255),
        "glow": (5, 150, 105),
        "bar": (52, 211, 153, 255),
    },
    "amber": {
        "accent": (217, 119, 6, 255),
        "pill": (254, 243, 199, 255),
        "txt": (180, 83, 9, 255),
        "glow": (217, 119, 6),
        "bar": (251, 191, 36, 255),
    },
}


def _get_turn_color_key(turn: Dict[str, Any]) -> str:
    ck = (turn.get("color") or "").strip().lower()
    if ck in PALETTE:
        return ck
    return "blue" if turn.get("speaker") == "PRO" else "red"


def _fetch_gemini_korean_voices(key: str) -> Tuple[Optional[str], Optional[str]]:
    if key in _GEMINI_KO_VOICES_CACHE:
        return _GEMINI_KO_VOICES_CACHE[key]
    pro_id: Optional[str] = None
    con_id: Optional[str] = None
    for qs in ("language_code=ko-KR&type=prebuilt&page_size=50", "language_code=ko-KR&page_size=50"):
        url = f"https://generativelanguage.googleapis.com/v1beta/voices?{qs}&key={key}"
        try:
            with urllib.request.urlopen(url, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            voices = data.get("voices") or []
            ko_list = [
                v for v in voices
                if not (v.get("languageCodes") or v.get("languageCode"))
                or any(str(l).lower().startswith("ko") for l in (v.get("languageCodes") or [v.get("languageCode")]))
            ]
            if ko_list:
                def pick_id(v: Dict[str, Any]) -> Optional[str]:
                    vid = v.get("voiceId") or re.sub(r"^voices/", "", v.get("name", ""))
                    return vid or None

                def is_male(v: Dict[str, Any]) -> bool:
                    desc = f"{v.get('gender', '')} {v.get('ssmlGender', '')} {v.get('displayName', '')} {v.get('name', '')}"
                    return bool(re.search(r"male|man|남", desc, re.I)) and not bool(re.search(r"female", desc, re.I))

                def is_female(v: Dict[str, Any]) -> bool:
                    desc = f"{v.get('gender', '')} {v.get('ssmlGender', '')} {v.get('displayName', '')} {v.get('name', '')}"
                    return bool(re.search(r"female|woman|여", desc, re.I))

                male_v = next((v for v in ko_list if is_male(v)), ko_list[0])
                female_v = next((v for v in ko_list if is_female(v) and v is not male_v), None) or next((v for v in ko_list if v is not male_v), ko_list[0])
                pro_id = pick_id(male_v)
                con_id = pick_id(female_v)
                break
        except Exception:
            continue
    _GEMINI_KO_VOICES_CACHE[key] = (pro_id, con_id)
    return pro_id, con_id


def _try_edge_tts_bytes(spoken_text: str, is_pro: bool) -> Optional[bytes]:
    """무료 Microsoft Edge Korean Neural 음성 (ko-KR-InJoonNeural / ko-KR-SunHiNeural) 폴백."""
    try:
        import asyncio
        import concurrent.futures
        import edge_tts  # type: ignore
    except Exception:
        return None

    voice = "ko-KR-InJoonNeural" if is_pro else "ko-KR-SunHiNeural"

    async def _run() -> bytes:
        comm = edge_tts.Communicate(spoken_text, voice)
        buf = bytearray()
        async for chunk in comm.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                buf.extend(chunk["data"])
        return bytes(buf)

    def _thread_entry() -> bytes:
        return asyncio.run(_run())

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            data = pool.submit(_thread_entry).result(timeout=8)
            return data if len(data) > 256 else None
    except Exception:
        return None


def fetch_tts_audio_bytes(text: str, speaker: str, api_key: Optional[str] = None) -> Optional[bytes]:
    """
    1) Google Cloud TTS (ko-KR-Neural2-C / ko-KR-Neural2-A, speakingRate=1.0)
    2) Edge TTS Korean Neural (ko-KR-InJoonNeural / ko-KR-SunHiNeural) — 무료 표준 한국어
    3) Gemini 3.8 Flash TTS 한국어 보이스 조회 후 합성 (외국인 억양 방지)
    """
    key = (api_key or os.environ.get("GOOGLE_API_KEY") or _DEFAULT_GKEY).strip()
    spoken_text = normalize_korean_for_tts(text)
    if not spoken_text:
        return None

    is_pro = speaker == "PRO"

    # Tier 1: Google Cloud Korean Neural2
    if key:
        cloud_url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}"
        for voice_name in (["ko-KR-Neural2-C", "ko-KR-Wavenet-C"] if is_pro else ["ko-KR-Neural2-A", "ko-KR-Wavenet-A"]):
            cloud_payload = json.dumps({
                "input": {"text": spoken_text},
                "voice": {"languageCode": "ko-KR", "name": voice_name},
                "audioConfig": {
                    "audioEncoding": "LINEAR16",
                    "sampleRateHertz": SAMPLE_RATE,
                    "speakingRate": 1.0,
                    "pitch": 0.0,
                },
            }).encode("utf-8")
            try:
                req = urllib.request.Request(cloud_url, data=cloud_payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    ac = data.get("audioContent")
                    if ac:
                        return base64.b64decode(ac)
            except Exception:
                break

    # Tier 2: Edge Korean Neural TTS
    edge_bytes = _try_edge_tts_bytes(spoken_text, is_pro)
    if edge_bytes:
        return edge_bytes

    # Tier 3: Gemini TTS (discover native Korean voices first, avoid Orus/Kore)
    if not key:
        return None
    pro_ko, con_ko = _fetch_gemini_korean_voices(key)
    ko_voice_id = pro_ko if is_pro else con_ko
    tries: List[Tuple[str, bool, Dict[str, Any]]] = []
    if ko_voice_id:
        tries.extend([
            ("gemini-3.8-flash-tts", True, {"voice": ko_voice_id}),
            ("gemini-3.8-flash-lite-tts", True, {"voice": ko_voice_id}),
        ])
    else:
        fallback_name = "Charon" if is_pro else "Sulafat"
        tries.extend([
            ("gemini-3.8-flash-tts", True, {"prebuiltVoiceConfig": {"voiceName": fallback_name}}),
            ("gemini-2.5-flash-tts", False, {"prebuiltVoiceConfig": {"voiceName": fallback_name}}),
        ])

    for model_id, use_meta, v_cfg in tries:
        gem_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
        part: Dict[str, Any] = {"text": spoken_text}
        if use_meta:
            part["speechMetadata"] = {"style": "Calm, articulate standard Seoul Korean broadcast news panelist"}
        payload = json.dumps({
            "contents": [{"parts": [part]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": v_cfg},
            },
        }).encode("utf-8")
        try:
            req = urllib.request.Request(gem_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                parts = data["candidates"][0]["content"]["parts"]
                b64 = next((p["inlineData"]["data"] for p in parts if p.get("inlineData", {}).get("data")), "")
                if b64:
                    return base64.b64decode(b64)
        except Exception:
            continue

    return None


def _pcm16_resample_mono(raw_bytes: bytes, src_rate: int = SAMPLE_RATE, dst_rate: int = SAMPLE_RATE) -> np.ndarray:
    if not raw_bytes:
        return np.zeros(0, dtype=np.float32)

    is_container = (
        raw_bytes[:4] in (b"RIFF", b"OggS", b"fLaC")
        or raw_bytes[:3] == b"ID3"
        or (len(raw_bytes) >= 2 and raw_bytes[0] == 0xFF and (raw_bytes[1] & 0xE0) == 0xE0)
        or (len(raw_bytes) >= 4 and raw_bytes[:4] == b"\x1a\x45\xdf\xa3")
    )

    if raw_bytes[:4] == b"RIFF":
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(raw_bytes)
            tpath = Path(tf.name)
        try:
            with wave.open(str(tpath), "rb") as wf:
                if wf.getsampwidth() == 2:
                    src_rate = wf.getframerate()
                    n_ch = wf.getnchannels()
                    pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
                    if n_ch > 1:
                        pcm = pcm.reshape(-1, n_ch).mean(axis=1)
                    if src_rate != dst_rate and len(pcm) > 1:
                        new_len = int(len(pcm) * dst_rate / src_rate)
                        pcm = np.interp(np.linspace(0, len(pcm) - 1, new_len), np.arange(len(pcm)), pcm).astype(np.float32)
                    return pcm
        except Exception:
            pass
        finally:
            tpath.unlink(missing_ok=True)

    if is_container:
        try:
            proc = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", str(dst_rate), "pipe:1"],
                input=raw_bytes,
                capture_output=True,
                timeout=15,
            )
            if proc.returncode == 0 and len(proc.stdout) >= 2:
                even = len(proc.stdout) - (len(proc.stdout) % 2)
                return np.frombuffer(proc.stdout[:even], dtype=np.int16).astype(np.float32) / 32768.0
        except Exception:
            return np.zeros(0, dtype=np.float32)

    even = len(raw_bytes) - (len(raw_bytes) % 2)
    if even <= 0:
        return np.zeros(0, dtype=np.float32)
    pcm = np.frombuffer(raw_bytes[:even], dtype=np.int16).astype(np.float32) / 32768.0
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

    chime_map = {
        "blue": [523.25, 659.25],
        "red": [587.33, 493.88],
        "violet": [554.37, 659.25],
        "emerald": [493.88, 659.25],
        "amber": [440.00, 587.33],
    }

    for idx, turn in enumerate(turns):
        t0 = turn_starts[idx]
        ckey = _get_turn_color_key(turn)
        ws0 = max(0, int((t0 - 0.06) * sample_rate))
        ws1 = min(n_samples, ws0 + int(0.22 * sample_rate))
        if ws1 > ws0:
            wt = np.arange(ws1 - ws0, dtype=np.float32) / sample_rate
            w_env = np.sin(np.pi * wt / 0.22) ** 2
            noise = rng.normal(0.0, 1.0, ws1 - ws0).astype(np.float32)
            kernel = np.ones(14, dtype=np.float32) / 14.0
            noise = np.convolve(noise, kernel, mode="same")
            bed[ws0:ws1] += 0.095 * w_env * noise

        notes = chime_map.get(ckey, [523.25, 659.25])
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


def _create_blink_variant(
    avatar: Image.Image,
    eye_specs: List[Dict[str, Any]],
) -> Image.Image:
    """해부학적 아몬드형 눈꺼풀 마스크 + 슈퍼샘플링 속눈썹으로 자연스러운 눈 깜빡임 생성."""
    arr = np.array(avatar).astype(np.float32)
    h, w = arr.shape[:2]
    mask_full = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask_full)
    filled = arr.copy()

    sx = w / 719.0
    sy = h / 1116.0
    for sp in eye_specs:
        poly = [(int(round(px * sx)), int(round(py * sy))) for px, py in sp["poly"]]
        md.polygon(poly, fill=255)
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        x0, x1 = max(2, min(xs) - 1), min(w - 3, max(xs) + 1)
        y0, y1 = max(2, min(ys)), min(h - 3, max(ys))
        # Sample clean eyelid skin beside outer/inner corners (avoiding dark brow/crease lines)
        c_l = arr[int(round(sp["skin_l"][1] * sy)) - 1 : int(round(sp["skin_l"][1] * sy)) + 2, int(round(sp["skin_l"][0] * sx)), :3].mean(axis=0)
        c_r = arr[int(round(sp["skin_r"][1] * sy)) - 1 : int(round(sp["skin_r"][1] * sy)) + 2, int(round(sp["skin_r"][0] * sx)), :3].mean(axis=0)
        bot_l = arr[min(h - 2, y1 + 1) : min(h, y1 + 4), max(0, x0 + (x1 - x0) // 4) : min(w, x0 + (x1 - x0) * 3 // 4), :3].mean(axis=(0, 1))
        for x in range(x0, x1 + 1):
            tx = (x - x0) / max(1, x1 - x0)
            top_rgb = c_l * (1.0 - tx) + c_r * tx
            for y in range(y0, y1 + 1):
                ty = (y - y0) / max(1, y1 - y0)
                filled[y, x, :3] = top_rgb * (1.0 - ty * 0.55) + bot_l * (ty * 0.55)

    soft_mask = mask_full.filter(ImageFilter.GaussianBlur(1.4))
    out = Image.composite(Image.fromarray(np.clip(filled, 0, 255).astype(np.uint8), "RGBA"), avatar, soft_mask)

    ss = 4
    lash_hi = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lash_hi, "RGBA")
    for sp in eye_specs:
        pts_hi = [(int(round(px * sx * ss)), int(round(py * sy * ss))) for px, py in sp["lash"]]
        ld.line(pts_hi, fill=(48, 32, 28, 205), width=max(4, int(round(1.6 * ss))), joint="curve")
    out.alpha_composite(lash_hi.resize((w, h), Image.Resampling.LANCZOS))
    return out


def _build_stage_assets() -> Dict[str, Any]:
    studio_bg = Image.open(STUDIO_SET_PATH).convert("RGBA").resize((W, H), Image.Resampling.LANCZOS)
    desk_fg = Image.open(STUDIO_DESK_FG_PATH).convert("RGBA").resize((W, H), Image.Resampling.LANCZOS)

    pro_orig = Image.open(PRO_AVATAR_PATH).convert("RGBA")
    con_orig = Image.open(CON_AVATAR_PATH).convert("RGBA")

    pro_active_grade = ImageEnhance.Contrast(ImageEnhance.Brightness(pro_orig).enhance(1.03)).enhance(1.04)
    con_active_grade = ImageEnhance.Contrast(ImageEnhance.Brightness(con_orig).enhance(1.03)).enhance(1.04)

    def fit_h(im: Image.Image, target_h: int) -> Image.Image:
        sc = target_h / im.height
        return im.resize((int(round(im.width * sc)), target_h), Image.Resampling.LANCZOS)

    pro_act = fit_h(pro_active_grade, 566)
    pro_eye_specs = [
        {
            "poly": [(336, 211), (348, 204), (364, 204), (378, 207), (387, 219), (370, 221), (350, 219)],
            "lash": [(338, 214), (355, 218), (373, 218), (386, 218)],
            "skin_l": (335, 202),
            "skin_r": (389, 206),
        },
        {
            "poly": [(432, 215), (441, 206), (455, 205), (467, 208), (474, 218), (460, 220), (442, 219)],
            "lash": [(433, 216), (449, 219), (464, 218), (473, 216)],
            "skin_l": (431, 206),
            "skin_r": (472, 205),
        },
    ]
    pro_act_blink = fit_h(_create_blink_variant(pro_active_grade, pro_eye_specs), 566)
    pro_idle = ImageEnhance.Color(
        ImageEnhance.Brightness(fit_h(pro_orig, 558)).enhance(0.76)
    ).enhance(0.88).filter(ImageFilter.GaussianBlur(0.45))

    con_act = fit_h(con_active_grade, 558)
    con_eye_specs = [
        {
            "poly": [(263, 201), (270, 196), (281, 197), (294, 212), (284, 216), (269, 215), (263, 211)],
            "lash": [(264, 210), (272, 214), (284, 215), (293, 213)],
            "skin_l": (271, 190),
            "skin_r": (294, 199),
        },
        {
            "poly": [(339, 212), (347, 196), (362, 193), (382, 199), (396, 211), (378, 216), (354, 216)],
            "lash": [(340, 213), (357, 215), (376, 214), (392, 211)],
            "skin_l": (337, 201),
            "skin_r": (391, 198),
        },
    ]
    con_act_blink = fit_h(_create_blink_variant(con_active_grade, con_eye_specs), 558)
    con_idle = ImageEnhance.Color(
        ImageEnhance.Brightness(fit_h(con_orig, 550)).enhance(0.76)
    ).enhance(0.88).filter(ImageFilter.GaussianBlur(0.45))

    # Bake soft ambient studio shadows onto chair backrests behind both anchors
    def add_chair_shadow(base: Image.Image, sprite: Image.Image, cx: int, by: int, dx: int) -> None:
        alpha_ch = sprite.split()[3]
        sh = Image.new("RGBA", sprite.size, (0, 0, 0, 115))
        sh.putalpha(alpha_ch.point(lambda v: int(v * 0.42)))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        layer.paste(sh, (cx - sprite.width // 2 + dx, by - sprite.height + 10))
        base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(14)))

    add_chair_shadow(studio_bg, pro_act, 225, 1318, 10)
    add_chair_shadow(studio_bg, con_act, 855, 1316, -10)

    # Bake subtle tabletop ambient occlusion shadow strip right along the curved back desk edge
    ao_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ao_draw = ImageDraw.Draw(ao_layer)
    for dy in range(-16, 6):
        op = max(0, 62 - abs(dy) * 3)
        pts = [(x, int(round(1212.0 + 18.0 * ((x - 540.0) / 540.0) ** 2 + dy))) for x in range(0, W + 1, 12)]
        ao_draw.line(pts, fill=(0, 0, 0, op), width=4)
    desk_fg_comp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    desk_fg_comp.alpha_composite(ao_layer)
    desk_fg_comp.alpha_composite(desk_fg)

    def make_glow(cx: int, cy: int, color: Tuple[int, int, int]) -> Image.Image:
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gd.ellipse([cx - 320, cy - 340, cx + 320, cy + 340], fill=(*color, 92))
        return g.filter(ImageFilter.GaussianBlur(105))

    glows: Dict[Tuple[str, str], Image.Image] = {}
    for ck, spec in PALETTE.items():
        glows[("PRO", ck)] = make_glow(235, 940, spec["glow"])
        glows[("CON", ck)] = make_glow(845, 940, spec["glow"])

    return {
        "studio_bg": studio_bg,
        "desk_fg": desk_fg_comp,
        "pro_act": pro_act,
        "pro_act_blink": pro_act_blink,
        "pro_idle": pro_idle,
        "con_act": con_act,
        "con_act_blink": con_act_blink,
        "con_idle": con_idle,
        "glows": glows,
    }


def _pick_title_font_and_lines(
    text: str, max_width: int, fonts: Dict[str, ImageFont.FreeTypeFont]
) -> Tuple[ImageFont.FreeTypeFont, List[str]]:
    clean = " ".join((text or "").split())
    total_words = len([w for w in clean.split() if w])
    for key in ["title_xl", "title_lg", "title_md"]:
        f = fonts[key]
        lines = _wrap_words_by_width(clean, f, max_width, max_lines=2)
        if sum(len(ln) for ln in lines) >= total_words:
            return f, [" ".join(ln) for ln in lines]
    f = fonts["title_md"]
    wrapped = _wrap_words_by_width(clean, f, max_width, max_lines=2)
    return f, [" ".join(ln) for ln in wrapped]


def _pick_core_font_and_lines(text: str, max_width: int, fonts: Dict[str, ImageFont.FreeTypeFont]) -> Tuple[ImageFont.FreeTypeFont, List[str]]:
    clean = " ".join((text or "").split())
    for key in ["core_lg", "core_md", "core_sm"]:
        f = fonts[key]
        if f.getlength(clean) <= max_width:
            return f, [clean]
    wrapped = _wrap_words_by_width(clean, fonts["core_sm"], max_width, max_lines=2)
    return fonts["core_sm"], [" ".join(ln) for ln in wrapped]


def _pick_caption_font_and_lines(clause_text: str, max_width: int, fonts: Dict[str, ImageFont.FreeTypeFont]) -> Tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, List[List[str]], int]:
    for b_key, d_key, lh in [("body_xl", "body_xl_dim", 54), ("body_lg", "body_lg_dim", 48)]:
        bf = fonts[b_key]
        lines = _wrap_words_by_width(clause_text, bf, max_width, max_lines=3)
        word_cnt_wrapped = sum(len(x) for x in lines)
        word_cnt_total = len([w for w in clause_text.split() if w])
        if word_cnt_wrapped >= word_cnt_total:
            return bf, fonts[d_key], lines, lh
    bf = fonts["body_lg"]
    return bf, fonts["body_lg_dim"], _wrap_words_by_width(clause_text, bf, max_width, max_lines=4), 42


def _resolve_perspectives(raw_stats: Dict[str, Any], perspectives: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if perspectives and isinstance(perspectives, list) and len(perspectives) >= 2:
        out: List[Dict[str, Any]] = []
        for idx, p in enumerate(perspectives[:4]):
            ck = (p.get("color") or "").lower()
            if ck not in PALETTE:
                ck = ["blue", "red", "violet", "emerald"][idx % 4]
            out.append({
                "short_label": (p.get("short_label") or p.get("label") or f"관점 {idx + 1}")[:12],
                "ratio": max(1, int(p.get("ratio", 25))),
                "color": ck,
            })
        return out
    pro_r = max(1, min(99, int(raw_stats.get("pro_ratio", 50))))
    con_r = max(1, 100 - pro_r)
    return [
        {"short_label": "찬성", "ratio": pro_r, "color": "blue"},
        {"short_label": "반대", "ratio": con_r, "color": "red"},
    ]


def _draw_desk_nameplates(
    desk_img: Image.Image,
    turns: List[Dict[str, Any]],
    turn_idx: int,
    fonts: Dict[str, ImageFont.FreeTypeFont],
) -> None:
    """커브드 스튜디오 데스크 전면 패널에 현재 발화자/대기 패널 입장 명패를 깔끔하게 각인."""
    cur_turn = turns[turn_idx]
    cur_is_pro = cur_turn.get("speaker") == "PRO"
    cur_ck = _get_turn_color_key(cur_turn)
    cur_lbl = (cur_turn.get("perspective_label") or "").strip() or (
        f"좌측 {turn_idx // 2 + 1}" if cur_is_pro else f"우측 {turn_idx // 2 + 1}"
    )

    opp_turn: Optional[Dict[str, Any]] = None
    for step in range(1, len(turns) + 1):
        for cand_i in (turn_idx + step, turn_idx - step):
            if 0 <= cand_i < len(turns) and (turns[cand_i].get("speaker") == "PRO") != cur_is_pro:
                opp_turn = turns[cand_i]
                break
        if opp_turn is not None:
            break
    opp_lbl = ((opp_turn.get("perspective_label") or "").strip() if opp_turn else "") or (
        "우측 패널" if cur_is_pro else "좌측 패널"
    )

    d = ImageDraw.Draw(desk_img, "RGBA")

    def paint_plate(center_x: int, label: str, active: bool, accent_col: Tuple[int, int, int, int]) -> None:
        plate_font = fonts["desk_plate"]
        tw = plate_font.getlength(label)
        badge_w = 68 if active else 0
        pw = int(max(220, min(390, tw + badge_w + 56)))
        x0 = max(54, min(W - 54 - pw, center_x - pw // 2))
        x1 = x0 + pw
        y0, y1 = 1368, 1424
        if active:
            d.rounded_rectangle([x0, y0 + 5, x1, y1 + 5], radius=14, fill=(0, 0, 0, 120))
            d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=(10, 14, 22, 240), outline=accent_col, width=3)
            d.rounded_rectangle([x0 + 8, y0 + 8, x0 + 68, y1 - 8], radius=9, fill=accent_col)
            d.text((x0 + 38, (y0 + y1) // 2), "발언", font=fonts["claim_tag"], fill=(255, 255, 255, 255), anchor="mm")
            d.text(((x0 + 72 + x1 - 10) // 2, (y0 + y1) // 2), label, font=plate_font, fill=(255, 255, 255, 255), anchor="mm")
        else:
            d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=(12, 16, 25, 200), outline=(255, 255, 255, 42), width=2)
            d.text((center_x, (y0 + y1) // 2), label, font=plate_font, fill=(182, 192, 208, 225), anchor="mm")

    cur_accent = PALETTE[cur_ck]["accent"]
    if cur_is_pro:
        paint_plate(242, cur_lbl, True, cur_accent)
        paint_plate(838, opp_lbl, False, cur_accent)
    else:
        paint_plate(242, opp_lbl, False, cur_accent)
        paint_plate(838, cur_lbl, True, cur_accent)


def _render_ui_hud_frame(
    issue_title: str,
    raw_stats: Dict[str, Any],
    perspectives: List[Dict[str, Any]],
    mode_label: str,
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
    """주제(골드+초대형 헤드라인) · 화자/입장(솔리드 컬러 배지) · 핵심 요점 · 발화 자막의 명확한 4단 계층 HUD."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay, "RGBA")

    is_pro = turn_data.get("speaker") == "PRO"
    ckey = _get_turn_color_key(turn_data)
    pal = PALETTE[ckey]
    accent = pal["accent"]
    accent_pill = pal["pill"]
    accent_badge_txt = pal["txt"]

    default_lbl = f"좌측 패널 {turn_idx // 2 + 1}" if is_pro else f"우측 패널 {turn_idx // 2 + 1}"
    speaker_label = (turn_data.get("perspective_label") or "").strip() or default_lbl

    # 1) TOPIC HERO BILLBOARD (y=98..288) — unmistakably the #1 show topic at a glance
    tx0, ty0, tx1, ty1 = 48, 98, W - 48, 288
    d.rounded_rectangle([tx0, ty0 + 8, tx1, ty1 + 8], radius=22, fill=(0, 0, 0, 125))
    d.rounded_rectangle([tx0, ty0, tx1, ty1], radius=22, fill=(9, 13, 22, 248), outline=(250, 204, 21, 145), width=2)
    d.rounded_rectangle([tx0, ty0, tx1, ty0 + 9], radius=8, fill=(250, 204, 21, 255))
    d.rectangle([tx0, ty0 + 4, tx1, ty0 + 9], fill=(250, 204, 21, 255))

    # Row 1 inside Topic Card: Solid Gold "영상 주제" chip + Mode tag + Total dataset count
    d.rounded_rectangle([76, ty0 + 20, 198, ty0 + 54], radius=10, fill=(250, 204, 21, 255))
    d.text((137, ty0 + 37), "영상 주제", font=fonts["topic_tag"], fill=(9, 13, 22, 255), anchor="mm")

    mode_chip = mode_label or "다관점 분석"
    mode_w = int(min(360, max(130, fonts["badge_sm"].getlength(mode_chip) + 32)))
    d.rounded_rectangle([210, ty0 + 20, 210 + mode_w, ty0 + 54], radius=10, fill=(255, 255, 255, 24))
    d.text((210 + mode_w // 2, ty0 + 37), mode_chip, font=fonts["badge_sm"], fill=(226, 232, 240, 255), anchor="mm")

    d.text((W - 76, ty0 + 37), f"댓글 {raw_stats.get('total_comments', 0)}건 분석", font=fonts["badge_sm"], fill=(148, 163, 184, 255), anchor="rm")

    # Giant Crisp Pure-White Topic Title (44px -> 40px -> 36px)
    title_font, title_lines = _pick_title_font_and_lines(issue_title, W - 156, fonts)
    if len(title_lines) == 1:
        d.text((W // 2, ty0 + 122), title_lines[0], font=title_font, fill=(255, 255, 255, 255), anchor="mm")
    else:
        d.text((W // 2, ty0 + 94), title_lines[0], font=title_font, fill=(255, 255, 255, 255), anchor="mm")
        d.text((W // 2, ty0 + 148), title_lines[1], font=title_font, fill=(255, 255, 255, 255), anchor="mm")

    # 2) SPEAKER STATEMENT BUBBLE (y=306..668, tail tip=708 -> clears anchor crowns y>=734!)
    bx0, by0, bx1, by1 = 48, 306, W - 48, 668
    d.rounded_rectangle([bx0, by0 + 10, bx1, by1 + 10], radius=24, fill=(0, 0, 0, 120))
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=24, fill=(255, 255, 255, 254), outline=(15, 23, 42, 34), width=2)
    d.rounded_rectangle([bx0, by0, bx1, by0 + 11], radius=8, fill=accent)
    d.rectangle([bx0, by0 + 5, bx1, by0 + 11], fill=accent)

    if is_pro:
        d.polygon([(265, by1 - 2), (335, by1 - 2), (295, by1 + 40)], fill=(255, 255, 255, 254))
    else:
        d.polygon([(W - 335, by1 - 2), (W - 265, by1 - 2), (W - 295, by1 + 40)], fill=(255, 255, 255, 254))

    # Row 1: Solid High-Contrast Perspective Badge (with directional arrow) + Clause Step Pill
    spk_display = f"◀ {speaker_label}" if is_pro else f"{speaker_label} ▶"
    sp_text_w = fonts["speaker"].getlength(spk_display)
    sp_pill_r = int(min(W - 244, 84 + max(168, sp_text_w + 48)))
    d.rounded_rectangle([84, by0 + 24, sp_pill_r, by0 + 70], radius=12, fill=accent)
    d.text(((84 + sp_pill_r) // 2, by0 + 47), spk_display, font=fonts["speaker"], fill=(255, 255, 255, 255), anchor="mm")

    d.rounded_rectangle([W - 224, by0 + 26, W - 84, by0 + 68], radius=11, fill=(241, 245, 249, 255), outline=(203, 213, 225, 255), width=1)
    d.text((W - 154, by0 + 47), f"논지 {clause_idx + 1} / {total_clauses}", font=fonts["meta"], fill=(51, 65, 85, 255), anchor="mm")

    # Row 2: Tinted Key Claim Banner (isolates Core Point from Spoken Subtitle)
    core_font, core_lines = _pick_core_font_and_lines(turn_data.get("core_point", ""), W - 268, fonts)
    claim_y0 = by0 + 84
    claim_y1 = claim_y0 + (54 if len(core_lines) == 1 else 82)
    d.rounded_rectangle([84, claim_y0, W - 84, claim_y1], radius=12, fill=accent_pill)
    d.rounded_rectangle([84, claim_y0, 96, claim_y1], radius=6, fill=accent)
    d.rectangle([90, claim_y0, 96, claim_y1], fill=accent)

    d.rounded_rectangle([108, claim_y0 + 12, 168, claim_y0 + 42], radius=7, fill=accent)
    d.text((138, claim_y0 + 27), "핵심", font=fonts["claim_tag"], fill=(255, 255, 255, 255), anchor="mm")

    if len(core_lines) == 1:
        d.text((180, (claim_y0 + claim_y1) // 2), core_lines[0], font=core_font, fill=accent_badge_txt, anchor="lm")
    else:
        d.text((180, claim_y0 + 26), core_lines[0], font=core_font, fill=accent_badge_txt, anchor="lm")
        d.text((180, claim_y0 + 57), core_lines[1], font=core_font, fill=accent_badge_txt, anchor="lm")

    # Row 3: Bold Kinetic Spoken Captions centered vertically in remaining box
    space_w = caption_font.getlength(" ") + 3.0
    running_idx = 0
    block_h = len(caption_lines) * line_h
    avail_h = (by1 - 18) - (claim_y1 + 14)
    start_y = claim_y1 + 16 + max(0, (avail_h - block_h) // 2)

    for li, line_words in enumerate(caption_lines):
        cx = 84.0
        cy = start_y + li * line_h
        for w_str in line_words:
            ww = caption_font.getlength(w_str)
            if running_idx < active_word_idx:
                d.text((cx, cy), w_str, font=caption_font, fill=(15, 23, 42, 255), anchor="lt")
            elif running_idx == active_word_idx:
                pill_pad_y = max(38, int(line_h * 0.84))
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

    if len(perspectives) <= 2:
        p0 = perspectives[0]
        p1 = perspectives[1] if len(perspectives) > 1 else {"short_label": "대안", "ratio": max(1, 100 - p0["ratio"]), "color": "red"}
        c0 = PALETTE.get(p0["color"], PALETTE["blue"])
        c1 = PALETTE.get(p1["color"], PALETTE["red"])
        d.text((94, ly0 + 50), f"{p0['short_label']} {p0['ratio']}%", font=fonts["stat"], fill=c0["bar"], anchor="lm")
        d.text((W - 94, ly0 + 50), f"{p1['short_label']} {p1['ratio']}%", font=fonts["stat"], fill=c1["bar"], anchor="rm")
        bar_x0, bar_x1 = 316, W - 316
        bar_w = bar_x1 - bar_x0
        tot_r = max(1, p0["ratio"] + p1["ratio"])
        w0 = max(24, int(bar_w * (p0["ratio"] / tot_r)))
        d.rounded_rectangle([bar_x0, ly0 + 42, bar_x0 + w0 - 4, ly0 + 56], radius=7, fill=c0["accent"])
        d.rounded_rectangle([bar_x0 + w0 + 4, ly0 + 42, bar_x1, ly0 + 56], radius=7, fill=c1["accent"])
        d.text((W // 2, ly0 + 84), mode_label or "AI 공론장 중재", font=fonts["badge_sm"], fill=(161, 161, 170, 255), anchor="mm")
    else:
        n_p = len(perspectives)
        tot_r = sum(max(1, p["ratio"]) for p in perspectives) or 100
        inner_l, inner_r = 90, W - 90
        span_w = inner_r - inner_l
        col_w = span_w / n_p
        for pi, p in enumerate(perspectives):
            pc = PALETTE.get(p["color"], PALETTE["blue"])
            cx_p = int(inner_l + col_w * (pi + 0.5))
            lbl = f"{p['short_label']} {p['ratio']}%"
            d.text((cx_p, ly0 + 40), lbl, font=fonts["stat_sm"], fill=pc["bar"], anchor="mm")

        seg_gap = 6
        avail_bar_w = span_w - seg_gap * (n_p - 1)
        cur_x = float(inner_l)
        for pi, p in enumerate(perspectives):
            pc = PALETTE.get(p["color"], PALETTE["blue"])
            seg_len = avail_bar_w * (max(1, p["ratio"]) / tot_r) if pi < n_p - 1 else (inner_r - cur_x)
            seg_end = min(float(inner_r), cur_x + max(18.0, seg_len))
            d.rounded_rectangle([int(cur_x), ly0 + 66, int(seg_end), ly0 + 80], radius=7, fill=pc["accent"])
            cur_x = seg_end + seg_gap
        d.text((W // 2, ly0 + 100), mode_label or f"{n_p}관점 여론 비교", font=fonts["badge_sm"], fill=(161, 161, 170, 255), anchor="mm")

    d.line([(86, ly0 + 118), (W - 86, ly0 + 118)], fill=(255, 255, 255, 20), width=2)

    dot_step = 30 if total_turns > 6 else 34
    for i in range(total_turns):
        dx = 94 + i * dot_step
        if i == turn_idx:
            d.rounded_rectangle([dx, ly0 + 150, dx + 24, ly0 + 160], radius=5, fill=accent)
        elif i < turn_idx:
            d.rounded_rectangle([dx, ly0 + 150, dx + 16, ly0 + 160], radius=5, fill=(161, 161, 170, 255))
        else:
            d.rounded_rectangle([dx, ly0 + 150, dx + 16, ly0 + 160], radius=5, fill=(45, 49, 62, 255))

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
    meta_out: Optional[Dict[str, Any]] = None,
    perspectives: Optional[List[Dict[str, Any]]] = None,
    mode_label: str = "",
) -> Path:
    """1080x1920 @ 30fps Full-HD 가변 길이 방송형 다관점 쇼츠 MP4 렌더링."""
    turns = debate_script[:8]
    total_turns = max(len(turns), 1)
    resolved_persp = _resolve_perspectives(raw_stats, perspectives)
    resolved_mode_lbl = (mode_label or "").strip() or (f"{len(resolved_persp)}관점 여론 비교" if len(resolved_persp) >= 3 else "AI 공론장 중재")

    # Step 1: Collect or synthesize voice audio FIRST so each turn fits speech length naturally
    turn_pcms: List[Optional[np.ndarray]] = []
    client_supplied_any = bool(turn_audio_b64_list and any(turn_audio_b64_list))
    server_tts_failed = False

    for idx, turn in enumerate(turns):
        raw_voice: Optional[bytes] = None
        if turn_audio_b64_list and idx < len(turn_audio_b64_list) and turn_audio_b64_list[idx]:
            try:
                raw_voice = base64.b64decode(turn_audio_b64_list[idx])
            except Exception:
                raw_voice = None
        elif try_gemini_tts and not client_supplied_any and not server_tts_failed:
            raw_voice = fetch_tts_audio_bytes(turn["text"], turn["speaker"])
            if not raw_voice:
                server_tts_failed = True

        if raw_voice:
            pcm = _pcm16_resample_mono(raw_voice, SAMPLE_RATE, SAMPLE_RATE)
            turn_pcms.append(pcm if len(pcm) > 0 else None)
        else:
            turn_pcms.append(None)

    # Prevent jarring mid-video flip when server TTS failed midway
    voiced_pcms = sum(1 for p in turn_pcms if p is not None and len(p) > int(SAMPLE_RATE * 0.25))
    if not client_supplied_any and 0 < voiced_pcms < len(turns):
        turn_pcms = [None] * len(turns)
        voiced_pcms = 0

    # Step 2: Natural adaptive per-turn durations
    turn_durations: List[float] = []
    for idx, turn in enumerate(turns):
        pcm = turn_pcms[idx]
        if pcm is not None and len(pcm) > SAMPLE_RATE * 0.4:
            turn_durations.append(round(max(2.6, (len(pcm) / SAMPLE_RATE) + 0.45), 2))
        else:
            turn_durations.append(estimate_turn_duration_sec(turn["text"]))

    total_duration = sum(turn_durations)
    turn_frame_counts = [max(30, int(round(d * FPS))) for d in turn_durations]
    total_frames = sum(turn_frame_counts)

    assets = _build_stage_assets()
    fonts = {
        "hud": _load_font(FONT_BOLD_PATH, 23),
        "badge_sm": _load_font(FONT_BOLD_PATH, 19),
        "topic_tag": _load_font(FONT_BOLD_PATH, 20),
        "claim_tag": _load_font(FONT_BOLD_PATH, 18),
        "desk_plate": _load_font(FONT_BOLD_PATH, 22),
        "title_xl": _load_font(FONT_BOLD_PATH, 44),
        "title_lg": _load_font(FONT_BOLD_PATH, 40),
        "title_md": _load_font(FONT_BOLD_PATH, 36),
        "title": _load_font(FONT_BOLD_PATH, 40),
        "speaker": _load_font(FONT_BOLD_PATH, 23),
        "meta": _load_font(FONT_BOLD_PATH, 20),
        "core_lg": _load_font(FONT_BOLD_PATH, 27),
        "core_md": _load_font(FONT_BOLD_PATH, 24),
        "core_sm": _load_font(FONT_BOLD_PATH, 21),
        "body_xl": _load_font(FONT_BOLD_PATH, 38),
        "body_xl_dim": _load_font(FONT_BOLD_PATH, 38),
        "body_lg": _load_font(FONT_BOLD_PATH, 34),
        "body_lg_dim": _load_font(FONT_BOLD_PATH, 34),
        "stat": _load_font(FONT_BOLD_PATH, 23),
        "stat_sm": _load_font(FONT_BOLD_PATH, 20),
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
        if meta_out is not None:
            meta_out["has_voice"] = bool(has_voice and voiced_pcms == len(turns) and len(turns) > 0)
            meta_out["voiced_turns"] = voiced_pcms
            meta_out["total_turns"] = len(turns)

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
        prev_focus_cx = W * 0.50
        for idx, turn in enumerate(turns):
            is_pro = turn.get("speaker") == "PRO"
            ckey = _get_turn_color_key(turn)
            accent_rgb = PALETTE[ckey]["accent"]

            clauses = _split_turn_into_clauses(turn["text"])
            clause_overlays: List[List[Image.Image]] = []
            clause_timelines: List[List[Tuple[float, float]]] = []

            for c_idx, c_text in enumerate(clauses):
                c_font, c_dim_font, c_lines, lh = _pick_caption_font_and_lines(c_text, W - 180, fonts)
                flat_words = [w for ln in c_lines for w in ln]
                w_cnt = max(len(flat_words), 1)
                clause_timelines.append(_build_weighted_word_timeline(flat_words))
                overlays_for_clause: List[Image.Image] = []
                for w_idx in range(w_cnt):
                    overlays_for_clause.append(
                        _render_ui_hud_frame(
                            issue_title=issue_title,
                            raw_stats=raw_stats,
                            perspectives=resolved_persp,
                            mode_label=resolved_mode_lbl,
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
                clause_overlays.append(overlays_for_clause)

            clause_windows = _analyze_pcm_clause_timing(
                turn_pcms[idx],
                SAMPLE_RATE,
                clauses,
                turn_durations[idx],
                lead_in_sec=0.14,
            )

            turn_bg = assets["studio_bg"].copy()
            side_key = "PRO" if is_pro else "CON"
            turn_bg.alpha_composite(assets["glows"][(side_key, ckey)])

            turn_desk = assets["desk_fg"].copy()
            _draw_desk_nameplates(turn_desk, turns, idx, fonts)

            focus_cx = (W * 0.468) if is_pro else (W * 0.532)
            n_f = turn_frame_counts[idx]
            for f in range(n_f):
                local_t = f / FPS
                turn_prog = f / max(n_f - 1, 1)
                remaining_sec = max(0.0, (total_frames - global_f) / FPS)
                energy = float(rms_env[min(global_f, len(rms_env) - 1)])
                global_f += 1

                pan_prog = min(1.0, local_t / 0.55)
                ease_pan = 1.0 - (1.0 - pan_prog) ** 3
                is_blinking = ((local_t + 1.1) % 3.6) < 0.13
                talk_cadence = (
                    math.sin(local_t * 1.8) * 0.9
                    - (0.4 + 1.4 * energy) * (0.5 + 0.5 * math.sin(local_t * 5.4))
                )
                idle_breath = math.sin(local_t * 1.45 + 1.1) * 1.0

                stage = turn_bg.copy()

                if is_pro:
                    p_spr = assets["pro_act_blink"] if is_blinking else assets["pro_act"]
                    c_spr = assets["con_idle"]
                    p_x = 225 - p_spr.width // 2
                    p_y = 1318 - p_spr.height + int(round(talk_cadence))
                    c_x = 855 - c_spr.width // 2
                    c_y = 1314 - c_spr.height + int(round(idle_breath))
                    stage.paste(c_spr, (c_x, c_y), c_spr)
                    stage.paste(p_spr, (p_x, p_y), p_spr)
                else:
                    p_spr = assets["pro_idle"]
                    c_spr = assets["con_act_blink"] if is_blinking else assets["con_act"]
                    p_x = 225 - p_spr.width // 2
                    p_y = 1316 - p_spr.height + int(round(idle_breath))
                    c_x = 855 - c_spr.width // 2
                    c_y = 1316 - c_spr.height + int(round(talk_cadence))
                    stage.paste(p_spr, (p_x, p_y), p_spr)
                    stage.paste(c_spr, (c_x, c_y), c_spr)

                stage.paste(turn_desk, (0, 0), turn_desk)

                zoom = 1.022 + 0.030 * turn_prog
                cw = W / zoom
                ch = H / zoom
                cx = prev_focus_cx + (focus_cx - prev_focus_cx) * ease_pan
                cy = H * 0.504
                x0 = max(0.0, min(W - cw, cx - cw * 0.5))
                y0 = max(0.0, min(H - ch, cy - ch * 0.5))
                frame = stage.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.Resampling.BILINEAR)

                c_idx, local_w = _resolve_clause_and_word(local_t, clause_timelines, clause_windows)
                ov_list = clause_overlays[min(c_idx, len(clause_overlays) - 1)]
                chosen_ov = ov_list[min(local_w, len(ov_list) - 1)]
                frame.paste(chosen_ov, (0, 0), chosen_ov)

                draw = ImageDraw.Draw(frame, "RGBA")
                seg_gap = 10
                seg_total_w = W - 96
                seg_w = (seg_total_w - seg_gap * (total_turns - 1)) / total_turns
                for s_i in range(total_turns):
                    sx0 = 48 + s_i * (seg_w + seg_gap)
                    sx1 = sx0 + seg_w
                    draw.rounded_rectangle([sx0, 34, sx1, 43], radius=4, fill=(45, 50, 65, 220))
                    if s_i < idx:
                        s_col = PALETTE[_get_turn_color_key(turns[s_i])]["accent"]
                        draw.rounded_rectangle([sx0, 34, sx1, 43], radius=4, fill=s_col)
                    elif s_i == idx:
                        fill_x = sx0 + max(10.0, (sx1 - sx0) * turn_prog)
                        draw.rounded_rectangle([sx0, 34, fill_x, 43], radius=4, fill=accent_rgb)

                draw.rounded_rectangle([48, 54, 162, 88], radius=12, fill=(14, 17, 25, 215))
                draw.text((105, 71), f"{idx + 1:02d} / {total_turns:02d}", font=fonts["hud"], fill=(244, 244, 245, 255), anchor="mm")
                draw.rounded_rectangle([W - 154, 54, W - 48, 88], radius=12, fill=(14, 17, 25, 215))
                draw.text((W - 101, 71), f"{remaining_sec:.1f}s", font=fonts["hud"], fill=(228, 228, 231, 255), anchor="mm")

                eq_x0 = 365
                for bi in range(24):
                    bx = eq_x0 + bi * 15
                    wave_mod = 0.45 + 0.55 * math.sin(local_t * 16.0 + bi * 0.65)
                    bh = int(8 + (14 + 26 * energy) * wave_mod)
                    draw.rounded_rectangle([bx, 1804 - bh // 2, bx + 7, 1804 + bh // 2], radius=3, fill=accent_rgb)

                proc.stdin.write(frame.tobytes())
            prev_focus_cx = focus_cx

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
            perspectives=data.get("perspectives"),
            mode_label=data.get("mode_label", ""),
        )
        print(f"[MP4 RENDERED 1080p 30fps] {out_file} ({out_file.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

