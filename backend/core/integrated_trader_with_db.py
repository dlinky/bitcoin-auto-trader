import logging
import time
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, date
from dataclasses import dataclass
import uuid

from backend.api.binance_client import BinanceClient
from backend.core.capital_manager import CapitalManager, CapitalConfig
from backend.core.risk_manager import RiskManager, RiskConfig, TradeRecord, RiskAction
from backend.core.trader import Trader, OrderSide, TradeResult
from backend.database.database_manager import DatabaseManager
from backend.database.models import (
    Trade as DBTrade, Position as DBPosition, TradingSession, 
    RiskEvent, SystemLog, PerformanceMetric
)

@dataclass
class IntegratedTraderConfig:
    """통합 트레이더 설정"""
    symbol: str = "BTCUSDT"
    trader_id: str = "default"
    
    # 자본 관리 설정
    capital_config: CapitalConfig = None
    
    # 리스크 관리 설정
    risk_config: RiskConfig = None
    
    # 거래 설정
    enable_auto_stop_loss: bool = True
    default_stop_loss_ratio: float = 0.05    # 5% 손절
    enable_auto_take_profit: bool = True
    default_take_profit_ratio: float = 0.10  # 10% 익절
    
    # 데이터베이스 설정
    enable_database_logging: bool = True
    auto_save_metrics: bool = True
    metrics_save_interval: int = 3600        # 1시간마다 성과 지표 저장
    
    # 모니터링 설정
    status_update_interval: int = 60         # 상태 업데이트 간격 (초)

class IntegratedTraderWithDB:
    """
    데이터베이스 연동 통합 트레이더
    - 모든 거래 활동 자동 저장
    - 실시간 성과 지표 계산
    - 리스크 이벤트 로깅
    - 거래 세션 관리
    - 시스템 로그 기록
    """
    
    def __init__(self, config: IntegratedTraderConfig, binance_client: BinanceClient, 
                 database_manager: Optional[DatabaseManager] = None):
        """
        데이터베이스 연동 통합 트레이더 초기화
        
        Args:
            config: 설정
            binance_client: 바이낸스 클라이언트
            database_manager: 데이터베이스 매니저 (None이면 자동 생성)
        """
        self.config = config
        self.binance_client = binance_client
        
        # 기본 설정값 적용
        if not config.capital_config:
            config.capital_config = CapitalConfig()
        if not config.risk_config:
            config.risk_config = RiskConfig()
        
        # 핵심 컴포넌트 초기화
        self.capital_manager = CapitalManager(config.capital_config)
        self.risk_manager = RiskManager(config.risk_config)
        self.trader = Trader(config.symbol, binance_client, self.capital_manager)
        
        # 데이터베이스 관리자
        if config.enable_database_logging:
            self.db_manager = database_manager or DatabaseManager()
        else:
            self.db_manager = None
        
        # 상태 관리
        self.is_active = False
        self.is_emergency_stopped = False
        self.current_session_id: Optional[str] = None
        self.current_position_id: Optional[str] = None
        self.last_status_update = datetime.now()
        self.last_metrics_save = datetime.now()
        
        # 세션 통계
        self.session_start_time = None
        self.session_start_balance = 0.0
        self.session_trades_count = 0
        self.session_winning_trades = 0
        self.session_losing_trades = 0
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"데이터베이스 연동 통합 트레이더 초기화 완료: {config.symbol}")
    
    def start(self, session_name: Optional[str] = None) -> bool:
        """
        통합 트레이더 시작 (거래 세션 생성 포함)
        
        Args:
            session_name: 거래 세션 이름
            
        Returns:
            bool: 시작 성공 여부
        """
        try:
            # 바이낸스 연결 확인
            if not self.binance_client.test_connection():
                self.logger.error("바이낸스 API 연결 실패")
                self._log_system_event("ERROR", "STARTUP_FAILED", "바이낸스 API 연결 실패")
                return False
            
            # 계정 정보 조회 및 초기화
            account_info = self.binance_client.get_account_info()
            if not account_info:
                self.logger.error("계정 정보 조회 실패")
                self._log_system_event("ERROR", "STARTUP_FAILED", "계정 정보 조회 실패")
                return False
            
            # 자본 및 리스크 관리자 초기화
            initial_balance = account_info['total_balance']
            self.capital_manager.update_balance(initial_balance)
            self.risk_manager.initialize_balance(initial_balance)
            
            # 트레이더 시작
            if not self.trader.start():
                self.logger.error("트레이더 시작 실패")
                self._log_system_event("ERROR", "STARTUP_FAILED", "트레이더 시작 실패")
                return False
            
            # 거래 세션 시작
            if self.db_manager:
                session_name = session_name or f"AUTO_SESSION_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                self.current_session_id = self._create_trading_session(session_name, initial_balance)
            
            # 상태 업데이트
            self.is_active = True
            self.is_emergency_stopped = False
            self.session_start_time = datetime.now()
            self.session_start_balance = initial_balance
            self.session_trades_count = 0
            self.session_winning_trades = 0
            self.session_losing_trades = 0
            
            self.logger.info(f"🚀 데이터베이스 연동 트레이더 시작 - 초기 잔고: ${initial_balance:,.2f}")
            self._log_system_event("INFO", "TRADER_STARTED", 
                                 f"트레이더 시작 - 세션: {session_name}, 잔고: ${initial_balance:,.2f}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"통합 트레이더 시작 실패: {e}")
            self._log_system_event("ERROR", "STARTUP_FAILED", f"시작 실패: {str(e)}")
            return False
    
    def stop(self, emergency: bool = False, reason: str = "") -> None:
        """
        통합 트레이더 중지 (거래 세션 종료 포함)
        
        Args:
            emergency: 긴급 정지 여부
            reason: 중지 사유
        """
        if emergency:
            self.logger.warning("🚨 긴급 정지 요청")
            self.is_emergency_stopped = True
            
            # 모든 포지션 즉시 청산 시도
            try:
                self.emergency_close_all_positions()
            except Exception as e:
                self.logger.error(f"긴급 청산 실패: {e}")
                self._log_system_event("ERROR", "EMERGENCY_CLOSE_FAILED", f"긴급 청산 실패: {str(e)}")
        
        # 거래 세션 종료
        if self.db_manager and self.current_session_id:
            self._end_trading_session(reason)
        
        # 최종 성과 지표 저장
        if self.db_manager:
            self._save_current_metrics()
        
        self.is_active = False
        self.trader.stop()
        
        self.logger.info(f"⏹️ 데이터베이스 연동 트레이더 중지 {'(긴급)' if emergency else ''}")
        self._log_system_event("INFO", "TRADER_STOPPED", 
                             f"트레이더 중지 - 긴급: {emergency}, 사유: {reason}")
    
    def place_smart_order_with_logging(self, side: OrderSide, 
                                     stop_loss_ratio: Optional[float] = None,
                                     take_profit_ratio: Optional[float] = None,
                                     custom_quantity: Optional[float] = None,
                                     notes: str = "") -> TradeResult:
        """
        스마트 주문 실행 + 데이터베이스 로깅
        
        Args:
            side: 매수/매도
            stop_loss_ratio: 손절 비율
            take_profit_ratio: 익절 비율  
            custom_quantity: 사용자 지정 수량
            notes: 거래 메모
            
        Returns:
            TradeResult: 거래 결과
        """
        if not self.is_active:
            return TradeResult(success=False, error_message="트레이더가 비활성 상태")
        
        if self.is_emergency_stopped:
            return TradeResult(success=False, error_message="긴급 정지 상태")
        
        # 1. 리스크 사전 체크
        risk_check = self._pre_trade_risk_check()
        if not risk_check[0]:
            self._log_system_event("WARNING", "TRADE_BLOCKED", f"리스크 체크 실패: {risk_check[1]}")
            return TradeResult(success=False, error_message=f"리스크 체크 실패: {risk_check[1]}")
        
        # 2. 현재가 조회
        current_price = self.binance_client.get_symbol_price(self.config.symbol)
        if not current_price:
            self._log_system_event("ERROR", "PRICE_FETCH_FAILED", "현재가 조회 실패")
            return TradeResult(success=False, error_message="현재가 조회 실패")
        
        # 3. 포지션 크기 계산 (리스크 기반)
        if custom_quantity is None:
            quantity = self._calculate_smart_position_size(current_price, side, stop_loss_ratio)
            if quantity <= 0:
                self._log_system_event("WARNING", "POSITION_SIZE_ZERO", "계산된 포지션 크기가 0 이하")
                return TradeResult(success=False, error_message="계산된 포지션 크기가 0 이하")
        else:
            quantity = custom_quantity
        
        # 4. 손절/익절 가격 계산
        stop_loss_price, take_profit_price = self._calculate_stop_prices(
            current_price, side, stop_loss_ratio, take_profit_ratio
        )
        
        # 5. 데이터베이스에 거래 기록 사전 저장 (PENDING 상태)
        trade_id = None
        if self.db_manager:
            db_trade = DBTrade(
                trader_id=self.config.trader_id,
                symbol=self.config.symbol,
                side=side.value,
                order_type="MARKET",
                quantity=quantity,
                price=current_price,
                status="PENDING",
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                notes=notes
            )
            trade_id = self.db_manager.save_trade(db_trade)
        
        # 6. 주문 실행
        self.logger.info(f"📊 스마트 주문 실행: {side.value} {quantity:.6f} @ ${current_price:,.2f}")
        if stop_loss_price:
            self.logger.info(f"   🛑 손절가: ${stop_loss_price:,.2f}")
        if take_profit_price:
            self.logger.info(f"   🎯 익절가: ${take_profit_price:,.2f}")
        
        result = self.trader.place_market_order(
            side=side,
            quantity=quantity,
            stop_loss=stop_loss_price,
            take_profit=take_profit_price
        )
        
        # 7. 거래 결과 업데이트 및 기록
        if result.success:
            # 데이터베이스 거래 기록 업데이트
            if self.db_manager and trade_id:
                self.db_manager.update_trade(trade_id, {
                    'status': 'FILLED',
                    'executed_quantity': result.quantity,
                    'executed_price': result.price,
                    'binance_order_id': result.order_id
                })
            
            # 세션 통계 업데이트
            self.session_trades_count += 1
            
            # 포지션 기록 저장
            self._save_current_position()
            
            # 리스크 관리자에 기록
            trade_record = TradeRecord(
                timestamp=result.timestamp or datetime.now(),
                symbol=result.symbol,
                side=result.side,
                quantity=result.quantity,
                price=result.price,
                pnl=0.0  # 진입 시에는 0
            )
            self.risk_manager.record_trade(trade_record)
            
            self.logger.info(f"✅ 스마트 주문 성공: {result.order_id}")
            self._log_system_event("INFO", "TRADE_SUCCESS", 
                                 f"거래 성공: {side.value} {quantity:.6f} @ ${result.price:.2f}")
            
        else:
            # 실패 시 데이터베이스 기록 업데이트
            if self.db_manager and trade_id:
                self.db_manager.update_trade(trade_id, {
                    'status': 'REJECTED',
                    'notes': f"{notes} - 실패: {result.error_message}"
                })
            
            self.logger.error(f"❌ 스마트 주문 실패: {result.error_message}")
            self._log_system_event("ERROR", "TRADE_FAILED", f"거래 실패: {result.error_message}")
        
        # 8. 사후 리스크 체크
        self._post_trade_risk_check()
        
        return result
    
    def close_position_with_logging(self, percentage: float = 100.0, 
                                   reason: str = "", notes: str = "") -> TradeResult:
        """
        스마트 포지션 청산 + 손익 기록
        
        Args:
            percentage: 청산 비율
            reason: 청산 사유
            notes: 메모
            
        Returns:
            TradeResult: 거래 결과
        """
        # 현재 포지션 확인
        current_position = self.trader.get_current_position()
        if not current_position:
            return TradeResult(success=False, error_message="청산할 포지션이 없습니다")
        
        # 청산 전 손익 계산
        unrealized_pnl = current_position.unrealized_pnl
        
        # 청산 실행
        result = self.trader.close_position(percentage)
        
        # 손익 기록 (리스크 관리 + 데이터베이스)
        if result.success:
            # 청산 비율에 따른 실제 손익 계산
            actual_pnl = unrealized_pnl * (percentage / 100.0)
            
            # 리스크 관리자에 기록
            trade_record = TradeRecord(
                timestamp=result.timestamp or datetime.now(),
                symbol=result.symbol,
                side=result.side,
                quantity=result.quantity,
                price=result.price,
                pnl=actual_pnl,
                is_loss=actual_pnl < 0
            )
            self.risk_manager.record_trade(trade_record)
            
            # 데이터베이스에 청산 거래 기록
            if self.db_manager:
                db_trade = DBTrade(
                    trader_id=self.config.trader_id,
                    symbol=self.config.symbol,
                    side=result.side,
                    order_type="MARKET",
                    quantity=result.quantity,
                    price=result.price,
                    executed_quantity=result.quantity,
                    executed_price=result.price,
                    status="FILLED",
                    binance_order_id=result.order_id,
                    notes=f"포지션 청산 ({percentage:.1f}%) - {reason} - {notes}"
                )
                self.db_manager.save_trade(db_trade)
            
            # 포지션 상태 업데이트
            if self.current_position_id and percentage == 100.0:
                # 완전 청산인 경우 포지션 비활성화
                if self.db_manager:
                    self.db_manager.update_position(self.current_position_id, {
                        'is_active': False,
                        'closed_at': datetime.now().isoformat(),
                        'realized_pnl': actual_pnl
                    })
                self.current_position_id = None
            
            # 세션 통계 업데이트
            if actual_pnl > 0:
                self.session_winning_trades += 1
            else:
                self.session_losing_trades += 1
            
            # 잔고 업데이트
            account_info = self.binance_client.get_account_info()
            if account_info:
                self.capital_manager.update_balance(account_info['total_balance'])
                self.risk_manager.update_balance(account_info['total_balance'])
            
            self.logger.info(f"💰 포지션 청산 완료: PnL ${actual_pnl:+,.2f} ({reason})")
            self._log_system_event("INFO", "POSITION_CLOSED", 
                                 f"포지션 청산: {percentage:.1f}%, PnL ${actual_pnl:+,.2f}, 사유: {reason}")
        
        # 사후 리스크 체크
        self._post_trade_risk_check()
        
        return result
    
    def monitor_and_auto_respond_with_logging(self) -> None:
        """
        모니터링 및 자동 대응 + 데이터베이스 로깅
        """
        if not self.is_active:
            return
        
        try:
            # 리스크 평가
            risk_status = self.risk_manager.assess_risk()
            
            # 자동 대응 실행 + 로깅
            if risk_status.action == RiskAction.EMERGENCY_STOP:
                self.logger.critical("🚨 리스크 매니저 긴급 정지 신호")
                self._log_risk_event("EMERGENCY_STOP", risk_status, "리스크 매니저 긴급 정지 신호")
                self.stop(emergency=True, reason="자동 긴급 정지")
                
            elif risk_status.action == RiskAction.CLOSE_ALL:
                self.logger.warning("⚠️ 리스크 매니저 전체 청산 권고")
                self._log_risk_event("CLOSE_ALL_TRIGGERED", risk_status, "전체 청산 권고")
                if self.risk_manager.should_close_all_positions():
                    self.close_position_with_logging(100.0, "자동 리스크 청산", "리스크 한도 초과")
                    
            elif risk_status.action == RiskAction.STOP_NEW:
                self.logger.warning("⚠️ 신규 거래 중단 권고")
                self._log_risk_event("NEW_TRADES_STOPPED", risk_status, "신규 거래 중단")
            
            # 정기적 성과 지표 저장
            now = datetime.now()
            if (now - self.last_metrics_save).total_seconds() >= self.config.metrics_save_interval:
                self._save_current_metrics()
                self.last_metrics_save = now
            
            # 상태 업데이트
            if (now - self.last_status_update).total_seconds() >= self.config.status_update_interval:
                self._log_status_summary()
                self.last_status_update = now
                
        except Exception as e:
            self.logger.error(f"모니터링 중 오류: {e}")
            self._log_system_event("ERROR", "MONITORING_ERROR", f"모니터링 오류: {str(e)}")
    
    def get_comprehensive_status_with_db(self) -> Dict[str, Any]:
        """
        데이터베이스 정보를 포함한 종합 상태 조회
        
        Returns:
            Dict: 종합 상태 정보
        """
        # 기본 상태 정보
        trader_status = self.trader.get_trading_status()
        risk_report = self.risk_manager.get_risk_report()
        capital_status = self.capital_manager.get_capital_status()
        
        # 데이터베이스 통계
        db_stats = {}
        if self.db_manager:
            db_stats = {
                'recent_trades': len(self.db_manager.get_trades(self.config.trader_id, limit=10)),
                'active_positions': len(self.db_manager.get_active_positions(self.config.trader_id)),
                'session_id': self.current_session_id,
                'trading_statistics': self.db_manager.get_trading_statistics(self.config.trader_id, days=7),
                'performance_summary': self.db_manager.get_performance_summary(self.config.trader_id, days=30)
            }
        
        # 세션 통계
        session_stats = {
            'session_id': self.current_session_id,
            'start_time': self.session_start_time,
            'start_balance': self.session_start_balance,
            'current_balance': risk_report['balance_info']['current'],
            'session_pnl': risk_report['balance_info']['current'] - self.session_start_balance,
            'total_trades': self.session_trades_count,
            'winning_trades': self.session_winning_trades,
            'losing_trades': self.session_losing_trades,
            'win_rate': (self.session_winning_trades / max(1, self.session_trades_count)) * 100
        }
        
        # 통합 상태 정보
        comprehensive_status = {
            'timestamp': datetime.now(),
            'system_status': {
                'active': self.is_active,
                'emergency_stopped': self.is_emergency_stopped,
                'trading_allowed': self.is_active and not self.is_emergency_stopped,
                'database_enabled': self.db_manager is not None,
            },
            'trader': trader_status,
            'risk_management': risk_report,
            'capital_management': capital_status,
            'session_statistics': session_stats,
            'database_statistics': db_stats,
            'recommendations': self._get_recommendations(),
        }
        
        return comprehensive_status
    
    # ========== 내부 유틸리티 메서드 ==========
    
    def _create_trading_session(self, session_name: str, start_balance: float) -> Optional[str]:
        """거래 세션 생성"""
        if not self.db_manager:
            return None
        
        session = TradingSession(
            trader_id=self.config.trader_id,
            session_name=session_name,
            symbol=self.config.symbol,
            start_balance=start_balance,
            current_balance=start_balance,
            peak_balance=start_balance,
            total_pnl=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            max_drawdown=0.0,
            is_active=True,
            notes="자동 생성된 거래 세션"
        )
        
        session_id = self.db_manager.create_trading_session(session)
        self.logger.info(f"거래 세션 생성: {session_name} ({session_id})")
        return session_id
    
    def _end_trading_session(self, reason: str) -> None:
        """거래 세션 종료"""
        if not self.db_manager or not self.current_session_id:
            return
        
        current_balance = self.risk_manager.current_balance
        total_pnl = current_balance - self.session_start_balance
        win_rate = (self.session_winning_trades / max(1, self.session_trades_count)) * 100
        
        final_stats = {
            'current_balance': current_balance,
            'total_pnl': total_pnl,
            'total_trades': self.session_trades_count,
            'winning_trades': self.session_winning_trades,
            'losing_trades': self.session_losing_trades,
            'win_rate': win_rate,
            'notes': f"세션 종료 - {reason}"
        }
        
        self.db_manager.end_trading_session(self.current_session_id, final_stats)
        self.logger.info(f"거래 세션 종료: {self.current_session_id} - {reason}")
        self.current_session_id = None
    
    def _save_current_position(self) -> Optional[str]:
        """현재 포지션 데이터베이스 저장"""
        if not self.db_manager:
            return None
        
        position = self.trader.get_current_position()
        if not position:
            return None
        
        db_position = DBPosition(
            trader_id=self.config.trader_id,
            symbol=position.symbol,
            side=position.side,
            size=position.size,
            entry_price=position.entry_price,
            mark_price=position.mark_price,
            unrealized_pnl=position.unrealized_pnl,
            percentage=position.percentage,
            notional=position.notional,
            is_active=True
        )
        
        if self.current_position_id:
            # 기존 포지션 업데이트
            updates = {
                'mark_price': position.mark_price,
                'unrealized_pnl': position.unrealized_pnl,
                'percentage': position.percentage,
                'notional': position.notional
            }
            self.db_manager.update_position(self.current_position_id, updates)
            return self.current_position_id
        else:
            # 새 포지션 생성
            position_id = self.db_manager.save_position(db_position)
            self.current_position_id = position_id
            return position_id
    
    def _log_risk_event(self, event_type: str, risk_status, description: str) -> None:
        """리스크 이벤트 로깅"""
        if not self.db_manager:
            return
        
        risk_event = RiskEvent(
            trader_id=self.config.trader_id,
            session_id=self.current_session_id,
            event_type=event_type,
            risk_level=risk_status.level.value,
            triggered_by="AUTO_RISK_MANAGER",
            trigger_value=risk_status.current_drawdown if hasattr(risk_status, 'current_drawdown') else 0.0,
            threshold_value=self.config.risk_config.max_drawdown_ratio * 100,
            action_taken=risk_status.action.value,
            description=description
        )
        
        self.db_manager.log_risk_event(risk_event)
    
    def _log_system_event(self, level: str, event: str, message: str, data: Optional[Dict] = None) -> None:
        """시스템 로그 기록"""
        if not self.db_manager:
            return
        
        log = SystemLog(
            trader_id=self.config.trader_id,
            log_level=level,
            component="INTEGRATED_TRADER_DB",
            event=event,
            message=message,
            data=data
        )
        
        self.db_manager.log_system_event(log)
    
    def _save_current_metrics(self) -> None:
        """현재 성과 지표 저장"""
        if not self.db_manager:
            return
        
        try:
            risk_report = self.risk_manager.get_risk_report()
            capital_status = self.capital_manager.get_capital_status()
            
            metrics = PerformanceMetric(
                trader_id=self.config.trader_id,
                session_id=self.current_session_id,
                metric_date=datetime.now(),
                daily_pnl=risk_report['period_pnl']['daily'],
                weekly_pnl=risk_report['period_pnl']['weekly'],
                monthly_pnl=risk_report['period_pnl']['monthly'],
                cumulative_pnl=risk_report['balance_info']['total_pnl'],
                total_trades_today=self.session_trades_count,
                winning_trades_today=self.session_winning_trades,
                losing_trades_today=self.session_losing_trades,
                win_rate_today=(self.session_winning_trades / max(1, self.session_trades_count)) * 100,
                max_drawdown=risk_report['drawdown']['current'] / 100,  # 비율로 변환
                current_drawdown=risk_report['drawdown']['current'] / 100,
                consecutive_losses=risk_report['consecutive_losses']['current'],
                account_balance=risk_report['balance_info']['current'],
                available_balance=capital_status['available_capital'],
                allocated_capital=capital_status['allocated_capital'],
                capital_utilization=capital_status['utilization_ratio']
            )
            
            self.db_manager.save_daily_metrics(metrics)
            self.logger.info("성과 지표 저장 완료")
            
        except Exception as e:
            self.logger.error(f"성과 지표 저장 실패: {e}")
    
    def _pre_trade_risk_check(self) -> Tuple[bool, str]:
        """거래 전 리스크 체크"""
        # 거래 허용 여부 확인
        allowed, reason = self.risk_manager.check_trading_allowed()
        if not allowed:
            return False, reason
        
        # 리스크 평가
        risk_status = self.risk_manager.assess_risk()
        if risk_status.action in [RiskAction.STOP_NEW, RiskAction.CLOSE_ALL, RiskAction.EMERGENCY_STOP]:
            return False, f"리스크 레벨: {risk_status.level.value}"
        
        return True, "거래 허용"
    
    def _post_trade_risk_check(self) -> None:
        """거래 후 리스크 체크"""
        risk_status = self.risk_manager.assess_risk()
        
        if risk_status.warnings:
            for warning in risk_status.warnings:
                self.logger.warning(f"⚠️ 리스크 경고: {warning}")
                # 경고 이벤트 로깅
                self._log_risk_event("RISK_WARNING", risk_status, warning)
    
    def _calculate_smart_position_size(self, current_price: float, side: OrderSide, 
                                     stop_loss_ratio: Optional[float]) -> float:
        """스마트 포지션 크기 계산"""
        # 기본 포지션 크기 계산 (자본 관리)
        stop_loss_price = None
        if stop_loss_ratio:
            if side == OrderSide.BUY:
                stop_loss_price = current_price * (1 - stop_loss_ratio)
            else:
                stop_loss_price = current_price * (1 + stop_loss_ratio)
        
        position_info = self.capital_manager.calculate_position_size(
            self.config.symbol, current_price, stop_loss_price
        )
        
        base_size = position_info['size']
        
        # 리스크 레벨에 따른 크기 조정
        risk_multiplier = self.risk_manager.get_position_size_multiplier()
        
        adjusted_size = base_size * risk_multiplier
        
        self.logger.info(f"포지션 크기 계산: {base_size:.6f} × {risk_multiplier:.1f} = {adjusted_size:.6f}")
        
        return adjusted_size
    
    def _calculate_stop_prices(self, current_price: float, side: OrderSide,
                             stop_loss_ratio: Optional[float], 
                             take_profit_ratio: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
        """손절/익절 가격 계산"""
        stop_loss_price = None
        take_profit_price = None
        
        if self.config.enable_auto_stop_loss:
            sl_ratio = stop_loss_ratio or self.config.default_stop_loss_ratio
            if side == OrderSide.BUY:
                stop_loss_price = current_price * (1 - sl_ratio)
            else:
                stop_loss_price = current_price * (1 + sl_ratio)
        
        if self.config.enable_auto_take_profit:
            tp_ratio = take_profit_ratio or self.config.default_take_profit_ratio
            if side == OrderSide.BUY:
                take_profit_price = current_price * (1 + tp_ratio)
            else:
                take_profit_price = current_price * (1 - tp_ratio)
        
        return stop_loss_price, take_profit_price
    
    def _get_recommendations(self) -> List[str]:
        """현재 상황에 대한 권고사항"""
        recommendations = []
        
        risk_status = self.risk_manager.assess_risk()
        capital_status = self.capital_manager.get_capital_status()
        
        # 리스크 기반 권고
        if risk_status.level.value == "HIGH":
            recommendations.append("높은 리스크 상태 - 신규 거래 자제 권장")
        elif risk_status.level.value == "MEDIUM":
            recommendations.append("중간 리스크 상태 - 포지션 크기 축소 권장")
        
        # 자본 사용률 기반 권고
        if capital_status['utilization_ratio'] > 80:
            recommendations.append("자본 사용률 높음 - 추가 투입 신중히 고려")
        elif capital_status['utilization_ratio'] < 20:
            recommendations.append("자본 사용률 낮음 - 기회 포착 시 적극 투자 가능")
        
        # 연속 손실 기반 권고
        if risk_status.consecutive_losses >= 3:
            recommendations.append("연속 손실 발생 - 전략 재검토 및 휴식 고려")
        
        # 세션 통계 기반 권고
        if self.session_trades_count > 0:
            session_win_rate = (self.session_winning_trades / self.session_trades_count) * 100
            if session_win_rate < 40:
                recommendations.append("세션 승률 낮음 - 전략 점검 필요")
            elif session_win_rate > 70:
                recommendations.append("세션 성과 양호 - 현재 전략 유지")
        
        return recommendations
    
    def _log_status_summary(self) -> None:
        """상태 요약 로그"""
        try:
            status = self.get_comprehensive_status_with_db()
            risk = status['risk_management']
            capital = status['capital_management']
            session = status['session_statistics']
            
            self.logger.info(f"📊 상태 요약:")
            self.logger.info(f"   잔고: ${risk['balance_info']['current']:,.2f}")
            self.logger.info(f"   세션 손익: ${session['session_pnl']:+,.2f}")
            self.logger.info(f"   세션 거래: {session['total_trades']}회 (승률: {session['win_rate']:.1f}%)")
            self.logger.info(f"   리스크: {risk['risk_level']}")
            self.logger.info(f"   자본 사용률: {capital['utilization_ratio']:.1f}%")
            
            # 시스템 로그로도 기록
            self._log_system_event("INFO", "STATUS_SUMMARY", "정기 상태 요약", {
                'balance': risk['balance_info']['current'],
                'session_pnl': session['session_pnl'],
                'session_trades': session['total_trades'],
                'win_rate': session['win_rate'],
                'risk_level': risk['risk_level']
            })
            
        except Exception as e:
            self.logger.error(f"상태 요약 로그 실패: {e}")
    
    def emergency_close_all_positions(self) -> bool:
        """
        모든 포지션 긴급 청산
        
        Returns:
            bool: 청산 성공 여부
        """
        try:
            self.logger.warning("🚨 모든 포지션 긴급 청산 시작")
            self._log_system_event("WARNING", "EMERGENCY_CLOSE_START", "모든 포지션 긴급 청산 시작")
            
            # 현재 포지션 확인
            position = self.trader.get_current_position()
            if not position:
                self.logger.info("청산할 포지션이 없습니다")
                return True
            
            # 모든 미결 주문 취소 시도
            try:
                self.binance_client.client.futures_cancel_all_open_orders(symbol=self.config.symbol)
                self.logger.info("모든 미결 주문 취소 완료")
            except Exception as e:
                self.logger.warning(f"미결 주문 취소 실패: {e}")
            
            # 포지션 청산
            result = self.close_position_with_logging(100.0, "긴급 청산", "시스템 긴급 정지")
            
            if result.success:
                self.logger.info("✅ 긴급 청산 완료")
                self._log_system_event("INFO", "EMERGENCY_CLOSE_SUCCESS", "긴급 청산 성공")
                return True
            else:
                self.logger.error(f"❌ 긴급 청산 실패: {result.error_message}")
                self._log_system_event("ERROR", "EMERGENCY_CLOSE_FAILED", f"긴급 청산 실패: {result.error_message}")
                return False
                
        except Exception as e:
            self.logger.error(f"긴급 청산 중 오류: {e}")
            self._log_system_event("ERROR", "EMERGENCY_CLOSE_ERROR", f"긴급 청산 오류: {str(e)}")
            return False
    
    def get_database_statistics(self) -> Dict[str, Any]:
        """데이터베이스 통계 조회"""
        if not self.db_manager:
            return {'error': '데이터베이스가 비활성화되어 있습니다'}
        
        try:
            return {
                'health': self.db_manager.health_check(),
                'trading_stats': self.db_manager.get_trading_statistics(self.config.trader_id, days=30),
                'performance_summary': self.db_manager.get_performance_summary(self.config.trader_id, days=30),
                'recent_trades': self.db_manager.get_trades(self.config.trader_id, limit=10),
                'active_positions': self.db_manager.get_active_positions(self.config.trader_id),
                'recent_risk_events': self.db_manager.get_recent_risk_events(self.config.trader_id, hours=24)
            }
            
        except Exception as e:
            return {'error': f'데이터베이스 통계 조회 실패: {str(e)}'}
    
    def export_session_report(self) -> Dict[str, Any]:
        """세션 리포트 생성 및 내보내기"""
        if not self.db_manager or not self.current_session_id:
            return {'error': '활성 세션이 없습니다'}
        
        try:
            # 세션 기간 동안의 모든 데이터 수집
            session_trades = self.db_manager.get_trades(
                self.config.trader_id, 
                start_date=self.session_start_time,
                end_date=datetime.now()
            )
            
            session_risk_events = self.db_manager.get_recent_risk_events(
                self.config.trader_id, 
                hours=int((datetime.now() - self.session_start_time).total_seconds() / 3600)
            )
            
            # 세션 요약
            current_balance = self.risk_manager.current_balance
            total_pnl = current_balance - self.session_start_balance
            
            report = {
                'session_info': {
                    'session_id': self.current_session_id,
                    'start_time': self.session_start_time,
                    'duration_hours': (datetime.now() - self.session_start_time).total_seconds() / 3600,
                    'symbol': self.config.symbol
                },
                'performance': {
                    'start_balance': self.session_start_balance,
                    'current_balance': current_balance,
                    'total_pnl': total_pnl,
                    'pnl_percentage': (total_pnl / self.session_start_balance) * 100,
                    'total_trades': self.session_trades_count,
                    'winning_trades': self.session_winning_trades,
                    'losing_trades': self.session_losing_trades,
                    'win_rate': (self.session_winning_trades / max(1, self.session_trades_count)) * 100
                },
                'trades': session_trades,
                'risk_events': session_risk_events,
                'final_status': self.get_comprehensive_status_with_db(),
                'generated_at': datetime.now()
            }
            
            # 시스템 로그에 리포트 생성 기록
            self._log_system_event("INFO", "SESSION_REPORT_GENERATED", 
                                 f"세션 리포트 생성: {len(session_trades)}개 거래, PnL ${total_pnl:+.2f}")
            
            return report
            
        except Exception as e:
            error_msg = f"세션 리포트 생성 실패: {str(e)}"
            self._log_system_event("ERROR", "SESSION_REPORT_FAILED", error_msg)
            return {'error': error_msg}