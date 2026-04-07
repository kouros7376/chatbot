"""
HAEMA Knowledge Base - TXT/DOCX 업로드 테스트 스크립트
API를 통해 TXT 파일 업로드 후 질의응답까지 검증합니다.
"""
import urllib.request
import json
import os
import http.client
import time

BASE_URL = "http://localhost:8000"

def upload_file(file_path: str) -> dict:
    """파일을 API를 통해 업로드합니다."""
    boundary = "----TestBoundary12345"
    file_name = os.path.basename(file_path)
    
    with open(file_path, "rb") as f:
        file_data = f.read()
    
    # multipart/form-data 바디 구성
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    
    req = urllib.request.Request(
        f"{BASE_URL}/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": json.loads(e.read()).get("detail", "")}


def query_chat(question: str) -> dict:
    """질문을 전송하고 답변을 받습니다."""
    data = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def get_status() -> dict:
    """시스템 상태를 조회합니다."""
    resp = urllib.request.urlopen(f"{BASE_URL}/api/status")
    return json.loads(resp.read())


def get_documents() -> dict:
    """문서 목록을 조회합니다."""
    resp = urllib.request.urlopen(f"{BASE_URL}/api/documents")
    return json.loads(resp.read())


if __name__ == "__main__":
    print("=" * 60)
    print("HAEMA Knowledge Base - 다중 문서 형식 지원 테스트")
    print("=" * 60)
    
    # 1. 현재 상태 확인
    print("\n[1/4] 현재 시스템 상태 확인...")
    status = get_status()
    print(f"  Store 연결: {status['store_connected']}")
    print(f"  문서 수: {status['document_count']}개")
    
    # 2. TXT 파일 업로드
    test_file = "docs/테스트_사내규정.txt"
    print(f"\n[2/4] TXT 파일 업로드: {test_file}...")
    result = upload_file(test_file)
    print(f"  결과: {json.dumps(result, ensure_ascii=False, indent=2)}")
    
    # 3. 인덱싱 대기 후 문서 목록 확인
    print("\n[3/4] 인덱싱 대기 (5초)...")
    time.sleep(5)
    docs = get_documents()
    print(f"  총 문서 수: {docs['total_count']}개")
    for doc in docs["documents"]:
        print(f"    - {doc['file_name']} ({doc['status']})")
    
    # 4. TXT 내용 기반 질의
    print("\n[4/4] TXT 문서 내용으로 질의 테스트...")
    question = "사내 규정에서 출근 시간과 퇴근 시간이 어떻게 되나요?"
    print(f"  질문: {question}")
    answer = query_chat(question)
    print(f"  답변: {answer['answer'][:300]}...")
    if answer["sources"]:
        print("  출처:")
        for s in answer["sources"]:
            print(f"    - {s['title']}")
    
    print("\n" + "=" * 60)
    print("테스트 완료!")
    print("=" * 60)
