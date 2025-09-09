import logging
from typing import Optional, Dict, Any
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass

@dataclass
class CapitalConfig:
    """자본 관리 설정"""
    total_capital_ratio: float = 0.1  # 전체 자본 대비 사용 비율 (10%)
    max_loss_ratio: float = 0.02      # 최대 손실 비율 (2%)
    max_position_ratio: float = 0.5   # 단일 포지션 최대 비율 (50%)
    min_order_size: float = 0.001     # 최소 주문 크기
    leverage: int = 1                 # 레버리지 (초기값: 1배)

class CapitalManager:
    """
    자본 관리 시스템
    - 사용 가능한 자본 계산
    - 포지션 크기 결정
    - 리스크 한도 관리
    """
    
    def __init__(self, config: CapitalConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 현재 상태 추적
        self.total_balance = 0.0
        self.allocated_capital = 0.0
        self.used_capital = 0.0
        self.current_positions = {}  # {symbol: position_info}
        
    def update_balance(self, total_balance: float) -> None:
        """
        총 잔고 업데이트
        
        Args:
            total_balance (float): 현재 총 잔고
        """
        self.total_balance = total_balance
        self.allocated_capital = total_balance * self.config.total_capital_ratio
        
        self.logger.info(f"잔고 업데이트: 총 {total_balance:.2f} USDT")
        self.logger.info(f"할당 자본: {self.allocated_capital:.2f} USDT ({self.config.total_capital_ratio*100:.1f}%)")
    
    def get_available_capital(self) -> float:
        """
        사용 가능한 자본 반환
        
        Returns:
            float: 사용 가능한 자본
        """
        available = self.allocated_capital - self.used_capital
        return max(0, available)
    
    def calculate_position_size(self, symbol: str, entry_price: float, 
                              stop_loss_price: Optional[float] = None) -> Dict[str, Any]:
        """
        포지션 크기 계산
        
        Args:
            symbol (str): 거래 심볼
            entry_price (float): 진입 가격
            stop_loss_price (Optional[float]): 손절가 (없으면 기본 리스크로 계산)
            
        Returns:
            Dict: 포지션 정보 {'size': float, 'notional': float, 'risk_amount': float}
        """
        available_capital = self.get_available_capital()
        
        if available_capital <= 0:
            self.logger.warning("사용 가능한 자본이 없습니다")
            return {'size': 0, 'notional': 0, 'risk_amount': 0}
        
        # 단일 포지션 최대 사용 자본
        max_position_capital = self.allocated_capital * self.config.max_position_ratio
        position_capital = min(available_capital, max_position_capital)
        
        # 리스크 기반 포지션 크기 계산
        if stop_loss_price:
            # 손절가가 있는 경우: 리스크 금액 기반 계산
            risk_per_unit = abs(entry_price - stop_loss_price)
            max_risk_amount = self.allocated_capital * self.config.max_loss_ratio
            
            if risk_per_unit > 0:
                # 리스크 기반 수량 = 최대 리스크 금액 / 단위당 리스크
                risk_based_size = max_risk_amount / risk_per_unit
                
                # 자본 기반 수량 = 사용 가능 자본 / 진입가
                capital_based_size = position_capital / entry_price
                
                # 두 값 중 작은 값 선택
                position_size = min(risk_based_size, capital_based_size)
                risk_amount = position_size * risk_per_unit
            else:
                position_size = 0
                risk_amount = 0
        else:
            # 손절가가 없는 경우: 기본 리스크 비율로 계산
            max_risk_amount = self.allocated_capital * self.config.max_loss_ratio
            
            # 기본 리스크를 진입가의 5%로 가정
            assumed_risk_ratio = 0.05
            risk_per_unit = entry_price * assumed_risk_ratio
            
            position_size = max_risk_amount / risk_per_unit
            risk_amount = max_risk_amount
        
        # 최소 주문 크기 확인
        if position_size < self.config.min_order_size:
            self.logger.warning(f"계산된 포지션 크기가 최소값보다 작습니다: {position_size:.6f}")
            position_size = 0
            risk_amount = 0
        
        # 소수점 정리 (바이낸스 규칙에 맞게)
        position_size = self._round_position_size(symbol, position_size)
        notional_value = position_size * entry_price
        
        result = {
            'size': position_size,
            'notional': notional_value,
            'risk_amount': risk_amount,
            'max_loss_ratio': (risk_amount / self.allocated_capital) * 100 if self.allocated_capital > 0 else 0
        }
        
        self.logger.info(f"포지션 크기 계산 - {symbol}")
        self.logger.info(f"  수량: {position_size:.6f}")
        self.logger.info(f"  명목가치: {notional_value:.2f} USDT")
        self.logger.info(f"  리스크 금액: {risk_amount:.2f} USDT ({result['max_loss_ratio']:.2f}%)")
        
        return result
    
    def reserve_capital(self, symbol: str, notional_value: float) -> bool:
        """
        자본 예약 (포지션 진입 시)
        
        Args:
            symbol (str): 거래 심볼
            notional_value (float): 명목가치
            
        Returns:
            bool: 예약 성공 여부
        """
        available = self.get_available_capital()
        
        if notional_value > available:
            self.logger.error(f"자본 부족: 필요 {notional_value:.2f}, 가용 {available:.2f}")
            return False
        
        self.used_capital += notional_value
        
        if symbol not in self.current_positions:
            self.current_positions[symbol] = {
                'notional': 0,
                'unrealized_pnl': 0
            }
        
        self.current_positions[symbol]['notional'] += notional_value
        
        self.logger.info(f"자본 예약: {symbol} {notional_value:.2f} USDT")
        self.logger.info(f"사용 자본: {self.used_capital:.2f} / {self.allocated_capital:.2f} USDT")
        
        return True
    
    def release_capital(self, symbol: str, notional_value: float) -> None:
        """
        자본 해제 (포지션 청산 시)
        
        Args:
            symbol (str): 거래 심볼
            notional_value (float): 해제할 명목가치
        """
        self.used_capital = max(0, self.used_capital - notional_value)
        
        if symbol in self.current_positions:
            self.current_positions[symbol]['notional'] -= notional_value
            
            # 포지션이 완전히 청산되면 제거
            if self.current_positions[symbol]['notional'] <= 0:
                del self.current_positions[symbol]
        
        self.logger.info(f"자본 해제: {symbol} {notional_value:.2f} USDT")
        self.logger.info(f"사용 자본: {self.used_capital:.2f} / {self.allocated_capital:.2f} USDT")
    
    def update_unrealized_pnl(self, symbol: str, pnl: float) -> None:
        """
        미실현 손익 업데이트
        
        Args:
            symbol (str): 거래 심볼
            pnl (float): 미실현 손익
        """
        if symbol in self.current_positions:
            self.current_positions[symbol]['unrealized_pnl'] = pnl
    
    def get_total_unrealized_pnl(self) -> float:
        """
        총 미실현 손익 반환
        
        Returns:
            float: 총 미실현 손익
        """
        total_pnl = sum(pos['unrealized_pnl'] for pos in self.current_positions.values())
        return total_pnl
    
    def check_risk_limits(self) -> Dict[str, Any]:
        """
        리스크 한도 체크
        
        Returns:
            Dict: 리스크 상태 정보
        """
        total_pnl = self.get_total_unrealized_pnl()
        current_loss_ratio = abs(min(0, total_pnl)) / self.allocated_capital if self.allocated_capital > 0 else 0
        max_loss_threshold = self.config.max_loss_ratio
        
        risk_status = {
            'current_loss_ratio': current_loss_ratio * 100,
            'max_loss_threshold': max_loss_threshold * 100,
            'is_risk_limit_exceeded': current_loss_ratio > max_loss_threshold,
            'total_unrealized_pnl': total_pnl,
            'capital_utilization': (self.used_capital / self.allocated_capital) * 100 if self.allocated_capital > 0 else 0
        }
        
        if risk_status['is_risk_limit_exceeded']:
            self.logger.warning(f"⚠️ 리스크 한도 초과!")
            self.logger.warning(f"현재 손실: {risk_status['current_loss_ratio']:.2f}%")
            self.logger.warning(f"한도: {risk_status['max_loss_threshold']:.2f}%")
        
        return risk_status
    
    def get_capital_status(self) -> Dict[str, Any]:
        """
        자본 현황 요약
        
        Returns:
            Dict: 자본 현황 정보
        """
        return {
            'total_balance': self.total_balance,
            'allocated_capital': self.allocated_capital,
            'used_capital': self.used_capital,
            'available_capital': self.get_available_capital(),
            'utilization_ratio': (self.used_capital / self.allocated_capital) * 100 if self.allocated_capital > 0 else 0,
            'total_unrealized_pnl': self.get_total_unrealized_pnl(),
            'active_positions': len(self.current_positions),
            'positions': dict(self.current_positions)
        }
    
    def _round_position_size(self, symbol: str, size: float) -> float:
        """
        포지션 크기를 바이낸스 규칙에 맞게 반올림
        
        Args:
            symbol (str): 거래 심볼
            size (float): 원본 크기
            
        Returns:
            float: 반올림된 크기
        """
        # BTCUSDT의 경우 보통 소수점 3자리까지 허용
        # 실제로는 거래소 정보를 조회해서 정확한 값을 사용해야 함
        if 'BTC' in symbol:
            precision = 3
        elif 'ETH' in symbol:
            precision = 2
        else:
            precision = 1
        
        decimal_size = Decimal(str(size))
        rounded_size = decimal_size.quantize(Decimal('0.' + '0' * precision), rounding=ROUND_DOWN)
        
        return float(rounded_size)