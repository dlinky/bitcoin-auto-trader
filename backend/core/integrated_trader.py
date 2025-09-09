import logging
import time
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
from dataclasses import dataclass

from backend.api.binance_client import BinanceClient
from backend.core.capital_manager import CapitalManager, CapitalConfig
from backend.core.risk_manager import RiskManager, RiskConfig, TradeRecord, RiskAction
from backend.core.trader import Trader, OrderSide, TradeResult

@dataclass
class IntegratedTraderConfig:
    """통합 트레이더 설정"""
    symbol: str = "BTCUSDT"
    
    # 자본 관리 설정
    capital_config: CapitalConfig = None
    
    # 리스크 관리 설정
    risk_config: RiskConfig = None
    
    # 거래 설정
    enable_auto_stop_loss: bool = True
    default_stop_loss_ratio: float = 0.05    # 5% 손절
    enable_auto_take_profit: bool = True
    default_take_profit_ratio: float = 0.10  # 10% 익절
    
    # 모니터링 설정
    status_update_interval: int = 60         # 상태 업데이트 간격 (초)

class IntegratedTrader:
    """
    트레이더 + 자본관리 + 리스크관리 통합 시스템
    - 안전한 자동매매 실행
    - 실시간 리스크 모니터링
    - 자동 포지션 크기 조정
    - 긴급 상황 대응
    """
    
    def __init__(self, config: IntegratedTraderConfig, binance_client: BinanceClient):
        """
        통합 트레이더 초기화
        
        Args:
            config (IntegratedTraderConfig): 설정
            binance_client (BinanceClient): 바이낸스 클라이언트
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
        
        # 상태 관리
        self.is_active = False
        self.is_emergency_stopped = False
        self.last_status_update = datetime.now()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"통합 트레이더 초기화 완료: {config.symbol}")
    
    def start(self) -> bool:
        """
        통합 트레이더 시작
        
        Returns:
            bool: 시작 성공 여부
        """
        try:
            # 바이낸스 연결 확인
            if not self.binance_client.test_connection():
                self.logger.error("바이낸스 API 연결 실패")
                return False
            
            # 계정 정보 조회 및 초기화
            account_info = self.binance_client.get_account_info()
            if not account_info:
                self.logger.error("계정 정보 조회 실패")
                return False
            
            # 자본 및 리스크 관리자 초기화
            initial_balance = account_info['total_balance']
            self.capital_manager.update_balance(initial_balance)
            self.risk_manager.initialize_balance(initial_balance)
            
            # 트레이더 시작
            if not self.trader.start():
                self.logger.error("트레이더 시작 실패")
                return False
            
            self.is_active = True
            self.is_emergency_stopped = False
            
            self.logger.info(f"🚀 통합 트레이더 시작 - 초기 잔고: ${initial_balance:,.2f}")
            return True
            
        except Exception as e:
            self.logger.error(f"통합 트레이더 시작 실패: {e}")
            return False
    
    def stop(self, emergency: bool = False) -> None:
        """
        통합 트레이더 중지
        
        Args:
            emergency (bool): 긴급 정지 여부
        """
        if emergency:
            self.logger.warning("🚨 긴급 정지 요청")
            self.is_emergency_stopped = True
            
            # 모든 포지션 즉시 청산 시도
            try:
                self.emergency_close_all_positions()
            except Exception as e:
                self.logger.error(f"긴급 청산 실패: {e}")
        
        self.is_active = False
        self.trader.stop()
        
        self.logger.info(f"⏹️ 통합 트레이더 중지 {'(긴급)' if emergency else ''}")
    
    def place_smart_order(self, side: OrderSide, 
                         stop_loss_ratio: Optional[float] = None,
                         take_profit_ratio: Optional[float] = None,
                         custom_quantity: Optional[float] = None) -> TradeResult:
        """
        스마트 주문 실행 (리스크 관리 통합)
        
        Args:
            side (OrderSide): 매수/매도
            stop_loss_ratio (Optional[float]): 손절 비율 (기본값 사용 시 None)
            take_profit_ratio (Optional[float]): 익절 비율 (기본값 사용 시 None)
            custom_quantity (Optional[float]): 사용자 지정 수량 (None이면 자동 계산)
            
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
            return TradeResult(success=False, error_message=f"리스크 체크 실패: {risk_check[1]}")
        
        # 2. 현재가 조회
        current_price = self.binance_client.get_symbol_price(self.config.symbol)
        if not current_price:
            return TradeResult(success=False, error_message="현재가 조회 실패")
        
        # 3. 포지션 크기 계산 (리스크 기반)
        if custom_quantity is None:
            quantity = self._calculate_smart_position_size(current_price, side, stop_loss_ratio)
            if quantity <= 0:
                return TradeResult(success=False, error_message="계산된 포지션 크기가 0 이하")
        else:
            quantity = custom_quantity
        
        # 4. 손절/익절 가격 계산
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
        
        # 5. 주문 실행
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
        
        # 6. 거래 결과 기록 (리스크 관리)
        if result.success:
            trade_record = TradeRecord(
                timestamp=result.timestamp or datetime.now(),
                symbol=result.symbol,
                side=result.side,
                quantity=result.quantity,
                price=result.price,
                pnl=0.0  # 진입 시에는 0, 청산 시에 실제 손익 기록
            )
            self.risk_manager.record_trade(trade_record)
            
            self.logger.info(f"✅ 스마트 주문 성공: {result.order_id}")
        else:
            self.logger.error(f"❌ 스마트 주문 실패: {result.error_message}")
        
        # 7. 사후 리스크 체크
        self._post_trade_risk_check()
        
        return result
    
    def close_position_smart(self, percentage: float = 100.0, 
                           record_pnl: bool = True) -> TradeResult:
        """
        스마트 포지션 청산 (손익 기록 포함)
        
        Args:
            percentage (float): 청산 비율
            record_pnl (bool): 손익 기록 여부
            
        Returns:
            TradeResult: 거래 결과
        """
        # 현재 포지션 확인
        current_position = self.trader.get_current_position()
        if not current_position:
            return TradeResult(success=False, error_message="청산할 포지션이 없습니다")
        
        # 청산 전 손익 계산
        unrealized_pnl = current_position.unrealized_pnl if record_pnl else 0.0
        
        # 청산 실행
        result = self.trader.close_position(percentage)
        
        # 손익 기록 (리스크 관리)
        if result.success and record_pnl:
            # 청산 비율에 따른 손익 계산
            actual_pnl = unrealized_pnl * (percentage / 100.0)
            
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
            
            # 잔고 업데이트
            account_info = self.binance_client.get_account_info()
            if account_info:
                self.capital_manager.update_balance(account_info['total_balance'])
                self.risk_manager.update_balance(account_info['total_balance'])
            
            self.logger.info(f"💰 포지션 청산 완료: PnL ${actual_pnl:+,.2f}")
        
        # 사후 리스크 체크
        self._post_trade_risk_check()
        
        return result
    
    def emergency_close_all_positions(self) -> bool:
        """
        모든 포지션 긴급 청산
        
        Returns:
            bool: 청산 성공 여부
        """
        try:
            self.logger.warning("🚨 모든 포지션 긴급 청산 시작")
            
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
            result = self.close_position_smart(100.0, record_pnl=True)
            
            if result.success:
                self.logger.info("✅ 긴급 청산 완료")
                return True
            else:
                self.logger.error(f"❌ 긴급 청산 실패: {result.error_message}")
                return False
                
        except Exception as e:
            self.logger.error(f"긴급 청산 중 오류: {e}")
            return False
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """
        종합 상태 정보 조회
        
        Returns:
            Dict: 종합 상태 정보
        """
        # 기본 상태 정보
        trader_status = self.trader.get_trading_status()
        risk_report = self.risk_manager.get_risk_report()
        capital_status = self.capital_manager.get_capital_status()
        
        # 통합 상태 정보
        comprehensive_status = {
            'timestamp': datetime.now(),
            'system_status': {
                'active': self.is_active,
                'emergency_stopped': self.is_emergency_stopped,
                'trading_allowed': self.is_active and not self.is_emergency_stopped,
            },
            'trader': trader_status,
            'risk_management': risk_report,
            'capital_management': capital_status,
            'recommendations': self._get_recommendations(),
        }
        
        return comprehensive_status
    
    def monitor_and_auto_respond(self) -> None:
        """
        모니터링 및 자동 대응
        (주기적으로 호출되어야 함)
        """
        if not self.is_active:
            return
        
        try:
            # 리스크 평가
            risk_status = self.risk_manager.assess_risk()
            
            # 자동 대응 실행
            if risk_status.action == RiskAction.EMERGENCY_STOP:
                self.logger.critical("🚨 리스크 매니저 긴급 정지 신호")
                self.stop(emergency=True)
                
            elif risk_status.action == RiskAction.CLOSE_ALL:
                self.logger.warning("⚠️ 리스크 매니저 전체 청산 권고")
                if self.risk_manager.should_close_all_positions():
                    self.close_position_smart(100.0)
                    
            elif risk_status.action == RiskAction.STOP_NEW:
                self.logger.warning("⚠️ 신규 거래 중단 권고")
                # 신규 거래는 place_smart_order에서 자동으로 차단됨
            
            # 상태 업데이트
            now = datetime.now()
            if (now - self.last_status_update).total_seconds() >= self.config.status_update_interval:
                self._log_status_summary()
                self.last_status_update = now
                
        except Exception as e:
            self.logger.error(f"모니터링 중 오류: {e}")
    
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
        
        return recommendations
    
    def _log_status_summary(self) -> None:
        """상태 요약 로그"""
        try:
            status = self.get_comprehensive_status()
            risk = status['risk_management']
            capital = status['capital_management']
            
            self.logger.info(f"📊 상태 요약:")
            self.logger.info(f"   잔고: ${risk['balance_info']['current']:,.2f}")
            self.logger.info(f"   일일 손익: ${risk['period_pnl']['daily']:+,.2f}")
            self.logger.info(f"   리스크: {risk['risk_level']}")
            self.logger.info(f"   자본 사용률: {capital['utilization_ratio']:.1f}%")
            
        except Exception as e:
            self.logger.error(f"상태 요약 로그 실패: {e}")