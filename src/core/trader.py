#!/usr/bin/env python3
"""
Trader 클래스 구현
파일 위치: src/core/trader.py
"""

from typing import Dict, Optional, Tuple
from datetime import datetime
import time

from src.utils.logger import get_logger

logger = get_logger(__name__)

class Trader:
    """개별 심볼 매매를 담당하는 트레이더"""
    
    def __init__(self, trader_id: int, symbol: str, binance_client, supabase_client, 
                 strategy, allocated_budget: float, investment_ratio: float = 1.0):
        """
        Trader 초기화
        
        Args:
            trader_id: 트레이더 ID (DB의 traders 테이블 ID)
            symbol: 거래 심볼 (예: 'BTCUSDT')
            binance_client: BinanceClient 인스턴스
            supabase_client: SupabaseClient 인스턴스
            strategy: Strategy 인스턴스 (MACDATRStrategy 등)
            allocated_budget: 할당받은 예산 (USDT)
            investment_ratio: 투자 비율 (0.0 ~ 1.0, 기본값: 1.0 = 100%)
        """
        self.trader_id = trader_id
        self.symbol = symbol
        self.binance_client = binance_client
        self.db_client = supabase_client
        self.strategy = strategy
        self.allocated_budget = allocated_budget
        self.investment_ratio = investment_ratio
        self.investment_amount = allocated_budget * investment_ratio
        
        # 현재 포지션 정보 캐시
        self.current_position = None
        self.position_size = 0.0
        self.entry_price = 0.0
        self.unrealized_pnl = 0.0
        
        # 상태 정보
        self.is_active = True
        self.last_signal_time = None
        
        logger.info(f"Trader 초기화 완료 - ID: {trader_id}, 심볼: {symbol}, 투자금: {self.investment_amount:.2f} USDT")
    
    def execute_trading_cycle(self) -> Dict:
        """
        매분 실행되는 메인 트레이딩 사이클
        
        Returns:
            실행 결과 딕셔너리
        """
        try:
            if not self.is_active:
                logger.debug(f"Trader {self.trader_id} 비활성 상태")
                return {'success': False, 'reason': 'inactive'}
            
            logger.debug(f"Trader {self.trader_id} 트레이딩 사이클 시작")
            start_time = time.time()
            
            # 1. 현재 포지션 상태 업데이트
            self.update_position_info()
            
            # 2. 매매 시그널 확인 및 실행
            signal_result = self.check_and_execute_signal()
            
            # 3. 포지션 정보 DB 업데이트 (변경사항 있는 경우)
            if signal_result.get('position_changed', False):
                self.save_position_to_db()
            
            # 4. 트레이더 PnL 업데이트
            self.update_trader_pnl()
            
            elapsed_time = time.time() - start_time
            
            logger.debug(f"Trader {self.trader_id} 트레이딩 사이클 완료 ({elapsed_time:.2f}초)")
            
            return {
                'success': True,
                'symbol': self.symbol,
                'signal_result': signal_result,
                'current_position': self.current_position,
                'unrealized_pnl': self.unrealized_pnl,
                'elapsed_time': elapsed_time
            }
            
        except Exception as e:
            logger.error(f"Trader {self.trader_id} 트레이딩 사이클 실패: {e}")
            return {
                'success': False,
                'symbol': self.symbol,
                'reason': str(e)
            }
    
    def check_and_execute_signal(self) -> Dict:
        """
        매매 시그널 확인 및 주문 실행
        
        Returns:
            시그널 실행 결과
        """
        try:
            # 1. Strategy에서 시그널 생성
            signal = self.strategy.generate_signal(self.symbol, self.current_position)
            
            logger.debug(f"Trader {self.trader_id} 시그널: {signal['signal']} (신뢰도: {signal['confidence']:.2f})")
            
            # 2. 시그널에 따른 주문 실행
            if signal['signal'] in ['ENTRY_LONG', 'ENTRY_SHORT']:
                return self.execute_entry_order(signal)
                
            elif signal['signal'] in ['EXIT_LONG', 'EXIT_SHORT']:
                return self.execute_exit_order(signal)
                
            else:  # HOLD
                return {
                    'action': 'hold',
                    'signal': signal,
                    'position_changed': False,
                    'reason': signal['reason']
                }
                
        except Exception as e:
            logger.error(f"Trader {self.trader_id} 시그널 처리 실패: {e}")
            return {
                'action': 'error',
                'signal': {},
                'position_changed': False,
                'reason': str(e)
            }
    
    def execute_entry_order(self, signal: Dict) -> Dict:
        """
        진입 주문 실행
        
        Args:
            signal: Strategy에서 생성된 시그널
            
        Returns:
            주문 실행 결과
        """
        try:
            if self.current_position is not None:
                logger.warning(f"Trader {self.trader_id} 이미 포지션 보유 중 - 진입 주문 취소")
                return {
                    'action': 'entry_cancelled',
                    'signal': signal,
                    'position_changed': False,
                    'reason': '이미 포지션 보유 중'
                }
            
            direction = signal['signal'].split('_')[1]  # 'ENTRY_LONG' -> 'LONG'
            
            # 현재 가격 조회 (최신 캔들에서)
            current_price = self.get_current_price()
            if not current_price:
                raise Exception("현재 가격 조회 실패")
            
            # 주문 수량 계산
            quantity = self.calculate_order_quantity(current_price)
            if not quantity:
                raise Exception("주문 수량 계산 실패")
            
            # 바이낸스 주문 실행
            order_side = 'BUY' if direction == 'LONG' else 'SELL'
            order_result = self.binance_client.place_market_order(
                symbol=self.symbol,
                side=order_side,
                quantity=quantity
            )
            
            if not order_result:
                raise Exception("바이낸스 주문 실행 실패")
            
            # 포지션 정보 업데이트
            self.current_position = direction
            self.position_size = quantity if direction == 'LONG' else -quantity
            self.entry_price = order_result['price']
            self.unrealized_pnl = 0.0
            
            # 거래 내역 DB 저장
            self.save_trade_to_db({
                'symbol': self.symbol,
                'side': order_side,
                'position_side': direction,
                'quantity': quantity,
                'price': self.entry_price,
                'order_type': 'MARKET',
                'trade_type': 'ENTRY',
                'binance_order_id': order_result.get('order_id'),
                'executed_at': datetime.now().isoformat()
            })
            
            logger.info(f"Trader {self.trader_id} {direction} 포지션 진입: {quantity} @ ${self.entry_price:.4f}")
            
            return {
                'action': 'entry',
                'signal': signal,
                'direction': direction,
                'quantity': quantity,
                'price': self.entry_price,
                'order_result': order_result,
                'position_changed': True
            }
            
        except Exception as e:
            logger.error(f"Trader {self.trader_id} 진입 주문 실패: {e}")
            return {
                'action': 'entry_failed',
                'signal': signal,
                'position_changed': False,
                'reason': str(e)
            }
    
    def execute_exit_order(self, signal: Dict) -> Dict:
        """
        청산 주문 실행
        
        Args:
            signal: Strategy에서 생성된 시그널
            
        Returns:
            주문 실행 결과
        """
        try:
            if self.current_position is None:
                logger.warning(f"Trader {self.trader_id} 청산할 포지션 없음")
                return {
                    'action': 'exit_cancelled',
                    'signal': signal,
                    'position_changed': False,
                    'reason': '청산할 포지션 없음'
                }
            
            # 현재 가격 조회
            current_price = self.get_current_price()
            if not current_price:
                raise Exception("현재 가격 조회 실패")
            
            # 미실현 손익 계산
            self.calculate_unrealized_pnl(current_price)
            
            # 청산 주문 실행
            quantity = abs(self.position_size)
            order_side = 'SELL' if self.current_position == 'LONG' else 'BUY'
            
            order_result = self.binance_client.place_market_order(
                symbol=self.symbol,
                side=order_side,
                quantity=quantity
            )
            
            if not order_result:
                raise Exception("바이낸스 청산 주문 실행 실패")
            
            exit_price = order_result['price']
            
            # 실현 손익 계산
            realized_pnl = self.calculate_realized_pnl(exit_price)
            
            # 거래 내역 DB 저장
            self.save_trade_to_db({
                'symbol': self.symbol,
                'side': order_side,
                'position_side': self.current_position,
                'quantity': quantity,
                'price': exit_price,
                'order_type': 'MARKET',
                'trade_type': 'EXIT',
                'realized_pnl': realized_pnl,
                'binance_order_id': order_result.get('order_id'),
                'executed_at': datetime.now().isoformat()
            })
            
            logger.info(f"Trader {self.trader_id} {self.current_position} 포지션 청산: {quantity} @ ${exit_price:.4f} (PnL: {realized_pnl:.2f})")
            
            # 포지션 정보 초기화
            previous_position = self.current_position
            self.current_position = None
            self.position_size = 0.0
            self.entry_price = 0.0
            self.unrealized_pnl = 0.0
            
            return {
                'action': 'exit',
                'signal': signal,
                'direction': previous_position,
                'quantity': quantity,
                'entry_price': self.entry_price,
                'exit_price': exit_price,
                'realized_pnl': realized_pnl,
                'order_result': order_result,
                'position_changed': True
            }
            
        except Exception as e:
            logger.error(f"Trader {self.trader_id} 청산 주문 실패: {e}")
            return {
                'action': 'exit_failed',
                'signal': signal,
                'position_changed': False,
                'reason': str(e)
            }
    
    def get_current_price(self) -> Optional[float]:
        """현재 시세 조회"""
        try:
            # 최신 1분봉에서 종가 조회
            klines = self.binance_client.get_klines(self.symbol, '1m', 1)
            if klines.empty:
                return None
            
            current_price = float(klines.iloc[-1]['close'])
            logger.debug(f"Trader {self.trader_id} 현재가: ${current_price:.4f}")
            
            return current_price
            
        except Exception as e:
            logger.error(f"Trader {self.trader_id} 현재가 조회 실패: {e}")
            return None
    
    def calculate_order_quantity(self, price: float) -> Optional[float]:
        """주문 수량 계산"""
        try:
            # 투자금액을 현재 가격으로 나눠서 수량 계산
            quantity = self.binance_client.calculate_quantity(
                self.symbol, 
                self.investment_amount, 
                price
            )
            
            logger.debug(f"Trader {self.trader_id} 주문 수량 계산: {self.investment_amount} USDT @ ${price:.4f} = {quantity}")
            
            return quantity
            
        except Exception as e:
            logger.error(f"Trader {self.trader_id} 주문 수량 계산 실패: {e}")
            return None
    
    def calculate_unrealized_pnl(self, current_price: float):
        """미실현 손익 계산"""
        if self.current_position is None or self.position_size == 0:
            self.unrealized_pnl = 0.0
            return
        
        if self.current_position == 'LONG':
            # 롱: (현재가 - 진입가) * 수량
            self.unrealized_pnl = (current_price - self.entry_price) * abs(self.position_size)
        else:  # SHORT
            # 숏: (진입가 - 현재가) * 수량
            self.unrealized_pnl = (self.entry_price - current_price) * abs(self.position_size)
        
        logger.debug(f"Trader {self.trader_id} 미실현 PnL: {self.unrealized_pnl:.2f} USDT")
    
    def calculate_realized_pnl(self, exit_price: float) -> float:
        """실현 손익 계산"""
        if self.current_position is None or self.position_size == 0:
            return 0.0
        
        quantity = abs(self.position_size)
        
        if self.current_position == 'LONG':
            realized_pnl = (exit_price - self.entry_price) * quantity
        else:  # SHORT
            realized_pnl = (self.entry_price - exit_price) * quantity
        
        logger.debug(f"Trader {self.trader_id} 실현 PnL: {realized_pnl:.2f} USDT")
        return realized_pnl
    
    def update_position_info(self):
        """바이낸스에서 실제 포지션 정보 조회 및 동기화"""
        try:
            # 바이낸스에서 실제 포지션 조회
            position_info = self.binance_client.get_position_info(self.symbol)
            
            if position_info['side'] == 'NONE':
                # 포지션 없음
                if self.current_position is not None:
                    logger.info(f"Trader {self.trader_id} 포지션 정리됨 (외부 청산 가능성)")
                self.current_position = None
                self.position_size = 0.0
                self.entry_price = 0.0
                self.unrealized_pnl = 0.0
            else:
                # 포지션 있음
                self.current_position = position_info['side']
                self.position_size = position_info['size']
                self.entry_price = position_info['entry_price']
                self.unrealized_pnl = position_info['unrealized_pnl']
                
                logger.debug(f"Trader {self.trader_id} 포지션 동기화: {self.current_position} {abs(self.position_size):.8f}")
                
        except Exception as e:
            logger.error(f"Trader {self.trader_id} 포지션 정보 업데이트 실패: {e}")
    
    def save_position_to_db(self):
        """포지션 정보를 DB에 저장"""
        try:
            if self.current_position is None:
                # 포지션 없으면 기존 open 포지션들을 close 처리
                response = self.db_client.client.table('positions').update({
                    'is_open': False,
                    'updated_at': datetime.now().isoformat()
                }).eq('trader_id', self.trader_id).eq('is_open', True).execute()
            else:
                # 포지션 있으면 upsert
                position_data = {
                    'trader_id': self.trader_id,
                    'symbol': self.symbol,
                    'side': self.current_position,
                    'size': abs(self.position_size),
                    'entry_price': self.entry_price,
                    'entry_time': datetime.now().isoformat(),
                    'unrealized_pnl': self.unrealized_pnl,
                    'is_open': True
                }
                
                response = self.db_client.client.table('positions').upsert(
                    position_data,
                    on_conflict='trader_id,symbol,side,is_open'
                ).execute()
                
        except Exception as e:
            logger.error(f"Trader {self.trader_id} 포지션 DB 저장 실패: {e}")
    
    def save_trade_to_db(self, trade_data: Dict):
        """거래 내역을 DB에 저장"""
        try:
            success = self.db_client.save_trade(self.trader_id, trade_data)
            if success:
                logger.debug(f"Trader {self.trader_id} 거래 내역 저장 완료")
            else:
                logger.error(f"Trader {self.trader_id} 거래 내역 저장 실패")
                
        except Exception as e:
            logger.error(f"Trader {self.trader_id} 거래 내역 저장 중 에러: {e}")
    
    def update_trader_pnl(self):
        """트레이더 총 손익 DB 업데이트"""
        try:
            # 실현 손익 합계 조회
            response = self.db_client.client.table('trades').select(
                'realized_pnl'
            ).eq('trader_id', self.trader_id).eq('trade_type', 'EXIT').execute()
            
            total_realized_pnl = 0.0
            if response.data:
                total_realized_pnl = sum(
                    float(trade.get('realized_pnl', 0) or 0) 
                    for trade in response.data
                )
            
            # 총 손익 = 실현 손익 + 미실현 손익
            total_pnl = total_realized_pnl + self.unrealized_pnl
            
            # DB 업데이트
            success = self.db_client.update_trader_pnl(self.trader_id, total_pnl)
            if success:
                logger.debug(f"Trader {self.trader_id} 총 PnL 업데이트: {total_pnl:.2f} USDT")
                
        except Exception as e:
            logger.error(f"Trader {self.trader_id} PnL 업데이트 실패: {e}")
    
    def get_trader_status(self) -> Dict:
        """트레이더 현재 상태 반환"""
        return {
            'trader_id': self.trader_id,
            'symbol': self.symbol,
            'is_active': self.is_active,
            'allocated_budget': self.allocated_budget,
            'investment_amount': self.investment_amount,
            'current_position': self.current_position,
            'position_size': self.position_size,
            'entry_price': self.entry_price,
            'unrealized_pnl': self.unrealized_pnl,
            'strategy': self.strategy.get_strategy_info()['name']
        }
    
    def stop_trading(self, reason: str = "수동 정지"):
        """트레이딩 정지"""
        self.is_active = False
        logger.info(f"Trader {self.trader_id} 트레이딩 정지: {reason}")
    
    def resume_trading(self, reason: str = "수동 재시작"):
        """트레이딩 재시작"""
        self.is_active = True
        logger.info(f"Trader {self.trader_id} 트레이딩 재시작: {reason}")