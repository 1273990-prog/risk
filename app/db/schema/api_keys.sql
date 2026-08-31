-- API Key 관리 테이블
-- 외부 앱 인증용 API Key를 관리합니다. 원본은 저장하지 않고 SHA256 해시만 보관합니다.
CREATE TABLE IF NOT EXISTS api_keys (
    rule_no         VARCHAR(80)     PRIMARY KEY,
    api_key_hash    VARCHAR(128)    UNIQUE NOT NULL,            -- API Key SHA256 해시
    api_key_prefix  VARCHAR(20)     NOT NULL,                   -- 키 앞 8자리 (관리 화면 식별용)
    client_name     VARCHAR(100)    NOT NULL,                   -- 발급 대상 이름
    client_contact  VARCHAR(200),                               -- 담당자 연락처
    is_active       BOOLEAN         DEFAULT true,               -- 활성/비활성 (즉시 차단용)
    rate_limit      INTEGER         DEFAULT 30,                 -- 분당 최대 호출 수
    expires_at      TIMESTAMPTZ,                                -- 만료일 (NULL이면 무기한)
    last_used_at    TIMESTAMPTZ,                                -- 마지막 사용 시각
    total_requests  INTEGER         DEFAULT 0,                  -- 누적 호출 수
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);
