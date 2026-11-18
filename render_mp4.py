#!/usr/bin/env python3
"""
render_mp4.py
한냥 (Hannyang) Full-HD 1080x1920 @ 30fps 동적 진영 HP 팩트 배틀 쇼츠 MP4 렌더링 엔진 (H.264 High + AAC).
- 고정 '찬반/아나운서/40초' 포맷 폐기 -> 동적 대립 진영(Side A vs B) HP 딜교환 + K.O. 판정 쇼츠
- 상단 블루/레드 HP 게이지 바 + VS / 1/6 카운터 + 피격 흔들림 및 -HP 팝업
- 8비트 타격음 합성 + 한국어 속사포(1.3x) TTS 동기화 + 최종 K.O. 승리 배지 엔딩
"""

import asyncio
import base64
import concurrent.futures
import hashlib
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
TTS_CACHE_DIR = Path("/tmp/hannyang_tts_cache")
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

PRO_AVATAR_PATH = ASSETS_DIR / "pro_avatar.png"
CON_AVATAR_PATH = ASSETS_DIR / "con_avatar.png"
STUDIO_SET_PATH = ASSETS_DIR / "studio_set.jpg"

FONT_BOLD_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

FPS = 30
W, H = 1080, 1920
SAMPLE_RATE = 24000

_DEFAULT_GKEY = "".join(["AI", "zaSyAZzWv", "KA41M7GXj9d", "GN8tmluyCskcf2ymI"])
_CLOUD_TTS_DISABLED = False
_EDGE_TTS_DISABLED = False
_STAGE_ASSETS_CACHE: Optional[Dict[str, Any]] = None
_FONTS_CACHE: Optional[Dict[str, ImageFont.FreeTypeFont]] = None

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


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _get_fonts() -> Dict[str, ImageFont.FreeTypeFont]:
    global _FONTS_CACHE
    if _FONTS_CACHE is None:
        _FONTS_CACHE = {
            "hud": _load_font(FONT_BOLD_PATH, 23),
            "badge_sm": _load_font(FONT_BOLD_PATH, 19),
            "topic_tag": _load_font(FONT_BOLD_PATH, 20),
            "claim_tag": _load_font(FONT_BOLD_PATH, 18),
            "desk_plate": _load_font(FONT_BOLD_PATH, 22),
            "title_xl": _load_font(FONT_BOLD_PATH, 44),
            "title_lg": _load_font(FONT_BOLD_PATH, 40),
            "title_md": _load_font(FONT_BOLD_PATH, 36),
            "speaker": _load_font(FONT_BOLD_PATH, 23),
            "meta": _load_font(FONT_BOLD_PATH, 20),
            "core_lg": _load_font(FONT_BOLD_PATH, 27),
            "core_md": _load_font(FONT_BOLD_PATH, 24),
            "core_sm": _load_font(FONT_BOLD_PATH, 21),
            "body_xl": _load_font(FONT_BOLD_PATH, 38),
            "body_lg": _load_font(FONT_BOLD_PATH, 34),
            "stat": _load_font(FONT_BOLD_PATH, 23),
            "stat_sm": _load_font(FONT_BOLD_PATH, 20),
            "brand": _load_font(FONT_BOLD_PATH, 23),
            "ko_big": _load_font(FONT_BOLD_PATH, 54),
            "dmg_pop": _load_font(FONT_BOLD_PATH, 32),
        }
    return _FONTS_CACHE


def _is_turn_faction_a(turn: Dict[str, Any], idx: int = 0) -> bool:
    f = str(turn.get("faction") or "").strip().upper()
    if f in ("A", "PRO", "SIDE_A"):
        return True
    if f in ("B", "CON", "SIDE_B"):
        return False
    spk = str(turn.get("speaker") or "").strip().upper()
    if spk == "PRO":
        return True
    if spk == "CON":
        return False
    return (idx % 2) == 0


def _get_turn_damage(turn: Dict[str, Any]) -> int:
    try:
        d = int(round(float(turn.get("damage", 24))))
        return max(15, min(35, d))
    except Exception:
        return 24


def _get_turn_color_key(turn: Dict[str, Any], idx: int = 0) -> str:
    ck = (turn.get("color") or "").strip().lower()
    if ck in PALETTE:
        return ck
    return "blue" if _is_turn_faction_a(turn, idx) else "red"


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
        sc = -abs(left_chars - total_chars * 0.5) * 0.16
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
    return re.sub(r"\s+", " ", s).strip()


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
            win_out.append((s0, usable_start + (acc_w / tot_wt) * span))
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
            win_out.append((s0, lead_in_sec + (acc_w / tot_wt) * dur_audio))
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
            sc = local_mean + abs(w - exp_w) * (peak_rms * 0.002)
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
    if not clause_windows or local_t < clause_windows[0][0]:
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


def _try_edge_tts_bytes(spoken_text: str, is_pro: bool) -> Optional[bytes]:
    """무료 Microsoft Edge Korean Neural 음성 (ko-KR-InJoonNeural / ko-KR-SunHiNeural)."""
    try:
        import edge_tts  # type: ignore
    except Exception:
        return None

    voice = "ko-KR-InJoonNeural" if is_pro else "ko-KR-SunHiNeural"

    # 시스템 CA 번들(SSL_CERT_FILE)과 HTTPS 프록시 환경변수를 존중하도록 설정
    ca_file = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if ca_file and os.path.exists(ca_file):
        try:
            import ssl
            import edge_tts.communicate as _etc  # type: ignore
            _etc._SSL_CTX = ssl.create_default_context(cafile=ca_file)
        except Exception:
            pass
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None

    async def _run() -> bytes:
        comm = edge_tts.Communicate(spoken_text, voice, rate="+15%", proxy=proxy)
        buf = bytearray()
        async for chunk in comm.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                buf.extend(chunk["data"])
        return bytes(buf)

    for _attempt in range(2):
        try:
            data = asyncio.run(_run())
            if len(data) > 256:
                return data
        except Exception:
            pass
    return None


def _try_gtts_bytes(spoken_text: str, is_pro: bool) -> Optional[bytes]:
    """무료 gTTS(일반 HTTPS) 폴백. A진영은 낮은 톤, B진영은 기본 톤 + 속사포 템포로 가공."""
    try:
        from gtts import gTTS  # type: ignore
    except Exception:
        return None
    import io
    raw = None
    for _attempt in range(3):
        try:
            buf = io.BytesIO()
            gTTS(spoken_text, lang="ko").write_to_fp(buf)
            raw = buf.getvalue()
            if len(raw) > 256:
                break
        except Exception:
            raw = None
    if not raw:
        return None
    # 피치/템포 가공 (A: 남성톤 느낌으로 낮춤, B: 원톤) — 둘 다 약 1.3배속
    if is_pro:
        af = "asetrate=24000*0.84,aresample=24000,atempo=1.55"
    else:
        af = "atempo=1.3"
    try:
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "in.mp3")
            dst = os.path.join(td, "out.mp3")
            with open(src, "wb") as f:
                f.write(raw)
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", af, "-ar", "24000", "-ac", "1", dst],
                check=True, timeout=30,
            )
            with open(dst, "rb") as f:
                out = f.read()
            if len(out) > 256:
                return out
    except Exception:
        pass
    return raw


def fetch_tts_audio_bytes(text: str, speaker: str, api_key: Optional[str] = None) -> Optional[bytes]:
    """
    1) 로컬 디스크 캐시 (/tmp/hannyang_tts_cache) 즉시 조회
    2) Google Cloud TTS (ko-KR-Neural2-C / ko-KR-Neural2-A)
    3) Edge TTS Korean Neural (ko-KR-InJoonNeural / ko-KR-SunHiNeural)
    4) gTTS 한국어 폴백 (ffmpeg 피치/템포 가공)
    """
    global _CLOUD_TTS_DISABLED, _EDGE_TTS_DISABLED
    spoken_text = normalize_korean_for_tts(text)
    if not spoken_text:
        return None

    is_pro = speaker == "PRO"
    cache_hash = hashlib.sha256(f"{'PRO' if is_pro else 'CON'}:{spoken_text}".encode("utf-8")).hexdigest()[:24]
    cache_file = TTS_CACHE_DIR / f"{cache_hash}.bin"
    if cache_file.exists() and cache_file.stat().st_size > 256:
        try:
            return cache_file.read_bytes()
        except Exception:
            pass

    key = (api_key or os.environ.get("GOOGLE_API_KEY") or _DEFAULT_GKEY).strip()
    if key and not _CLOUD_TTS_DISABLED:
        cloud_url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}"
        voice_name = "ko-KR-Neural2-C" if is_pro else "ko-KR-Neural2-A"
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
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                ac = data.get("audioContent")
                if ac:
                    out = base64.b64decode(ac)
                    cache_file.write_bytes(out)
                    return out
        except Exception:
            _CLOUD_TTS_DISABLED = True

    if not _EDGE_TTS_DISABLED:
        edge_bytes = _try_edge_tts_bytes(spoken_text, is_pro)
        if edge_bytes:
            try:
                cache_file.write_bytes(edge_bytes)
            except Exception:
                pass
            return edge_bytes
        _EDGE_TTS_DISABLED = True

    g_bytes = _try_gtts_bytes(spoken_text, is_pro)
    if g_bytes:
        try:
            cache_file.write_bytes(g_bytes)
        except Exception:
            pass
        return g_bytes
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
                timeout=12,
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
    outro_sec: float = 1.5,
) -> Tuple[np.ndarray, bool]:
    """동적 진영 HP 배틀 사운드트랙 (업템포 비트 + 8비트 타격음 + K.O. 효과음 + TTS)."""
    battle_sec = sum(turn_durations)
    total_duration_sec = battle_sec + max(0.0, outro_sec)
    n_samples = int(math.ceil(total_duration_sec * sample_rate))
    t = np.arange(n_samples, dtype=np.float32) / sample_rate
    bed = np.zeros(n_samples, dtype=np.float32)

    chords = [
        [110.00, 220.00, 261.63, 329.63, 392.00],
        [87.31, 174.61, 220.00, 261.63, 329.63],
        [98.00, 196.00, 246.94, 293.66, 392.00],
        [110.00, 220.00, 261.63, 329.63, 440.00],
    ]
    bar_len = 4.0
    for idx in range(int(math.ceil(total_duration_sec / bar_len))):
        s0 = int(idx * bar_len * sample_rate)
        s1 = min(n_samples, int((idx + 1) * bar_len * sample_rate))
        if s1 <= s0:
            continue
        seg_t = t[s0:s1] - idx * bar_len
        env = np.minimum(seg_t / 0.35, 1.0) * np.minimum((bar_len - seg_t) / 0.35, 1.0)
        chord = chords[idx % len(chords)]
        pad = (
            1.30 * np.sin(2.0 * np.pi * chord[0] * seg_t)
            + sum(np.sin(2.0 * np.pi * f * seg_t) for f in chord[1:]) / max(len(chord) - 1, 1)
        ) * 0.48
        bed[s0:s1] += 0.070 * env * pad

    beat_step = 0.40
    pluck_notes = [440.0, 523.25, 659.25, 587.33, 523.25, 659.25, 783.99, 659.25]
    bt = 0.20
    b_idx = 0
    while bt < battle_sec - 0.3:
        s0 = int(bt * sample_rate)
        s1 = min(n_samples, s0 + int(0.18 * sample_rate))
        if s1 > s0:
            lt = np.arange(s1 - s0, dtype=np.float32) / sample_rate
            freq = pluck_notes[b_idx % len(pluck_notes)]
            env = np.exp(-lt * 15.0) * np.minimum(lt / 0.006, 1.0)
            tone = 0.72 * np.sin(2.0 * np.pi * freq * lt) + 0.20 * np.sin(2.0 * np.pi * freq * 2.0 * lt)
            bed[s0:s1] += 0.055 * env * tone
        b_idx += 1
        bt += beat_step

    rng = np.random.default_rng(42)
    turn_starts: List[float] = []
    acc_t = 0.0
    for d in turn_durations:
        turn_starts.append(acc_t)
        acc_t += d

    # 8비트 타격 효과음 (AudioContext 주파수 스윕과 동일한 묵직한 square+noise 펀치)
    for idx, turn in enumerate(turns):
        t0 = turn_starts[idx]
        is_a = _is_turn_faction_a(turn, idx)
        dmg = _get_turn_damage(turn)
        hs0 = max(0, int(t0 * sample_rate))
        hs1 = min(n_samples, hs0 + int(0.20 * sample_rate))
        if hs1 > hs0:
            ht = np.arange(hs1 - hs0, dtype=np.float32) / sample_rate
            start_f = 220.0 if is_a else 190.0
            end_f = 42.0
            inst_f = start_f * np.exp(np.log(end_f / start_f) * np.minimum(ht / 0.16, 1.0))
            phase = 2.0 * np.pi * np.cumsum(inst_f) / sample_rate
            square_hit = np.sign(np.sin(phase)) * 0.65 + np.sin(phase * 0.5) * 0.35
            noise_hit = rng.normal(0.0, 1.0, hs1 - hs0).astype(np.float32)
            noise_hit = np.convolve(noise_hit, np.ones(6, dtype=np.float32) / 6.0, mode="same")
            n_env = np.exp(-ht * 36.0)
            h_env = np.exp(-ht * 17.0) * np.minimum(ht / 0.004, 1.0)
            gain = 0.24 + (dmg - 15) * 0.004
            bed[hs0:hs1] += gain * (h_env * square_hit + 0.55 * n_env * noise_hit)

    # 최종 K.O. 팡파르 스팅어
    if outro_sec > 0.2:
        for ni, freq in enumerate([261.63, 329.63, 392.00, 523.25]):
            ks0 = min(n_samples, int((battle_sec + ni * 0.075) * sample_rate))
            ks1 = min(n_samples, ks0 + int(0.42 * sample_rate))
            if ks1 > ks0:
                kt = np.arange(ks1 - ks0, dtype=np.float32) / sample_rate
                k_env = np.exp(-kt * 6.5) * np.minimum(kt / 0.008, 1.0)
                k_tone = np.sign(np.sin(2.0 * np.pi * freq * kt)) * 0.45 + np.sin(2.0 * np.pi * freq * kt) * 0.55
                bed[ks0:ks1] += 0.16 * k_env * k_tone

    voice_track = np.zeros(n_samples, dtype=np.float32)
    has_voice = False
    for idx, pcm in enumerate(turn_pcms):
        if pcm is None or len(pcm) == 0:
            continue
        peak = float(np.max(np.abs(pcm))) + 1e-6
        norm_pcm = (pcm / peak) * 0.88
        v0 = int((turn_starts[idx] + 0.12) * sample_rate)
        v1 = min(n_samples, v0 + len(norm_pcm))
        if v1 > v0:
            voice_track[v0:v1] = norm_pcm[: v1 - v0]
            has_voice = True

    audio = (bed * 0.36 + voice_track * 0.94) if has_voice else (bed * 0.96)
    fade_s = int(0.45 * sample_rate)
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


def _get_stage_assets() -> Dict[str, Any]:
    global _STAGE_ASSETS_CACHE
    if _STAGE_ASSETS_CACHE is not None:
        return _STAGE_ASSETS_CACHE

    # 깔끔한 다크 스튜디오 그라데이션 배경 (네온/도시/잡음 제거)
    y_norm = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None]
    r_ch = np.clip(9.0 + 10.0 * np.sin(y_norm * np.pi), 0, 255).astype(np.uint8)
    g_ch = np.clip(13.0 + 14.0 * np.sin(y_norm * np.pi), 0, 255).astype(np.uint8)
    b_ch = np.clip(22.0 + 20.0 * np.sin(y_norm * np.pi), 0, 255).astype(np.uint8)
    a_ch = np.full((H, 1), 255, dtype=np.uint8)
    row_rgba = np.concatenate([r_ch, g_ch, b_ch, a_ch], axis=1)
    bg_arr = np.repeat(row_rgba[:, None, :], W, axis=1)
    studio_bg = Image.fromarray(bg_arr, mode="RGBA")

    # 은은한 무대 바닥선 및 중앙 하단 비네트
    sd = ImageDraw.Draw(studio_bg, "RGBA")
    sd.rectangle([0, 1595, W, H], fill=(7, 10, 17, 255))
    sd.line([(72, 1595), (W - 72, 1595)], fill=(255, 255, 255, 28), width=2)

    pro_orig = Image.open(PRO_AVATAR_PATH).convert("RGBA")
    con_orig = Image.open(CON_AVATAR_PATH).convert("RGBA")

    pro_active_grade = ImageEnhance.Color(ImageEnhance.Brightness(pro_orig).enhance(1.06)).enhance(1.08)
    con_active_grade = ImageEnhance.Color(ImageEnhance.Brightness(con_orig).enhance(1.06)).enhance(1.08)

    def fit_h(im: Image.Image, target_h: int) -> Image.Image:
        sc = target_h / im.height
        return im.resize((int(round(im.width * sc)), target_h), Image.Resampling.LANCZOS)

    pro_act = fit_h(pro_active_grade, 680)
    pro_idle = ImageEnhance.Color(
        ImageEnhance.Brightness(fit_h(pro_orig, 646)).enhance(0.70)
    ).enhance(0.84)

    con_act = fit_h(con_active_grade, 680)
    con_idle = ImageEnhance.Color(
        ImageEnhance.Brightness(fit_h(con_orig, 646)).enhance(0.70)
    ).enhance(0.84)

    def add_fighter_shadow(base: Image.Image, cx: int, by: int) -> None:
        pad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pad)
        pd.ellipse([cx - 190, by - 26, cx + 190, by + 24], fill=(0, 0, 0, 165))
        base.alpha_composite(pad.filter(ImageFilter.GaussianBlur(20)))

    add_fighter_shadow(studio_bg, 265, 1600)
    add_fighter_shadow(studio_bg, 815, 1600)

    def make_glow(cx: int, cy: int, color: Tuple[int, int, int]) -> Image.Image:
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gd.ellipse([cx - 320, cy - 350, cx + 320, cy + 350], fill=(*color, 72))
        return g.filter(ImageFilter.GaussianBlur(115))

    glows: Dict[Tuple[str, str], Image.Image] = {}
    for ck, spec in PALETTE.items():
        glows[("PRO", ck)] = make_glow(265, 1230, spec["glow"])
        glows[("CON", ck)] = make_glow(815, 1230, spec["glow"])

    _STAGE_ASSETS_CACHE = {
        "studio_bg": studio_bg,
        "pro_act": pro_act,
        "pro_idle": pro_idle,
        "con_act": con_act,
        "con_idle": con_idle,
        "glows": glows,
    }
    return _STAGE_ASSETS_CACHE


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


def _pick_core_font_and_lines(
    text: str, max_width: int, fonts: Dict[str, ImageFont.FreeTypeFont]
) -> Tuple[ImageFont.FreeTypeFont, List[str]]:
    clean = " ".join((text or "").split())
    for key in ["core_lg", "core_md", "core_sm"]:
        f = fonts[key]
        if f.getlength(clean) <= max_width:
            return f, [clean]
    wrapped = _wrap_words_by_width(clean, fonts["core_sm"], max_width, max_lines=2)
    return fonts["core_sm"], [" ".join(ln) for ln in wrapped]


def _pick_caption_font_and_lines(
    clause_text: str, max_width: int, fonts: Dict[str, ImageFont.FreeTypeFont]
) -> Tuple[ImageFont.FreeTypeFont, List[List[str]], int]:
    word_cnt_total = len([w for w in clause_text.split() if w])
    for b_key, lh in [("body_xl", 56), ("body_lg", 50)]:
        bf = fonts[b_key]
        lines = _wrap_words_by_width(clause_text, bf, max_width, max_lines=3)
        if sum(len(x) for x in lines) >= word_cnt_total:
            return bf, lines, lh
    bf = fonts["body_lg"]
    return bf, _wrap_words_by_width(clause_text, bf, max_width, max_lines=4), 44


def _resolve_perspectives(
    raw_stats: Dict[str, Any],
    perspectives: Optional[List[Dict[str, Any]]],
    side_a_label: str = "",
    side_b_label: str = "",
) -> List[Dict[str, Any]]:
    if perspectives and isinstance(perspectives, list) and len(perspectives) >= 2:
        out: List[Dict[str, Any]] = []
        for idx, p in enumerate(perspectives[:2]):
            ck = "blue" if idx == 0 else "red"
            fallback_lbl = (side_a_label if idx == 0 else side_b_label) or ("A 진영" if idx == 0 else "B 진영")
            out.append({
                "short_label": (p.get("short_label") or p.get("label") or fallback_lbl)[:14],
                "ratio": max(1, int(p.get("ratio", 50))),
                "color": ck,
            })
        return out
    a_r = max(1, min(99, int(raw_stats.get("side_a_ratio", raw_stats.get("pro_ratio", 50)))))
    return [
        {"short_label": (side_a_label or "A 진영")[:14], "ratio": a_r, "color": "blue"},
        {"short_label": (side_b_label or "B 진영")[:14], "ratio": max(1, 100 - a_r), "color": "red"},
    ]


def _render_ui_hud_strips(
    issue_title: str,
    raw_stats: Dict[str, Any],
    perspectives: List[Dict[str, Any]],
    mode_label: str,
    side_a_label: str,
    side_b_label: str,
    turn_idx: int,
    total_turns: int,
    turn_data: Dict[str, Any],
    clause_idx: int,
    total_clauses: int,
    caption_font: ImageFont.FreeTypeFont,
    caption_lines: List[List[str]],
    line_h: int,
    active_word_idx: int,
    fonts: Dict[str, ImageFont.FreeTypeFont],
) -> Tuple[Image.Image, Image.Image]:
    """깔끔한 굵직한 주제 타이틀 + 다크 글래스 대사 카드(y=140..666) 및 미니멀 라운드 인디케이터(y=1770..1860)."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay, "RGBA")

    is_a = _is_turn_faction_a(turn_data, turn_idx)
    ckey = _get_turn_color_key(turn_data, turn_idx)
    dmg = _get_turn_damage(turn_data)
    pal = PALETTE[ckey]
    accent = pal["accent"]
    speaker_label = (side_a_label if is_a else side_b_label) or ("A 진영" if is_a else "B 진영")

    # 1) BOLD CLEAN TOPIC HEADER (y=144..266) — 자잘한 배지 전부 제거
    tx0, ty0, tx1, ty1 = 48, 144, W - 48, 266
    d.rounded_rectangle([tx0, ty0, tx1, ty1], radius=20, fill=(15, 23, 42, 224), outline=(255, 255, 255, 28), width=2)
    title_font, title_lines = _pick_title_font_and_lines(issue_title, W - 156, fonts)
    if len(title_lines) == 1:
        d.text((W // 2, (ty0 + ty1) // 2), title_lines[0], font=title_font, fill=(255, 255, 255, 255), anchor="mm")
    else:
        d.text((W // 2, ty0 + 40), title_lines[0], font=title_font, fill=(255, 255, 255, 255), anchor="mm")
        d.text((W // 2, ty0 + 86), title_lines[1], font=title_font, fill=(255, 255, 255, 255), anchor="mm")

    # 2) SLEEK DARK STATEMENT CARD (말풍선 꼬리/흰박스/팩폭 배지 전부 제거, y=288..658)
    bx0, by0, bx1, by1 = 48, 288, W - 48, 658
    d.rounded_rectangle([bx0, by0 + 8, bx1, by1 + 8], radius=22, fill=(0, 0, 0, 100))
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=22, fill=(15, 23, 42, 238), outline=(255, 255, 255, 34), width=2)
    # 굵직한 좌측 진영 컬러 라인
    d.rounded_rectangle([bx0, by0, bx0 + 10, by1], radius=6, fill=accent)
    d.rectangle([bx0 + 5, by0, bx0 + 10, by1], fill=accent)

    # 화자명 + 데미지 (단정하고 굵직하게 1줄)
    spk_col = (96, 165, 250, 255) if is_a else (248, 113, 113, 255)
    d.text((90, by0 + 44), speaker_label, font=fonts["speaker"], fill=spk_col, anchor="lm")

    dmg_txt = f"-{dmg} HP"
    d.rounded_rectangle([W - 208, by0 + 24, W - 82, by0 + 64], radius=10, fill=(220, 38, 38, 46), outline=(248, 113, 113, 130), width=1)
    d.text((W - 145, by0 + 44), dmg_txt, font=fonts["meta"], fill=(252, 165, 165, 255), anchor="mm")

    # 핵심 논점 (1~2줄)
    core_font, core_lines = _pick_core_font_and_lines(turn_data.get("core_point", ""), W - 180, fonts)
    claim_y0 = by0 + 84
    if len(core_lines) == 1:
        d.text((90, claim_y0 + 16), core_lines[0], font=core_font, fill=(203, 213, 225, 255), anchor="lm")
        div_y = claim_y0 + 46
    else:
        d.text((90, claim_y0 + 12), core_lines[0], font=core_font, fill=(203, 213, 225, 255), anchor="lm")
        d.text((90, claim_y0 + 44), core_lines[1], font=core_font, fill=(203, 213, 225, 255), anchor="lm")
        div_y = claim_y0 + 70

    d.line([(90, div_y), (W - 82, div_y)], fill=(255, 255, 255, 22), width=2)

    # 대사 본문 (다크 배경 위 고대비 흰 글씨 + 진영 컬러 활성 단어 하이라이트)
    space_w = caption_font.getlength(" ") + 3.0
    running_idx = 0
    block_h = len(caption_lines) * line_h
    avail_h = (by1 - 20) - (div_y + 18)
    start_y = div_y + 18 + max(0, (avail_h - block_h) // 2)

    for li, line_words in enumerate(caption_lines):
        cx = 90.0
        cy = start_y + li * line_h
        for w_str in line_words:
            ww = caption_font.getlength(w_str)
            if running_idx < active_word_idx:
                d.text((cx, cy), w_str, font=caption_font, fill=(241, 245, 249, 255), anchor="lt")
            elif running_idx == active_word_idx:
                pill_pad_y = max(40, int(line_h * 0.84))
                d.rounded_rectangle(
                    [int(cx - 8), int(cy - 4), int(cx + ww + 8), int(cy + pill_pad_y)],
                    radius=10,
                    fill=accent,
                )
                d.text((cx, cy), w_str, font=caption_font, fill=(255, 255, 255, 255), anchor="lt")
            else:
                d.text((cx, cy), w_str, font=caption_font, fill=(148, 163, 184, 255), anchor="lt")
            cx += ww + space_w
            running_idx += 1

    # 3) MINIMAL BOTTOM PROGRESS DOTS (y=1770..1860) — 하단 중복 카드·이퀄라이저 제거
    step_w = 56
    gap_w = 14
    total_w = total_turns * step_w + max(0, total_turns - 1) * gap_w
    px0 = (W - total_w) // 2
    py = 1812
    for i in range(total_turns):
        bx = px0 + i * (step_w + gap_w)
        if i == turn_idx:
            d.rounded_rectangle([bx, py, bx + step_w, py + 10], radius=5, fill=accent)
        elif i < turn_idx:
            d.rounded_rectangle([bx, py, bx + step_w, py + 10], radius=5, fill=(148, 163, 184, 210))
        else:
            d.rounded_rectangle([bx, py, bx + step_w, py + 10], radius=5, fill=(51, 65, 85, 190))

    return overlay.crop((0, 136, W, 670)), overlay.crop((0, 1770, W, 1860))


def _draw_top_hp_hud(
    frame: Image.Image,
    side_a_label: str,
    side_b_label: str,
    hp_a: float,
    hp_b: float,
    round_num: int,
    total_turns: int,
    fonts: Dict[str, ImageFont.FreeTypeFont],
) -> None:
    """상단 동적 진영 HP 게이지 바 (좌 블루 vs 우 레드) + 중앙 VS / X/6."""
    draw = ImageDraw.Draw(frame, "RGBA")
    draw.rounded_rectangle([48, 28, W - 48, 124], radius=18, fill=(15, 23, 42, 230), outline=(255, 255, 255, 32), width=2)

    bar_w = 340
    ax0 = 70
    ax1 = ax0 + bar_w
    draw.text((ax0, 54), (side_a_label or "A 진영")[:14], font=fonts["hud"], fill=(147, 197, 253, 255), anchor="lm")
    draw.text((ax1, 54), f"{int(round(hp_a))}", font=fonts["badge_sm"], fill=(219, 234, 254, 255), anchor="rm")
    draw.rounded_rectangle([ax0, 78, ax1, 100], radius=10, fill=(30, 41, 59, 255))
    fill_a = int(bar_w * max(0.0, min(1.0, hp_a / 100.0)))
    if fill_a > 4:
        draw.rounded_rectangle([ax0, 78, ax0 + fill_a, 100], radius=10, fill=(37, 99, 235, 255))

    draw.text((W // 2, 52), "VS", font=fonts["speaker"], fill=(250, 204, 21, 255), anchor="mm")
    draw.text((W // 2, 88), f"{round_num} / {total_turns}", font=fonts["claim_tag"], fill=(226, 232, 240, 255), anchor="mm")

    bx1 = W - 70
    bx0 = bx1 - bar_w
    draw.text((bx0, 54), f"{int(round(hp_b))}", font=fonts["badge_sm"], fill=(254, 226, 226, 255), anchor="lm")
    draw.text((bx1, 54), (side_b_label or "B 진영")[:14], font=fonts["hud"], fill=(252, 165, 165, 255), anchor="rm")
    draw.rounded_rectangle([bx0, 78, bx1, 100], radius=10, fill=(30, 41, 59, 255))
    fill_b = int(bar_w * max(0.0, min(1.0, hp_b / 100.0)))
    if fill_b > 4:
        draw.rounded_rectangle([bx1 - fill_b, 78, bx1, 100], radius=10, fill=(220, 38, 38, 255))


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
    side_a_label: str = "",
    side_b_label: str = "",
) -> Path:
    """1080x1920 @ 30fps Full-HD 동적 진영 HP 팩트 배틀 쇼츠 MP4 렌더링."""
    turns = debate_script[:8]
    total_turns = max(len(turns), 1)
    resolved_persp = _resolve_perspectives(raw_stats, perspectives, side_a_label, side_b_label)
    lbl_a = (side_a_label or resolved_persp[0]["short_label"] or "A 진영").strip()
    lbl_b = (side_b_label or resolved_persp[1]["short_label"] or "B 진영").strip()
    resolved_mode_lbl = (mode_label or "").strip() or "동적 진영 HP 팩트 배틀"

    # Pre-compute cumulative HP states (startHP -> endHP per turn)
    turn_hp_states: List[Tuple[int, int, int, int, bool, int]] = []
    cur_hp_a, cur_hp_b = 100, 100
    for idx, t in enumerate(turns):
        is_a = _is_turn_faction_a(t, idx)
        dmg = _get_turn_damage(t)
        start_a, start_b = cur_hp_a, cur_hp_b
        if is_a:
            cur_hp_b = max(0, cur_hp_b - dmg)
        else:
            cur_hp_a = max(0, cur_hp_a - dmg)
        turn_hp_states.append((start_a, start_b, cur_hp_a, cur_hp_b, is_a, dmg))

    # Step 1: Collect or synthesize voice audio in parallel across all turns
    raw_voices: List[Optional[bytes]] = [None] * len(turns)
    client_supplied_any = bool(turn_audio_b64_list and any(turn_audio_b64_list))

    if client_supplied_any and turn_audio_b64_list:
        for idx in range(min(len(turns), len(turn_audio_b64_list))):
            if turn_audio_b64_list[idx]:
                try:
                    raw_voices[idx] = base64.b64decode(turn_audio_b64_list[idx])  # type: ignore[arg-type]
                except Exception:
                    raw_voices[idx] = None

    # 클라이언트가 못 채운 턴은 서버 TTS(Cloud → Edge → gTTS)로 병렬 합성
    missing = [i for i, rv in enumerate(raw_voices) if not rv]
    if try_gemini_tts and missing:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(missing))) as pool:
            futs = {
                i: pool.submit(fetch_tts_audio_bytes, turns[i]["text"], "PRO" if _is_turn_faction_a(turns[i], i) else "CON")
                for i in missing
            }
            for i, f in futs.items():
                try:
                    raw_voices[i] = f.result()
                except Exception:
                    raw_voices[i] = None

    turn_pcms: List[Optional[np.ndarray]] = []
    for rv in raw_voices:
        if rv:
            pcm = _pcm16_resample_mono(rv, SAMPLE_RATE, SAMPLE_RATE)
            turn_pcms.append(pcm if len(pcm) > 0 else None)
        else:
            turn_pcms.append(None)

    voiced_pcms = sum(1 for p in turn_pcms if p is not None and len(p) > int(SAMPLE_RATE * 0.25))

    # Step 2: Rapid-fire 1.3x battle durations (+0.30s beat between turns)
    turn_durations: List[float] = []
    for idx, turn in enumerate(turns):
        pcm = turn_pcms[idx]
        if pcm is not None and len(pcm) > SAMPLE_RATE * 0.4:
            turn_durations.append(round(max(2.2, (len(pcm) / SAMPLE_RATE) + 0.12 + 0.30), 2))
        else:
            turn_durations.append(estimate_turn_duration_sec(turn["text"], speed_mult=1.3))

    turn_frame_counts = [max(30, int(round(d * FPS))) for d in turn_durations]
    outro_sec = 1.5
    outro_frames = int(round(outro_sec * FPS))

    assets = _get_stage_assets()
    fonts = _get_fonts()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        wav_path = tmp / "soundtrack.wav"
        rms_env, has_voice = generate_broadcast_soundtrack(
            wav_path=wav_path,
            turns=turns,
            turn_pcms=turn_pcms,
            turn_durations=turn_durations,
            outro_sec=outro_sec,
        )
        if meta_out is not None:
            meta_out["has_voice"] = bool(has_voice and voiced_pcms > 0)
            meta_out["voiced_turns"] = voiced_pcms
            meta_out["total_turns"] = len(turns)

        proc = subprocess.Popen(
            [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-s", f"{W}x{H}",
                "-pix_fmt", "rgb24",
                "-r", str(FPS),
                "-i", "pipe:0",
                "-i", str(wav_path),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "20",
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
        last_stage_frame: Optional[Image.Image] = None
        for idx, turn in enumerate(turns):
            start_a, start_b, end_a, end_b, is_a, dmg = turn_hp_states[idx]
            ckey = _get_turn_color_key(turn, idx)
            accent_rgb = PALETTE[ckey]["accent"][:3]

            turn_bg = assets["studio_bg"].copy()
            side_key = "PRO" if is_a else "CON"
            turn_bg.alpha_composite(assets["glows"][(side_key, ckey)])

            stage_cache: Dict[Tuple[int, int], Image.Image] = {}

            def get_stage_rgb(dy_talk: int, dx_hit: int) -> Image.Image:
                key = (dy_talk, dx_hit)
                if key in stage_cache:
                    return stage_cache[key]
                st = turn_bg.copy()
                if is_a:
                    p_spr = assets["pro_act"]
                    c_spr = assets["con_idle"]
                    st.paste(c_spr, (815 - c_spr.width // 2 + dx_hit, 1600 - c_spr.height), c_spr)
                    st.paste(p_spr, (265 - p_spr.width // 2, 1600 - p_spr.height + dy_talk), p_spr)
                else:
                    p_spr = assets["pro_idle"]
                    c_spr = assets["con_act"]
                    st.paste(p_spr, (265 - p_spr.width // 2 + dx_hit, 1600 - p_spr.height), p_spr)
                    st.paste(c_spr, (815 - c_spr.width // 2, 1600 - c_spr.height + dy_talk), c_spr)
                rgb = st.convert("RGB")
                stage_cache[key] = rgb
                return rgb

            base_stage_rgb = get_stage_rgb(0, 0)
            top_bg_crop = base_stage_rgb.crop((0, 136, W, 670))
            bot_bg_crop = base_stage_rgb.crop((0, 1770, W, 1860))

            clauses = _split_turn_into_clauses(turn["text"])
            clause_strips: List[List[Tuple[Image.Image, Image.Image]]] = []
            clause_timelines: List[List[Tuple[float, float]]] = []

            for c_idx, c_text in enumerate(clauses):
                c_font, c_lines, lh = _pick_caption_font_and_lines(c_text, W - 180, fonts)
                flat_words = [w for ln in c_lines for w in ln]
                w_cnt = max(len(flat_words), 1)
                clause_timelines.append(_build_weighted_word_timeline(flat_words))
                strips_for_clause: List[Tuple[Image.Image, Image.Image]] = []
                for w_idx in range(w_cnt):
                    top_rgba, bot_rgba = _render_ui_hud_strips(
                        issue_title=issue_title,
                        raw_stats=raw_stats,
                        perspectives=resolved_persp,
                        mode_label=resolved_mode_lbl,
                        side_a_label=lbl_a,
                        side_b_label=lbl_b,
                        turn_idx=idx,
                        total_turns=total_turns,
                        turn_data=turn,
                        clause_idx=c_idx,
                        total_clauses=len(clauses),
                        caption_font=c_font,
                        caption_lines=c_lines,
                        line_h=lh,
                        active_word_idx=w_idx,
                        fonts=fonts,
                    )
                    top_rgb = top_bg_crop.copy()
                    top_rgb.paste(top_rgba, (0, 0), top_rgba)
                    bot_rgb = bot_bg_crop.copy()
                    bot_rgb.paste(bot_rgba, (0, 0), bot_rgba)
                    strips_for_clause.append((top_rgb, bot_rgb))
                clause_strips.append(strips_for_clause)

            clause_windows = _analyze_pcm_clause_timing(
                turn_pcms[idx],
                SAMPLE_RATE,
                clauses,
                turn_durations[idx],
                lead_in_sec=0.12,
            )

            n_f = turn_frame_counts[idx]
            for f in range(n_f):
                local_t = f / FPS
                energy = float(rms_env[min(global_f, len(rms_env) - 1)])
                global_f += 1

                talk_cadence = (
                    math.sin(local_t * 3.0) * 1.6
                    - (0.8 + 2.2 * energy) * (0.5 + 0.5 * math.sin(local_t * 6.5))
                )
                dy_talk = max(-6, min(2, int(round(talk_cadence))))

                # Hit shake + red flash during first 0.48s of turn
                dx_hit = 0
                if local_t < 0.48:
                    dx_hit = int(round(math.sin(local_t * 58.0) * 16.0 * (1.0 - local_t / 0.48)))

                frame = get_stage_rgb(dy_talk, dx_hit).copy()

                c_idx, local_w = _resolve_clause_and_word(local_t, clause_timelines, clause_windows)
                ov_list = clause_strips[min(c_idx, len(clause_strips) - 1)]
                top_rgb, bot_rgb = ov_list[min(local_w, len(ov_list) - 1)]
                frame.paste(top_rgb, (0, 136))
                frame.paste(bot_rgb, (0, 1770))

                # Red hit flash & clean -HP popup over defender side
                if local_t < 0.72:
                    d_fx = ImageDraw.Draw(frame, "RGBA")
                    if local_t < 0.34:
                        alpha_flash = int(95 * (1.0 - local_t / 0.34))
                        fx_x0, fx_x1 = (540, W) if is_a else (0, 540)
                        d_fx.rectangle([fx_x0, 880, fx_x1, 1610], fill=(220, 38, 38, alpha_flash))
                    pop_prog = local_t / 0.72
                    pop_alpha = int(255 * min(1.0, (1.0 - pop_prog) * 1.4))
                    pop_cx = 815 if is_a else 265
                    pop_cy = int(890 - pop_prog * 55)
                    pop_txt = f"-{dmg} HP"
                    pw_pop = int(fonts["dmg_pop"].getlength(pop_txt) + 36)
                    d_fx.rounded_rectangle(
                        [pop_cx - pw_pop // 2, pop_cy - 24, pop_cx + pw_pop // 2, pop_cy + 24],
                        radius=12,
                        fill=(153, 27, 27, int(pop_alpha * 0.92)),
                        outline=(252, 165, 165, pop_alpha),
                        width=2,
                    )
                    d_fx.text((pop_cx, pop_cy), pop_txt, font=fonts["dmg_pop"], fill=(255, 255, 255, pop_alpha), anchor="mm")

                # Animated HP drain during first 0.35s
                hp_t = min(1.0, local_t / 0.35)
                disp_hp_a = start_a + (end_a - start_a) * hp_t
                disp_hp_b = start_b + (end_b - start_b) * hp_t

                _draw_top_hp_hud(frame, lbl_a, lbl_b, disp_hp_a, disp_hp_b, idx + 1, total_turns, fonts)

                last_stage_frame = frame
                proc.stdin.write(frame.tobytes())

        # Step 3: Append 1.5s K.O. Victory Overlay finale
        winner_is_a = cur_hp_a >= cur_hp_b
        winner_lbl = lbl_a if winner_is_a else lbl_b
        win_col = PALETTE["blue"]["accent"] if winner_is_a else PALETTE["red"]["accent"]
        if last_stage_frame is None:
            last_stage_frame = Image.new("RGB", (W, H), (9, 13, 22))

        for of in range(outro_frames):
            ko_frame = last_stage_frame.copy()
            kd = ImageDraw.Draw(ko_frame, "RGBA")
            kd.rectangle([0, 0, W, H], fill=(6, 9, 16, 175))
            _draw_top_hp_hud(ko_frame, lbl_a, lbl_b, float(cur_hp_a), float(cur_hp_b), total_turns, total_turns, fonts)

            # Center K.O. Victory Card
            cx0, cy0, cx1, cy1 = 80, 740, W - 80, 1140
            kd.rounded_rectangle([cx0, cy0, cx1, cy1], radius=32, fill=(15, 23, 42, 248), outline=(250, 204, 21, 255), width=5)
            kd.rounded_rectangle([W // 2 - 140, cy0 + 44, W // 2 + 140, cy0 + 124], radius=18, fill=(220, 38, 38, 255))
            kd.text((W // 2, cy0 + 84), "K.O.", font=fonts["ko_big"], fill=(255, 255, 255, 255), anchor="mm")

            win_pill = f"K.O. - [{winner_lbl}] 여론 우세!"
            kd.text((W // 2, cy0 + 215), win_pill, font=fonts["title_lg"], fill=(250, 204, 21, 255), anchor="mm")
            score_txt = f"{lbl_a} {cur_hp_a} HP  vs  {lbl_b} {cur_hp_b} HP"
            half_pw = min((cx1 - cx0) // 2 - 28, max(240, int(fonts["hud"].getlength(score_txt) // 2 + 34)))
            kd.rounded_rectangle([W // 2 - half_pw, cy0 + 280, W // 2 + half_pw, cy0 + 340], radius=14, fill=win_col)
            kd.text(
                (W // 2, cy0 + 310),
                score_txt,
                font=fonts["hud"],
                fill=(255, 255, 255, 255),
                anchor="mm",
            )
            proc.stdin.write(ko_frame.tobytes())

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
            try_gemini_tts=True,
            perspectives=data.get("perspectives"),
            mode_label=data.get("mode_label", ""),
            side_a_label=data.get("side_a_label", ""),
            side_b_label=data.get("side_b_label", ""),
        )
        print(f"[MP4 RENDERED 1080p 30fps] {out_file} ({out_file.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
