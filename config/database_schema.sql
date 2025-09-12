-- 암호화폐 자동매매 프로그램 데이터베이스 스키마
-- 생성일: 2025-09-11
-- 설명: 바이낸스 선물 자동매매를 위한 데이터베이스 구조

-- 1. strategies 테이블 (다른 테이블이 참조하므로 먼저 생성)
CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    parameters JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. market_data 테이블 (독립적)
CREATE TABLE market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    open DECIMAL(12,4) NOT NULL,
    high DECIMAL(12,4) NOT NULL,
    low DECIMAL(12,4) NOT NULL,
    close DECIMAL(12,4) NOT NULL,
    volume DECIMAL(18,4) NOT NULL,
    macd_12_26_9_line DECIMAL(12,8),
    macd_12_26_9_signal DECIMAL(12,8),
    macd_12_26_9_histogram DECIMAL(12,8),
    atr_14_value DECIMAL(12,8),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_symbol_timestamp UNIQUE (symbol, timestamp)
);

-- 3. system_logs 테이블 (독립적)
CREATE TABLE system_logs (
    id SERIAL PRIMARY KEY,
    module_name VARCHAR(100) NOT NULL,
    trader_id INTEGER,
    level VARCHAR(20) NOT NULL CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    message TEXT NOT NULL,
    data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. traders 테이블 (strategies를 참조)
CREATE TABLE traders (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    symbol VARCHAR(20) NOT NULL,
    strategy_id INTEGER NOT NULL,
    allocated_budget DECIMAL(15,2) NOT NULL,
    investment_amount DECIMAL(15,2) NOT NULL,
    total_pnl DECIMAL(15,2) DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT fk_traders_strategy FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

-- 5. positions 테이블 (traders를 참조)
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    trader_id INTEGER NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    size DECIMAL(18,8) NOT NULL,
    entry_price DECIMAL(12,4) NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE NOT NULL,
    unrealized_pnl DECIMAL(15,2) DEFAULT 0,
    is_open BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT fk_positions_trader FOREIGN KEY (trader_id) REFERENCES traders(id)
);

-- 6. trades 테이블 (traders를 참조)
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    trader_id INTEGER NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    position_side VARCHAR(10) NOT NULL CHECK (position_side IN ('LONG', 'SHORT')),
    quantity DECIMAL(18,8) NOT NULL,
    price DECIMAL(12,4) NOT NULL,
    order_type VARCHAR(20) NOT NULL DEFAULT 'MARKET',
    trade_type VARCHAR(10) NOT NULL CHECK (trade_type IN ('ENTRY', 'EXIT')),
    realized_pnl DECIMAL(15,2),
    binance_order_id BIGINT,
    executed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT fk_trades_trader FOREIGN KEY (trader_id) REFERENCES traders(id)
);