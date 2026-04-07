"""
HAEMA Knowledge Base - FastAPI 메인 서버

건축사사무소 사내 매뉴얼 RAG 챗봇의 백엔드 서버입니다.
Gemini File Search API를 활용하여 PDF 문서 기반 질의응답을 제공합니다.
"""

import os
import logging
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from file_search_manager import FileSearchManager

# ──────────────────────────────────────────────
# 환경 변수 및 로깅 설정
# ──────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 상수 정의
DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB (Gemini File Search 제한)

# ──────────────────────────────────────────────
# File Search Manager 인스턴스 (전역)
# ──────────────────────────────────────────────
manager = FileSearchManager()


# ──────────────────────────────────────────────
# 서버 시작/종료 시 실행되는 이벤트 핸들러
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    서버 시작 시:
    1. File Search Store 자동 초기화
    2. docs/ 폴더에 있는 PDF 자동 인덱싱
    """
    logger.info("=" * 50)
    logger.info("HAEMA Knowledge Base 서버를 시작합니다...")
    logger.info("=" * 50)

    try:
        # Store 초기화
        await manager.initialize_store()
        logger.info("File Search Store 초기화 완료")

        # docs/ 폴더의 기존 PDF 자동 업로드
        result = await manager.upload_documents()
        uploaded = len(result["uploaded"])
        skipped = len(result["skipped"])
        failed = len(result["failed"])
        logger.info(
            f"문서 자동 인덱싱 완료 - "
            f"업로드: {uploaded}건, 건너뜀: {skipped}건, 실패: {failed}건"
        )
    except Exception as e:
        logger.error(f"서버 초기화 중 오류: {e}")
        logger.warning("서버는 시작되지만 일부 기능이 제한될 수 있습니다.")

    yield  # 서버 실행 중

    logger.info("HAEMA Knowledge Base 서버를 종료합니다.")


# ──────────────────────────────────────────────
# FastAPI 앱 생성
# ──────────────────────────────────────────────
app = FastAPI(
    title="HAEMA Knowledge Base",
    description="건축사사무소 사내 매뉴얼 RAG 챗봇 API",
    version="1.0.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────
# 요청/응답 모델 정의
# ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    """채팅 요청 모델"""
    question: str


class SourceInfo(BaseModel):
    """출처 정보 모델"""
    title: str
    text: str


class ChatResponse(BaseModel):
    """채팅 응답 모델"""
    answer: str
    sources: list[SourceInfo]


# ──────────────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    사용자 질문을 받아 RAG 기반 답변을 반환합니다.

    - File Search Store에서 관련 문서를 검색
    - 검색 결과를 바탕으로 Gemini LLM이 답변 생성
    - 답변과 함께 출처 정보 반환
    """
    try:
        if not request.question.strip():
            raise HTTPException(status_code=400, detail="질문을 입력해 주세요.")

        logger.info(f"질문 수신: {request.question[:50]}...")
        result = await manager.query(request.question)

        return ChatResponse(
            answer=result["answer"],
            sources=[
                SourceInfo(title=s.get("title", ""), text=s.get("text", ""))
                for s in result["sources"]
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"채팅 API 오류: {e}")
        raise HTTPException(status_code=500, detail=f"답변 생성 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    PDF 파일을 업로드하고 File Search Store에 인덱싱합니다.

    - docs/ 폴더에 파일 저장
    - 즉시 File Search Store에 업로드
    - 100MB 이하 PDF 파일만 허용
    """
    try:
        # 허용되는 파일 확장자 목록 (Gemini File Search 지원 형식)
        ALLOWED_EXTENSIONS = {
            ".pdf", ".hwp",                          # PDF, 한글
            ".doc", ".docx",                         # Word
            ".xlsx", ".xls",                         # Excel
            ".pptx",                                 # PowerPoint
            ".txt", ".csv", ".md",                   # 텍스트 기반
        }
        file_ext = os.path.splitext(file.filename.lower())[1]
        if file_ext not in ALLOWED_EXTENSIONS:
            allowed_str = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 파일 형식입니다. 허용: {allowed_str}",
            )

        # 파일 크기 검증 (100MB 제한)
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"파일 크기가 100MB를 초과합니다. ({len(content) / 1024 / 1024:.1f}MB)",
            )

        # docs/ 폴더에 파일 저장
        file_path = os.path.join(DOCS_DIR, file.filename)
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"파일 저장 완료: {file.filename} ({len(content) / 1024:.1f}KB)")

        # File Search Store에 즉시 인덱싱
        result = await manager.upload_single_file(file_path)

        return {
            "success": result["success"],
            "file_name": result["file_name"],
            "message": result["message"],
            "document_count": manager.get_document_count(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"파일 업로드 API 오류: {e}")
        raise HTTPException(status_code=500, detail=f"파일 업로드 중 오류가 발생했습니다: {str(e)}")


@app.get("/api/documents")
async def get_documents():
    """인덱싱된 문서 목록을 반환합니다."""
    try:
        documents = manager.get_document_list()
        return {
            "documents": documents,
            "total_count": len(documents),
        }
    except Exception as e:
        logger.error(f"문서 목록 API 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status")
async def get_status():
    """시스템 상태 정보를 반환합니다."""
    try:
        status = manager.get_status()
        return status
    except Exception as e:
        logger.error(f"상태 API 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# 정적 파일 서빙 (프론트엔드)
# ──────────────────────────────────────────────

# static 폴더의 CSS, JS 파일 서빙
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_index():
    """메인 페이지 (index.html) 서빙"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ──────────────────────────────────────────────
# 서버 실행 (직접 실행 시)
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    logger.info(f"서버를 http://localhost:{port} 에서 시작합니다.")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
