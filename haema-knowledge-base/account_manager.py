"""
HAEMA Account Manager v1.0
===========================
사내 계정정보를 관리하고 원본 엑셀과 자동 동기화하는 데스크톱 프로그램입니다.

주요 기능:
  - 계정정보 빠른 검색 및 조회 (실시간 필터링)
  - 원본 엑셀 파일과 서버 CSV 자동 비교/동기화
  - 변경사항 미리보기 (추가/삭제/변경)
  - 자동 백업 및 변경이력 관리
  - 서버 자동 재로드

실행:
  python account_manager.py

필수 패키지:
  pip install openpyxl pandas python-dotenv requests
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import os
import json
import shutil
import random
import logging
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────
# 설정 & 상수
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CSV_PATH = BASE_DIR / "data" / "account_list.csv"
BACKUP_DIR = BASE_DIR / "data" / "backups"
SYNC_LOG = BACKUP_DIR / "sync_log.json"

# .env 환경변수 로드
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "197819")
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")

# 보호 계정: 엑셀에 없어도 CSV에서 삭제하지 않는 사번 (서장준 = 관리자)
PROTECTED_SABUN = {"197"}

# 비교 대상 컬럼
COMPARE_COLS = ["한글이름", "메일", "계정", "비밀번호", "직급", "부서"]

# 테이블 표시 컬럼 순서
TABLE_COLS = ["이름", "사번", "계정", "비밀번호", "직급", "부서", "메일", "보안코드"]
TABLE_WIDTHS = [80, 60, 90, 100, 60, 120, 180, 80]

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("AccountManager")

# ──────────────────────────────────────────────
# UI 테마 설정
# ──────────────────────────────────────────────
COLORS = {
    "bg": "#F0F2F5",
    "card_bg": "#FFFFFF",
    "primary": "#E8820E",       # HAEMA 오렌지
    "primary_dark": "#D4740B",
    "primary_light": "#FFF3E0",
    "danger": "#DC2626",
    "danger_light": "#FEE2E2",
    "success": "#16A34A",
    "success_light": "#DCFCE7",
    "warning": "#F59E0B",
    "warning_light": "#FEF3C7",
    "text": "#1F2937",
    "text_muted": "#6B7280",
    "border": "#D1D5DB",
    "row_even": "#FFFFFF",
    "row_odd": "#FDF6EC",
    "row_selected": "#FFF7ED",
}

FONT = ("맑은 고딕", 10)
FONT_BOLD = ("맑은 고딕", 10, "bold")
FONT_TITLE = ("맑은 고딕", 14, "bold")
FONT_SMALL = ("맑은 고딕", 9)
FONT_MONO = ("Consolas", 10)


# ──────────────────────────────────────────────
# 유틸리티 함수
# ──────────────────────────────────────────────

def load_csv_data(csv_path=None):
    """
    서버 CSV 파일을 DataFrame으로 로드합니다.
    - 여러 인코딩 자동 시도
    - 사번/보안코드를 문자열로 변환
    """
    path = csv_path or CSV_PATH
    if not os.path.exists(path):
        logger.error(f"CSV 파일을 찾을 수 없습니다: {path}")
        return pd.DataFrame()

    for enc in ["utf-8-sig", "cp949", "euc-kr"]:
        try:
            df = pd.read_csv(path, encoding=enc)
            # 사번, 보안코드를 문자열로 변환 (소수점 제거)
            for col in ["사번", "보안코드"]:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.replace(r"\.0$", "", regex=True)
            logger.info(f"CSV 로드 완료: {len(df)}건 ({enc})")
            return df
        except Exception:
            continue

    logger.error("CSV 파일 인코딩 오류")
    return pd.DataFrame()


def load_excel_data(file_path):
    """
    엑셀 파일의 첫 번째 시트를 로드합니다.
    - nan(빈 행) 자동 필터링
    - 사번을 문자열로 변환
    """
    try:
        df = pd.read_excel(file_path, sheet_name=0, engine="openpyxl")
        # 한글이름 또는 사번이 비어있는 행 제거
        df = df.dropna(subset=["한글이름"])
        df = df[df["한글이름"].astype(str).str.strip() != ""]
        # 사번이 있는 행만 유지
        if "사번" in df.columns:
            df = df.dropna(subset=["사번"])
            df["사번"] = df["사번"].astype(str).str.replace(r"\.0$", "", regex=True)

        logger.info(f"엑셀 로드 완료: {len(df)}건 (시트: {pd.ExcelFile(file_path).sheet_names[0]})")
        return df
    except Exception as e:
        logger.error(f"엑셀 로드 실패: {e}")
        return None


def generate_security_code(sabun):
    """
    보안코드를 자동 생성합니다.
    규칙: 사번 + 랜덤 3자리 숫자
    """
    suffix = str(random.randint(100, 999))
    return f"{sabun}{suffix}"


def create_backup():
    """
    현재 CSV 파일을 타임스탬프로 백업합니다.
    최근 20개까지만 보관합니다.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"account_list_{timestamp}.csv"

    try:
        shutil.copy2(CSV_PATH, backup_path)
        logger.info(f"백업 생성: {backup_path}")

        # 오래된 백업 정리 (최근 20개만 유지)
        backups = sorted(BACKUP_DIR.glob("account_list_*.csv"), reverse=True)
        for old_backup in backups[20:]:
            old_backup.unlink()
            logger.info(f"오래된 백업 삭제: {old_backup.name}")

        return str(backup_path)
    except Exception as e:
        logger.error(f"백업 실패: {e}")
        return None


def save_sync_log(entry):
    """동기화 이력을 JSON 파일에 기록합니다."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    logs = []
    if SYNC_LOG.exists():
        try:
            with open(SYNC_LOG, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    logs.insert(0, entry)  # 최신 기록을 앞에 추가
    logs = logs[:50]  # 최근 50개만 유지

    try:
        with open(SYNC_LOG, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"이력 저장 실패: {e}")


def reload_server(password):
    """챗봇 서버에 CSV 재로드 요청을 보냅니다."""
    try:
        import requests
        res = requests.post(
            f"{SERVER_URL}/api/admin/reload-accounts",
            json={"password": password},
            timeout=5
        )
        data = res.json()
        if data.get("success"):
            logger.info(f"서버 재로드 완료: {data.get('count', '?')}건")
            return True, data.get("message", "재로드 완료")
        else:
            return False, data.get("detail", "인증 실패")
    except Exception as e:
        logger.warning(f"서버 연결 불가: {e}")
        return False, f"서버 연결 불가 (CSV는 저장됨)\n{e}"


def compare_excel_with_csv(df_excel, df_csv):
    """
    엑셀과 CSV를 사번 기준으로 비교하여 차이점을 반환합니다.

    Returns:
        dict: {
            "added": [...],     # 엑셀에만 있는 인원 (신규)
            "deleted": [...],   # CSV에만 있는 인원 (퇴사)
            "modified": [...],  # 변경된 인원
            "protected": [...], # 보호 계정 (삭제 방지)
        }
    """
    # 사번을 문자열로 통일
    excel_ids = set(df_excel["사번"].astype(str))
    csv_ids = set(df_csv["사번"].astype(str))

    added_ids = sorted(excel_ids - csv_ids)
    deleted_ids = sorted(csv_ids - excel_ids)
    common_ids = sorted(excel_ids & csv_ids)

    # 추가 대상
    added = []
    for sid in added_ids:
        row = df_excel[df_excel["사번"] == sid].iloc[0]
        added.append({
            "사번": sid,
            "한글이름": str(row.get("한글이름", "")),
            "메일": str(row.get("메일", "")),
            "계정": str(row.get("계정", "")),
            "직급": str(row.get("직급", "")),
            "부서": str(row.get("부서", "")),
        })

    # 삭제 대상 (보호 계정 분리)
    deleted = []
    protected = []
    for sid in deleted_ids:
        row = df_csv[df_csv["사번"] == sid].iloc[0]
        info = {
            "사번": sid,
            "한글이름": str(row.get("한글이름", "")),
            "메일": str(row.get("메일", "")),
            "계정": str(row.get("계정", "")),
            "직급": str(row.get("직급", "")),
            "부서": str(row.get("부서", "")),
        }
        if sid in PROTECTED_SABUN:
            protected.append(info)
        else:
            deleted.append(info)

    # 변경 감지
    modified = []
    for sid in common_ids:
        row_e = df_excel[df_excel["사번"] == sid].iloc[0]
        row_c = df_csv[df_csv["사번"] == sid].iloc[0]
        changes = {}
        for col in COMPARE_COLS:
            if col in df_excel.columns and col in df_csv.columns:
                val_e = str(row_e[col]).strip()
                val_c = str(row_c[col]).strip()
                if val_e != val_c and val_e != "nan":
                    changes[col] = {"old": val_c, "new": val_e}
        if changes:
            modified.append({
                "사번": sid,
                "한글이름": str(row_e.get("한글이름", "")),
                "changes": changes,
            })

    return {
        "added": added,
        "deleted": deleted,
        "modified": modified,
        "protected": protected,
    }


def apply_sync(df_excel, df_csv, diff_result):
    """
    비교 결과를 적용하여 새 CSV DataFrame을 생성합니다.

    로직:
    1. 엑셀 데이터를 기반으로 구성
    2. 보호 계정은 기존 CSV에서 유지
    3. 기존 보안코드 매칭, 없으면 자동 생성
    """
    # 기존 보안코드 맵 구축
    security_map = {}
    if "보안코드" in df_csv.columns:
        for _, row in df_csv.iterrows():
            sid = str(row["사번"]).replace(".0", "")
            security_map[sid] = str(row["보안코드"])

    # 엑셀 데이터를 기반으로 새 DataFrame 구성
    new_rows = []
    for idx, (_, row) in enumerate(df_excel.iterrows(), start=1):
        sid = str(row["사번"]).replace(".0", "")
        # 보안코드: 기존 것 유지 또는 자동 생성
        if sid in security_map:
            sec_code = security_map[sid]
        else:
            sec_code = generate_security_code(sid)

        new_rows.append({
            "Unnamed: 0": idx,
            "한글이름": row.get("한글이름", ""),
            "메일": row.get("메일", ""),
            "계정": row.get("계정", ""),
            "비밀번호": row.get("비밀번호", ""),
            "사번": sid,
            "직급": row.get("직급", ""),
            "부서": row.get("부서", ""),
            "보안코드": sec_code,
        })

    # 보호 계정 추가 (엑셀에 없지만 유지해야 하는 계정)
    for prot in diff_result.get("protected", []):
        sid = prot["사번"]
        csv_row = df_csv[df_csv["사번"] == sid]
        if len(csv_row) > 0:
            row = csv_row.iloc[0]
            new_rows.append({
                "Unnamed: 0": len(new_rows) + 1,
                "한글이름": row.get("한글이름", ""),
                "메일": row.get("메일", ""),
                "계정": row.get("계정", ""),
                "비밀번호": row.get("비밀번호", ""),
                "사번": sid,
                "직급": row.get("직급", ""),
                "부서": row.get("부서", ""),
                "보안코드": row.get("보안코드", generate_security_code(sid)),
            })

    df_new = pd.DataFrame(new_rows)

    # Unnamed: 0 순번 재정렬
    df_new["Unnamed: 0"] = range(1, len(df_new) + 1)

    return df_new


# ──────────────────────────────────────────────
# GUI: 메인 애플리케이션
# ──────────────────────────────────────────────

class AccountManagerApp:
    """HAEMA Account Manager 메인 윈도우"""

    def __init__(self, root):
        self.root = root
        self.root.withdraw()  # 인증 전에 메인 윈도우 숨김

        self.df = pd.DataFrame()          # 현재 CSV 데이터
        self.df_filtered = pd.DataFrame()  # 필터링된 결과
        self.show_password = False         # 비밀번호 표시 여부
        self.selected_sabun = None         # 선택된 직원 사번

        # 인증 확인
        if not self.show_login():
            self.root.destroy()
            return

        # 메인 윈도우 설정
        self.root.deiconify()
        self.root.title("🏢 HAEMA Account Manager v1.0")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)
        self.root.configure(bg=COLORS["bg"])

        # CSV 로드
        self.df = load_csv_data()

        # UI 구성
        self.build_ui()

        # 키보드 단축키
        self.root.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.root.bind("<Control-s>", lambda e: self.open_sync())

        # 초기 테이블 표시
        self.refresh_table()

    # ── 인증 ──────────────────────────────

    def show_login(self):
        """관리자 비밀번호 인증 다이얼로그"""
        login_win = tk.Toplevel(self.root)
        login_win.title("🔐 관리자 인증")
        login_win.geometry("380x220")
        login_win.resizable(False, False)
        login_win.configure(bg=COLORS["card_bg"])
        
        # 메인 창이 숨겨진 상태이므로 transient를 설정하지 않거나,
        # 아래처럼 포커스를 강제로 가져옵니다.
        login_win.attributes('-topmost', True)

        # 화면 중앙 배치
        login_win.update_idletasks()
        x = (login_win.winfo_screenwidth() // 2) - 190
        y = (login_win.winfo_screenheight() // 2) - 110
        login_win.geometry(f"+{x}+{y}")

        # 포커스 획득
        login_win.grab_set()
        login_win.focus_force()

        self.auth_result = False
        self.login_attempts = 0

        # 아이콘
        tk.Label(login_win, text="🔐", font=("", 28), bg=COLORS["card_bg"]).pack(pady=(15, 5))
        tk.Label(login_win, text="관리자 인증", font=FONT_BOLD, bg=COLORS["card_bg"],
                 fg=COLORS["text"]).pack()
        tk.Label(login_win, text="관리자 비밀번호를 입력하세요", font=FONT_SMALL,
                 bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(pady=(2, 8))

        # 비밀번호 입력
        pw_frame = tk.Frame(login_win, bg=COLORS["card_bg"])
        pw_frame.pack(padx=30, fill="x")
        self.login_entry = tk.Entry(pw_frame, show="●", font=FONT, justify="center",
                                     relief="solid", bd=1)
        self.login_entry.pack(fill="x", ipady=6)
        self.login_entry.focus_set()

        # 에러 메시지
        self.login_error = tk.Label(login_win, text="", font=FONT_SMALL,
                                     fg=COLORS["danger"], bg=COLORS["card_bg"])
        self.login_error.pack(pady=(3, 0))

        def do_login(event=None):
            pw = self.login_entry.get().strip()
            if pw == ADMIN_PASSWORD:
                self.auth_result = True
                login_win.destroy()
            else:
                self.login_attempts += 1
                self.login_error.config(text=f"비밀번호가 일치하지 않습니다. ({self.login_attempts}/3)")
                self.login_entry.delete(0, tk.END)
                if self.login_attempts >= 3:
                    messagebox.showerror("인증 실패", "3회 연속 인증 실패. 프로그램을 종료합니다.")
                    login_win.destroy()

        self.login_entry.bind("<Return>", do_login)

        # 버튼
        btn = tk.Button(login_win, text="인증하기", font=FONT_BOLD, bg=COLORS["primary"],
                        fg="white", relief="flat", cursor="hand2", command=do_login)
        btn.pack(padx=30, fill="x", pady=(5, 5), ipady=4)

        login_win.protocol("WM_DELETE_WINDOW", login_win.destroy)
        self.root.wait_window(login_win)
        return self.auth_result

    # ── 메인 UI 구성 ─────────────────────

    def build_ui(self):
        """메인 화면 레이아웃 구성"""
        # 상단 제목바
        header = tk.Frame(self.root, bg=COLORS["primary"], height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🏢  HAEMA Account Manager", font=FONT_TITLE,
                 bg=COLORS["primary"], fg="white").pack(side="left", padx=15, pady=10)
        tk.Label(header, text=f"서버: {SERVER_URL}", font=FONT_SMALL,
                 bg=COLORS["primary"], fg="#FFDCAB").pack(side="right", padx=15)

        # 메인 컨테이너
        main_frame = tk.Frame(self.root, bg=COLORS["bg"])
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 상단: 검색 영역
        self.build_search_frame(main_frame)

        # 중앙: 테이블
        self.build_table_frame(main_frame)

        # 하단: 상세정보 + 액션 버튼
        bottom_frame = tk.Frame(main_frame, bg=COLORS["bg"])
        bottom_frame.pack(fill="x", pady=(8, 0))

        self.build_detail_frame(bottom_frame)
        self.build_action_frame(bottom_frame)

    def build_search_frame(self, parent):
        """검색/필터링 영역"""
        card = tk.Frame(parent, bg=COLORS["card_bg"], relief="solid", bd=1,
                        highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill="x", pady=(0, 8))

        inner = tk.Frame(card, bg=COLORS["card_bg"])
        inner.pack(fill="x", padx=12, pady=10)

        # 검색 입력
        tk.Label(inner, text="🔍 검색:", font=FONT_BOLD, bg=COLORS["card_bg"],
                 fg=COLORS["text"]).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(inner, textvariable=self.search_var, font=FONT,
                                      width=25, relief="solid", bd=1)
        self.search_entry.pack(side="left", padx=(5, 15), ipady=4)
        self.search_var.trace_add("write", lambda *_: self.on_search())

        # 부서 필터
        tk.Label(inner, text="부서:", font=FONT, bg=COLORS["card_bg"],
                 fg=COLORS["text_muted"]).pack(side="left")
        self.dept_var = tk.StringVar(value="전체")
        self.dept_combo = ttk.Combobox(inner, textvariable=self.dept_var, state="readonly",
                                        width=14, font=FONT_SMALL)
        self.dept_combo.pack(side="left", padx=(3, 12))
        self.dept_combo.bind("<<ComboboxSelected>>", lambda e: self.on_search())

        # 직급 필터
        tk.Label(inner, text="직급:", font=FONT, bg=COLORS["card_bg"],
                 fg=COLORS["text_muted"]).pack(side="left")
        self.rank_var = tk.StringVar(value="전체")
        self.rank_combo = ttk.Combobox(inner, textvariable=self.rank_var, state="readonly",
                                        width=10, font=FONT_SMALL)
        self.rank_combo.pack(side="left", padx=(3, 12))
        self.rank_combo.bind("<<ComboboxSelected>>", lambda e: self.on_search())

        # 비밀번호 표시 체크박스
        self.show_pw_var = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(inner, text="비밀번호 표시", variable=self.show_pw_var,
                              font=FONT_SMALL, bg=COLORS["card_bg"],
                              command=self.toggle_password_visibility)
        chk.pack(side="right")

    def build_table_frame(self, parent):
        """데이터 테이블"""
        table_frame = tk.Frame(parent, bg=COLORS["card_bg"], relief="solid", bd=1,
                               highlightbackground=COLORS["border"], highlightthickness=1)
        table_frame.pack(fill="both", expand=True)

        # 스타일 설정
        style = ttk.Style()
        style.configure("Custom.Treeview", font=FONT_SMALL, rowheight=28,
                         background=COLORS["row_even"], fieldbackground=COLORS["row_even"])
        style.configure("Custom.Treeview.Heading", font=FONT_BOLD, padding=5)
        style.map("Custom.Treeview", background=[("selected", COLORS["row_selected"])],
                  foreground=[("selected", COLORS["text"])])

        # Treeview
        cols = TABLE_COLS
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings",
                                  style="Custom.Treeview", selectmode="browse")

        for i, col in enumerate(cols):
            width = TABLE_WIDTHS[i] if i < len(TABLE_WIDTHS) else 100
            self.tree.heading(col, text=col,
                              command=lambda c=col: self.sort_by_column(c, False))
            self.tree.column(col, width=width, minwidth=50)

        # 교대 행 색상
        self.tree.tag_configure("odd", background=COLORS["row_odd"])
        self.tree.tag_configure("even", background=COLORS["row_even"])

        # 스크롤바
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        # 행 선택 이벤트
        self.tree.bind("<<TreeviewSelect>>", self.on_row_select)

    def build_detail_frame(self, parent):
        """선택한 직원 상세정보 패널"""
        detail_card = tk.LabelFrame(parent, text="  📋 선택한 직원 상세정보  ", font=FONT_BOLD,
                                     bg=COLORS["card_bg"], fg=COLORS["text"], padx=12, pady=8,
                                     relief="solid", bd=1)
        detail_card.pack(side="left", fill="both", expand=True, padx=(0, 8))

        # 상세정보 라벨들
        info_frame = tk.Frame(detail_card, bg=COLORS["card_bg"])
        info_frame.pack(fill="both", expand=True)

        left_col = tk.Frame(info_frame, bg=COLORS["card_bg"])
        left_col.pack(side="left", fill="both", expand=True)
        right_col = tk.Frame(info_frame, bg=COLORS["card_bg"])
        right_col.pack(side="left", fill="both", expand=True)

        def make_info_row(parent, label_text):
            """정보 행 생성 헬퍼"""
            row = tk.Frame(parent, bg=COLORS["card_bg"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label_text, font=FONT_SMALL, bg=COLORS["card_bg"],
                     fg=COLORS["text_muted"], width=10, anchor="e").pack(side="left")
            val = tk.Label(row, text="-", font=FONT_BOLD, bg=COLORS["card_bg"],
                          fg=COLORS["text"], anchor="w")
            val.pack(side="left", padx=(5, 0))
            return val

        self.detail_name = make_info_row(left_col, "이름:")
        self.detail_sabun = make_info_row(left_col, "사번:")
        self.detail_account = make_info_row(left_col, "계정:")
        self.detail_password = make_info_row(left_col, "비밀번호:")

        self.detail_mail = make_info_row(right_col, "메일:")
        self.detail_rank = make_info_row(right_col, "직급:")
        self.detail_dept = make_info_row(right_col, "부서:")
        self.detail_security = make_info_row(right_col, "보안코드:")

        # 복사 버튼들
        btn_frame = tk.Frame(detail_card, bg=COLORS["card_bg"])
        btn_frame.pack(fill="x", pady=(5, 0))

        self.copy_info_btn = tk.Button(
            btn_frame, text="📋 계정정보 복사", font=FONT_SMALL, bg=COLORS["primary_light"],
            fg=COLORS["primary_dark"], relief="flat", cursor="hand2", padx=10,
            command=self.copy_info
        )
        self.copy_info_btn.pack(side="left", padx=(0, 5))

        self.copy_pw_btn = tk.Button(
            btn_frame, text="🔑 비밀번호 복사", font=FONT_SMALL, bg=COLORS["primary_light"],
            fg=COLORS["primary_dark"], relief="flat", cursor="hand2", padx=10,
            command=self.copy_password
        )
        self.copy_pw_btn.pack(side="left")

        self.copy_feedback = tk.Label(btn_frame, text="", font=FONT_SMALL,
                                       bg=COLORS["card_bg"], fg=COLORS["success"])
        self.copy_feedback.pack(side="left", padx=10)

    def build_action_frame(self, parent):
        """하단 액션 버튼 영역"""
        action_card = tk.Frame(parent, bg=COLORS["card_bg"], relief="solid", bd=1,
                               padx=12, pady=10)
        action_card.pack(side="right", fill="y")

        # 인원 수 표시
        self.count_label = tk.Label(action_card, text="총 0명", font=FONT_BOLD,
                                     bg=COLORS["card_bg"], fg=COLORS["primary"])
        self.count_label.pack(pady=(0, 8))

        # 동기화 버튼
        sync_btn = tk.Button(
            action_card, text="📂 엑셀 동기화", font=FONT_BOLD, bg=COLORS["primary"],
            fg="white", relief="flat", cursor="hand2", width=16,
            command=self.open_sync
        )
        sync_btn.pack(pady=2, ipady=4)

        # 새로고침 버튼
        refresh_btn = tk.Button(
            action_card, text="🔄 새로고침", font=FONT, bg=COLORS["bg"],
            fg=COLORS["text"], relief="flat", cursor="hand2", width=16,
            command=self.reload_data
        )
        refresh_btn.pack(pady=2, ipady=2)

        # 변경이력 버튼
        history_btn = tk.Button(
            action_card, text="📜 변경이력", font=FONT, bg=COLORS["bg"],
            fg=COLORS["text"], relief="flat", cursor="hand2", width=16,
            command=self.open_history
        )
        history_btn.pack(pady=2, ipady=2)

    # ── 검색/필터링 ────────────────────────

    def on_search(self, event=None):
        """검색어/필터 변경 시 실시간 필터링"""
        if self.df.empty:
            return

        query = self.search_var.get().strip().lower()
        dept = self.dept_var.get()
        rank = self.rank_var.get()

        df = self.df.copy()

        # 텍스트 검색 (이름, 사번, 계정 통합)
        if query:
            mask = (
                df["한글이름"].astype(str).str.lower().str.contains(query, na=False) |
                df["사번"].astype(str).str.contains(query, na=False) |
                df["계정"].astype(str).str.lower().str.contains(query, na=False)
            )
            df = df[mask]

        # 부서 필터
        if dept and dept != "전체":
            df = df[df["부서"].astype(str) == dept]

        # 직급 필터
        if rank and rank != "전체":
            df = df[df["직급"].astype(str) == rank]

        self.df_filtered = df
        self.refresh_table(df)

    def refresh_table(self, df=None):
        """테이블 내용 갱신"""
        if df is None:
            df = self.df

        self.df_filtered = df

        # 기존 행 삭제
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 필터 드롭다운 업데이트 (처음 로드 시)
        if not self.df.empty:
            depts = sorted(self.df["부서"].dropna().unique().tolist())
            self.dept_combo["values"] = ["전체"] + depts
            ranks = sorted(self.df["직급"].dropna().unique().tolist())
            self.rank_combo["values"] = ["전체"] + ranks

        # 행 삽입
        for i, (_, row) in enumerate(df.iterrows()):
            # 비밀번호/보안코드 마스킹 처리
            pw = str(row.get("비밀번호", ""))
            sec = str(row.get("보안코드", ""))
            if not self.show_password:
                pw = "●" * min(len(pw), 8) if pw and pw != "nan" else ""
                sec = "●" * min(len(sec), 6) if sec and sec != "nan" else ""

            values = (
                str(row.get("한글이름", "")),
                str(row.get("사번", "")),
                str(row.get("계정", "")),
                pw,
                str(row.get("직급", "")),
                str(row.get("부서", "")),
                str(row.get("메일", "")),
                sec,
            )
            tag = "odd" if i % 2 else "even"
            self.tree.insert("", "end", values=values, tags=(tag,))

        # 인원 수 업데이트
        total = len(self.df)
        filtered = len(df)
        if total == filtered:
            self.count_label.config(text=f"총 {total}명")
        else:
            self.count_label.config(text=f"{filtered}명 / 총 {total}명")

    def on_row_select(self, event):
        """테이블 행 선택 시 상세정보 업데이트"""
        selection = self.tree.selection()
        if not selection:
            return

        item = self.tree.item(selection[0])
        values = item["values"]

        # values: (이름, 사번, 계정, 비밀번호, 직급, 부서, 메일, 보안코드)
        self.selected_sabun = str(values[1])

        # 원본 데이터에서 조회 (마스킹 없는 원본)
        row = self.df[self.df["사번"] == self.selected_sabun]
        if row.empty:
            return
        row = row.iloc[0]

        self.detail_name.config(text=str(row.get("한글이름", "-")))
        self.detail_sabun.config(text=str(row.get("사번", "-")))
        self.detail_account.config(text=str(row.get("계정", "-")))
        self.detail_password.config(text=str(row.get("비밀번호", "-")))
        self.detail_mail.config(text=str(row.get("메일", "-")))
        self.detail_rank.config(text=str(row.get("직급", "-")))
        self.detail_dept.config(text=str(row.get("부서", "-")))
        self.detail_security.config(text=str(row.get("보안코드", "-")))

    def copy_info(self):
        """선택 직원의 계정정보를 클립보드에 복사"""
        if not self.selected_sabun:
            messagebox.showinfo("알림", "직원을 선택해주세요.")
            return

        row = self.df[self.df["사번"] == self.selected_sabun]
        if row.empty:
            return
        row = row.iloc[0]

        text = (
            f"이름: {row.get('한글이름', '')}\n"
            f"계정: {row.get('계정', '')}\n"
            f"비밀번호: {row.get('비밀번호', '')}\n"
            f"보안코드: {row.get('보안코드', '')}"
        )

        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.show_copy_feedback("계정정보 복사됨 ✓")

    def copy_password(self):
        """선택 직원의 비밀번호만 클립보드에 복사"""
        if not self.selected_sabun:
            messagebox.showinfo("알림", "직원을 선택해주세요.")
            return

        row = self.df[self.df["사번"] == self.selected_sabun]
        if row.empty:
            return
        pw = str(row.iloc[0].get("비밀번호", ""))

        self.root.clipboard_clear()
        self.root.clipboard_append(pw)
        self.show_copy_feedback("비밀번호 복사됨 ✓")

    def show_copy_feedback(self, msg):
        """복사 완료 피드백 표시 (1.5초 후 사라짐)"""
        self.copy_feedback.config(text=msg)
        self.root.after(1500, lambda: self.copy_feedback.config(text=""))

    def toggle_password_visibility(self):
        """비밀번호 표시/숨기 토글"""
        self.show_password = self.show_pw_var.get()
        self.refresh_table(self.df_filtered)

    def sort_by_column(self, col, reverse):
        """컬럼 헤더 클릭 시 정렬"""
        col_map = {
            "이름": "한글이름", "사번": "사번", "계정": "계정",
            "비밀번호": "비밀번호", "직급": "직급", "부서": "부서",
            "메일": "메일", "보안코드": "보안코드"
        }
        actual_col = col_map.get(col, col)

        if actual_col in self.df_filtered.columns:
            sorted_df = self.df_filtered.sort_values(by=actual_col, ascending=not reverse,
                                                      key=lambda x: x.astype(str).str.lower())
            self.refresh_table(sorted_df)
            # 다음 클릭 시 반대 정렬
            self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))

    # ── 동기화 ─────────────────────────────

    def open_sync(self):
        """엑셀 파일 선택 후 동기화 미리보기 열기"""
        file_path = filedialog.askopenfilename(
            title="원본 엑셀 파일 선택",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
            initialdir=str(BASE_DIR.parent)
        )
        if not file_path:
            return

        # 엑셀 로드
        df_excel = load_excel_data(file_path)
        if df_excel is None or df_excel.empty:
            messagebox.showerror("오류", "엑셀 파일을 읽을 수 없습니다.")
            return

        # 비교 실행
        diff = compare_excel_with_csv(df_excel, self.df)

        total_changes = len(diff["added"]) + len(diff["deleted"]) + len(diff["modified"])
        if total_changes == 0:
            messagebox.showinfo("동기화", "변경사항이 없습니다. 엑셀과 CSV가 동일합니다.")
            return

        # 미리보기 윈도우 열기
        SyncPreviewWindow(self.root, self, df_excel, self.df, diff, file_path)

    def reload_data(self):
        """CSV 데이터 새로고침"""
        self.df = load_csv_data()
        self.search_var.set("")
        self.dept_var.set("전체")
        self.rank_var.set("전체")
        self.refresh_table()
        self.clear_detail()
        messagebox.showinfo("새로고침", f"데이터를 다시 로드했습니다. (총 {len(self.df)}명)")

    def clear_detail(self):
        """상세정보 패널 초기화"""
        for label in [self.detail_name, self.detail_sabun, self.detail_account,
                      self.detail_password, self.detail_mail, self.detail_rank,
                      self.detail_dept, self.detail_security]:
            label.config(text="-")
        self.selected_sabun = None

    # ── 변경이력 ───────────────────────────

    def open_history(self):
        """변경이력 윈도우"""
        hist_win = tk.Toplevel(self.root)
        hist_win.title("📜 동기화 변경이력")
        hist_win.geometry("700x450")
        hist_win.configure(bg=COLORS["bg"])
        hist_win.transient(self.root)

        # 제목
        tk.Label(hist_win, text="📜 동기화 변경이력", font=FONT_TITLE,
                 bg=COLORS["bg"], fg=COLORS["text"]).pack(pady=10)

        # 이력 테이블
        cols = ("날짜", "엑셀파일", "추가", "삭제", "변경", "총인원")
        tree = ttk.Treeview(hist_win, columns=cols, show="headings", height=15)
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=100 if col != "엑셀파일" else 200)

        # 이력 로드
        if SYNC_LOG.exists():
            try:
                with open(SYNC_LOG, "r", encoding="utf-8") as f:
                    logs = json.load(f)
                for log_entry in logs:
                    tree.insert("", "end", values=(
                        log_entry.get("timestamp", ""),
                        log_entry.get("excel_file", ""),
                        f"+{log_entry.get('added', 0)}",
                        f"-{log_entry.get('deleted', 0)}",
                        f"~{log_entry.get('modified', 0)}",
                        log_entry.get("total_after", ""),
                    ))
            except Exception:
                pass

        if not tree.get_children():
            tk.Label(hist_win, text="아직 동기화 이력이 없습니다.",
                     font=FONT, bg=COLORS["bg"], fg=COLORS["text_muted"]).pack(pady=20)

        scrollbar = ttk.Scrollbar(hist_win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(fill="both", expand=True, padx=10)
        scrollbar.pack(side="right", fill="y")


# ──────────────────────────────────────────────
# GUI: 동기화 미리보기 윈도우
# ──────────────────────────────────────────────

class SyncPreviewWindow:
    """엑셀 vs CSV 비교 결과를 표시하고 적용하는 윈도우"""

    def __init__(self, parent, app, df_excel, df_csv, diff_result, excel_path):
        self.app = app
        self.df_excel = df_excel
        self.df_csv = df_csv
        self.diff = diff_result
        self.excel_path = excel_path

        self.win = tk.Toplevel(parent)
        self.win.title("⚡ 동기화 미리보기")
        self.win.geometry("900x650")
        self.win.configure(bg=COLORS["bg"])
        self.win.transient(parent)
        self.win.grab_set()

        self.build_ui()

    def build_ui(self):
        """미리보기 UI 구성"""
        # 상단 정보
        info_frame = tk.Frame(self.win, bg=COLORS["card_bg"], relief="solid", bd=1)
        info_frame.pack(fill="x", padx=10, pady=(10, 5))

        tk.Label(info_frame, text="⚡ 동기화 미리보기", font=FONT_TITLE,
                 bg=COLORS["card_bg"], fg=COLORS["text"]).pack(anchor="w", padx=12, pady=(8, 2))

        excel_name = os.path.basename(self.excel_path)
        info_text = f"원본: {excel_name}  |  대상: data/account_list.csv"
        tk.Label(info_frame, text=info_text, font=FONT_SMALL,
                 bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(anchor="w", padx=12, pady=(0, 3))

        # 보호 계정 안내
        if self.diff["protected"]:
            prot_names = ", ".join([p["한글이름"] for p in self.diff["protected"]])
            prot_label = tk.Label(info_frame, text=f"🛡️ 보호 계정 (삭제 방지): {prot_names}",
                                   font=FONT_SMALL, bg="#EFF6FF", fg="#1D4ED8", padx=8, pady=3)
            prot_label.pack(anchor="w", padx=12, pady=(0, 8))
        else:
            tk.Label(info_frame, text="", bg=COLORS["card_bg"]).pack(pady=(0, 4))

        # 요약 카운트
        summary_frame = tk.Frame(self.win, bg=COLORS["bg"])
        summary_frame.pack(fill="x", padx=10, pady=5)

        added_count = len(self.diff["added"])
        deleted_count = len(self.diff["deleted"])
        modified_count = len(self.diff["modified"])

        self._make_summary_badge(summary_frame, f"🟢 추가 {added_count}명",
                                  COLORS["success"], COLORS["success_light"])
        self._make_summary_badge(summary_frame, f"🔴 삭제 {deleted_count}명",
                                  COLORS["danger"], COLORS["danger_light"])
        self._make_summary_badge(summary_frame, f"🟡 변경 {modified_count}건",
                                  COLORS["warning"], COLORS["warning_light"])

        # 탭 노트북
        notebook = ttk.Notebook(self.win)
        notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # 각 탭 구성
        if added_count > 0:
            added_tab = tk.Frame(notebook, bg=COLORS["card_bg"])
            notebook.add(added_tab, text=f" 🟢 추가 ({added_count}) ")
            self.build_added_tab(added_tab)

        if deleted_count > 0:
            deleted_tab = tk.Frame(notebook, bg=COLORS["card_bg"])
            notebook.add(deleted_tab, text=f" 🔴 삭제 ({deleted_count}) ")
            self.build_deleted_tab(deleted_tab)

        if modified_count > 0:
            modified_tab = tk.Frame(notebook, bg=COLORS["card_bg"])
            notebook.add(modified_tab, text=f" 🟡 변경 ({modified_count}) ")
            self.build_modified_tab(modified_tab)

        # 하단 버튼
        btn_frame = tk.Frame(self.win, bg=COLORS["bg"])
        btn_frame.pack(fill="x", padx=10, pady=(5, 10))

        apply_btn = tk.Button(
            btn_frame, text="✅ 적용하기", font=FONT_BOLD, bg=COLORS["primary"],
            fg="white", relief="flat", cursor="hand2", width=18,
            command=self.apply_changes
        )
        apply_btn.pack(side="left", padx=(0, 10), ipady=5)

        cancel_btn = tk.Button(
            btn_frame, text="❌ 취소", font=FONT, bg=COLORS["bg"],
            fg=COLORS["text_muted"], relief="flat", cursor="hand2", width=12,
            command=self.win.destroy
        )
        cancel_btn.pack(side="left", ipady=5)

    def _make_summary_badge(self, parent, text, fg_color, bg_color):
        """요약 배지 생성"""
        badge = tk.Label(parent, text=text, font=FONT_BOLD, fg=fg_color, bg=bg_color,
                          padx=15, pady=5, relief="flat")
        badge.pack(side="left", padx=(0, 8))

    def build_added_tab(self, parent):
        """추가 대상 탭"""
        cols = ("이름", "사번", "직급", "부서", "계정", "메일")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=15)
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=100 if col != "메일" else 200)

        for item in self.diff["added"]:
            tree.insert("", "end", values=(
                item["한글이름"], item["사번"], item.get("직급", ""),
                item.get("부서", ""), item.get("계정", ""), item.get("메일", "")
            ))

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

    def build_deleted_tab(self, parent):
        """삭제 대상 탭"""
        cols = ("이름", "사번", "직급", "부서", "계정", "메일")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=15)
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=100 if col != "메일" else 200)

        tree.tag_configure("deleted", background=COLORS["danger_light"])

        for item in self.diff["deleted"]:
            tree.insert("", "end", values=(
                item["한글이름"], item["사번"], item.get("직급", ""),
                item.get("부서", ""), item.get("계정", ""), item.get("메일", "")
            ), tags=("deleted",))

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

    def build_modified_tab(self, parent):
        """변경 대상 탭"""
        cols = ("이름", "사번", "변경항목", "이전값", "새값")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=15)
        tree.heading("이름", text="이름")
        tree.heading("사번", text="사번")
        tree.heading("변경항목", text="변경 항목")
        tree.heading("이전값", text="이전값")
        tree.heading("새값", text="새값")

        tree.column("이름", width=80)
        tree.column("사번", width=60)
        tree.column("변경항목", width=80)
        tree.column("이전값", width=200)
        tree.column("새값", width=200)

        tree.tag_configure("modified", background=COLORS["warning_light"])

        for item in self.diff["modified"]:
            for field, change in item["changes"].items():
                tree.insert("", "end", values=(
                    item["한글이름"], item["사번"],
                    field, change["old"], change["new"]
                ), tags=("modified",))

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

    def apply_changes(self):
        """동기화 적용"""
        added = len(self.diff["added"])
        deleted = len(self.diff["deleted"])
        modified = len(self.diff["modified"])
        protected = len(self.diff["protected"])

        msg = (
            f"다음 변경사항을 적용하시겠습니까?\n\n"
            f"  🟢 추가: {added}명\n"
            f"  🔴 삭제: {deleted}명\n"
            f"  🟡 변경: {modified}건\n"
        )
        if protected > 0:
            prot_names = ", ".join([p["한글이름"] for p in self.diff["protected"]])
            msg += f"  🛡️ 보호: {prot_names} (유지)\n"

        msg += f"\n⚠️ 적용 전 자동으로 백업됩니다."

        if not messagebox.askyesno("동기화 확인", msg):
            return

        try:
            # 1. 백업 생성
            backup_path = create_backup()
            if not backup_path:
                messagebox.showerror("오류", "백업 생성에 실패했습니다.")
                return

            # 2. 새 CSV 데이터 생성
            df_new = apply_sync(self.df_excel, self.df_csv, self.diff)

            # 3. CSV 저장
            df_new.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
            logger.info(f"CSV 저장 완료: {len(df_new)}건")

            # 4. 서버 재로드 요청
            server_ok, server_msg = reload_server(ADMIN_PASSWORD)

            # 5. 이력 기록
            save_sync_log({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "excel_file": os.path.basename(self.excel_path),
                "added": added,
                "deleted": deleted,
                "modified": modified,
                "protected": protected,
                "backup_file": os.path.basename(backup_path),
                "total_after": len(df_new),
            })

            # 6. 결과 메시지
            result_msg = (
                f"✅ 동기화 완료!\n\n"
                f"  총 인원: {len(df_new)}명\n"
                f"  백업: {os.path.basename(backup_path)}\n\n"
            )
            if server_ok:
                result_msg += f"  🔄 서버 반영 완료"
            else:
                result_msg += f"  ⚠️ 서버: {server_msg}\n  (서버 재시작 시 자동 반영됩니다)"

            messagebox.showinfo("완료", result_msg)

            # 7. 메인 윈도우 갱신
            self.app.df = load_csv_data()
            self.app.search_var.set("")
            self.app.dept_var.set("전체")
            self.app.rank_var.set("전체")
            self.app.refresh_table()
            self.app.clear_detail()

            # 8. 미리보기 윈도우 닫기
            self.win.destroy()

        except Exception as e:
            logger.error(f"동기화 실패: {e}")
            messagebox.showerror("오류", f"동기화 중 오류가 발생했습니다.\n\n{e}")


# ──────────────────────────────────────────────
# 프로그램 진입점
# ──────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app = AccountManagerApp(root)
    root.mainloop()
