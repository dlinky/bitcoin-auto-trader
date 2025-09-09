"""
데이터베이스 모델 정의
Supabase PostgreSQL용 테이블 구조
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

class TradeStatus(Enum):
    """거래 상태"""
    PENDING = "PENDING"     # 대기중
    FILLED = "FILLED"       # 체결완료
    CANCELLED = "CANCELLED" # 취소
    REJECTED = "REJECTED"   # 거부
    EXPIRED = "EXPIRED"     # 만료

class PositionSide(Enum):
    """포지션 방향"""
    LONG = "LONG"
    SHORT = "SHORT"

class OrderSide(Enum):
    """주문 방향"""
    BUY = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    """주문 타입"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"

@dataclass
class Trade:
    """거래 기록 모델"""
    id: Optional[str] = None
    trader_id: str = "default"
    symbol: str = ""
    side: str = ""  # BUY/SELL
    order_type: str = "MARKET"
    quantity: float = 0.0
    price: float = 0.0
    executed_quantity: float = 0.0
    executed_price: float = 0.0
    commission: float = 0.0
    commission_asset: str = "USDT"
    status: str = "PENDING"
    binance_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 추가 정보
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    notes: Optional[str] = None

@dataclass
class Position:
    """포지션 기록 모델"""
    id: Optional[str] = None
    trader_id: str = "default"
    symbol: str = ""
    side: str = ""  # LONG/SHORT
    size: float = 0.0
    entry_price: float = 0.0
    mark_price: float = 0.0
    liquidation_price: Optional[float] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    percentage: float = 0.0
    notional: float = 0.0
    margin: float = 0.0
    margin_ratio: Optional[float] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

@dataclass
class TradingSession:
    """거래 세션 모델"""
    id: Optional[str] = None
    trader_id: str = "default"
    session_name: str = ""
    strategy: Optional[str] = None
    symbol: str = ""
    start_balance: float = 0.0
    current_balance: float = 0.0
    peak_balance: float = 0.0
    total_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: Optional[float] = None
    is_active: bool = True
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None

@dataclass
class RiskEvent:
    """리스크 이벤트 기록"""
    id: Optional[str] = None
    trader_id: str = "default"
    session_id: Optional[str] = None
    event_type: str = ""  # CONSECUTIVE_LOSS, DAILY_LIMIT, DRAWDOWN_LIMIT, etc.
    risk_level: str = ""  # LOW, MEDIUM, HIGH, CRITICAL
    triggered_by: str = "" # LOSS_AMOUNT, LOSS_COUNT, DRAWDOWN_RATIO, etc.
    trigger_value: float = 0.0
    threshold_value: float = 0.0
    action_taken: str = "" # CONTINUE, REDUCE_SIZE, STOP_NEW, CLOSE_ALL, EMERGENCY_STOP
    description: str = ""
    created_at: Optional[datetime] = None

@dataclass
class SystemLog:
    """시스템 로그 모델"""
    id: Optional[str] = None
    trader_id: str = "default"
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    component: str = ""  # TRADER, RISK_MANAGER, CAPITAL_MANAGER, API_CLIENT
    event: str = ""
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

@dataclass
class Configuration:
    """설정 저장 모델"""
    id: Optional[str] = None
    trader_id: str = "default"
    config_type: str = ""  # CAPITAL, RISK, TRADER, STRATEGY
    config_name: str = ""
    config_data: Dict[str, Any] = None
    is_active: bool = True
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class PerformanceMetric:
    """성과 지표 모델"""
    id: Optional[str] = None
    trader_id: str = "default"
    session_id: Optional[str] = None
    metric_date: Optional[datetime] = None
    # 손익 지표
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0
    cumulative_pnl: float = 0.0
    # 거래 지표
    total_trades_today: int = 0
    winning_trades_today: int = 0
    losing_trades_today: int = 0
    win_rate_today: float = 0.0
    # 리스크 지표
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    consecutive_losses: int = 0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    # 자본 지표
    account_balance: float = 0.0
    available_balance: float = 0.0
    allocated_capital: float = 0.0
    capital_utilization: float = 0.0
    # 계산 지표
    sharpe_ratio: Optional[float] = None
    profit_factor: Optional[float] = None
    recovery_factor: Optional[float] = None
    created_at: Optional[datetime] = None

# SQL 테이블 생성 스크립트
CREATE_TABLES_SQL = """
-- 거래 기록 테이블
CREATE TABLE IF NOT EXISTS trades (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    trader_id VARCHAR(50) NOT NULL DEFAULT 'default',
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) DEFAULT 'MARKET',
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 2) NOT NULL,
    executed_quantity DECIMAL(20, 8) DEFAULT 0,
    executed_price DECIMAL(20, 2) DEFAULT 0,
    commission DECIMAL(20, 8) DEFAULT 0,
    commission_asset VARCHAR(10) DEFAULT 'USDT',
    status VARCHAR(20) DEFAULT 'PENDING',
    binance_order_id VARCHAR(50),
    client_order_id VARCHAR(50),
    stop_loss_price DECIMAL(20, 2),
    take_profit_price DECIMAL(20, 2),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 포지션 기록 테이블
CREATE TABLE IF NOT EXISTS positions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    trader_id VARCHAR(50) NOT NULL DEFAULT 'default',
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    size DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 2) NOT NULL,
    mark_price DECIMAL(20, 2) NOT NULL,
    liquidation_price DECIMAL(20, 2),
    unrealized_pnl DECIMAL(20, 4) DEFAULT 0,
    realized_pnl DECIMAL(20, 4) DEFAULT 0,
    percentage DECIMAL(10, 4) DEFAULT 0,
    notional DECIMAL(20, 4) DEFAULT 0,
    margin DECIMAL(20, 4) DEFAULT 0,
    margin_ratio DECIMAL(10, 4),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

-- 거래 세션 테이블
CREATE TABLE IF NOT EXISTS trading_sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    trader_id VARCHAR(50) NOT NULL DEFAULT 'default',
    session_name VARCHAR(100) NOT NULL,
    strategy VARCHAR(50),
    symbol VARCHAR(20) NOT NULL,
    start_balance DECIMAL(20, 4) NOT NULL,
    current_balance DECIMAL(20, 4) NOT NULL,
    peak_balance DECIMAL(20, 4) NOT NULL,
    total_pnl DECIMAL(20, 4) DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    win_rate DECIMAL(5, 2) DEFAULT 0,
    max_drawdown DECIMAL(5, 4) DEFAULT 0,
    sharpe_ratio DECIMAL(10, 4),
    is_active BOOLEAN DEFAULT TRUE,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    notes TEXT
);

-- 리스크 이벤트 테이블
CREATE TABLE IF NOT EXISTS risk_events (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    trader_id VARCHAR(50) NOT NULL DEFAULT 'default',
    session_id UUID REFERENCES trading_sessions(id),
    event_type VARCHAR(50) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    triggered_by VARCHAR(50) NOT NULL,
    trigger_value DECIMAL(20, 4) NOT NULL,
    threshold_value DECIMAL(20, 4) NOT NULL,
    action_taken VARCHAR(50) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 시스템 로그 테이블
CREATE TABLE IF NOT EXISTS system_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    trader_id VARCHAR(50) NOT NULL DEFAULT 'default',
    log_level VARCHAR(20) NOT NULL,
    component VARCHAR(50) NOT NULL,
    event VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 설정 저장 테이블
CREATE TABLE IF NOT EXISTS configurations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    trader_id VARCHAR(50) NOT NULL DEFAULT 'default',
    config_type VARCHAR(50) NOT NULL,
    config_name VARCHAR(100) NOT NULL,
    config_data JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 성과 지표 테이블
CREATE TABLE IF NOT EXISTS performance_metrics (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    trader_id VARCHAR(50) NOT NULL DEFAULT 'default',
    session_id UUID REFERENCES trading_sessions(id),
    metric_date DATE NOT NULL DEFAULT CURRENT_DATE,
    daily_pnl DECIMAL(20, 4) DEFAULT 0,
    weekly_pnl DECIMAL(20, 4) DEFAULT 0,
    monthly_pnl DECIMAL(20, 4) DEFAULT 0,
    cumulative_pnl DECIMAL(20, 4) DEFAULT 0,
    total_trades_today INTEGER DEFAULT 0,
    winning_trades_today INTEGER DEFAULT 0,
    losing_trades_today INTEGER DEFAULT 0,
    win_rate_today DECIMAL(5, 2) DEFAULT 0,
    max_drawdown DECIMAL(5, 4) DEFAULT 0,
    current_drawdown DECIMAL(5, 4) DEFAULT 0,
    consecutive_losses INTEGER DEFAULT 0,
    largest_win DECIMAL(20, 4) DEFAULT 0,
    largest_loss DECIMAL(20, 4) DEFAULT 0,
    account_balance DECIMAL(20, 4) DEFAULT 0,
    available_balance DECIMAL(20, 4) DEFAULT 0,
    allocated_capital DECIMAL(20, 4) DEFAULT 0,
    capital_utilization DECIMAL(5, 2) DEFAULT 0,
    sharpe_ratio DECIMAL(10, 4),
    profit_factor DECIMAL(10, 4),
    recovery_factor DECIMAL(10, 4),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_trades_trader_symbol ON trades(trader_id, symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_positions_trader_active ON positions(trader_id, is_active, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_trader ON risk_events(trader_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(log_level, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_performance_date ON performance_metrics(trader_id, metric_date DESC);
"""