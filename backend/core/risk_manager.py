import logging
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque

class RiskLevel(Enum):
    """리스크 레벨"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class RiskAction(Enum):
    """리스크 대응 액션"""
    CONTINUE = "CONTINUE"           # 거래 계속
    REDUCE_SIZE = "REDUCE_SIZE"     # 포지션 크기 축소
    STOP_NEW = "STOP_NEW"          # 신규 거래 중단
    CLOSE_ALL = "CLOSE_ALL"        # 모든 포지션 청산
    EMERGENCY_STOP = "EMERGENCY_STOP"  # 비상 정지

@dataclass
class RiskConfig:
    """리스크 관리 설정"""
    # 기본 손실 한도
    max_daily_loss_ratio: float = 0.05      # 일일 최대 손실 5%
    max_weekly_loss_ratio: float = 0.15     # 주간 최대 손실 15%
    max_monthly_loss_ratio: float = 0.30    # 월간 최대 손실 30%
    
    # 연속 손실 관리
    max_consecutive_losses: int = 5         # 최대 연속 손실 횟수
    consecutive_loss_threshold: float = 0.02 # 연속 손실 시 개별 손실 임계값 2%
    
    # 드로다운 관리
    max_drawdown_ratio: float = 0.20        # 최대 드로다운 20%
    drawdown_stop_ratio: float = 0.15       # 드로다운 거래 중단 15%
    
    # 포지션 관리
    max_correlation_positions: int = 3      # 상관관계 높은 포지션 최대 개수
    position_concentration_limit: float = 0.40  # 단일 포지션 집중도 한계 40%
    
    # 시간별 제한
    max_trades_per_hour: int = 10           # 시간당 최대 거래 수
    max_trades_per_day: int = 50            # 일일 최대 거래 수
    
    # 휴식 기간
    cool_down_after_loss: int = 30          # 손실 후 휴식 시간 (분)
    cool_down_after_consecutive: int = 60   # 연속 손실 후 휴식 시간 (분)

@dataclass
class TradeRecord:
    """거래 기록"""
    timestamp: datetime
    symbol: str
    side: str
    quantity: float
    price: float
    pnl: Optional[float] = None
    is_loss: bool = False

@dataclass
class RiskStatus:
    """리스크 현황"""
    level: RiskLevel
    action: RiskAction
    daily_pnl: float
    weekly_pnl: float
    monthly_pnl: float
    consecutive_losses: int
    current_drawdown: float
    trades_today: int
    trades_this_hour: int
    last_trade_time: Optional[datetime]
    cool_down_until: Optional[datetime]
    warnings: List[str] = field(default_factory=list)

class RiskManager:
    """
    종합 리스크 관리 시스템
    - 손실 한도 모니터링
    - 연속 손실 방지
    - 드로다운 제어
    - 거래 빈도 제한
    - 자동 리스크 대응
    """
    
    def __init__(self, config: RiskConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 거래 기록 관리
        self.trade_history: deque = deque(maxlen=1000)  # 최근 1000개 거래
        self.daily_trades: deque = deque(maxlen=100)    # 오늘 거래
        self.hourly_trades: deque = deque(maxlen=50)    # 이번 시간 거래
        
        # 상태 추적
        self.initial_balance = 0.0
        self.peak_balance = 0.0
        self.current_balance = 0.0
        
        # 연속 손실 추적
        self.consecutive_losses = 0
        self.last_loss_time: Optional[datetime] = None
        self.cool_down_until: Optional[datetime] = None
        
        # 리스크 상태
        self.current_risk_level = RiskLevel.LOW
        self.is_trading_allowed = True
        
        self.logger.info("리스크 관리자 초기화 완료")
    
    def initialize_balance(self, balance: float) -> None:
        """
        초기 잔고 설정
        
        Args:
            balance (float): 초기 잔고
        """
        self.initial_balance = balance
        self.peak_balance = balance
        self.current_balance = balance
        self.logger.info(f"초기 잔고 설정: ${balance:,.2f}")
    
    def update_balance(self, new_balance: float) -> None:
        """
        현재 잔고 업데이트
        
        Args:
            new_balance (float): 새로운 잔고
        """
        old_balance = self.current_balance
        self.current_balance = new_balance
        
        # 새로운 최고점 기록
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance
            self.logger.info(f"💎 신규 최고 잔고: ${new_balance:,.2f}")
        
        # 잔고 변화 로그
        pnl = new_balance - old_balance
        if pnl != 0:
            self.logger.info(f"잔고 업데이트: ${old_balance:,.2f} → ${new_balance:,.2f} (PnL: ${pnl:+,.2f})")
    
    def record_trade(self, trade_record: TradeRecord) -> None:
        """
        거래 기록 추가
        
        Args:
            trade_record (TradeRecord): 거래 기록
        """
        # 기록 추가
        self.trade_history.append(trade_record)
        
        # 시간별 거래 추가
        now = datetime.now()
        self.daily_trades.append(trade_record)
        self.hourly_trades.append(trade_record)
        
        # 오래된 기록 정리
        self._cleanup_old_records()
        
        # 연속 손실 추적
        if trade_record.is_loss:
            if trade_record.pnl and trade_record.pnl < -abs(self.current_balance * self.config.consecutive_loss_threshold):
                self.consecutive_losses += 1
                self.last_loss_time = trade_record.timestamp
                self.logger.warning(f"⚠️ 연속 손실 {self.consecutive_losses}회")
            else:
                # 소액 손실은 연속 손실로 카운트하지 않음
                pass
        else:
            # 수익이 나면 연속 손실 리셋
            if self.consecutive_losses > 0:
                self.logger.info(f"✅ 연속 손실 종료 (이전: {self.consecutive_losses}회)")
                self.consecutive_losses = 0
                self.last_loss_time = None
        
        self.logger.info(f"거래 기록: {trade_record.symbol} {trade_record.side} ${trade_record.pnl:+.2f}")
    
    def check_trading_allowed(self) -> Tuple[bool, str]:
        """
        거래 허용 여부 체크
        
        Returns:
            Tuple[bool, str]: (허용 여부, 사유)
        """
        now = datetime.now()
        
        # 쿨다운 체크
        if self.cool_down_until and now < self.cool_down_until:
            remaining = (self.cool_down_until - now).total_seconds() / 60
            return False, f"쿨다운 중 (남은 시간: {remaining:.1f}분)"
        
        # 리스크 레벨 체크
        risk_status = self.assess_risk()
        
        if risk_status.action in [RiskAction.STOP_NEW, RiskAction.CLOSE_ALL, RiskAction.EMERGENCY_STOP]:
            return False, f"리스크 레벨: {risk_status.level.value}"
        
        # 거래 빈도 체크
        if risk_status.trades_this_hour >= self.config.max_trades_per_hour:
            return False, "시간당 거래 한도 초과"
        
        if risk_status.trades_today >= self.config.max_trades_per_day:
            return False, "일일 거래 한도 초과"
        
        return True, "거래 허용"
    
    def assess_risk(self) -> RiskStatus:
        """
        종합 리스크 평가
        
        Returns:
            RiskStatus: 리스크 현황
        """
        now = datetime.now()
        
        # 기간별 손익 계산
        daily_pnl = self._calculate_period_pnl(hours=24)
        weekly_pnl = self._calculate_period_pnl(days=7)
        monthly_pnl = self._calculate_period_pnl(days=30)
        
        # 드로다운 계산
        current_drawdown = (self.peak_balance - self.current_balance) / self.peak_balance if self.peak_balance > 0 else 0
        
        # 거래 빈도 계산
        trades_today = self._count_trades_in_period(hours=24)
        trades_this_hour = self._count_trades_in_period(hours=1)
        
        # 경고 메시지 수집
        warnings = []
        
        # 리스크 레벨 결정
        risk_level = RiskLevel.LOW
        action = RiskAction.CONTINUE
        
        # 임계값 체크 및 리스크 레벨 상향 조정
        if current_drawdown >= self.config.max_drawdown_ratio:
            risk_level = RiskLevel.CRITICAL
            action = RiskAction.EMERGENCY_STOP
            warnings.append(f"최대 드로다운 초과: {current_drawdown*100:.1f}%")
            
        elif abs(daily_pnl) >= self.current_balance * self.config.max_daily_loss_ratio:
            risk_level = RiskLevel.HIGH
            action = RiskAction.CLOSE_ALL
            warnings.append(f"일일 손실 한도 초과: ${daily_pnl:.2f}")
            
        elif self.consecutive_losses >= self.config.max_consecutive_losses:
            risk_level = RiskLevel.HIGH
            action = RiskAction.STOP_NEW
            warnings.append(f"연속 손실 {self.consecutive_losses}회")
            self._set_cool_down(self.config.cool_down_after_consecutive)
            
        elif current_drawdown >= self.config.drawdown_stop_ratio:
            risk_level = RiskLevel.MEDIUM
            action = RiskAction.REDUCE_SIZE
            warnings.append(f"드로다운 경고: {current_drawdown*100:.1f}%")
            
        elif abs(weekly_pnl) >= self.current_balance * self.config.max_weekly_loss_ratio * 0.8:  # 80% 도달 시 경고
            risk_level = RiskLevel.MEDIUM
            action = RiskAction.REDUCE_SIZE
            warnings.append(f"주간 손실 경고: ${weekly_pnl:.2f}")
            
        elif self.consecutive_losses >= 3:  # 3연속 손실 시 주의
            risk_level = RiskLevel.MEDIUM
            action = RiskAction.REDUCE_SIZE
            warnings.append(f"연속 손실 주의: {self.consecutive_losses}회")
        
        # 거래 빈도 체크
        if trades_this_hour >= self.config.max_trades_per_hour * 0.9:
            warnings.append(f"시간당 거래 한도 임박: {trades_this_hour}/{self.config.max_trades_per_hour}")
        
        if trades_today >= self.config.max_trades_per_day * 0.9:
            warnings.append(f"일일 거래 한도 임박: {trades_today}/{self.config.max_trades_per_day}")
        
        # 상태 업데이트
        self.current_risk_level = risk_level
        self.is_trading_allowed = action in [RiskAction.CONTINUE, RiskAction.REDUCE_SIZE]
        
        return RiskStatus(
            level=risk_level,
            action=action,
            daily_pnl=daily_pnl,
            weekly_pnl=weekly_pnl,
            monthly_pnl=monthly_pnl,
            consecutive_losses=self.consecutive_losses,
            current_drawdown=current_drawdown * 100,  # 퍼센트로 변환
            trades_today=trades_today,
            trades_this_hour=trades_this_hour,
            last_trade_time=self.trade_history[-1].timestamp if self.trade_history else None,
            cool_down_until=self.cool_down_until,
            warnings=warnings
        )
    
    def get_position_size_multiplier(self) -> float:
        """
        리스크 레벨에 따른 포지션 크기 조정 배수
        
        Returns:
            float: 포지션 크기 배수 (0.1 ~ 1.0)
        """
        risk_status = self.assess_risk()
        
        multipliers = {
            RiskLevel.LOW: 1.0,      # 100%
            RiskLevel.MEDIUM: 0.5,   # 50%
            RiskLevel.HIGH: 0.2,     # 20%
            RiskLevel.CRITICAL: 0.1  # 10%
        }
        
        return multipliers.get(risk_status.level, 0.5)
    
    def should_close_all_positions(self) -> bool:
        """
        모든 포지션 청산 필요 여부
        
        Returns:
            bool: 청산 필요 여부
        """
        risk_status = self.assess_risk()
        return risk_status.action in [RiskAction.CLOSE_ALL, RiskAction.EMERGENCY_STOP]
    
    def get_risk_report(self) -> Dict[str, Any]:
        """
        상세 리스크 리포트 생성
        
        Returns:
            Dict: 리스크 리포트
        """
        risk_status = self.assess_risk()
        
        return {
            'timestamp': datetime.now(),
            'risk_level': risk_status.level.value,
            'recommended_action': risk_status.action.value,
            'trading_allowed': self.is_trading_allowed,
            'balance_info': {
                'initial': self.initial_balance,
                'current': self.current_balance,
                'peak': self.peak_balance,
                'total_pnl': self.current_balance - self.initial_balance,
                'total_pnl_percentage': ((self.current_balance - self.initial_balance) / self.initial_balance * 100) if self.initial_balance > 0 else 0
            },
            'period_pnl': {
                'daily': risk_status.daily_pnl,
                'weekly': risk_status.weekly_pnl,
                'monthly': risk_status.monthly_pnl
            },
            'drawdown': {
                'current': risk_status.current_drawdown,
                'max_allowed': self.config.max_drawdown_ratio * 100
            },
            'consecutive_losses': {
                'current': risk_status.consecutive_losses,
                'max_allowed': self.config.max_consecutive_losses,
                'last_loss_time': self.last_loss_time
            },
            'trading_limits': {
                'trades_today': risk_status.trades_today,
                'max_daily': self.config.max_trades_per_day,
                'trades_this_hour': risk_status.trades_this_hour,
                'max_hourly': self.config.max_trades_per_hour
            },
            'cool_down': {
                'active': self.cool_down_until is not None and datetime.now() < self.cool_down_until,
                'until': self.cool_down_until,
                'remaining_minutes': (self.cool_down_until - datetime.now()).total_seconds() / 60 if self.cool_down_until and datetime.now() < self.cool_down_until else 0
            },
            'warnings': risk_status.warnings,
            'position_size_multiplier': self.get_position_size_multiplier()
        }
    
    def _calculate_period_pnl(self, hours: int = None, days: int = None) -> float:
        """기간별 손익 계산"""
        if days:
            hours = days * 24
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        period_pnl = 0.0
        for trade in self.trade_history:
            if trade.timestamp >= cutoff_time and trade.pnl:
                period_pnl += trade.pnl
        
        return period_pnl
    
    def _count_trades_in_period(self, hours: int = None, days: int = None) -> int:
        """기간별 거래 수 계산"""
        if days:
            hours = days * 24
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        count = 0
        for trade in self.trade_history:
            if trade.timestamp >= cutoff_time:
                count += 1
        
        return count
    
    def _set_cool_down(self, minutes: int) -> None:
        """쿨다운 설정"""
        self.cool_down_until = datetime.now() + timedelta(minutes=minutes)
        self.logger.warning(f"🚫 쿨다운 설정: {minutes}분 ({self.cool_down_until.strftime('%H:%M')}까지)")
    
    def _cleanup_old_records(self) -> None:
        """오래된 거래 기록 정리"""
        now = datetime.now()
        
        # 24시간 이전 기록 제거 (daily_trades)
        self.daily_trades = deque([t for t in self.daily_trades if (now - t.timestamp).total_seconds() < 24 * 3600], maxlen=100)
        
        # 1시간 이전 기록 제거 (hourly_trades)
        self.hourly_trades = deque([t for t in self.hourly_trades if (now - t.timestamp).total_seconds() < 3600], maxlen=50)