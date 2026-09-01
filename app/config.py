import os
from dataclasses import dataclass
from dotenv import load_dotenv

# .env 파일이 존재하면 환경변수로 등록 (이미 설정된 OS 환경변수는 덮어쓰지 않음)
load_dotenv()


@dataclass
class AppConfig:
    """애플리케이션 환경 설정.
    환경변수에서 값을 로드하며, 미설정 시 기본값을 사용합니다.
    """

    # ─── 데이터베이스 ───
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"
    DB_NAME: str = "risk_assessment"
    DB_USER: str = "risk_user"
    DB_PASSWORD: str = ""

    # ─── LLM (LM Studio) ───
    LLM_BASE_URL: str = "http://localhost:1234/v1"
    LLM_MODEL: str = "gemma-4"
    LLM_TEMPERATURE: str = "0.3"

    # ─── API 서버 ───
    API_SERVER_HOST: str = "localhost"
    API_SERVER_PORT: str = "8443"

    # ─── 관리자 인증 (Admin Secret Key) ───
    ADMIN_SECRET_KEY: str = ""

    # ─── Rate Limit ───
    RATE_LIMIT_PER_MINUTE: str = "30"

    @classmethod
    def load(cls) -> "AppConfig":
        """환경변수에서 설정값을 로드합니다. 미설정 시 기본값을 사용합니다."""
        return cls(
            DB_HOST=os.environ.get("DB_HOST", cls.DB_HOST),
            DB_PORT=os.environ.get("DB_PORT", cls.DB_PORT),
            DB_NAME=os.environ.get("DB_NAME", cls.DB_NAME),
            DB_USER=os.environ.get("DB_USER", cls.DB_USER),
            DB_PASSWORD=os.environ.get("DB_PASSWORD", cls.DB_PASSWORD),
            LLM_BASE_URL=os.environ.get("LLM_BASE_URL", cls.LLM_BASE_URL),
            LLM_MODEL=os.environ.get("LLM_MODEL", cls.LLM_MODEL),
            LLM_TEMPERATURE=os.environ.get("LLM_TEMPERATURE", cls.LLM_TEMPERATURE),
            API_SERVER_HOST=os.environ.get("API_SERVER_HOST", cls.API_SERVER_HOST),
            API_SERVER_PORT=os.environ.get("API_SERVER_PORT", cls.API_SERVER_PORT),
            ADMIN_SECRET_KEY=os.environ.get("ADMIN_SECRET_KEY", cls.ADMIN_SECRET_KEY),
            RATE_LIMIT_PER_MINUTE=os.environ.get("RATE_LIMIT_PER_MINUTE", cls.RATE_LIMIT_PER_MINUTE),
        )

    def get_db_net_value(self, action: str = "SELECT") -> dict:
        """DbConn에 전달할 net_value 딕셔너리를 생성합니다."""
        return {
            "action": action,
            "host": self.DB_HOST,
            "port": self.DB_PORT,
            "database": self.DB_NAME,
            "username": self.DB_USER,
            "password": self.DB_PASSWORD,
        }
