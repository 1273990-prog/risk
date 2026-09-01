-- 평가 요청 테이블
-- "누가, 언제, 무엇을 평가 요청했는가"를 기록합니다.
CREATE TABLE IF NOT EXISTS risk_request (
    rule_no             VARCHAR(51)     PRIMARY KEY,
    domain_id           VARCHAR(40)     NOT NULL,               -- 도메인 식별자
    subject             TEXT            NOT NULL,               -- 평가 주제 (예: FastAPI 서버 탈취)
    request_type        VARCHAR(20)     DEFAULT 'REALTIME',     -- REALTIME, BATCH, REGENERATE
    status              VARCHAR(20)     DEFAULT 'PENDING',      -- PENDING, PROCESSING, COMPLETED, FAILED
    total_threats       INTEGER         DEFAULT 0,              -- 도출된 위험 항목 수
    model_name          VARCHAR(50),                            -- 사용된 LLM 모델명
    prompt_tokens       INTEGER,                                -- 입력 토큰 수
    completion_tokens   INTEGER,                                -- 출력 토큰 수
    elapsed_ms          INTEGER,                                -- 처리 소요 시간 (밀리초)
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    completed_at        TIMESTAMPTZ                             -- 완료 시각
);
