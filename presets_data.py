"""
presets_data.py
YouTube Data API v3로 실제 수집한 12개 방송사 뉴스 영상 댓글(총 N = 527건) 기반 실측 프리셋 데이터셋.
"""

import json
from pathlib import Path
from typing import Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent
REAL_YT_PATH = BASE_DIR / "data" / "real_youtube_comments.json"

_raw_yt = {}
if REAL_YT_PATH.exists():
    try:
        _raw_yt = json.loads(REAL_YT_PATH.read_text(encoding="utf-8"))
    except Exception:
        _raw_yt = {}


def _get_real_comments_text_list(pid: str, fallback: List[str]) -> List[str]:
    if pid in _raw_yt and _raw_yt[pid].get("comments"):
        return [c["text"] for c in _raw_yt[pid]["comments"] if c.get("text")]
    return fallback


PRESETS: Dict[str, Dict[str, Any]] = {
    "preset_1": {
        "id": "preset_1",
        "button_label": "프리셋 1: 심야 배달 오토바이 소음 규제 (실측 N=200)",
        "category_badge": "YTN·MBC·연합뉴스TV 실측 댓글 200건 | 환경권 vs 생존권",
        "source_label": "YouTube Data API v3 실측 수집 · YTN(vNIXiWyXs90), MBC(lt7knjTuuOM), 연합뉴스TV(Cs_A2EcMsto) 댓글 200건",
        "source_url": "https://www.youtube.com/watch?v=vNIXiWyXs90",
        "video_mp4_url": "/static/videos/preset_1.mp4",
        "has_voice_track": False,
        "analysis_mode": "debate",
        "mode_label": "찬반 공론장 중재",
        "issue_title": "심야 시간대 배달 오토바이 배기 소음 규제 및 단속 의무화 논란",
        "perspectives": [
            {"id": "P1", "label": "단속·소음 규제 강화", "short_label": "규제 강화", "ratio": 88, "color": "blue", "keywords": ["배기소음", "단속강화", "번호판"]},
            {"id": "P2", "label": "라이더 생존권·인프라", "short_label": "신중·보완", "ratio": 12, "color": "red", "keywords": ["생계형", "전기이륜차", "핀셋단속"]},
        ],
        "raw_stats": {
            "total_comments": 200,
            "filtered_curse_count": 58,
            "pro_ratio": 88,
            "con_ratio": 12,
            "toxicity_before": 64.2,
            "toxicity_after": 14.5,
        },
        "debate_script": [
            {
                "speaker": "PRO",
                "perspective_id": "P1",
                "perspective_label": "규제 강화",
                "color": "blue",
                "core_point": "헌법상 주거 평온권 및 심야 수면권 침해 심각",
                "text": "새벽 시간대 주택가를 관통하는 불법 개조 오토바이의 폭발적인 배기음은 시민들의 수면 건강과 일상을 심각하게 파괴하고 있습니다. 유명무실한 현행 소음 기준을 대폭 낮추고 상시 음향 단속 카메라와 즉각적인 처벌 법안을 도입해야 합니다."
            },
            {
                "speaker": "CON",
                "perspective_id": "P2",
                "perspective_label": "신중·보완",
                "color": "red",
                "core_point": "생계형 배달 라이더 생존권 및 플랫폼 속도 경쟁 구조",
                "text": "일부 불법 개조 운전자의 일탈을 이유로 야간 생계형 라이더 전체의 운행을 제한하는 것은 과도한 생존권 침해입니다. 배달 시간 단축을 강요하는 플랫폼 알고리즘과 야간 할증 구조를 개선하는 것이 근본적인 해결책입니다."
            },
            {
                "speaker": "PRO",
                "perspective_id": "P1",
                "perspective_label": "규제 강화",
                "color": "blue",
                "core_point": "전면 번호판 의무화 및 불법 소음기 개조 원천 차단",
                "text": "단속 경찰 앞에서도 보란 듯이 굉음을 내며 도주할 수 있는 이유는 후면 번호판 중심의 허술한 식별 체계 때문입니다. 전면 번호판 부착을 의무화하고 불법 머플러 개조 업체와 운전자에게 징벌적 과태료를 부과해야 합니다."
            },
            {
                "speaker": "CON",
                "perspective_id": "P2",
                "perspective_label": "신중·보완",
                "color": "red",
                "core_point": "전기 이륜차 보급 인프라 및 배터리 교환소 선행 확충",
                "text": "단속과 처벌만으로는 반복되는 소음 갈등을 근본적으로 해결할 수 없습니다. 영세 배달 종사자들이 무소음 전기 이륜차로 부담 없이 전환할 수 있도록 구매 보조금과 배터리 교환 인프라를 먼저 확충해야 합니다."
            },
            {
                "speaker": "PRO",
                "perspective_id": "P1",
                "perspective_label": "규제 강화",
                "color": "blue",
                "core_point": "주거 밀집 지역 심야 내연기관 이륜차 통행 제한 구역 지정",
                "text": "아파트 단지와 주택가 골목에서는 밤 열한 시 이후 고소음 내연기관 이륜차 진입을 제한하는 심야 정온 구역 지정이 시급합니다. 다수 시민의 건강권과 환경권 보호는 더 이상 미룰 수 없는 공공의 책무입니다."
            },
            {
                "speaker": "CON",
                "perspective_id": "P2",
                "perspective_label": "신중·보완",
                "color": "red",
                "core_point": "야간 자영업 생태계 보호 및 핀셋 단속 기반 상생 거버넌스",
                "text": "심야 배달을 일괄 차단하면 야간 매출에 의존하는 영세 소상공인과 교대 근무 소비자들까지 연쇄적인 피해를 입게 됩니다. 획일적 통행 금지 대신 소음 기준 초과 차량만 정밀 타격하는 스마트 단속과 친환경 인센티브를 병행해야 합니다."
            }
        ],
        "detox_samples": [
            {
                "side": "PRO",
                "perspective_label": "규제 강화",
                "color": "blue",
                "raw": "[실제 댓글 · @user-ytn] 단속 의지도 없으면서 ㄱ ㅐ소리!!! 파출소 배달가는 딸배도 붕붕 거리더라",
                "cleaned": "일선 단속의 실효성이 부족하여 공공기관 인근에서도 이륜차 소음이 방치되고 있으므로 상시 단속 체계를 강화해야 합니다.",
                "removed_tokens": ["ㄱ ㅐ소리!!!", "딸배도"]
            },
            {
                "side": "PRO",
                "perspective_label": "규제 강화",
                "color": "blue",
                "raw": "[실제 댓글 · 좋아요 53] 강력처벌 해야 합니다..오토바이 자동차 배기음 폭발하는 소리 진짜 살인을 부릅니다.",
                "cleaned": "심야 시간대 기준치를 초과하는 배기 소음은 극심한 정신적 고통을 유발하므로 처벌 수위를 대폭 강화해야 합니다.",
                "removed_tokens": ["살인을 부릅니다"]
            },
            {
                "side": "PRO",
                "perspective_label": "규제 강화",
                "color": "blue",
                "raw": "[실제 댓글 · MBC뉴스] 오토바이 소음 단속 백날해봐라 없어지는가....처벌법이 개법인데 그때뿐이지.",
                "cleaned": "일회성 합동 단속만으로는 소음 근절이 어려우므로 관련 처벌 법규와 배기음 허용 기준 자체를 실효성 있게 개정해야 합니다.",
                "removed_tokens": ["백날해봐라", "개법인데"]
            },
            {
                "side": "CON",
                "perspective_label": "신중·보완",
                "color": "red",
                "raw": "[실제 댓글 · 연합뉴스TV] 먹고살려고 밤잠 줄여가며 배달 뛰는 기사들까지 싸잡아서 범죄자 취급하네 법 지키는 사람이 더 많다",
                "cleaned": "법규를 준수하는 다수의 생계형 배달 종사자까지 일괄 규제의 대상으로 삼기보다 불법 개조 차량에 한정한 핀셋 단속이 필요합니다.",
                "removed_tokens": ["싸잡아서", "범죄자 취급하네"]
            }
        ],
        "raw_comments": _get_real_comments_text_list("preset_1", [
            "단속 의지도 없으면서 ㄱ ㅐ소리!!! 파출소 배달가는 딸배도 붕붕 거리더라",
            "강력처벌 해야 합니다..오토바이 자동차 배기음 폭발하는 소리 진짜 살인을 부릅니다.",
            "오토바이 소음 단속 백날해봐라 없어지는가....처벌법이 개법인데 그때뿐이지."
        ])
    },

    "preset_2": {
        "id": "preset_2",
        "button_label": "프리셋 2: 전동킥보드 즉시 견인·금지 (실측 N=180)",
        "category_badge": "MBC·SBS·TBS 실측 댓글 180건 | 보행안전 vs 이동권·인프라",
        "source_label": "YouTube Data API v3 실측 수집 · MBC(Xt8TRqMuZRc), SBS(aI0awk0NBfc), TBS(D2hNIe74HEQ) 댓글 180건",
        "source_url": "https://www.youtube.com/watch?v=Xt8TRqMuZRc",
        "video_mp4_url": "/static/videos/preset_2.mp4",
        "has_voice_track": False,
        "analysis_mode": "debate",
        "mode_label": "찬반 공론장 중재",
        "issue_title": "대학가·도심 공유 전동킥보드 즉시 견인 및 통행 금지 논란",
        "perspectives": [
            {"id": "P1", "label": "보행 안전·즉시 견인", "short_label": "견인·규제", "ratio": 87, "color": "blue", "keywords": ["보행안전", "무단방치", "허가제"]},
            {"id": "P2", "label": "전용 주차·이동권 공존", "short_label": "인프라·공존", "ratio": 13, "color": "red", "keywords": ["주차존", "GPS감속", "라스트마일"]},
        ],
        "raw_stats": {
            "total_comments": 180,
            "filtered_curse_count": 32,
            "pro_ratio": 87,
            "con_ratio": 13,
            "toxicity_before": 61.5,
            "toxicity_after": 14.2,
        },
        "debate_script": [
            {
                "speaker": "PRO",
                "perspective_id": "P1",
                "perspective_label": "견인·규제",
                "color": "blue",
                "core_point": "보행자 안전 위협 및 인도 무단 방치 기기 즉시 견인",
                "text": "인도와 골목길 한가운데 아무렇게나 방치된 공유 전동킥보드는 보행자의 통행을 가로막고 심각한 안전사고를 유발하고 있습니다. 유예 시간 없는 즉시 강제 견인을 전국 지자체로 확대하고 무단 방치 이용자에게 과태료를 직접 부과해야 합니다."
            },
            {
                "speaker": "CON",
                "perspective_id": "P2",
                "perspective_label": "인프라·공존",
                "color": "red",
                "core_point": "전용 주차 구역(PM 파킹존) 인프라 확충 선행 필요",
                "text": "반납할 수 있는 전용 주차 구역조차 마련하지 않은 채 무조건 견인부터 시행하는 것은 앞뒤가 바뀐 행정입니다. 지자체와 대여 업체가 협력하여 보도 위 지정 거치대와 표준 주차 인프라를 먼저 구축해야 합니다."
            },
            {
                "speaker": "PRO",
                "perspective_id": "P1",
                "perspective_label": "견인·규제",
                "color": "blue",
                "core_point": "민간 공유 킥보드 대여 업체의 관리 책임 및 허가제 도입",
                "text": "수익은 민간 대여 업체가 거두면서 무면허 주행과 기기 방치로 인한 사회적 비용은 시민과 지자체가 떠안고 있습니다. 공유 모빌리티 사업을 등록제에서 허가제로 전환하고 안전 관리 의무를 위반한 업체의 영업을 제한해야 합니다."
            },
            {
                "speaker": "CON",
                "perspective_id": "P2",
                "perspective_label": "인프라·공존",
                "color": "red",
                "core_point": "억울한 견인료 부과 피해 방지 및 GPS 기술적 규제 대안",
                "text": "정상적으로 반납한 이용자에게까지 며칠 뒤 수만 원의 견인료를 일방 청구하는 등 무분별한 견인 행정의 부작용이 속출하고 있습니다. 전면 퇴출이나 과잉 견인 대신 지피에스 기반 지정 구역 외 반납 차단 기술을 의무화해야 합니다."
            },
            {
                "speaker": "PRO",
                "perspective_id": "P1",
                "perspective_label": "견인·규제",
                "color": "blue",
                "core_point": "교통약자 보행권 수호 및 보행 밀집 구역 통행 금지",
                "text": "점자블록과 횡단보도 앞에 쓰러진 킥보드는 시각장애인과 유모차, 노약자에게 도로 위 흉기와 다름없습니다. 대학가와 어린이 보호구역 등 보행 밀집 지역에서는 전동킥보드 통행을 전면 금지해야 합니다."
            },
            {
                "speaker": "CON",
                "perspective_id": "P2",
                "perspective_label": "인프라·공존",
                "color": "red",
                "core_point": "단거리 대중교통 보완재로서의 편익 및 합리적 제도화",
                "text": "전동킥보드는 대중교통 사각지대를 연결하는 친환경 라스트마일 이동수단으로서 분명한 수요와 편익이 존재합니다. 일괄적인 퇴출보다는 속도 제한과 번호판 부착, 전용 주차존 확충을 통해 제도권 안에서 안전하게 공존해야 합니다."
            }
        ],
        "detox_samples": [
            {
                "side": "PRO",
                "perspective_label": "견인·규제",
                "color": "blue",
                "raw": "[실제 댓글 · MBC뉴스] 제발 그냥 전동킥보드든 전기자전거든 다 없애라.... 사용자들이 저렇게 개판치고 서로 불편해지는데 왜 있어야 되냐???",
                "cleaned": "무단 방치와 안전수칙 미준수로 인한 사회적 불편이 크므로 공유 모빌리티에 대한 강력한 통행 및 영업 규제가 필요합니다.",
                "removed_tokens": ["다 없애라", "개판치고"]
            },
            {
                "side": "PRO",
                "perspective_label": "견인·규제",
                "color": "blue",
                "raw": "[실제 댓글 · 좋아요 29] 도대체 킥보드는 안전문제에 불법주차등 문제투성인데 왜 채택하는거죠? 불법주차하는 사용자에게 책임을 물으세요!!!",
                "cleaned": "보행 안전과 보도 질서 확립을 위해 불법 주차 및 무단 방치 이용자에게 명확한 법적·경제적 책임을 부과해야 합니다.",
                "removed_tokens": ["문제투성인데", "!!!"]
            },
            {
                "side": "CON",
                "perspective_label": "인프라·공존",
                "color": "red",
                "raw": "[실제 댓글 · 좋아요 19] 킥보드 업체가 주차장소를 만들고 영업을 해야지... 아무 길이나 방치되어 있는 킥보드는 주차 인프라부터 강제해야 한다",
                "cleaned": "무단 방치 문제를 근본적으로 해결하기 위해 대여 업체와 지자체가 전용 주차 공간을 의무적으로 확보하도록 제도화해야 합니다.",
                "removed_tokens": ["아무 길이나"]
            },
            {
                "side": "CON",
                "perspective_label": "인프라·공존",
                "color": "red",
                "raw": "[실제 댓글 · SBS뉴스] 킥보드 타지도 않았는데 번호판도 없으니 누가 옮겨놔도 사용자한테 4만원 덤터기 씌우는 게 말이 되냐 황당하네",
                "cleaned": "제3자의 기기 이동 등으로 인한 억울한 견인료 부과 피해를 막기 위해 명확한 반납 인증 및 과징금 분쟁 조정 절차가 필요합니다.",
                "removed_tokens": ["덤터기 씌우는", "황당하네"]
            }
        ],
        "raw_comments": _get_real_comments_text_list("preset_2", [
            "제발 그냥 전동킥보드든 전기자전거든 다 없애라.... 사용자들이 저렇게 개판치고 서로 불편해지는데 왜 있어야 되냐???",
            "도대체 킥보드는 안전문제에 불법주차등 문제투성인데 왜 채택하는거죠? 불법주차하는 사용자에게 책임을 물으세요!!!"
        ])
    },

    "preset_3": {
        "id": "preset_3",
        "button_label": "프리셋 3: 고령 운전자 3관점 해법 (실측 N=147)",
        "category_badge": "MBC·KBS·YTN 실측 댓글 147건 | 실기검증 vs 이동권 vs 안전기술 대안",
        "source_label": "YouTube Data API v3 실측 수집 · MBC(NKIvNrtdiGA), KBS(x3J5hpBci98 외 2건), YTN(yfAshZpECCo) 댓글 147건",
        "source_url": "https://www.youtube.com/watch?v=NKIvNrtdiGA",
        "video_mp4_url": "/static/videos/preset_3.mp4",
        "has_voice_track": False,
        "analysis_mode": "multi",
        "mode_label": "3관점 여론 비교",
        "issue_title": "고령 운전자 면허 논쟁, 실기검증·이동권·안전기술 3대 시각",
        "perspectives": [
            {"id": "P1", "label": "실기·정기 검증 강화", "short_label": "안전 검증", "ratio": 47, "color": "blue", "keywords": ["실기시험", "면허갱신", "정년"]},
            {"id": "P2", "label": "농촌·생계 이동권 보장", "short_label": "이동권 보장", "ratio": 33, "color": "red", "keywords": ["대중교통", "농어촌", "생계운전"]},
            {"id": "P3", "label": "오조작 장치·기술 대안", "short_label": "기술 대안", "ratio": 20, "color": "violet", "keywords": ["오조작방지", "자율주행", "복지택시"]},
        ],
        "raw_stats": {
            "total_comments": 147,
            "filtered_curse_count": 36,
            "pro_ratio": 78,
            "con_ratio": 22,
            "toxicity_before": 62.4,
            "toxicity_after": 14.5,
        },
        "debate_script": [
            {
                "speaker": "PRO",
                "perspective_id": "P1",
                "perspective_label": "안전 검증",
                "color": "blue",
                "core_point": "페달 오조작 및 인지 저하 예방을 위한 정기 실기 평가",
                "text": "전체 댓글의 47퍼센트를 차지한 안전 검증 측에서는 고령 운전자의 판단 지연과 페달 오조작 사고를 막기 위해 정기 실주행 시험과 인지 적성검사를 대폭 강화해야 한다고 강조합니다."
            },
            {
                "speaker": "CON",
                "perspective_id": "P2",
                "perspective_label": "이동권 보장",
                "color": "red",
                "core_point": "일회성 10만 원 지원의 한계와 농어촌 대중교통 공백",
                "text": "반면 33퍼센트 비중의 이동권 보장 측에서는 버스조차 드문 지방과 농어촌에서 단발성 십만 원 교통카드만 주고 면허를 반납하라는 것은 일상생활을 포기하라는 탁상행정이라고 지적합니다."
            },
            {
                "speaker": "PRO",
                "perspective_id": "P3",
                "perspective_label": "기술 대안",
                "color": "violet",
                "core_point": "페달 오조작 방지 장치 및 자율주행 보조 기술 의무화",
                "text": "여기에 제3의 시각인 20퍼센트의 기술 대안 측에서는 나이로 면허를 일괄 회수하기보다 페달 오조작 방지 센서와 긴급 자동 제동 장치를 국가 보조금으로 보급하는 것이 현실적이라고 제안합니다."
            },
            {
                "speaker": "CON",
                "perspective_id": "P2",
                "perspective_label": "이동권 보장",
                "color": "red",
                "core_point": "생계형 운전자 차별 경계 및 연령 중심 획일 규제 반대",
                "text": "또한 택시나 화물로 생계를 이어가는 고령층에게 연령만을 잣대로 운전을 막는 것은 공정하지 않으며, 실제 건강 상태와 주행 데이터로 역량을 따져야 한다는 목소리도 높습니다."
            },
            {
                "speaker": "PRO",
                "perspective_id": "P1",
                "perspective_label": "안전 검증",
                "color": "blue",
                "core_point": "면허 갱신 주기 단축과 사고 치사율 구간 단계적 제한",
                "text": "안전 검증 측 역시 형식적인 서류 갱신을 폐지하고 야간과 고속도로 주행을 제한하는 조건부 면허를 단계적으로 적용해 공공 도로 안전을 먼저 확보하자고 거듭 촉구합니다."
            },
            {
                "speaker": "CON",
                "perspective_id": "P3",
                "perspective_label": "기술 대안",
                "color": "violet",
                "core_point": "수요응답형 복지 택시 확충과 안전장치 기반 상생 해법",
                "text": "결국 댓글창의 다각도 의견을 종합하면 정기 검증으로 위험 운전을 거르되, 호출형 복지 택시와 안전 보조장치를 함께 지원해야 실효성 있는 제도 정착이 가능합니다."
            }
        ],
        "detox_samples": [
            {
                "side": "PRO",
                "perspective_label": "안전 검증",
                "color": "blue",
                "raw": "[실제 댓글 · MBC뉴스] 오늘 운전하다가 미친각으로 끼어드는 차 있어서 욕하고 넘어갔는데 70대 할머니더라 본인이 민폐라 생각하면 면허 반납 좀 해라",
                "cleaned": "고령에 따른 인지능력 및 시야 저하로 위험 주행이 발생할 경우 공공 안전을 위해 자발적 면허 반납과 적성검사 강화가 필요합니다.",
                "removed_tokens": ["미친각으로", "욕하고", "민폐라"]
            },
            {
                "side": "PRO",
                "perspective_label": "안전 검증",
                "color": "blue",
                "raw": "[실제 댓글 · KBS뉴스] 솔직히 도로에 나가보면 말도안되게 운전하는 사람들 나이 많으신분들이 대다수 본인 먹고 살겠다고 남한테 피해주면 안되지 정기 시험 봐라!!",
                "cleaned": "생계 목적의 운전이더라도 도로 위 타인의 안전을 위협하지 않도록 고령 운전자 대상 정기 실기시험을 의무화해야 합니다.",
                "removed_tokens": ["말도안되게", "!!"]
            },
            {
                "side": "CON",
                "perspective_label": "이동권 보장",
                "color": "red",
                "raw": "[실제 댓글 · MBC뉴스] 면허 반납하면 10만원 카드 한 장 달랑 주면서 반납하라고 하는 게 코미디지 시골은 버스도 없는데 걸어 다니란 소리냐",
                "cleaned": "대중교통이 취약한 지역 여건을 무시한 일회성 10만 원 지원책은 실효성이 낮으므로 지속적인 대체 이동수단 지원이 선행되어야 합니다.",
                "removed_tokens": ["달랑 주면서", "코미디지"]
            },
            {
                "side": "PRO",
                "perspective_label": "기술 대안",
                "color": "violet",
                "raw": "[실제 댓글 · YTN뉴스] 나이로만 딱 잘라서 면허 뺏는 건 차별이다 젊은 사람 음주운전 난폭운전이 더 위험한데 운전 능력으로만 평가해야 맞지",
                "cleaned": "연령만을 기준으로 한 획일적 면허 제한 대신 안전 보조장치 장착과 객관적 개인별 실주행 능력 평가 제도를 도입해야 합니다.",
                "removed_tokens": ["딱 잘라서", "면허 뺏는"]
            }
        ],
        "raw_comments": _get_real_comments_text_list("preset_3", [
            "오늘 운전하다가 미친각으로 끼어드는 차 있어서 욕하고 넘어갔는데 70대 할머니더라 본인이 민폐라 생각하면 면허 반납 좀 해라",
            "솔직히 도로에 나가보면 말도안되게 운전하는 사람들 나이 많으신분들이 대다수 본인 먹고 살겠다고 남한테 피해주면 안되지 정기 시험 봐라!!"
        ])
    }
}

