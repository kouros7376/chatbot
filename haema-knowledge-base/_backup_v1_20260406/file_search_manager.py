"""
HAEMA Knowledge Base - Gemini File Search Store 관리 모듈

Google Gemini의 File Search Store를 활용하여
PDF 문서를 벡터 인덱싱하고 RAG 질의응답을 처리합니다.
임베딩, 청킹, 벡터 검색을 Gemini가 자동 처리합니다.
"""

import os
import json
import time
import shutil
import tempfile
import logging
from pathlib import Path

from google import genai
from google.genai import types
from dotenv import load_dotenv

# ──────────────────────────────────────────────
# 환경 변수 로드
# ──────────────────────────────────────────────
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 상수 정의
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)
DOCS_DIR = os.path.join(BASE_DIR, "docs")
UPLOAD_HISTORY_FILE = os.path.join(BASE_DIR, "upload_history.json")
STORE_NAME_FILE = os.path.join(BASE_DIR, "store_name.json")
STORE_DISPLAY_NAME = os.getenv("STORE_DISPLAY_NAME", "HAEMA-Knowledge-Base")
GEMINI_MODEL = "gemini-2.5-flash"

# 시스템 프롬프트 (HAEMA 건축사사무소 맞춤)
SYSTEM_PROMPT = (
    "당신은 HAEMA 건축사사무소의 사내 관리규정 전문 AI 어시스턴트입니다. "
    "File Search로 검색된 사내 문서를 기반으로 정확하고 상세한 답변을 제공합니다. "
    "답변 시 다음 규칙을 따르세요:\n"
    "1. 등록된 문서에 있는 내용만 기반으로 답변하세요.\n"
    "2. 관련 내용을 찾을 수 없으면 솔직히 '등록된 문서에서 해당 내용을 찾을 수 없습니다'라고 답하세요.\n"
    "3. 답변은 명확하고 구조적으로 작성하세요 (필요시 번호 목록 사용).\n"
    "4. 전문 용어는 쉽게 풀어서 설명해 주세요.\n"
    "5. 답변 본문에 파일 ID나 문서 식별자를 직접 언급하지 마세요. 출처는 시스템이 자동으로 표시합니다."
)


class FileSearchManager:
    """
    Gemini File Search Store를 관리하는 클래스

    주요 기능:
    - File Search Store 생성/조회 (영구 보관)
    - PDF 파일 업로드 및 벡터 인덱싱 (Gemini가 자동 처리)
    - File Search 기반 RAG 질의응답 + 출처 추출
    - 등록 문서 목록 관리
    """

    def __init__(self):
        """Gemini API 클라이언트 초기화"""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY가 설정되지 않았습니다. "
                ".env 파일에 API 키를 입력해 주세요."
            )
        # Gemini API 클라이언트 생성
        self.client = genai.Client(api_key=api_key)
        # File Search Store 이름 (initialize_store 후 설정)
        self.store_name = None
        # 업로드 이력 (파일명 → 업로드 정보)
        self.upload_history = self._load_upload_history()
        # 초기화 완료 플래그
        self.initialized = False
        logger.info("Gemini API 클라이언트가 초기화되었습니다.")

    # ──────────────────────────────────────────
    # 파일 저장/로드 유틸리티
    # ──────────────────────────────────────────

    def _load_upload_history(self) -> dict:
        """업로드 이력 파일을 읽어오는 함수"""
        try:
            if os.path.exists(UPLOAD_HISTORY_FILE):
                with open(UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"업로드 이력 파일 읽기 실패: {e}")
        return {}

    def _save_upload_history(self):
        """업로드 이력을 파일에 저장"""
        try:
            with open(UPLOAD_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.upload_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"업로드 이력 저장 실패: {e}")

    def _save_store_name(self):
        """Store 이름을 파일에 저장 (서버 재시작 시 재사용)"""
        try:
            with open(STORE_NAME_FILE, "w", encoding="utf-8") as f:
                json.dump({"store_name": self.store_name}, f)
        except Exception as e:
            logger.error(f"Store 이름 저장 실패: {e}")

    def _load_store_name(self) -> str | None:
        """저장된 Store 이름을 불러오는 함수"""
        try:
            if os.path.exists(STORE_NAME_FILE):
                with open(STORE_NAME_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("store_name")
        except Exception as e:
            logger.warning(f"Store 이름 파일 읽기 실패: {e}")
        return None

    # ──────────────────────────────────────────
    # 한글 파일명 우회 업로드
    # ──────────────────────────────────────────

    def _upload_file_to_api(self, file_path: str, display_name: str):
        """
        한글 파일명 ASCII 인코딩 오류를 우회하여 Gemini Files API에 업로드합니다.

        google-genai SDK에서 한글 파일 경로 처리 시 ASCII 에러가 발생하므로,
        영문 임시 파일로 복사 후 업로드하고 display_name에 원본 한글명을 지정합니다.

        Args:
            file_path: 원본 파일 경로
            display_name: Gemini에 표시할 파일명 (한글 가능)

        Returns:
            업로드된 파일 객체
        """
        # 임시 영문 파일명으로 복사 (원본 확장자 유지)
        file_ext = os.path.splitext(file_path)[1].lower() or ".bin"
        temp_name = f"upload_{int(time.time())}_{os.getpid()}{file_ext}"
        temp_path = os.path.join(tempfile.gettempdir(), temp_name)

        try:
            shutil.copy2(file_path, temp_path)
            # 영문 경로로 업로드 (display_name에 한글 원본명 지정)
            uploaded = self.client.files.upload(
                file=temp_path,
                config={"display_name": display_name},
            )
            return uploaded
        finally:
            # 임시 파일 정리
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # ──────────────────────────────────────────
    # File Search Store 초기화
    # ──────────────────────────────────────────

    async def initialize_store(self):
        """
        File Search Store를 생성하거나 기존 Store를 재사용합니다.

        1. 저장된 Store 이름이 있으면 해당 Store 조회 시도
        2. 조회 실패 시 새 Store 생성
        """
        try:
            # 이전에 저장된 Store 이름이 있는지 확인
            saved_name = self._load_store_name()
            if saved_name:
                try:
                    store = self.client.file_search_stores.get(name=saved_name)
                    self.store_name = store.name
                    self.initialized = True
                    logger.info(f"기존 Store를 재사용합니다: {self.store_name}")
                    return
                except Exception:
                    logger.info("저장된 Store를 찾을 수 없어 새로 생성합니다.")

            # 새 Store 생성
            store = self.client.file_search_stores.create(
                config={"display_name": STORE_DISPLAY_NAME}
            )
            self.store_name = store.name
            self._save_store_name()
            self.initialized = True
            logger.info(f"새 File Search Store를 생성했습니다: {self.store_name}")

        except Exception as e:
            logger.error(f"Store 초기화 실패: {e}")
            raise

    # ──────────────────────────────────────────
    # PDF 문서 업로드
    # ──────────────────────────────────────────

    async def upload_documents(self, docs_dir: str = None) -> dict:
        """
        지정된 폴더의 모든 지원 문서 파일을 File Search Store에 업로드합니다.

        지원 형식: PDF, HWP, DOCX, DOC, XLSX, XLS, PPTX, TXT, CSV, MD

        업로드 프로세스:
        1. Files API에 파일 업로드 (한글 파일명 우회)
        2. File Search Store에 import (벡터 인덱싱 자동 수행)
        3. 인덱싱 완료 대기

        Args:
            docs_dir: 문서 파일이 있는 폴더 경로 (기본값: ./docs/)

        Returns:
            dict: {"uploaded": [...], "skipped": [...], "failed": [...]}
        """
        if not self.store_name:
            raise RuntimeError("Store가 초기화되지 않았습니다.")

        target_dir = docs_dir or DOCS_DIR
        result = {"uploaded": [], "skipped": [], "failed": []}

        # 지원하는 확장자 목록
        SUPPORTED_EXTENSIONS = {
            ".pdf", ".hwp",
            ".doc", ".docx",
            ".xlsx", ".xls",
            ".pptx",
            ".txt", ".csv", ".md",
        }

        try:
            # 모든 지원 형식의 파일 수집
            doc_files = sorted(
                f for f in Path(target_dir).iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
            )
            if not doc_files:
                logger.info(f"'{target_dir}' 폴더에 지원 문서 파일이 없습니다.")
                return result

            logger.info(f"총 {len(doc_files)}개의 문서 파일을 발견했습니다.")

            for doc_path in doc_files:
                file_name = doc_path.name

                # 이미 업로드된 파일은 건너뜀
                if file_name in self.upload_history:
                    logger.info(f"[건너뜀] 이미 업로드됨: {file_name}")
                    result["skipped"].append(file_name)
                    continue

                try:
                    # 1단계: Files API에 업로드 (한글 파일명 우회)
                    logger.info(f"[1/2] Files API 업로드: {file_name}")
                    uploaded_file = self._upload_file_to_api(
                        str(doc_path), file_name
                    )

                    # 2단계: File Search Store에 import (벡터 인덱싱)
                    logger.info(f"[2/2] Store import + 인덱싱: {file_name}")
                    operation = self.client.file_search_stores.import_file(
                        file_search_store_name=self.store_name,
                        file_name=uploaded_file.name,
                    )

                    # 인덱싱 완료 대기
                    while not operation.done:
                        time.sleep(3)
                        operation = self.client.operations.get(operation)

                    # 이력에 기록
                    self.upload_history[file_name] = {
                        "gemini_file_name": uploaded_file.name,
                        "display_name": file_name,
                        "status": "indexed",
                    }
                    self._save_upload_history()
                    result["uploaded"].append(file_name)
                    logger.info(f"[완료] {file_name} → 인덱싱 완료")

                except Exception as e:
                    logger.error(f"[실패] {file_name}: {e}")
                    result["failed"].append({"file": file_name, "error": str(e)})

        except Exception as e:
            logger.error(f"문서 업로드 중 오류 발생: {e}")
            raise

        return result

    async def upload_single_file(self, file_path: str) -> dict:
        """
        단일 PDF 파일을 File Search Store에 업로드합니다.

        Args:
            file_path: PDF 파일 경로

        Returns:
            dict: {"success": bool, "file_name": str, "message": str}
        """
        if not self.store_name:
            raise RuntimeError("Store가 초기화되지 않았습니다.")

        file_name = os.path.basename(file_path)

        try:
            # 중복 체크
            if file_name in self.upload_history:
                return {
                    "success": True,
                    "file_name": file_name,
                    "message": "이미 등록된 파일입니다.",
                }

            # 1단계: Files API에 업로드 (한글 파일명 우회)
            logger.info(f"[1/2] Files API 업로드: {file_name}")
            uploaded_file = self._upload_file_to_api(file_path, file_name)

            # 2단계: File Search Store에 import
            logger.info(f"[2/2] Store import + 인덱싱: {file_name}")
            operation = self.client.file_search_stores.import_file(
                file_search_store_name=self.store_name,
                file_name=uploaded_file.name,
            )

            # 인덱싱 완료 대기
            while not operation.done:
                time.sleep(3)
                operation = self.client.operations.get(operation)

            # 이력에 기록
            self.upload_history[file_name] = {
                "gemini_file_name": uploaded_file.name,
                "display_name": file_name,
                "status": "indexed",
            }
            self._save_upload_history()
            logger.info(f"[완료] {file_name} → 인덱싱 완료")

            return {
                "success": True,
                "file_name": file_name,
                "message": f"{file_name} 파일이 성공적으로 등록 및 인덱싱되었습니다.",
            }

        except Exception as e:
            logger.error(f"[실패] {file_name}: {e}")
            return {
                "success": False,
                "file_name": file_name,
                "message": f"업로드 실패: {str(e)}",
            }

    # ──────────────────────────────────────────
    # RAG 질의응답 (File Search 기반)
    # ──────────────────────────────────────────

    async def query(self, question: str) -> dict:
        """
        File Search Store를 활용한 RAG 질의응답을 수행합니다.

        Gemini가 자동으로:
        1. 질문을 벡터로 변환
        2. Store에서 관련 문서 청크 검색
        3. 검색 결과를 컨텍스트로 답변 생성

        Args:
            question: 사용자 질문 문자열

        Returns:
            dict: {"answer": "AI 답변", "sources": [{"title": ..., "text": ...}]}
        """
        if not self.store_name:
            raise RuntimeError("Store가 초기화되지 않았습니다.")

        try:
            if not self.upload_history:
                return {
                    "answer": "등록된 문서가 없습니다. 먼저 PDF 파일을 업로드해 주세요.",
                    "sources": [],
                }

            # File Search Tool을 사용하여 RAG 질의
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=question,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[
                        types.Tool(
                            file_search=types.FileSearch(
                                file_search_store_names=[self.store_name]
                            )
                        )
                    ],
                ),
            )

            # 답변 텍스트 추출
            answer_text = response.text if response.text else "답변을 생성할 수 없습니다."

            # ★ 답변 본문에 남은 Gemini 파일 ID를 한글 파일명으로 치환
            answer_text = self._replace_file_ids_in_text(answer_text)

            # 출처 정보 추출 (grounding_metadata → grounding_chunks)
            sources = self._extract_sources(response)

            logger.info(f"질의 완료 - 출처 {len(sources)}건")
            return {"answer": answer_text, "sources": sources}

        except Exception as e:
            logger.error(f"RAG 질의 실패: {e}")
            return {
                "answer": f"질문 처리 중 오류가 발생했습니다: {str(e)}",
                "sources": [],
            }

    def _extract_sources(self, response) -> list:
        """
        Gemini 응답에서 출처 정보(grounding_chunks)를 추출합니다.

        File Search는 검색된 문서 청크의 제목과 원문을 반환합니다.
        """
        sources = []
        seen_titles = set()

        try:
            candidates = response.candidates
            if not candidates:
                return sources

            grounding = candidates[0].grounding_metadata
            if not grounding or not grounding.grounding_chunks:
                return sources

            for chunk in grounding.grounding_chunks:
                if not chunk.retrieved_context:
                    continue

                ctx = chunk.retrieved_context
                title = getattr(ctx, "title", "알 수 없는 문서") or "알 수 없는 문서"
                text = getattr(ctx, "text", "") or ""

                # display_name으로 매핑 (Gemini file ID → 한글 파일명)
                display_title = self._resolve_display_name(title)

                # 같은 문서의 중복 출처는 텍스트만 합침
                if display_title not in seen_titles:
                    seen_titles.add(display_title)
                    sources.append({
                        "title": display_title,
                        "text": text[:300] if text else "",
                    })

        except Exception as e:
            logger.warning(f"출처 정보 추출 중 오류 (답변은 정상): {e}")

        return sources

    def _resolve_display_name(self, gemini_title: str) -> str:
        """
        Gemini가 반환한 파일 ID/이름을 한글 원본 파일명으로 변환합니다.

        File Search Store는 출처에 gemini_file_name(예: 6pjfgxy47cb3)을 반환하므로,
        upload_history에서 원본 한글 파일명을 찾아 매핑합니다.
        """
        # 이미 알려진 원본 파일명이면 그대로 반환 (PDF, HWP, TXT 등 모든 확장자)
        KNOWN_EXTENSIONS = {".pdf", ".hwp", ".doc", ".docx", ".xlsx", ".xls",
                           ".pptx", ".txt", ".csv", ".md"}
        for ext in KNOWN_EXTENSIONS:
            if gemini_title.lower().endswith(ext):
                return gemini_title

        # upload_history에서 gemini_file_name으로 역매핑
        for file_name, info in self.upload_history.items():
            gemini_name = info.get("gemini_file_name", "")
            # "files/6pjfgxy47cb3" → "6pjfgxy47cb3" 비교
            short_name = gemini_name.replace("files/", "")
            if short_name == gemini_title or gemini_name == gemini_title:
                return file_name

        return gemini_title

    def _replace_file_ids_in_text(self, text: str) -> str:
        """
        답변 본문에 포함된 Gemini 파일 ID (예: 'fgdc4k02xvfe')를
        한글 원본 파일명으로 치환합니다.
        """
        for file_name, info in self.upload_history.items():
            gemini_name = info.get("gemini_file_name", "")
            short_id = gemini_name.replace("files/", "")
            if short_id and short_id in text:
                # 파일 ID를 '문서명' 형태로 치환
                text = text.replace(short_id, f"'{file_name}'")
        return text

    # ──────────────────────────────────────────
    # 문서 목록 / 상태 조회
    # ──────────────────────────────────────────

    def get_document_list(self) -> list:
        """현재 인덱싱된 문서 목록을 반환합니다."""
        try:
            documents = []
            for file_name, info in self.upload_history.items():
                documents.append({
                    "file_name": file_name,
                    "status": info.get("status", "unknown"),
                })
            return sorted(documents, key=lambda x: x["file_name"])
        except Exception as e:
            logger.error(f"문서 목록 조회 실패: {e}")
            return []

    def get_document_count(self) -> int:
        """등록된 문서 수를 반환합니다."""
        return len(self.upload_history)

    def get_status(self) -> dict:
        """시스템 상태 정보를 반환합니다."""
        return {
            "store_connected": self.store_name is not None,
            "store_name": self.store_name or "미연결",
            "document_count": self.get_document_count(),
        }
