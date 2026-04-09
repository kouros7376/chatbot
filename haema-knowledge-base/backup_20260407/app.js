/**
 * HAEMA Knowledge Base - 프론트엔드 앱
 *
 * 채팅 UI, API 호출, 문서 관리 기능을 처리합니다.
 * Vanilla JavaScript만 사용합니다.
 */

// ──────────────────────────────────────────────
// DOM 요소 참조
// ──────────────────────────────────────────────
const chatArea = document.getElementById("chatArea");
const questionInput = document.getElementById("questionInput");
const sendBtn = document.getElementById("sendBtn");
const docCount = document.getElementById("docCount");
const progressBar = document.getElementById("progressBar");
const chatView = document.getElementById("chatView");
const docsView = document.getElementById("docsView");
const docList = document.getElementById("docList");
const docEmpty = document.getElementById("docEmpty");
const uploadArea = document.getElementById("uploadArea");
const uploadStatus = document.getElementById("uploadStatus");
const faqSection = document.getElementById("faqSection");
const faqChips = document.getElementById("faqChips");
const categoryBadge = document.getElementById("categoryBadge");
const categoryBadgeText = document.getElementById("categoryBadgeText");

// ──────────────────────────────────────────────
// ① 카테고리 정의 (탭 + FAQ 세트)
// ──────────────────────────────────────────────

/** 현재 선택된 카테고리 */
let currentCategory = "all";

/** 카테고리별 표시 이름 */
const CATEGORY_LABELS = {
  all:        "전체 문서",
  hr:         "취업/인사 규정",
  pms:        "PMS/업무 매뉴얼",
  groupware:  "그룹웨어 가이드",
};

/** 카테고리별 시스템 프롬프트 힌트 (백엔드 전달용) */
const CATEGORY_HINTS = {
  all:        "",
  hr:         "취업규칙, 인사규정, 복리후생, 휴가 관련 내용 위주로 답변해 주세요.",
  pms:        "PMS 프로젝트 관리 매뉴얼 관련 내용 위주로 답변해 주세요.",
  groupware:  "그룹웨어 사용 방법, 결재, 공가 관련 내용 위주로 답변해 주세요.",
};

/** 카테고리별 FAQ 목록 */
const FAQ_DATA = {
  all: [
    "연차 신청 방법이 어떻게 되나요?",
    "야근 식대 지급 기준을 알려주세요",
    "PMS에서 프로젝트 등록하는 방법",
    "그룹웨어 공가 신청 절차",
    "재직증명서 발급은 어떻게 하나요?",
  ],
  hr: [
    "연차 신청 방법이 어떻게 되나요?",
    "경조사 휴가는 며칠인가요?",
    "야근 식대 지급 기준을 알려주세요",
    "복리후생 항목이 무엇인가요?",
    "수습기간은 얼마나 되나요?",
  ],
  pms: [
    "PMS에서 프로젝트 등록하는 방법",
    "착수계 제출 절차",
    "PMS 팀원과 팀장 화면 차이",
    "계약서류 확인 방법",
    "프로젝트 상태 변경은 어떻게 하나요?",
  ],
  groupware: [
    "그룹웨어 공가 신청 절차",
    "결재선 설정 방법",
    "휴일근무 신청 방법",
    "야근 식비 신청 방법",
    "전자 서명 적용 방법",
  ],
};


// ──────────────────────────────────────────────
// 초기화 (페이지 로드 시)
// ──────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // 시스템 상태 및 문서 수 조회
  loadStatus();
  // FAQ 초기 렌더링
  renderFAQ("all");
  // Enter 키로 전송
  questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) {
      e.preventDefault();
      sendQuestion();
    }
  });
  // 드래그 앤 드롭 이벤트
  setupDragAndDrop();
});

// ──────────────────────────────────────────────
// ① 카테고리 탭 제어
// ──────────────────────────────────────────────

/**
 * 카테고리 탭 클릭 시 호출
 * - 탭 active 상태 변경
 * - FAQ 목록 업데이트
 * - 검색 범위 뱃지 업데이트
 */
function selectCategory(el, category) {
  // 탭 active 상태
  document.querySelectorAll(".cat-tab").forEach(t => t.classList.remove("active"));
  el.classList.add("active");

  currentCategory = category;

  // FAQ 재렌더링
  renderFAQ(category);

  // 카테고리 뱃지 표시
  if (category === "all") {
    categoryBadge.style.display = "none";
  } else {
    categoryBadge.style.display = "inline-flex";
    categoryBadgeText.textContent = "📂 " + CATEGORY_LABELS[category] + " 범위 검색 중";
  }
}

// ──────────────────────────────────────────────
// ② FAQ 렌더링
// ──────────────────────────────────────────────

/**
 * 카테고리에 맞는 FAQ 칩들을 렌더링
 * 대화가 시작되면 faqSection 자체를 숨김
 */
function renderFAQ(category) {
  const faqs = FAQ_DATA[category] || FAQ_DATA["all"];
  faqChips.innerHTML = "";
  faqs.forEach(q => {
    const chip = document.createElement("button");
    chip.className = "faq-chip";
    chip.textContent = q;
    chip.onclick = () => clickFAQ(q);
    faqChips.appendChild(chip);
  });
}

/** FAQ 칩 클릭 → 입력창에 넣고 바로 검색 */
function clickFAQ(question) {
  questionInput.value = question;
  sendQuestion();
}

/** 대화 시작 시 FAQ 숨기기 / 새 대화 시 다시 보이기 */
function hideFAQ() {
  if (faqSection) faqSection.style.display = "none";
}
function showFAQ() {
  if (faqSection) {
    faqSection.style.display = "block";
    renderFAQ(currentCategory);
  }
}


// ──────────────────────────────────────────────
// 시스템 상태 조회
// ──────────────────────────────────────────────

/** 서버 상태와 문서 수를 가져와 프로그레스 바 업데이트 */
async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    updateProgress(data.document_count);
  } catch (err) {
    console.error("상태 조회 실패:", err);
  }
}

/** 프로그레스 바와 문서 수 표시 업데이트 */
function updateProgress(count) {
  docCount.textContent = count + "개";
  // 최대 20개 기준으로 퍼센트 계산 (0개일 때도 표시)
  const maxDocs = 20;
  const percent = Math.min((count / maxDocs) * 100, 100);
  progressBar.style.width = percent + "%";
}

// ──────────────────────────────────────────────
// 채팅 리셋 (새 대화)
// ──────────────────────────────────────────────

/** 채팅 내역을 초기화하고 메인 화면으로 돌아가기 */
function resetChat() {
  // 채팅 영역 초기화
  chatArea.innerHTML = '';
  // 입력창 초기화
  questionInput.value = "";
  sendBtn.disabled = false;
  // 채팅 뷰로 전환 (문서 관리 화면이었을 경우)
  docsView.classList.remove("active");
  chatView.classList.remove("hidden");
  // FAQ 섹션 다시 표시
  showFAQ();
  questionInput.focus();
}

// ──────────────────────────────────────────────
// 뷰 전환 (채팅 ↔ 문서 관리)
// ──────────────────────────────────────────────

/** 문서 관리 화면으로 전환 */
function showDocsView() {
  chatView.classList.add("hidden");
  docsView.classList.add("active");
  loadDocuments();
}

/** 채팅 화면으로 전환 */
function showChatView() {
  docsView.classList.remove("active");
  chatView.classList.remove("hidden");
  questionInput.focus();
}

// ──────────────────────────────────────────────
// 채팅 기능
// ──────────────────────────────────────────────

/** 사용자 질문을 서버에 전송하고 AI 답변을 표시 */
async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;

  // FAQ 영역 숨기기
  hideFAQ();

  // 사용자 메시지 표시
  appendUserMessage(question);
  questionInput.value = "";

  // 버튼 비활성화 + 로딩 표시
  sendBtn.disabled = true;
  const loadingEl = appendLoading();

  // 카테고리 힌트 (전체 탭이 아닐 경우 질문에 컨텍스트 추가)
  const hint = CATEGORY_HINTS[currentCategory] || "";
  const questionWithHint = hint ? `${question}\n\n[참고: ${hint}]` : question;

  try {
    // 서버에 질문 전송 (카테고리 힌트 포함)
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: questionWithHint }),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "서버 오류가 발생했습니다.");
    }

    const data = await res.json();

    // 로딩 제거
    loadingEl.remove();

    // AI 답변 표시 (타이핑 효과)
    await appendAIMessage(data.answer, data.sources);
  } catch (err) {
    loadingEl.remove();
    appendErrorMessage(err.message);
  } finally {
    sendBtn.disabled = false;
    questionInput.focus();
  }
}

/** 사용자 메시지 말풍선 추가 */
function appendUserMessage(text) {
  const wrapper = document.createElement("div");
  wrapper.className = "msg-wrapper user";

  const bubble = document.createElement("div");
  bubble.className = "msg-user";
  bubble.textContent = text;

  wrapper.appendChild(bubble);
  chatArea.appendChild(wrapper);
  scrollToBottom();
}

/** AI 답변 말풍선 추가 (타이핑 효과 포함) */
async function appendAIMessage(answer, sources) {
  const wrapper = document.createElement("div");
  wrapper.className = "msg-wrapper ai";

  const bubble = document.createElement("div");
  bubble.className = "msg-ai";
  wrapper.appendChild(bubble);
  chatArea.appendChild(wrapper);

  // 타이핑 효과: 한 글자씩 출력
  await typeText(bubble, answer);

  // ③ 복사 버튼 (답변 영역 상단 우측에 배치)
  const copyBtn = document.createElement("button");
  copyBtn.className = "copy-btn";
  copyBtn.innerHTML = "📋 복사";
  copyBtn.onclick = () => copyAnswer(answer, copyBtn);
  wrapper.appendChild(copyBtn);

  // 출처 정보가 있으면 표시
  if (sources && sources.length > 0) {
    const sourcesEl = createSourcesElement(sources);
    wrapper.appendChild(sourcesEl);
  }

  // ★ 답변 완료 시 AI 답변의 최상단으로 스크롤
  wrapper.scrollIntoView({ behavior: "smooth", block: "start" });
}

/** 답변 텍스트를 클립보드에 복사 */
async function copyAnswer(text, btn) {
  // 마크다운 기호 제거한 순수 텍스트 복사
  const plainText = text
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/#{1,6}\s/g, "")
    .replace(/`{1,3}[^`]*`{1,3}/g, "")
    .trim();
  try {
    await navigator.clipboard.writeText(plainText);
    btn.classList.add("copied");
    btn.innerHTML = "✅ 복사됨";
    setTimeout(() => {
      btn.classList.remove("copied");
      btn.innerHTML = "📋 복사";
    }, 1800);
  } catch {
    // 클립보드 API 미지원 폴백
    const el = document.createElement("textarea");
    el.value = plainText;
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
    btn.innerHTML = "✅ 복사됨";
    setTimeout(() => { btn.innerHTML = "📋 복사"; }, 1800);
  }
}

/** 텍스트를 한 글자씩 타이핑 효과로 출력 */
function typeText(element, text) {
  return new Promise((resolve) => {
    // 원본 텍스트를 글자 단위로 타이핑 (HTML 변환은 매 프레임마다)
    let index = 0;
    const plainText = text;
    element.innerHTML = "";

    // 청크 단위로 원본 텍스트를 추가하면서 매번 전체를 마크다운 변환
    const chunkSize = 5;
    const interval = setInterval(() => {
      if (index < plainText.length) {
        const end = Math.min(index + chunkSize, plainText.length);
        index = end;
        // 현재까지의 텍스트를 마크다운 변환하여 전체 교체
        element.innerHTML = formatMarkdown(plainText.substring(0, index));
        scrollToBottom();
      } else {
        clearInterval(interval);
        resolve();
      }
    }, 15);
  });
}

/** 마크다운 → HTML 변환 (Gemini 응답 형식 대응) */
function formatMarkdown(text) {
  // 줄 단위로 처리
  const lines = text.split("\n");
  const result = [];
  let inList = false;

  for (let line of lines) {
    // 빈 줄 처리
    if (line.trim() === "") {
      if (inList) {
        result.push("</ul>");
        inList = false;
      }
      result.push("<br>");
      continue;
    }

    // 불릿 리스트 (* 또는 - 시작)
    if (/^\s*[\*\-]\s+/.test(line)) {
      if (!inList) {
        result.push("<ul>");
        inList = true;
      }
      const content = line.replace(/^\s*[\*\-]\s+/, "");
      result.push("<li>" + inlineFormat(content) + "</li>");
      continue;
    }

    // 번호 리스트 (1. 2. 3.)
    if (/^\s*\d+\.\s+/.test(line)) {
      const content = line.replace(/^\s*\d+\.\s+/, "");
      const num = line.match(/^\s*(\d+)\./)[1];
      if (inList) {
        result.push("</ul>");
        inList = false;
      }
      result.push("<p><strong>" + num + ".</strong> " + inlineFormat(content) + "</p>");
      continue;
    }

    // 리스트 종료
    if (inList) {
      result.push("</ul>");
      inList = false;
    }

    // 일반 텍스트
    result.push("<p>" + inlineFormat(line) + "</p>");
  }

  // 열린 리스트 닫기
  if (inList) {
    result.push("</ul>");
  }

  return result.join("");
}

/** 인라인 마크다운 변환 (볼드, 이탤릭, 코드) */
function inlineFormat(text) {
  return text
    // 볼드 (**text** 또는 __text__)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/__(.*?)__/g, "<strong>$1</strong>")
    // 이탤릭 (*text* 또는 _text_) — 볼드 처리 후
    .replace(/\*([^\*]+)\*/g, "<em>$1</em>")
    // 인라인 코드 (`code`)
    .replace(/`([^`]+)`/g, '<code style="background:#f0f0f0;padding:1px 4px;border-radius:3px;font-size:13px;">$1</code>');
}

/** 출처 정보 요소 생성 */
function createSourcesElement(sources) {
  const container = document.createElement("div");
  container.className = "msg-sources";

  const label = document.createElement("span");
  label.className = "msg-sources-label";
  label.textContent = "📎 참고 문서";
  container.appendChild(label);

  // 중복 제거 (같은 title의 출처)
  const uniqueSources = [];
  const seenTitles = new Set();
  for (const s of sources) {
    const title = s.title || "알 수 없는 문서";
    if (!seenTitles.has(title)) {
      seenTitles.add(title);
      uniqueSources.push(s);
    }
  }

  for (const source of uniqueSources) {
    const item = document.createElement("div");
    item.className = "msg-source-item";

    const title = document.createElement("div");
    title.className = "msg-source-title";
    title.textContent = source.title || "알 수 없는 문서";
    item.appendChild(title);

    if (source.text) {
      const text = document.createElement("div");
      // 원문 발췌가 너무 길면 잘라서 표시
      text.textContent =
        source.text.length > 150
          ? source.text.substring(0, 150) + "..."
          : source.text;
      item.appendChild(text);
    }

    container.appendChild(item);
  }

  return container;
}

/** 오류 메시지 표시 */
function appendErrorMessage(message) {
  const wrapper = document.createElement("div");
  wrapper.className = "msg-wrapper ai";

  const bubble = document.createElement("div");
  bubble.className = "msg-ai";
  bubble.style.borderLeft = "3px solid #EF4444";
  bubble.textContent = "⚠️ " + message;

  wrapper.appendChild(bubble);
  chatArea.appendChild(wrapper);
  scrollToBottom();
}

/** 로딩 애니메이션 표시 (오렌지 dot 바운스) */
function appendLoading() {
  const wrapper = document.createElement("div");
  wrapper.className = "msg-wrapper ai";
  wrapper.id = "loadingMsg";

  const loading = document.createElement("div");
  loading.className = "loading-wrapper";

  const dots = document.createElement("div");
  dots.className = "loading-dots";
  dots.innerHTML =
    '<div class="loading-dot"></div>' +
    '<div class="loading-dot"></div>' +
    '<div class="loading-dot"></div>';

  const text = document.createElement("span");
  text.className = "loading-text";
  text.textContent = "문서에서 검색 중...";

  loading.appendChild(dots);
  loading.appendChild(text);
  wrapper.appendChild(loading);
  chatArea.appendChild(wrapper);
  scrollToBottom();

  return wrapper;
}

/** 채팅 영역을 맨 아래로 스크롤 */
function scrollToBottom() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

// ──────────────────────────────────────────────
// 문서 관리 기능
// ──────────────────────────────────────────────

/** 등록된 문서 목록을 서버에서 조회하여 표시 */
async function loadDocuments() {
  try {
    const res = await fetch("/api/documents");
    const data = await res.json();

    // 문서 수 업데이트
    updateProgress(data.total_count);

    // 리스트 렌더링
    docList.innerHTML = "";

    if (data.documents.length === 0) {
      const empty = document.createElement("div");
      empty.className = "doc-empty";
      empty.textContent = "등록된 문서가 없습니다.";
      docList.appendChild(empty);
      return;
    }

    for (const doc of data.documents) {
      const item = document.createElement("div");
      item.className = "doc-item";

      item.innerHTML =
        '<span class="doc-icon">📄</span>' +
        '<div class="doc-info">' +
        '  <div class="doc-name">' + escapeHtml(doc.file_name) + "</div>" +
        '  <div class="doc-status">등록됨</div>' +
        "</div>" +
        '<span class="doc-check">✓</span>';

      docList.appendChild(item);
    }
  } catch (err) {
    console.error("문서 목록 조회 실패:", err);
    docList.innerHTML =
      '<div class="doc-empty">문서 목록을 불러올 수 없습니다.</div>';
  }
}

/** 문서 파일 업로드 처리 (PDF, HWP, DOCX, XLSX, PPTX 등) */
async function uploadFile(input) {
  const file = input.files[0];
  if (!file) return;

  // 허용 확장자 검증
  const allowedExts = [".pdf", ".hwp", ".doc", ".docx", ".xlsx", ".xls", ".pptx", ".txt", ".csv", ".md"];
  const fileExt = file.name.toLowerCase().substring(file.name.lastIndexOf("."));
  if (!allowedExts.includes(fileExt)) {
    showUploadStatus("지원하지 않는 파일 형식입니다. (PDF, HWP, DOCX, XLSX, PPTX 등)", "error");
    input.value = "";
    return;
  }

  // 100MB 제한 확인
  if (file.size > 100 * 1024 * 1024) {
    showUploadStatus("파일 크기가 100MB를 초과합니다.", "error");
    input.value = "";
    return;
  }

  showUploadStatus(file.name + " 업로드 중...", "");

  try {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();

    if (data.success) {
      showUploadStatus(data.message, "success");
      // 문서 목록 새로고침
      await loadDocuments();
    } else {
      showUploadStatus(data.message, "error");
    }
  } catch (err) {
    showUploadStatus("업로드 중 오류가 발생했습니다: " + err.message, "error");
  } finally {
    input.value = "";
  }
}

/** 업로드 상태 메시지 표시 */
function showUploadStatus(message, type) {
  uploadStatus.textContent = message;
  uploadStatus.className = "upload-status" + (type ? " " + type : "");

  // 3초 후 자동으로 메시지 제거
  if (type) {
    setTimeout(() => {
      uploadStatus.textContent = "";
      uploadStatus.className = "upload-status";
    }, 3000);
  }
}

// ──────────────────────────────────────────────
// 드래그 앤 드롭
// ──────────────────────────────────────────────

/** 업로드 영역에 드래그 앤 드롭 이벤트 설정 */
function setupDragAndDrop() {
  const area = uploadArea;
  if (!area) return;

  // 드래그 진입
  area.addEventListener("dragover", (e) => {
    e.preventDefault();
    area.classList.add("drag-over");
  });

  // 드래그 이탈
  area.addEventListener("dragleave", () => {
    area.classList.remove("drag-over");
  });

  // 파일 드롭
  area.addEventListener("drop", (e) => {
    e.preventDefault();
    area.classList.remove("drag-over");

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      // 파일 입력에 설정 후 업로드 함수 호출
      const fileInput = document.getElementById("fileInput");
      fileInput.files = files;
      uploadFile(fileInput);
    }
  });
}

// ──────────────────────────────────────────────
// 유틸리티
// ──────────────────────────────────────────────

/** HTML 특수문자 이스케이프 (XSS 방지) */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
