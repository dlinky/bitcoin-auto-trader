-- 암호화폐 자동매매 프로그램 데이터베이스 스키마
-- 생성일: 2025-09-11
-- 설명: 바이낸스 선물 자동매매를 위한 데이터베이스 구조

-- 1. 트레이더 정보 테이블
CREATE TABLE traders (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,                -- 트레이더 이름 (예: "BTC_MACD_Trader_1")
    symbol VARCHAR(20) NOT NULL,                      -- 거래 심볼 (예: "BTCUSDT")
    strategy_id INTEGER NOT NULL,                     -- 사용하는 전략 ID
    allocated_budget DECIMAL(15,2) NOT NULL,          -- 할당받은 예산 (USDT)
    investment_amount DECIMAL(15,2) NOT NULL,         -- 실제 투자금액 (예산의 일정 비율)
    total_pnl DECIMAL(15,2) DEFAULT 0,               -- 현재까지의 총 손익
    is_active BOOLEAN DEFAULT true,                   -- 활성화 상태
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT fk_traders_strategy FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

-- 2. 전략 설정 테이블
CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,               -- 전략 이름 (예: "MACD_ATR_Strategy")
    parameters JSONB NOT NULL,                       -- 전략별 파라미터 (JSON 형태)
    -- parameters 예시: {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "atr_period": 14, "atr_multiplier": 3.0}
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. 현재 포지션 정보 테이블
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    trader_id INTEGER NOT NULL,                      -- 트레이더 ID
    symbol VARCHAR(20) NOT NULL,                     -- 거래 심볼
    side VARCHAR(10) NOT NULL CHECK (side IN ('LONG', 'SHORT')), -- 포지션 방향
    size DECIMAL(18,8) NOT NULL,                     -- 포지션 크기 (계약 수량)
    entry_price DECIMAL(12,4) NOT NULL,              -- 진입가격
    entry_time TIMESTAMP WITH TIME ZONE NOT NULL,    -- 진입시간
    unrealized_pnl DECIMAL(15,2) DEFAULT 0,         -- 미실현 손익
    is_open BOOLEAN DEFAULT true,                    -- 포지션 열림 상태
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT fk_positions_trader FOREIGN KEY (trader_id) REFERENCES traders(id),
    CONSTRAINT unique_trader_symbol_side UNIQUE (trader_id, symbol, side, is_open)
);

-- 4. 거래 내역 테이블
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    trader_id INTEGER NOT NULL,                      -- 트레이더 ID
    symbol VARCHAR(20) NOT NULL,                     -- 거래 심볼
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')), -- 거래 방향
    position_side VARCHAR(10) NOT NULL CHECK (position_side IN ('LONG', 'SHORT')), -- 포지션 방향
    quantity DECIMAL(18,8) NOT NULL,                 -- 거래 수량
    price DECIMAL(12,4) NOT NULL,                    -- 거래 가격
    order_type VARCHAR(20) NOT NULL DEFAULT 'MARKET', -- 주문 타입 (MARKET/LIMIT)
    trade_type VARCHAR(10) NOT NULL CHECK (trade_type IN ('ENTRY', 'EXIT')), -- 거래 유형
    realized_pnl DECIMAL(15,2),                      -- 실현 손익 (청산시에만)
    binance_order_id BIGINT,                         -- 바이낸스 주문 ID
    executed_at TIMESTAMP WITH TIME ZONE NOT NULL,   -- 체결 시간
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT fk_trades_trader FOREIGN KEY (trader_id) REFERENCES traders(id)
);

-- 5. 시장 데이터/지표 테이블
CREATE TABLE market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,                     -- 거래 심볼
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,     -- 시간 (1분봉 기준)
    open DECIMAL(12,4) NOT NULL,                     -- 시가
    high DECIMAL(12,4) NOT NULL,                     -- 고가
    low DECIMAL(12,4) NOT NULL,                      -- 저가
    close DECIMAL(12,4) NOT NULL,                    -- 종가
    volume DECIMAL(18,4) NOT NULL,                   -- 거래량
    
    -- MACD 지표 (12,26,9 파라미터)
    macd_12_26_9_line DECIMAL(12,8),                 -- MACD 라인
    macd_12_26_9_signal DECIMAL(12,8),               -- MACD 시그널
    macd_12_26_9_histogram DECIMAL(12,8),            -- MACD 히스토그램
    
    -- ATR 지표 (14 기간)
    atr_14_value DECIMAL(12,8),                      -- ATR 값
    
    -- 향후 추가될 지표들을 위한 여유 공간
    -- 예: rsi_14_value, bb_20_2_upper, bb_20_2_lower 등
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_symbol_timestamp UNIQUE (symbol, timestamp)
);

-- 6. 시스템 로그 테이블
CREATE TABLE system_logs (
    id SERIAL PRIMARY KEY,
    trader_id INTEGER,                               -- 트레이더 ID (옵션)
    level VARCHAR(20) NOT NULL CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')), -- 로그 레벨
    message TEXT NOT NULL,                           -- 로그 메시지
    data JSONB,                                      -- 추가 데이터 (JSON 형태)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT fk_logs_trader FOREIGN KEY (trader_id) REFERENCES traders(id)
);

-- 인덱스 생성
CREATE INDEX idx_traders_symbol ON traders(symbol);
CREATE INDEX idx_traders_active ON traders(is_active);
CREATE INDEX idx_positions_trader_symbol ON positions(trader_id, symbol);
CREATE INDEX idx_positions_open ON positions(is_open);
CREATE INDEX idx_trades_trader_symbol ON trades(trader_id, symbol);
CREATE INDEX idx_trades_executed_at ON trades(executed_at);
CREATE INDEX idx_market_data_symbol_timestamp ON market_data(symbol, timestamp DESC);
CREATE INDEX idx_system_logs_module_level ON system_logs(module_name, level);
CREATE INDEX idx_system_logs_trader_id ON system_logs(trader_id);
CREATE INDEX idx_system_logs_created_at ON system_logs(created_at DESC);

-- RLS (Row Level Security) 정책 (현재는 비활성화, 필요시 추가)
-- ALTER TABLE traders ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE strategies ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE market_data ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE system_logs ENABLE ROW LEVEL SECURITY;

-- 트리거 함수: updated_at 자동 업데이트
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 트리거 적용
CREATE TRIGGER update_traders_updated_at BEFORE UPDATE ON traders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_strategies_updated_at BEFORE UPDATE ON strategies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 샘플 데이터 삽입 (개발/테스트용)
-- 1. 기본 MACD+ATR 전략
INSERT INTO strategies (name, parameters) VALUES 
('MACD_ATR_Strategy', '{"macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "atr_period": 14, "atr_multiplier": 3.0}');

-- 2. BTC 트레이더 생성 예시
-- INSERT INTO traders (name, symbol, strategy_id, allocated_budget, investment_amount) VALUES 
-- ('BTC_MACD_Trader_1', 'BTCUSDT', 1, 1000.00, 500.00);