import json
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, Any
from app.common.constants import RiskConstants
from app.common.logger import get_logger

logger = get_logger(__name__)


SAFE_QUERY_REGISTRY: Dict[str, str] = {
    # ─── 도메인 설정 관리 쿼리 ───

    "SELECT_DOMAIN_CONFIG_BY_ID": """
                        SELECT *
                        FROM domain_config
                        WHERE domain_id = %(domain_id)s
                          AND is_active = true
                        """,

    "SELECT_ALL_DOMAIN_CONFIGS": """
                        SELECT *
                        FROM domain_config
                        WHERE is_active = true
                        ORDER BY created_at DESC
                        """,

    "INSERT_DOMAIN_CONFIG": """
                        INSERT INTO domain_config
                            (rule_no, domain_id, domain_name, role_description,
                             standards, legal_references, risk_categories,
                             output_instruction, example_subjects,
                             temperature, generated_at, is_active, is_reviewed, created_at, updated_at)
                        VALUES
                            (%(rule_no)s, %(domain_id)s, %(domain_name)s, %(role_description)s,
                             %(standards)s, %(legal_references)s, %(risk_categories)s,
                             %(output_instruction)s, %(example_subjects)s,
                             %(temperature)s::NUMERIC, NOW(),
                             %(is_active)s::BOOLEAN,
                             %(is_reviewed)s::BOOLEAN, NOW(), NOW())
                        """,

    "UPDATE_DOMAIN_CONFIG": """
                        UPDATE domain_config
                        SET standards = %(standards)s,
                            legal_references = %(legal_references)s,
                            risk_categories = %(risk_categories)s,
                            output_instruction = %(output_instruction)s,
                            example_subjects = %(example_subjects)s,
                            temperature = %(temperature)s::NUMERIC,
                            is_reviewed = %(is_reviewed)s::BOOLEAN,
                            updated_at = NOW()
                        WHERE domain_id = %(domain_id)s
                        """,

    "APPROVE_DOMAIN_CONFIG": """
                        UPDATE domain_config
                        SET is_reviewed = true, updated_at = NOW()
                        WHERE domain_id = %(domain_id)s
                        """,

    # ─── API Key 관리 쿼리 ───

    "SELECT_API_KEY_BY_HASH": """
                        SELECT *
                        FROM api_keys
                        WHERE api_key_hash = %(api_key_hash)s
                          AND is_active = true
                          AND (expires_at IS NULL OR expires_at > NOW())
                        """,

    "INSERT_API_KEY": """
                        INSERT INTO api_keys
                            (rule_no, api_key_hash, api_key_prefix, client_name,
                             is_active, rate_limit, expires_at,
                             last_used_at, total_requests, created_at)
                        VALUES
                            (%(rule_no)s, %(api_key_hash)s, %(api_key_prefix)s,
                             %(client_name)s,
                             %(is_active)s::BOOLEAN, %(rate_limit)s::INTEGER,
                             %(expires_at)s, %(last_used_at)s,
                             %(total_requests)s::INTEGER, NOW())
                        """,

    "UPDATE_API_KEY_USAGE": """
                        UPDATE api_keys
                        SET last_used_at = NOW(),
                            total_requests = total_requests + 1
                        WHERE rule_no = %(rule_no)s
                        """,

    "DEACTIVATE_API_KEY": """
                        UPDATE api_keys
                        SET is_active = false
                        WHERE rule_no = %(rule_no)s
                        """,

    "SELECT_ALL_API_KEYS": """
                        SELECT rule_no, api_key_prefix, client_name,
                               is_active, rate_limit, expires_at, last_used_at,
                               total_requests, created_at
                        FROM api_keys
                        ORDER BY created_at DESC
                        """,

    # ─── 평가 요청 관리 쿼리 ───

    "INSERT_RISK_REQUEST": """
                        INSERT INTO risk_request
                            (rule_no, domain_id, subject,
                             request_type, status, total_threats, model_name,
                             prompt_tokens, completion_tokens, elapsed_ms,
                             created_at, completed_at)
                        VALUES
                            (%(rule_no)s, %(domain_id)s, %(subject)s,
                             %(request_type)s, %(status)s, %(total_threats)s::INTEGER,
                             %(model_name)s, %(prompt_tokens)s::INTEGER,
                             %(completion_tokens)s::INTEGER, %(elapsed_ms)s::INTEGER,
                             NOW(), %(completed_at)s)
                        """,

    "UPDATE_RISK_REQUEST_STATUS": """
                        UPDATE risk_request
                        SET status = %(status)s,
                            total_threats = %(total_threats)s::INTEGER,
                            model_name = %(model_name)s,
                            prompt_tokens = %(prompt_tokens)s::INTEGER,
                            completion_tokens = %(completion_tokens)s::INTEGER,
                            elapsed_ms = %(elapsed_ms)s::INTEGER,
                            completed_at = CASE
                                WHEN %(status)s IN ('COMPLETED', 'FAILED') THEN NOW()
                                ELSE completed_at
                            END
                        WHERE rule_no = %(rule_no)s
                        """,

    "SELECT_RISK_REQUEST_BY_ID": """
                        SELECT *
                        FROM risk_request
                        WHERE rule_no = %(rule_no)s
                        """,

    "SELECT_RISK_REQUESTS": """
                        SELECT *
                        FROM risk_request
                        ORDER BY created_at DESC
                        LIMIT %(limit)s
                        OFFSET %(offset)s
                        """,

    # ─── 평가 결과 관리 쿼리 ───

    "INSERT_RISK_RESULT": """
                        INSERT INTO risk_result
                            (rule_no, group_no, seq, threat_name, category,
                             risk_level, likelihood, impact, risk_score,
                             description, mitigation, legal_basis, created_at)
                        VALUES
                            (%(rule_no)s, %(group_no)s, %(seq)s::INTEGER,
                             %(threat_name)s, %(category)s,
                             %(risk_level)s, %(likelihood)s, %(impact)s,
                             %(risk_score)s::INTEGER,
                             %(description)s, %(mitigation)s, %(legal_basis)s, NOW())
                        """,

    "SELECT_RISK_RESULTS_BY_REQUEST": """
                        SELECT *
                        FROM risk_result
                        WHERE group_no = %(group_no)s
                        ORDER BY seq
                        """,
}


class DbConn:
    """데이터베이스 연결 및 쿼리 실행 관리 클래스.
    기존 agent/src/common/db_conn.py의 구조를 그대로 따릅니다.
    SAFE_QUERY_REGISTRY를 통한 쿼리 화이트리스트 방식으로 SQL Injection을 방지합니다.
    """

    def __init__(self, net_value_json: str):
        self.__connection: Optional[psycopg2.extensions.connection] = None
        self.__cursor: Optional[psycopg2.extensions.cursor] = None

        self.__sql_query: str = ""
        self.__action: str = ""  # SELECT, INSERT, UPDATE, DELETE 등

        # 1. 받아온 데이터베이스 연결 설정 JSON 문자열을 딕셔너리로 변환
        try:
            self.__net_value: Dict[str, Any] = json.loads(net_value_json)
        except json.JSONDecodeError as e:
            logger.error(f"[DB] net_value JSON 파싱 실패: {e}")
            raise e

        self.__data_value: Optional[Dict[str, Any]] = None

        # 초기 연결 설정 빌드
        self._create()

    # --- 외부 노출 프로퍼티들 ---
    @property
    def net_value(self) -> Dict[str, Any]:
        return self.__net_value

    @net_value.setter
    def net_value(self, net_value_json: str):
        self.__net_value = json.loads(net_value_json)

    @property
    def data_value(self) -> Optional[Dict[str, Any]]:
        return self.__data_value

    def create_request(self, data_value_json: str) -> str:
        try:
            self.__data_value = json.loads(data_value_json)
        except json.JSONDecodeError as e:
            logger.error(f"[DB] data_value JSON 파싱 실패: {e}")
            raise e

        query_key = ""

        try:
            # JSON 데이터 내부에서 실행할 SQL 쿼리문 추출
            query_key = self.__data_value.get("query_key", "")

            # 서버 내부에서 매핑된 안전한 정적 쿼리문 할당
            self.__sql_query = SAFE_QUERY_REGISTRY[query_key]

            return self.__sql_query
        except Exception as e:
            logger.error(f"[DB] 보안 경고 - 허가되지 않은 쿼리 키 요청: {query_key}")
            raise e

    def _create(self):
        """__net_value 딕셔너리에서 DB 접속 기본 필드 추출"""
        self.__action = self.__net_value.get("action", "")

    def create_response(self) -> str:
        """데이터베이스 연결 후 쿼리를 실행하고 결과를 JSON 스트링으로 리턴"""
        try:
            # net_value에 포함된 DB 접속 정보 추출 (호스트, 포트, DB명, 계정 등)
            db_args = {
                "host": self.__net_value.get("host", ""),
                "port": int(self.__net_value.get("port", 0)),
                "database": self.__net_value.get("database", ""),
                "user": self.__net_value.get("username", ""),
                "password": self.__net_value.get("password", ""),
            }

            # 1) DB 커넥션 및 커서 오픈
            self.__connection = psycopg2.connect(**db_args)
            self.__connection.set_client_encoding("UTF-8")

            # RealDictCursor를 사용하여 SELECT 결과를 딕셔너리 리스트 구조로 파싱 유도
            self.__cursor = self.__connection.cursor(cursor_factory=RealDictCursor)

            # Query에 바인딩할 파라미터 추출
            bind_params = self.__data_value.get("params", {}) if self.__data_value else {}

            # 2) 쿼리 실행 (리스트 파라미터 전달 시 executemany 일괄 처리)
            if isinstance(bind_params, list):
                self.__cursor.executemany(self.__sql_query, bind_params)
            else:
                self.__cursor.execute(self.__sql_query, bind_params)

            # 3) 액션에 따른 반환 데이터 처리
            result_data: Any = None

            if self.__action == RiskConstants.SELECT:
                rows = self.__cursor.fetchall()
                # SELECT 계열이면 결과 로우 전체 Fetch
                result_data = [{}] if len(rows) == 0 else rows
            else:
                # INSERT, UPDATE, DELETE 계열이면 트랜잭션 반영 및 영향받은 행 수 리턴
                self.__connection.commit()
                result_data = {"affected_rows": self.__cursor.rowcount, "status": "success"}

            # 결과를 JSON String으로 직렬화하여 반환
            return json.dumps(result_data, ensure_ascii=False, default=str)

        except psycopg2.Error as e:
            logger.error(f"[DB] 쿼리 실행 예외 발생 - SQLState: {e.pgcode}, 메시지: {e.pgerror}")
            # 트랜잭션 롤백 처리
            if self.__connection:
                self.__connection.rollback()
            raise e
        except Exception as e:
            logger.error(f"[DB] 응답 처리 실패: {e}")
            raise e
        finally:
            # 4) 자원 해제 부
            if self.__cursor:
                self.__cursor.close()
            if self.__connection:
                self.__connection.close()
