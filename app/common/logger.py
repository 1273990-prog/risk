# ============================================================
# [라이브러리 교체 가이드]
#
# 현재: Python 표준 라이브러리 logging 사용
# 대체 가능 라이브러리:
#   - loguru  : pip install loguru  → 설정 대폭 단순화, 자동 로테이션 내장
#   - structlog: pip install structlog → JSON 구조화 로그, 클라우드/ELK 연동 적합
#
# 교체 시 변경이 필요한 지점은 # [REPLACE: ...] 주석으로 표시되어 있습니다.
# get_logger()의 반환 타입만 맞춰주면 각 모듈 코드는 수정 불필요합니다.
# ============================================================

# [REPLACE: import] loguru 교체 시 → from loguru import logger
# [REPLACE: import] structlog 교체 시 → import structlog
import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logger(
    log_level: str = "INFO",
    log_file_enabled: str = "true",
    log_dir: str = "logs",          # ← 파일 경로의 베이스 디렉토리 (환경변수 LOG_DIR)
) -> None:
    """애플리케이션 루트 로거를 초기화합니다.

    Args:
        log_level: 로그 레벨 문자열 (DEBUG / INFO / WARNING / ERROR / OFF)
        log_file_enabled: 파일 저장 여부 ("true" / "false")
        log_dir: 로그 파일 저장 디렉토리 경로
                 ※ 실제 파일 경로 = {log_dir}/app.log, {log_dir}/error.log
                 ※ 기본값 "logs" → 서버 실행 위치(CWD) 기준 상대경로
                 ※ 절대경로 사용 권장 (.env 파일에 설정):
                     LOG_DIR=/var/log/risk        (Linux)
                     LOG_DIR=D:/logs/risk         (Windows D드라이브) ← 권장
                     LOG_DIR=C:/logs/risk         (Windows C드라이브)
                 ※ Windows 주의: 역슬래시(\)는 이스케이프 오류 발생 가능
                     LOG_DIR=D:\logs\risk  ← ❌ 사용 금지
                     LOG_DIR=D:/logs/risk  ← ✅ 포워드 슬래시 사용
                 ※ 폴더가 없으면 자동 생성됨 (mkdir parents=True)
    """
    # ----------------------------------------------------------
    # [REPLACE: 레벨 파싱] loguru 교체 시 이 블록 전체 삭제
    # loguru는 logger.add() 호출 시 level= 인자로 직접 문자열 전달
    # ----------------------------------------------------------
    # "OFF" 레벨 처리 — 표준 logging에 없으므로 CRITICAL+1로 설정
    if log_level.upper() == "OFF":
        numeric_level = logging.CRITICAL + 1
    else:
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # ----------------------------------------------------------
    # [REPLACE: 루트 로거 초기화] loguru 교체 시 이 블록 삭제
    # loguru는 전역 logger 객체 하나로 동작 (getLogger 불필요)
    # ----------------------------------------------------------
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # 기존 핸들러 중복 방지 (uvicorn reload 시 재호출 방지)
    # [REPLACE: 핸들러 중복 방지] loguru 교체 시 → logger.remove()
    if root_logger.handlers:
        root_logger.handlers.clear()

    # ----------------------------------------------------------
    # [REPLACE: 포맷터] loguru 교체 시 이 블록 삭제
    # loguru는 logger.add()의 format= 인자로 문자열 직접 지정
    # ----------------------------------------------------------
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ----------------------------------------------------------
    # [REPLACE: 콘솔 핸들러] loguru 교체 시 →
    #   logger.add(sys.stdout, level=log_level, format="...")
    # ----------------------------------------------------------
    # ── 콘솔 핸들러 (항상 활성) ──
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ── 파일 핸들러 (LOG_FILE_ENABLED=true 일 때만) ──
    if log_file_enabled.lower() == "true":
        # ★ 파일 저장 경로 결정 지점 ★
        # log_dir 값은 AppConfig.LOG_DIR 환경변수에서 전달됨
        # → .env 파일의 LOG_DIR 값을 변경하는 것으로 경로 제어 가능
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # ── app.log: INFO 이상 전체 ──
        # [REPLACE: 파일 핸들러] loguru 교체 시 →
        #   logger.add(log_path / "app.log", level="INFO",
        #              rotation="10 MB", retention=30, encoding="utf-8")
        app_handler = logging.handlers.RotatingFileHandler(
            filename=log_path / "app.log",  # ← 실제 파일 경로 (1): {LOG_DIR}/app.log
            maxBytes=10 * 1024 * 1024,      # 10MB
            backupCount=30,                 # 최대 30개 보관 (app.log.1 ~ app.log.30)
            encoding="utf-8",
        )
        app_handler.setFormatter(formatter)
        root_logger.addHandler(app_handler)

        # ── error.log: WARNING 이상만 ──
        # [REPLACE: 에러 파일 핸들러] loguru 교체 시 →
        #   logger.add(log_path / "error.log", level="WARNING",
        #              rotation="5 MB", retention=90, encoding="utf-8")
        error_handler = logging.handlers.RotatingFileHandler(
            filename=log_path / "error.log",  # ← 실제 파일 경로 (2): {LOG_DIR}/error.log
            maxBytes=5 * 1024 * 1024,         # 5MB
            backupCount=90,                   # 최대 90개 보관
            encoding="utf-8",
        )
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)

    # ----------------------------------------------------------
    # [REPLACE: uvicorn 연동] loguru 교체 시 →
    #   import logging
    #   class InterceptHandler(logging.Handler): ...  (표준 핸들러를 loguru로 리다이렉트)
    # ----------------------------------------------------------
    # uvicorn 자체 로거가 중복 출력하지 않도록 propagate 억제
    for uvicorn_logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_log = logging.getLogger(uvicorn_logger_name)
        uvicorn_log.propagate = False


# ----------------------------------------------------------
# [REPLACE: get_logger] 라이브러리 교체 시 반환 타입만 변경하면
# 각 모듈(db_conn, lmstudio_client 등)의 코드는 수정 불필요
#
#   loguru 교체 시   → from loguru import logger; return logger
#   structlog 교체 시 → return structlog.get_logger(name)
# ----------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    """모듈별 로거를 반환합니다.

    Args:
        name: 로거 이름 (보통 __name__ 사용)

    Returns:
        logging.Logger 인스턴스
    """
    return logging.getLogger(name)
