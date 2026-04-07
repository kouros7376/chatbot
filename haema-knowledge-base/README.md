# HAEMA Knowledge Base

HAEMA 건축사사무소 사내 매뉴얼 AI 검색 시스템

## 개요

사내 매뉴얼 PDF 문서를 Google Gemini File Search로 인덱싱하고,
자연어 질의응답이 가능한 RAG 챗봇입니다.

## 기술 스택

- **Backend**: Python 3.11+ / FastAPI
- **RAG Engine**: Google Gemini API File Search (벡터DB/임베딩/청킹 자동 처리)
- **Frontend**: Vanilla HTML + CSS + JavaScript
- **AI Model**: Gemini 2.5 Flash

## 설치 및 실행

### 1. 의존성 설치

```bash
cd haema-knowledge-base
pip install -r requirements.txt
```

### 2. API 키 설정

```bash
# .env.example을 복사하여 .env 파일 생성
cp .env.example .env
```

`.env` 파일을 열어 Google Gemini API 키를 입력합니다:

```
GOOGLE_API_KEY=여기에_실제_API_키_입력
```

API 키 발급: https://aistudio.google.com/apikey

### 3. PDF 문서 등록

`docs/` 폴더에 검색 대상 PDF 파일을 넣습니다.
서버 시작 시 자동으로 인덱싱됩니다.

### 4. 서버 실행

```bash
python main.py
```

브라우저에서 http://localhost:8000 접속

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | 메인 페이지 |
| POST | `/api/chat` | 질문 → RAG 답변 |
| POST | `/api/upload` | PDF 파일 업로드 + 인덱싱 |
| GET | `/api/documents` | 등록 문서 목록 |
| GET | `/api/status` | 시스템 상태 |

## 프로젝트 구조

```
haema-knowledge-base/
├── .env                      # API 키 (gitignore 대상)
├── .env.example              # API 키 템플릿
├── requirements.txt          # Python 의존성
├── main.py                   # FastAPI 서버
├── file_search_manager.py    # Gemini File Search 관리 모듈
├── docs/                     # PDF 업로드 폴더
├── static/
│   ├── index.html            # 메인 페이지
│   ├── style.css             # HAEMA 디자인 시스템
│   └── app.js                # 프론트엔드 로직
└── README.md
```
