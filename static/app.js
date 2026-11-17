/**
 * static/app.js
 * Agora-Shorts 프론트엔드 컨트롤러
 * - 3대 사회 갈등 프리셋 0.1초 즉시 전환 및 자유 댓글/URL 분석 API 연동
 * - 좌측 공론장 정화 데이터 분석 리포트 렌더링
 * - 우측 9:16 세로형 쇼츠 시뮬레이터 & Web Speech API 듀얼 피치(찬성 저음 / 반대 고음) 실시간 낭독
 */

const OFFLINE_PRESETS = {
  preset_1: {
    id: "preset_1",
    category_badge: "주거 환경권 vs 플랫폼 노동 생존권",
    source_label: "유튜브 뉴스 · [단독] 밤마다 굉음 내는 배달 오토바이... 심야 운행·소음 규제 논란 (댓글 100건)",
    source_url: "https://www.youtube.com/watch?v=agora-noise-regulation-01",
    issue_title: "심야 시간대 배달 오토바이 배기 소음 규제 및 단속 의무화 논란",
    raw_stats: {
      total_comments: 100,
      filtered_curse_count: 68,
      pro_ratio: 58,
      con_ratio: 42,
      toxicity_before: 84.6,
      toxicity_after: 14.2
    },
    debate_script: [
      {
        speaker: "PRO",
        core_point: "헌법상 주거 평온권 및 수면권 침해 심각",
        text: "새벽 시간대 주택가를 관통하는 구십 데시벨 이상의 불법 개조 배기음은 시민의 헌법상 환경권과 수면 건강을 심각하게 파괴하고 있습니다. 야간 시간대 소음 기준을 대폭 강화하고 상시 이동식 소음 단속 카메라를 의무 도입해야 합니다."
      },
      {
        speaker: "CON",
        core_point: "심야 생계형 라이더 생존권 및 플랫폼 구조 문제",
        text: "일부 불법 개조 차량의 문제를 전체 생계형 배달 노동자에 대한 심야 운행 규제로 확대하는 것은 과도한 생존권 침해입니다. 배달 시간 단축을 강요하는 플랫폼 알고리즘과 야간 할증 구조를 개선하는 것이 근본적인 해법입니다."
      },
      {
        speaker: "PRO",
        core_point: "실효성 없는 현행 배기음 단속 기준 개편 시급",
        text: "현행 백오 데시벨로 설정된 이륜차 배기 소음 허용 기준은 사실상 기차 통과 소음과 맞먹는 수준으로 실효성이 전혀 없습니다. 제작 단계부터 소음기 임의 변경을 원천 차단하고 적발 시 즉시 운행 정지 처분을 내려야 합니다."
      },
      {
        speaker: "CON",
        core_point: "전기 이륜차 전환 인프라 및 보조금 선행 필요",
        text: "처벌과 단속만 앞세우기보다 무소음 전기 이륜차로의 전환이 현장에서 이루어질 수 있도록 배터리 교환 스테이션을 확충해야 합니다. 영세 라이더들이 체감할 수 있는 구매 보조금과 정비 인프라 지원이 선행되어야 합니다."
      },
      {
        speaker: "PRO",
        core_point: "주거 밀집 구역 심야 에코존(Eco-Zone) 지정",
        text: "병원과 학교, 대단지 아파트가 밀집한 주거 지역만이라도 밤 열한 시 이후 내연기관 이륜차 진입을 제한하는 심야 정온 구역 지정이 시급합니다. 공공의 건강권 보호는 더 이상 미룰 수 없는 사회적 책무입니다."
      },
      {
        speaker: "CON",
        core_point: "야간 외식 자영업 생태계 및 소비자 편익 고려",
        text: "심야 배달을 일괄 제한할 경우 야간 시간대 매출에 의존하는 영세 소상공인과 교대 근무 노동자들의 불편이 급증할 것입니다. 일방적 통행 금지 대신 친환경 이륜차 인센티브와 핀셋 단속을 병행하는 상생 모델이 필요합니다."
      }
    ],
    detox_samples: [
      {
        side: "PRO",
        raw: "ㅅㅂ 새벽 2시에 부아아앙 머플러 뚫고 달리는 딸배충 새끼들 다 감옥 쳐넣어라 잠 좀 자자 미친놈들아!!",
        cleaned: "새벽 시간대 불법 개조 소음기로 인한 주거지 수면권 침해가 극심하므로 강력한 단속과 처벌이 필요합니다.",
        removed_tokens: ["ㅅㅂ", "딸배충", "새끼들", "쳐넣어라", "미친놈들아"]
      },
      {
        side: "CON",
        raw: "방구석 백수 ㅂㅅ들이 배달 시켜먹을 땐 빨리 오라고 ㅈㄹ하면서 오토바이 소리 난다고 다 막으라네 내로남불 역겹다 ㅋㅋ",
        cleaned: "빠른 배달을 요구하는 소비 구조와 플랫폼 압박은 외면한 채 라이더에게만 책임을 전가하는 규제는 부당합니다.",
        removed_tokens: ["ㅂㅅ들이", "ㅈㄹ하면서", "역겹다"]
      },
      {
        side: "PRO",
        raw: "신호위반에 인도주행에 소음공해까지 ㅈ같은 오토바이들 번호판 앞뒤로 박고 100dB 넘으면 바로 폐차시켜라!!",
        cleaned: "교통법규 준수와 소음 저감을 위해 전면 번호판 부착 및 배기음 기준 초과 차량에 대한 행정 처분을 강화해야 합니다.",
        removed_tokens: ["ㅈ같은", "바로 폐차시켜라"]
      },
      {
        side: "CON",
        raw: "전기오토바이 타라는데 ㅅㅂ 언덕길도 못 올라가고 충전소도 없는데 탁상행정 개소리 좀 작작 해라 ㅉㅉ",
        cleaned: "전기 이륜차의 주행 성능 한계와 충전 인프라 부족 문제를 해결하지 않은 일방적 규제 도입은 현실성이 떨어집니다.",
        removed_tokens: ["ㅅㅂ", "개소리", "작작 해라", "ㅉㅉ"]
      }
    ]
  },

  preset_2: {
    id: "preset_2",
    category_badge: "보행자 안전·공공질서 vs 청년 라스트마일 이동권",
    source_label: "네이버 사회 뉴스 · 대학가 원룸촌 뒤덮은 전동킥보드... 즉시 견인·전면 금지 찬반 가열 (댓글 100건)",
    source_url: "https://news.example.com/society/agora-pm-scooter-ban-02",
    issue_title: "대학가 원룸촌 공유 전동킥보드 즉시 견인 및 통행 전면 금지 설전",
    raw_stats: {
      total_comments: 100,
      filtered_curse_count: 64,
      pro_ratio: 62,
      con_ratio: 38,
      toxicity_before: 81.2,
      toxicity_after: 15.6
    },
    debate_script: [
      {
        speaker: "PRO",
        core_point: "보행자 치명상 위협 및 인도 무단 방치 심각",
        text: "좁은 대학가 골목길에서 무면허와 이인 탑승 상태로 질주하는 공유 킥보드는 보행자에게 언제든 치명적인 사고를 유발할 수 있습니다. 점자블록과 건물 입구를 가로막는 무단 방치 기기에 대해 유예 시간 없는 즉시 견인과 영업 제한이 필요합니다."
      },
      {
        speaker: "CON",
        core_point: "대학생·청년층 라스트마일 필수 대중교통 보완재",
        text: "공유 전동킥보드는 마을버스가 끊긴 심야 시간이나 언덕이 많은 대학가에서 청년들의 이동 비용과 시간을 줄여주는 핵심 교통수단입니다. 인프라 구축 없이 프랑스 파리식 전면 퇴출만을 모방하는 것은 모빌리티 혁신을 가로막는 과잉 규제입니다."
      },
      {
        speaker: "PRO",
        core_point: "민간 대여 업체의 안전 관리 책임 외면과 사회적 비용 전가",
        text: "수익은 민간 공유 킥보드 업체가 독점하면서 면허 인증 해태와 기기 방치로 발생하는 행정 비용은 지자체와 시민이 떠안고 있습니다. 사고 발생 시 대여 업체의 연대 배상 책임을 법제화하고 보행자 전용 거리 내 통행을 전면 금지해야 합니다."
      },
      {
        speaker: "CON",
        core_point: "지정 주차존(PM 파킹존) 확충 및 GPS 속도 제한으로 해결 가능",
        text: "무단 방치 문제는 대학 캠퍼스와 원룸촌 골목마다 전용 주차 구역을 촘촘히 설치하고 반납 구역 외 주차를 시스템적으로 차단하면 해결할 수 있습니다. 전면 금지 대신 보행 밀집 구역 내 지피에스 기반 시속 십오 킬로미터 자동 감속 기술을 의무화해야 합니다."
      },
      {
        speaker: "PRO",
        core_point: "소방차 진입로 확보 및 교통약자 보행 안전권 최우선",
        text: "다세대 주택이 밀집한 원룸촌 골목에 쓰러진 킥보드들은 화재 시 소방차 진입을 방해하고 시각장애인과 노약자의 보행을 위협합니다. 시민의 생명과 직결된 보행 안전권은 개인의 단거리 이동 편의보다 항상 우선시되어야 합니다."
      },
      {
        speaker: "CON",
        core_point: "친환경 마이크로 모빌리티 제도권 편입 및 이용자 교육 강화",
        text: "친환경 단거리 이동수단 자체를 불법화하기보다 번호판 등록제와 본인 인증 의무화를 통해 제도권 안에서 안전하게 관리해야 합니다. 지자체와 대학, 플랫폼 기업이 협력하여 표준 주차 인프라를 구축하는 합리적 공존 방안이 바람직합니다."
      }
    ],
    detox_samples: [
      {
        side: "PRO",
        raw: "길바닥에 킥보드 개판으로 던져놓는 킥라니 새끼들 다 싹 쓸어버려라!! 헬멧도 안 쓰고 둘이 타다가 사람 치는 흉기임 ㅅㅂ",
        cleaned: "인도 무단 방치와 안전모 미착용·다인 탑승으로 인한 보행자 사고 위험이 크므로 강력한 견인 및 통행 규제가 필요합니다.",
        removed_tokens: ["개판으로", "킥라니 새끼들", "싹 쓸어버려라", "ㅅㅂ"]
      },
      {
        side: "CON",
        raw: "주차장 만들 생각은 안 하고 무조건 금지부터 외치는 꼰대 행정 ㅈ같네 ㅋㅋ 마을버스 배차나 늘리고 금지하든가 ㅂㅅ들아",
        cleaned: "전용 주차 구역이나 대중교통 배차 확충 없이 전면 금지부터 추진하는 것은 청년층의 이동 편의를 무시한 행정입니다.",
        removed_tokens: ["꼰대 행정", "ㅈ같네", "ㅂㅅ들아"]
      },
      {
        side: "PRO",
        raw: "골목길에서 갑자기 튀어나오는 킥보드 때문에 심장 떨어질 뻔한 게 한두 번이 아님 업체들 벌금 폭탄 때려서 다 망하게 해야 됨",
        cleaned: "이면도로에서 급출발하는 기기로 인한 보행 위협이 심각하므로 대여 업체의 관리 책임과 과징금을 대폭 강화해야 합니다.",
        removed_tokens: ["다 망하게 해야 됨"]
      },
      {
        side: "CON",
        raw: "GPS로 주차구역 아니면 반납 안 되게 기술적으로 막으면 될 걸 왜 멀쩡히 잘 타는 학생들 발을 묶냐고 답답한 인간들아 ㅉㅉ",
        cleaned: "지오펜싱(GPS) 기반 지정 구역 반납 의무화 등 기술적 대안을 통해 질서를 확립하고 이동권을 보장해야 합니다.",
        removed_tokens: ["답답한 인간들아", "ㅉㅉ"]
      }
    ]
  },

  preset_3: {
    id: "preset_3",
    category_badge: "공공 교통안전 예방 vs 고령층 이동권·생계 보호",
    source_label: "유튜브 시사토론 · 70세 이상 고령 운전자 조건부 면허 및 반납 의무화, 안전인가 차별인가 (댓글 100건)",
    source_url: "https://www.youtube.com/watch?v=agora-senior-license-03",
    issue_title: "고령 운전자 조건부 면허제 도입 및 면허 반납 의무화 논란",
    raw_stats: {
      total_comments: 100,
      filtered_curse_count: 61,
      pro_ratio: 55,
      con_ratio: 45,
      toxicity_before: 79.8,
      toxicity_after: 15.1
    },
    debate_script: [
      {
        speaker: "PRO",
        core_point: "인지·반응 속도 저하로 인한 대형 인명사고 예방",
        text: "고령화에 따라 급증하는 페달 오조작과 역주행 사고는 인도와 상가를 덮쳐 다수의 무고한 시민에게 돌이킬 수 없는 피해를 남기고 있습니다. 일정 연령 이상 운전자를 대상으로 야간 및 고속도로 주행을 제한하는 조건부 면허제와 정밀 적성검사를 의무화해야 합니다."
      },
      {
        speaker: "CON",
        core_point: "대중교통 소외지역 고령층 이동권 박탈 및 사회적 고립",
        text: "버스가 하루 몇 차례뿐인 농어촌과 외곽 지역에서 운전면허를 일괄 회수하는 것은 고령층의 병원 진료와 일상 이동을 원천 봉쇄하는 조치입니다. 대체 교통망 확충 없이 나이만을 기준으로 면허 반납을 강제하는 것은 헌법상 평등권과 이동권을 침해합니다."
      },
      {
        speaker: "PRO",
        core_point: "비상자동제동장치(AEBS) 및 페달 오조작 방지 장치 의무화",
        text: "신체 노화로 인한 반응 지연은 개인의 주의력만으로 극복하기 어려운 객관적인 생리 현상입니다. 페달 오조작 방지 장치 부착 차량에 한해 운전을 허용하는 조건부 면허를 도입하고 실질적인 대중교통 바우처 보상을 대폭 확대해야 합니다."
      },
      {
        speaker: "CON",
        core_point: "화물·택시 등 생계형 고령 운전자의 생존권 위협",
        text: "은퇴 후 택시나 소형 화물 운송으로 생계를 유지하는 고령 노동자들에게 일률적인 면허 제한은 곧바로 빈곤 추락을 의미합니다. 연령에 따른 획일적 규제가 아니라 전 연령대 고위험군을 선별하는 가상현실 기반 실주행 능력 평가가 공정한 대안입니다."
      },
      {
        speaker: "PRO",
        core_point: "초고령사회 진입에 따른 선제적 교통안전 안전망 구축",
        text: "이미 초고령사회에 진입한 상황에서 고령 운전자 사고로 인한 사회적 비용과 보험 손실은 매년 최고치를 경신하고 있습니다. 면허 갱신 주기를 일 년으로 단축하고 의료기관의 인지기능 진단 연계를 강화하여 도로 위 공공 안전망을 확립해야 합니다."
      },
      {
        speaker: "CON",
        core_point: "수요응답형 교통(DRT) 및 안전 보조장치 보조금 지원 병행",
        text: "일회성 지원금 십만 원으로는 평생의 이동 수단을 포기하도록 설득할 수 없습니다. 호출형 복지 택시와 수요응답형 버스를 촘촘히 보급하고 첨단 안전 보조장치 장착 비용을 국가가 지원하여 안전과 이동권을 동시에 지키는 정책이 필요합니다."
      }
    ],
    detox_samples: [
      {
        side: "PRO",
        raw: "브레이크랑 엑셀도 구분 못해서 인도 돌진해놓고 급발진 우기는 틀딱 노인네들 ㅅㅂ 70살 넘으면 무조건 면허 뺏어라 도로 위 시한폭탄임!!",
        cleaned: "페달 오조작으로 인한 인도 돌진 등 중대 인명사고를 예방하기 위해 70세 이상 고령층의 면허 적성검사와 조건부 제한을 강화해야 합니다.",
        removed_tokens: ["틀딱 노인네들", "ㅅㅂ", "무조건 면허 뺏어라", "시한폭탄임"]
      },
      {
        side: "CON",
        raw: "방구석 2030 ㅂㅅ들아 니들은 안 늙을 줄 아냐?? 시골은 버스도 없는데 면허 뺏으면 병원도 가지 말고 그냥 뒤지라는 소리냐 ㅈㄹ하네",
        cleaned: "대중교통 인프라가 취약한 지방 및 농어촌 고령층에게 면허 반납을 강제할 경우 의료 접근성과 기본 이동권이 심각하게 침해됩니다.",
        removed_tokens: ["ㅂㅅ들아", "그냥 뒤지라는", "ㅈㄹ하네"]
      },
      {
        side: "PRO",
        raw: "치매 검사도 대충 보건소에서 도장 찍어주는 게 말이 되냐? 1년마다 실기시험 다시 보고 불합격이면 칼같이 면허 취소시켜라!!",
        cleaned: "형식적인 인지능력 검사를 개선하여 면허 갱신 주기를 단축하고 실질적인 주행 반응 속도 평가를 의무화해야 합니다.",
        removed_tokens: ["대충", "칼같이"]
      },
      {
        side: "CON",
        raw: "택시랑 용달 몰아서 먹고사는 노인들 밥줄 다 끊어놓으려고 환장했네 나이로 싸잡아 차별하지 말고 운전 못하는 인간만 걸러내라 ㅉㅉ",
        cleaned: "생계형 고령 운전자의 생존권을 고려하여 연령 기준의 일괄 규제 대신 개인별 실제 운전 역량 중심의 평가 체계를 도입해야 합니다.",
        removed_tokens: ["환장했네", "싸잡아", "ㅉㅉ"]
      }
    ]
  }
};

// State variables
let currentData = OFFLINE_PRESETS.preset_1;
let isPlaying = false;
let currentTurnIndex = 0;
let totalDurationSec = 40.0;
let elapsedSec = 0.0;
let timerInterval = null;
let turnTimeout = null;
let activeUtterance = null;
let audioCtx = null;

/**
 * Web Audio API로 방송 턴 전환 시 은은한 시그널 차임 사운드 재생
 */
function playTurnChime(speaker) {
  const toggle = document.getElementById("chimeToggle");
  if (toggle && !toggle.checked) return;

  try {
    if (!audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;
      audioCtx = new AudioContextClass();
    }
    if (audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    // PRO: 낮은 차분한 톤(440Hz -> 554Hz), CON: 높은 맑은 톤(587Hz -> 740Hz)
    const baseFreq = speaker === "PRO" ? 440 : 587.33;
    osc.frequency.setValueAtTime(baseFreq, audioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(baseFreq * 1.25, audioCtx.currentTime + 0.14);

    gain.gain.setValueAtTime(0.06, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.18);

    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.19);
  } catch (err) {
    // Ignore audio context restriction errors
  }
}

/**
 * 프리셋 버튼 선택 (0.1초 이내 즉시 UI 업데이트)
 */
async function selectPreset(presetId) {
  stopShortsPlayback();

  // Highlight active preset button
  ["preset_1", "preset_2", "preset_3"].forEach((id) => {
    const btn = document.getElementById(`presetBtn_${id}`);
    if (btn) {
      btn.classList.toggle("active", id === presetId);
    }
  });

  const t0 = performance.now();
  // 1) 즉시 로컬 프리셋으로 렌더링 (지연 0ms)
  if (OFFLINE_PRESETS[presetId]) {
    const localCopy = OFFLINE_PRESETS[presetId];
    document.getElementById("sourceUrlInput").value = localCopy.source_url || "";
    document.getElementById("rawCommentsInput").value =
      localCopy.detox_samples.map((d) => d.raw).join(" | ");
    renderAll(localCopy, "FALLBACK_PRESET_INSTANT", (performance.now() - t0).toFixed(1));
  }

  // 2) 백엔드 API 동기화
  try {
    const res = await fetch(`/api/preset/${presetId}`);
    if (res.ok) {
      const serverData = await res.json();
      renderAll(serverData, serverData.engine_mode, serverData.latency_ms);
    }
  } catch (e) {
    // 오프라인 시에도 이미 로컬 프리셋으로 완벽히 작동함
  }
}

/**
 * 사용자 직접 입력 (URL 또는 댓글 텍스트 묶음) 분석 실행
 */
async function runCustomAnalysis() {
  stopShortsPlayback();
  const sourceUrl = document.getElementById("sourceUrlInput").value.trim();
  const rawText = document.getElementById("rawCommentsInput").value.trim();

  const btn = document.getElementById("runPipelineBtn");
  const origHtml = btn.innerHTML;
  btn.innerHTML = `<span>AI 중재 분석 중...</span>`;
  btn.disabled = true;

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_url: sourceUrl,
        raw_text: rawText
      })
    });
    if (res.ok) {
      const data = await res.json();
      renderAll(data, data.engine_mode, data.latency_ms);
    }
  } catch (err) {
    renderAll(OFFLINE_PRESETS.preset_1, "OFFLINE_FALLBACK", 0.5);
  } finally {
    btn.innerHTML = origHtml;
    btn.disabled = false;
  }
}

/**
 * 전체 대시보드 및 9:16 쇼츠 시뮬레이터 화면 갱신
 */
function renderAll(data, engineMode = "FALLBACK_PRESET_INSTANT", latencyMs = 0.4) {
  currentData = data;
  const stats = data.raw_stats;

  // Header & Issue Title
  document.getElementById("reportIssueTitle").textContent = data.issue_title;
  document.getElementById("activeSourceLabel").textContent = data.source_label || "";
  document.getElementById("latencyBadge").textContent = `응답 속도: ${latencyMs}ms (${engineMode})`;

  // Core 4 Cards
  const filterRate = ((stats.filtered_curse_count / Math.max(stats.total_comments, 1)) * 100).toFixed(1);
  const logicIndex = (100 - stats.toxicity_after).toFixed(1);
  const delta = (stats.toxicity_after - stats.toxicity_before).toFixed(1);

  document.getElementById("statFilterRate").textContent = `${filterRate}%`;
  document.getElementById("statFilterCount").textContent = `(${stats.filtered_curse_count} / ${stats.total_comments}건)`;
  document.getElementById("statToxicityBefore").textContent = stats.toxicity_before.toFixed(1);
  document.getElementById("statLogicAfter").textContent = logicIndex;
  document.getElementById("statToxicityAfterSub").textContent = `(과열도 ${stats.toxicity_after.toFixed(1)}↓)`;
  document.getElementById("statToxicityDelta").textContent = `${delta}pt`;

  // Stance Ratio Bar
  document.getElementById("stanceTotalLabel").textContent = `표본 N = ${stats.total_comments}`;
  document.getElementById("proRatioText").textContent = `${stats.pro_ratio}%`;
  document.getElementById("conRatioText").textContent = `${stats.con_ratio}%`;
  document.getElementById("proBarFill").style.width = `${stats.pro_ratio}%`;
  document.getElementById("conBarFill").style.width = `${stats.con_ratio}%`;

  // Before/After Bars
  document.getElementById("barToxBeforeLabel").textContent = `${stats.toxicity_before.toFixed(1)} / 100`;
  document.getElementById("barToxBeforeFill").style.width = `${stats.toxicity_before}%`;
  document.getElementById("barLogicAfterLabel").textContent = `${logicIndex} / 100`;
  document.getElementById("barLogicAfterFill").style.width = `${logicIndex}%`;

  // Render 6-Turn Debate Script List
  const scriptContainer = document.getElementById("debateScriptList");
  scriptContainer.innerHTML = "";
  data.debate_script.forEach((turn, idx) => {
    const isPro = turn.speaker === "PRO";
    const card = document.createElement("div");
    card.id = `scriptTurnItem_${idx}`;
    card.className = `turn-item glass-card p-3.5 border ${
      idx === 0 ? (isPro ? "active-turn-pro" : "active-turn-con") : "border-slate-800"
    }`;
    card.onclick = () => playSpecificTurn(idx);

    card.innerHTML = `
      <div class="flex items-center justify-between gap-2 mb-1">
        <div class="flex items-center gap-2">
          <span class="px-2 py-0.5 text-[11px] font-extrabold rounded ${
            isPro
              ? "bg-blue-500/20 text-blue-300 border border-blue-500/40"
              : "bg-rose-500/20 text-rose-300 border border-rose-500/40"
          }">
            TURN ${idx + 1} · ${isPro ? "PRO 찬성" : "CON 반대"}
          </span>
          <span class="text-xs font-bold ${isPro ? "text-sky-300" : "text-rose-300"}">
            ${turn.core_point}
          </span>
        </div>
        <span class="text-[11px] text-slate-400 mono-num">${(idx * 6.7).toFixed(0)}s ~ ${((idx + 1) * 6.7).toFixed(0)}s</span>
      </div>
      <p class="text-xs sm:text-sm text-slate-200 leading-relaxed mt-1">${turn.text}</p>
    `;
    scriptContainer.appendChild(card);
  });

  // Render Detoxification Log Samples
  const detoxContainer = document.getElementById("detoxSamplesList");
  detoxContainer.innerHTML = "";
  const samples = data.detox_samples || OFFLINE_PRESETS.preset_1.detox_samples;
  samples.forEach((item) => {
    const isPro = item.side === "PRO";
    const box = document.createElement("div");
    box.className = "glass-card p-3 border border-slate-800/90";
    const tokensHtml = (item.removed_tokens || [])
      .map((t) => `<span class="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 text-[10px] font-bold line-through">${t}</span>`)
      .join(" ");

    box.innerHTML = `
      <div class="flex items-center justify-between mb-1">
        <span class="text-[10px] font-bold px-1.5 py-0.5 rounded ${
          isPro ? "bg-blue-500/20 text-blue-300" : "bg-rose-500/20 text-rose-300"
        }">${isPro ? "찬성 진영 원문 댓글" : "반대 진영 원문 댓글"}</span>
        <div class="flex flex-wrap gap-1">${tokensHtml}</div>
      </div>
      <p class="text-xs text-slate-400 line-through mb-1.5 leading-snug">${item.raw}</p>
      <div class="flex items-start gap-1.5 text-xs text-emerald-300 font-medium bg-emerald-950/30 border border-emerald-500/20 rounded-lg p-2">
        <span class="shrink-0 font-bold">→ 정화:</span>
        <span>${item.cleaned}</span>
      </div>
    `;
    detoxContainer.appendChild(box);
  });

  // Render Strictly Required JSON Schema Preview
  const strictSchemaObj = {
    issue_title: data.issue_title,
    raw_stats: data.raw_stats,
    debate_script: data.debate_script
  };
  document.getElementById("jsonSchemaPreview").textContent = JSON.stringify(strictSchemaObj, null, 2);

  // Update 9:16 Shorts Simulator Initial State (Turn 0)
  document.getElementById("shortsCategoryBadge").textContent =
    data.category_badge || "AI 공론장 중재 핵심 쟁점";
  document.getElementById("shortsIssueTitle").textContent = data.issue_title;
  document.getElementById("shortsProShare").textContent = `${stats.pro_ratio}%`;
  document.getElementById("shortsConShare").textContent = `${stats.con_ratio}%`;

  updateShortsTurnVisual(0, false);
}

/**
 * 9:16 쇼츠 화면의 특정 턴(0~5) 시각 상태 업데이트
 */
function updateShortsTurnVisual(turnIdx, speakingActive = false) {
  const turns = currentData.debate_script || [];
  if (!turns.length) return;
  const turn = turns[turnIdx] || turns[0];
  const isPro = turn.speaker === "PRO";

  // Update turn counter
  document.getElementById("shortsTurnCounter").textContent = `TURN ${turnIdx + 1} / ${turns.length}`;

  // Avatar speaking highlight
  const proCard = document.getElementById("avatarCardPro");
  const conCard = document.getElementById("avatarCardCon");
  proCard.classList.toggle("speaking", speakingActive && isPro);
  conCard.classList.toggle("speaking", speakingActive && !isPro);

  // Caption stage styling
  const stage = document.getElementById("shortsCaptionStage");
  stage.classList.toggle("pro-active", isPro);
  stage.classList.toggle("con-active", !isPro);

  const badge = document.getElementById("shortsSpeakerBadge");
  const turnNumForSide = Math.floor(turnIdx / 2) + 1;
  if (isPro) {
    badge.className = "text-[11px] font-extrabold px-2 py-0.5 rounded-md bg-blue-600 text-white";
    badge.textContent = `찬성 측 핵심 논거 #${turnNumForSide} (PRO)`;
    document.getElementById("shortsCorePoint").className = "text-xs font-extrabold text-sky-300 mb-1.5";
  } else {
    badge.className = "text-[11px] font-extrabold px-2 py-0.5 rounded-md bg-rose-600 text-white";
    badge.textContent = `반대 측 핵심 논거 #${turnNumForSide} (CON)`;
    document.getElementById("shortsCorePoint").className = "text-xs font-extrabold text-rose-300 mb-1.5";
  }

  document.getElementById("shortsCorePoint").textContent = turn.core_point;
  document.getElementById("shortsSubtitleText").textContent = turn.text;

  // Update 6 step dots
  const dotsContainer = document.getElementById("shortsTurnDots");
  dotsContainer.innerHTML = turns
    .map((t, i) => {
      if (i === turnIdx) {
        const color = t.speaker === "PRO" ? "bg-blue-500" : "bg-rose-500";
        return `<span class="w-6 h-1.5 rounded-full ${color} transition-all"></span>`;
      }
      if (i < turnIdx) {
        return `<span class="w-2.5 h-1.5 rounded-full bg-slate-400"></span>`;
      }
      return `<span class="w-2 h-1.5 rounded-full bg-slate-700"></span>`;
    })
    .join("");

  // Highlight left panel turn card
  turns.forEach((t, i) => {
    const el = document.getElementById(`scriptTurnItem_${i}`);
    if (!el) return;
    el.classList.remove("active-turn-pro", "active-turn-con");
    if (i === turnIdx) {
      el.classList.add(t.speaker === "PRO" ? "active-turn-pro" : "active-turn-con");
    }
  });
}

/**
 * [40초 토론 쇼츠 재생 / 일시정지] 토글
 */
function toggleShortsPlayback() {
  if (isPlaying) {
    stopShortsPlayback();
  } else {
    startShortsPlayback(0);
  }
}

/**
 * 특정 턴부터 즉시 재생
 */
function playSpecificTurn(turnIdx) {
  startShortsPlayback(turnIdx);
}

/**
 * 40초 양자 토론 쇼츠 재생 시작 (Web Speech API + 40초 카운트다운 프로그레스 바 동기화)
 */
function startShortsPlayback(startIdx = 0) {
  stopShortsPlayback();

  const turns = currentData.debate_script || [];
  if (!turns.length) return;

  isPlaying = true;
  currentTurnIndex = startIdx;
  const turnDurationSec = totalDurationSec / turns.length; // 6.666s per turn
  elapsedSec = startIdx * turnDurationSec;

  // Update Play Button UI
  document.getElementById("playBtnLabel").textContent = "[40초 쇼츠 재생 중 · 일시정지]";
  document.getElementById("ttsStatusLabel").textContent = "🔊 Web Speech API 실시간 발화 중";
  document.getElementById("ttsStatusLabel").className =
    "text-[11px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 mono-num";

  // Start 40-second smooth countdown progress bar (updates every 100ms)
  timerInterval = setInterval(() => {
    if (!isPlaying) return;
    elapsedSec = Math.min(totalDurationSec, elapsedSec + 0.1);
    const pct = Math.min(100, (elapsedSec / totalDurationSec) * 100);
    const remaining = Math.max(0, totalDurationSec - elapsedSec);

    document.getElementById("shortsProgressBar").style.width = `${pct.toFixed(1)}%`;
    document.getElementById("shortsTimerDisplay").textContent = `${remaining.toFixed(1)}s 남음`;

    if (elapsedSec >= totalDurationSec) {
      stopShortsPlayback(true);
    }
  }, 100);

  speakTurn(currentTurnIndex);
}

/**
 * 개별 턴 음성 합성(window.speechSynthesis) 및 다음 턴 자동 전환
 */
function speakTurn(turnIdx) {
  if (!isPlaying) return;
  const turns = currentData.debate_script || [];
  if (turnIdx >= turns.length) {
    stopShortsPlayback(true);
    return;
  }

  currentTurnIndex = turnIdx;
  const turn = turns[turnIdx];
  const isPro = turn.speaker === "PRO";
  const turnDurationMs = (totalDurationSec / turns.length) * 1000; // ~6667ms

  // Sync progress timer to start of current turn
  elapsedSec = turnIdx * (totalDurationSec / turns.length);

  playTurnChime(turn.speaker);
  updateShortsTurnVisual(turnIdx, true);

  let advanced = false;
  const advanceToNext = () => {
    if (advanced || !isPlaying) return;
    advanced = true;
    if (turnTimeout) {
      clearTimeout(turnTimeout);
      turnTimeout = null;
    }
    if (turnIdx + 1 < turns.length) {
      speakTurn(turnIdx + 1);
    } else {
      stopShortsPlayback(true);
    }
  };

  // Fallback timer ensures exact 40s pacing even if browser TTS is muted or unavailable
  turnTimeout = setTimeout(advanceToNext, turnDurationMs);

  // Web Speech API synthesis
  if ("speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(turn.text);
      utter.lang = "ko-KR";
      // 찬성(PRO): 낮은 피치(0.82), 반대(CON): 높은 피치(1.22)
      utter.pitch = isPro ? 0.82 : 1.22;
      utter.rate = 1.12;
      utter.volume = 1.0;

      // 한국어 음성 선택 시도
      const voices = window.speechSynthesis.getVoices();
      const koVoices = voices.filter((v) => v.lang && v.lang.toLowerCase().includes("ko"));
      if (koVoices.length > 1) {
        utter.voice = isPro ? koVoices[0] : koVoices[koVoices.length - 1];
      } else if (koVoices.length === 1) {
        utter.voice = koVoices[0];
      }

      utter.onend = () => {
        // Wait at least 5.8s per turn so the 40-second visual pacing stays natural
        // (turnTimeout handles advancing smoothly)
      };

      activeUtterance = utter;
      window.speechSynthesis.speak(utter);
    } catch (e) {
      // Fallback timer handles progression
    }
  }
}

/**
 * 재생 중지 및 상태 초기화
 */
function stopShortsPlayback(completed = false) {
  isPlaying = false;
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
  if (turnTimeout) {
    clearTimeout(turnTimeout);
    turnTimeout = null;
  }
  if ("speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
    } catch (e) {}
  }

  document.getElementById("avatarCardPro").classList.remove("speaking");
  document.getElementById("avatarCardCon").classList.remove("speaking");
  document.getElementById("playBtnLabel").textContent = completed
    ? "[40초 토론 쇼츠 다시 재생]"
    : "[40초 토론 쇼츠 재생]";

  const ttsLabel = document.getElementById("ttsStatusLabel");
  ttsLabel.textContent = completed ? "✓ 40초 6턴 토론 완료" : "Web Speech API 대기 중";
  ttsLabel.className = "text-[11px] px-2 py-0.5 rounded bg-slate-800 text-sky-300 mono-num";

  if (!completed) {
    elapsedSec = 0;
    document.getElementById("shortsProgressBar").style.width = "0%";
    document.getElementById("shortsTimerDisplay").textContent = "40.0s 남음";
    updateShortsTurnVisual(0, false);
  } else {
    document.getElementById("shortsProgressBar").style.width = "100%";
    document.getElementById("shortsTimerDisplay").textContent = "0.0s 완료";
  }
}

/**
 * JSON 스키마 복사 버튼
 */
function copyJsonSchema() {
  const pre = document.getElementById("jsonSchemaPreview");
  if (!pre) return;
  navigator.clipboard.writeText(pre.textContent).then(() => {
    const btn = document.getElementById("copyJsonBtn");
    btn.textContent = "✓ 복사됨!";
    setTimeout(() => {
      btn.textContent = "JSON 복사";
    }, 1500);
  });
}

// 초기 로드 시 프리셋 1 자동 활성화
window.addEventListener("DOMContentLoaded", () => {
  if ("speechSynthesis" in window) {
    window.speechSynthesis.getVoices();
  }
  selectPreset("preset_1");
});
