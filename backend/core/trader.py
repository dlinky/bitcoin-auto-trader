import logging
import time
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime

from backend.api.binance_client import BinanceClient
from backend.core.capital_manager import CapitalManager, CapitalConfig

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

class PositionSide(Enum):
    """포지션 방향"""
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"  # 양방향 포지션 모드

@dataclass
class TradeResult:
    """거래 결과"""
    success: bool
    order_id: Optional[str] = None
    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0
    timestamp: datetime = None
    error_message: str = ""

@dataclass
class Position:
    """포지션 정보"""
    symbol: str
    side: str  # LONG/SHORT
    size: float  # 포지션 크기 (음수면 SHORT)
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    percentage: float
    notional: float
    timestamp: datetime

class Trader:
    """
    기본 트레이더 클래스
    - 단일 심볼 전용 (BTCUSDT)
    - 매수/매도 주문 실행
    - 포지션 관리
    - 자본 관리 통합
    """
    
    def __init__(self, symbol: str, binance_client: BinanceClient, capital_manager: CapitalManager):
        """
        트레이더 초기화
        
        Args:
            symbol (str): 거래할 심볼 (예: BTCUSDT)
            binance_client (BinanceClient): 바이낸스 클라이언트
            capital_manager (CapitalManager): 자본 관리자
        """
        self.symbol = symbol
        self.binance_client = binance_client
        self.capital_manager = capital_manager
        
        self.logger = logging.getLogger(__name__)
        
        # 트레이더 상태
        self.is_active = False
        self.current_position: Optional[Position] = None
        self.trade_history: List[TradeResult] = []
        
        # 설정
        self.max_retries = 3
        self.retry_delay = 1.0  # 초
        
        self.logger.info(f"트레이더 초기화: {symbol}")
    
    def start(self) -> bool:
        """
        트레이더 시작
        
        Returns:
            bool: 시작 성공 여부
        """
        if not self._validate_setup():
            return False
        
        self.is_active = True
        self._update_account_balance()
        self._update_position()
        
        self.logger.info(f"🚀 {self.symbol} 트레이더 시작")
        return True
    
    def stop(self) -> None:
        """트레이더 중지"""
        self.is_active = False
        self.logger.info(f"⏹️ {self.symbol} 트레이더 중지")
    
    def place_market_order(self, side: OrderSide, quantity: float, 
                          stop_loss: Optional[float] = None,
                          take_profit: Optional[float] = None) -> TradeResult:
        """
        시장가 주문 실행
        
        Args:
            side (OrderSide): 매수/매도
            quantity (float): 수량
            stop_loss (Optional[float]): 손절가
            take_profit (Optional[float]): 익절가
            
        Returns:
            TradeResult: 거래 결과
        """
        if not self.is_active:
            return TradeResult(success=False, error_message="트레이더가 비활성 상태입니다")
        
        self.logger.info(f"📊 시장가 주문: {side.value} {quantity} {self.symbol}")
        
        # 현재가 조회
        current_price = self.binance_client.get_symbol_price(self.symbol)
        if not current_price:
            return TradeResult(success=False, error_message="현재가 조회 실패")
        
        # 자본 관리 체크
        notional_value = quantity * current_price
        
        if side == OrderSide.BUY:
            # 매수 시 자본 예약 확인
            if not self.capital_manager.reserve_capital(self.symbol, notional_value):
                return TradeResult(success=False, error_message="자본 부족")
        
        # 주문 실행 (재시도 로직 포함)
        for attempt in range(self.max_retries):
            try:
                order = self.binance_client.client.futures_create_order(
                    symbol=self.symbol,
                    side=side.value,
                    type=OrderType.MARKET.value,
                    quantity=quantity
                )
                
                # 주문 성공
                trade_result = TradeResult(
                    success=True,
                    order_id=str(order['orderId']),
                    symbol=self.symbol,
                    side=side.value,
                    quantity=quantity,
                    price=float(order.get('avgPrice', current_price)),
                    timestamp=datetime.now()
                )
                
                # 포지션 업데이트
                self._update_position()
                
                # 손절/익절 주문 설정
                if stop_loss or take_profit:
                    self._set_stop_orders(stop_loss, take_profit)
                
                # 거래 기록 저장
                self.trade_history.append(trade_result)
                
                self.logger.info(f"✅ 주문 체결: {order['orderId']} - {side.value} {quantity} @ ${trade_result.price:.2f}")
                return trade_result
                
            except Exception as e:
                self.logger.warning(f"주문 실행 실패 (시도 {attempt + 1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    # 실패 시 자본 해제
                    if side == OrderSide.BUY:
                        self.capital_manager.release_capital(self.symbol, notional_value)
                    
                    return TradeResult(
                        success=False,
                        error_message=f"주문 실행 실패: {str(e)}"
                    )
        
        return TradeResult(success=False, error_message="예상치 못한 오류")
    
    def place_limit_order(self, side: OrderSide, quantity: float, price: float) -> TradeResult:
        """
        지정가 주문 실행
        
        Args:
            side (OrderSide): 매수/매도
            quantity (float): 수량
            price (float): 지정 가격
            
        Returns:
            TradeResult: 거래 결과
        """
        if not self.is_active:
            return TradeResult(success=False, error_message="트레이더가 비활성 상태입니다")
        
        self.logger.info(f"📋 지정가 주문: {side.value} {quantity} {self.symbol} @ ${price}")
        
        # 자본 관리 체크 (매수 시에만)
        notional_value = quantity * price
        
        if side == OrderSide.BUY:
            if not self.capital_manager.reserve_capital(self.symbol, notional_value):
                return TradeResult(success=False, error_message="자본 부족")
        
        try:
            order = self.binance_client.client.futures_create_order(
                symbol=self.symbol,
                side=side.value,
                type=OrderType.LIMIT.value,
                quantity=quantity,
                price=price,
                timeInForce='GTC'  # Good Till Cancelled
            )
            
            trade_result = TradeResult(
                success=True,
                order_id=str(order['orderId']),
                symbol=self.symbol,
                side=side.value,
                quantity=quantity,
                price=price,
                timestamp=datetime.now()
            )
            
            self.trade_history.append(trade_result)
            
            self.logger.info(f"✅ 지정가 주문 등록: {order['orderId']}")
            return trade_result
            
        except Exception as e:
            # 실패 시 자본 해제
            if side == OrderSide.BUY:
                self.capital_manager.release_capital(self.symbol, notional_value)
            
            error_msg = f"지정가 주문 실패: {str(e)}"
            self.logger.error(error_msg)
            return TradeResult(success=False, error_message=error_msg)
    
    def close_position(self, percentage: float = 100.0) -> TradeResult:
        """
        포지션 청산
        
        Args:
            percentage (float): 청산 비율 (기본값: 100% 전체 청산)
            
        Returns:
            TradeResult: 거래 결과
        """
        if not self.current_position:
            return TradeResult(success=False, error_message="청산할 포지션이 없습니다")
        
        # 청산 수량 계산
        position_size = abs(self.current_position.size)
        close_quantity = position_size * (percentage / 100.0)
        
        # 청산 방향 결정 (포지션과 반대)
        if self.current_position.size > 0:
            # 롱 포지션 → 매도로 청산
            close_side = OrderSide.SELL
        else:
            # 숏 포지션 → 매수로 청산
            close_side = OrderSide.BUY
        
        self.logger.info(f"🔄 포지션 청산: {close_quantity:.6f} {self.symbol} ({percentage:.1f}%)")
        
        # 시장가로 청산
        result = self.place_market_order(close_side, close_quantity)
        
        if result.success:
            # 자본 해제
            notional_value = close_quantity * result.price
            self.capital_manager.release_capital(self.symbol, notional_value)
            
            self.logger.info(f"✅ 포지션 청산 완료")
        
        return result
    
    def get_current_position(self) -> Optional[Position]:
        """
        현재 포지션 정보 반환
        
        Returns:
            Optional[Position]: 포지션 정보
        """
        self._update_position()
        return self.current_position
    
    def get_account_balance(self) -> Dict[str, float]:
        """
        계정 잔고 조회
        
        Returns:
            Dict: 잔고 정보
        """
        account_info = self.binance_client.get_account_info()
        if account_info:
            return {
                'total_balance': account_info['total_balance'],
                'available_balance': account_info['available_balance']
            }
        return {'total_balance': 0.0, 'available_balance': 0.0}
    
    def get_trading_status(self) -> Dict[str, Any]:
        """
        트레이딩 상태 종합 정보
        
        Returns:
            Dict: 상태 정보
        """
        position = self.get_current_position()
        balance = self.get_account_balance()
        capital_status = self.capital_manager.get_capital_status()
        risk_status = self.capital_manager.check_risk_limits()
        
        return {
            'trader_active': self.is_active,
            'symbol': self.symbol,
            'account_balance': balance,
            'current_position': asdict(position) if position else None,
            'capital_status': capital_status,
            'risk_status': risk_status,
            'total_trades': len(self.trade_history),
            'last_update': datetime.now()
        }
    
    def _validate_setup(self) -> bool:
        """설정 유효성 검사"""
        # API 연결 테스트
        if not self.binance_client.test_connection():
            self.logger.error("바이낸스 API 연결 실패")
            return False
        
        # 심볼 유효성 확인
        current_price = self.binance_client.get_symbol_price(self.symbol)
        if not current_price:
            self.logger.error(f"심볼 {self.symbol} 가격 조회 실패")
            return False
        
        return True
    
    def _update_account_balance(self) -> None:
        """계정 잔고 업데이트"""
        account_info = self.binance_client.get_account_info()
        if account_info:
            self.capital_manager.update_balance(account_info['total_balance'])
    
    def _update_position(self) -> None:
        """포지션 정보 업데이트"""
        try:
            positions = self.binance_client.client.futures_position_information(symbol=self.symbol)
            
            for pos in positions:
                position_amt = float(pos['positionAmt'])
                
                if position_amt != 0:  # 활성 포지션이 있는 경우
                    entry_price = float(pos['entryPrice'])
                    mark_price = float(pos['markPrice'])
                    unrealized_pnl = float(pos['unRealizedProfit'])
                    
                    # percentage 계산 (진입가 대비 손익률)
                    if entry_price > 0:
                        percentage = ((mark_price - entry_price) / entry_price) * 100
                        if position_amt < 0:  # 숏 포지션인 경우 부호 반전
                            percentage = -percentage
                    else:
                        percentage = 0.0
                    
                    self.current_position = Position(
                        symbol=self.symbol,
                        side="LONG" if position_amt > 0 else "SHORT",
                        size=position_amt,
                        entry_price=entry_price,
                        mark_price=mark_price,
                        unrealized_pnl=unrealized_pnl,
                        percentage=percentage,
                        notional=abs(float(pos['notional'])),
                        timestamp=datetime.now()
                    )
                    
                    # 자본 관리자에 손익 업데이트
                    self.capital_manager.update_unrealized_pnl(
                        self.symbol, 
                        self.current_position.unrealized_pnl
                    )
                    
                    return
            
            # 포지션이 없는 경우
            self.current_position = None
            self.capital_manager.update_unrealized_pnl(self.symbol, 0.0)
            
        except Exception as e:
            self.logger.error(f"포지션 업데이트 실패: {e}")
    
    def _set_stop_orders(self, stop_loss: Optional[float], take_profit: Optional[float]) -> None:
        """
        손절/익절 주문 설정
        
        Args:
            stop_loss (Optional[float]): 손절가
            take_profit (Optional[float]): 익절가
        """
        if not self.current_position:
            return
        
        try:
            position_side = "LONG" if self.current_position.size > 0 else "SHORT"
            quantity = abs(self.current_position.size)
            
            # 손절 주문
            if stop_loss:
                stop_side = "SELL" if position_side == "LONG" else "BUY"
                
                self.binance_client.client.futures_create_order(
                    symbol=self.symbol,
                    side=stop_side,
                    type="STOP_MARKET",
                    quantity=quantity,
                    stopPrice=stop_loss,
                    reduceOnly=True
                )
                
                self.logger.info(f"🛑 손절 주문 설정: ${stop_loss}")
            
            # 익절 주문
            if take_profit:
                profit_side = "SELL" if position_side == "LONG" else "BUY"
                
                self.binance_client.client.futures_create_order(
                    symbol=self.symbol,
                    side=profit_side,
                    type="LIMIT",
                    quantity=quantity,
                    price=take_profit,
                    timeInForce="GTC",
                    reduceOnly=True
                )
                
                self.logger.info(f"🎯 익절 주문 설정: ${take_profit}")
                
        except Exception as e:
            self.logger.error(f"손절/익절 주문 설정 실패: {e}")