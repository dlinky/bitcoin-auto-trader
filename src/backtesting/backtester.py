#!/usr/bin/env python3
"""
백테스팅 엔진
파일 위치: src/backtesting/backtester.py
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from src.utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class BacktestTrade:
    """백테스트 거래 기록"""
    timestamp: datetime
    action: str  # 'BUY', 'SELL'
    position_side: str  # 'LONG', 'SHORT' 
    price: float
    quantity: float
    trade_type: str  # 'ENTRY', 'EXIT'
    signal_data: Dict  # 시그널 생성 시 데이터

@dataclass
class BacktestPosition:
    """백테스트 포지션"""
    side: str  # 'LONG', 'SHORT'
    entry_price: float
    entry_time: datetime
    quantity: float
    unrealized_pnl: float = 0.0

@dataclass
class BacktestResult:
    """백테스트 결과"""
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    trades: List[BacktestTrade]
    equity_curve: pd.DataFrame

class Backtester:
    """백테스팅 엔진"""
    
    def __init__(self, initial_capital: float = 10000.0, commission_rate: float = 0.001):
        """
        백테스터 초기화
        
        Args:
            initial_capital: 초기 자본금
            commission_rate: 수수료율 (기본 0.1%)
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        
        # 백테스트 상태
        self.current_capital = initial_capital
        self.current_position = None
        self.trades = []
        self.equity_curve = []
        
        logger.info(f"Backtester 초기화 - 초기자본: ${initial_capital}, 수수료: {commission_rate*100}%")
    
    def run_backtest(self, strategy, market_data: pd.DataFrame, symbol: str = "BTCUSDT") -> BacktestResult:
        """
        백테스트 실행
        
        Args:
            strategy: 전략 객체 (generate_signal 메서드 필요)
            market_data: 시장 데이터 (OHLCV + 지표)
            symbol: 거래 심볼
            
        Returns:
            BacktestResult 객체
        """
        try:
            logger.info(f"백테스트 시작 - {symbol} ({len(market_data)}개 데이터)")
            
            # 초기화
            self._reset_state()
            
            # 데이터 검증
            if not self._validate_market_data(market_data):
                raise ValueError("시장 데이터가 유효하지 않습니다")

            # 시장 데이터를 인스턴스 변수로 저장 (중요!)
            self.market_data = market_data.copy()

            # 백테스트 실행
            for i in range(len(market_data)):
                current_row = market_data.iloc[i]
                self._process_bar(strategy, current_row, symbol, i)
            
            # 마지막 포지션 청산
            if self.current_position:
                final_price = market_data.iloc[-1]['close']
                self._close_position(final_price, market_data.iloc[-1]['timestamp'], "BACKTEST_END")
            
            # 결과 생성
            result = self._generate_result(strategy, market_data, symbol)
            
            logger.info(f"백테스트 완료 - 수익률: {result.total_return_pct:.2f}%, 거래: {result.total_trades}회")
            return result
            
        except Exception as e:
            logger.error(f"백테스트 실행 실패: {e}")
            raise
    
    def _reset_state(self):
        """백테스트 상태 초기화"""
        self.current_capital = self.initial_capital
        self.current_position = None
        self.trades = []
        self.equity_curve = []
    
    def _validate_market_data(self, market_data: pd.DataFrame) -> bool:
        """시장 데이터 유효성 검증"""
        required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        
        for col in required_columns:
            if col not in market_data.columns:
                logger.error(f"필수 컬럼 누락: {col}")
                return False
        
        if len(market_data) < 50:
            logger.error(f"데이터가 부족합니다: {len(market_data)}개")
            return False
        
        return True
    
    def _process_bar(self, strategy, current_row: pd.Series, symbol: str, current_index: int):
        """개별 바 처리 (market_data 전달 추가)"""
        try:
            timestamp = current_row['timestamp']
            current_price = current_row['close']
            
            # 미실현 손익 업데이트
            if self.current_position:
                self._update_unrealized_pnl(current_price)
            
            # 전략용 시장 데이터 준비 (현재 시점까지의 데이터)
            lookback_period = min(100, current_index + 1)
            start_idx = max(0, current_index + 1 - lookback_period)
            
            # 전략에 전달할 market_data 준비
            market_data_for_strategy = self.market_data.iloc[start_idx:current_index + 1].copy()
            
            # 현재 포지션 정보
            position_info = self.current_position.side if self.current_position else None
            
            # 전략에서 시그널 생성 (market_data 명시적 전달) ← 핵심!
            signal = strategy.generate_signal(
                symbol=symbol, 
                current_position=position_info,
                market_data=market_data_for_strategy
            )
            
            # 시그널 처리
            if signal['signal'] in ['ENTRY_LONG', 'ENTRY_SHORT'] and not self.current_position:
                self._open_position(signal, current_price, timestamp)
            elif signal['signal'] in ['EXIT_LONG', 'EXIT_SHORT'] and self.current_position:
                self._close_position(current_price, timestamp, signal['reason'])
            
            # 자본 곡선 기록
            total_value = self._calculate_total_value(current_price)
            self.equity_curve.append({
                'timestamp': timestamp,
                'capital': self.current_capital,
                'unrealized_pnl': self.current_position.unrealized_pnl if self.current_position else 0,
                'total_value': total_value,
                'position': self.current_position.side if self.current_position else None
            })
            
        except Exception as e:
            logger.error(f"바 처리 중 에러 ({timestamp}): {e}")
    
    def _open_position(self, signal: Dict, price: float, timestamp: datetime):
        """포지션 진입"""
        try:
            direction = signal['signal'].split('_')[1]  # 'ENTRY_LONG' -> 'LONG'
            
            # 투자 가능 금액 (현재 자본의 100%)
            investment_amount = self.current_capital
            
            # 수량 계산
            quantity = investment_amount / price
            
            # 수수료 차감
            commission = investment_amount * self.commission_rate
            self.current_capital -= commission
            
            # 포지션 생성
            self.current_position = BacktestPosition(
                side=direction,
                entry_price=price,
                entry_time=timestamp,
                quantity=quantity
            )
            
            # 거래 기록
            action = 'BUY' if direction == 'LONG' else 'SELL'
            trade = BacktestTrade(
                timestamp=timestamp,
                action=action,
                position_side=direction,
                price=price,
                quantity=quantity,
                trade_type='ENTRY',
                signal_data=signal
            )
            self.trades.append(trade)
            
            logger.debug(f"포지션 진입: {direction} {quantity:.6f} @ ${price:.2f}")
            
        except Exception as e:
            logger.error(f"포지션 진입 실패: {e}")
    
    def _close_position(self, price: float, timestamp: datetime, reason: str = "SIGNAL"):
        """포지션 청산"""
        try:
            if not self.current_position:
                return
            
            # 손익 계산
            if self.current_position.side == 'LONG':
                pnl = (price - self.current_position.entry_price) * self.current_position.quantity
            else:  # SHORT
                pnl = (self.current_position.entry_price - price) * self.current_position.quantity
            
            # 청산 금액 계산
            exit_value = price * self.current_position.quantity
            commission = exit_value * self.commission_rate
            net_pnl = pnl - commission
            
            # 자본 업데이트
            self.current_capital += net_pnl
            
            # 거래 기록
            action = 'SELL' if self.current_position.side == 'LONG' else 'BUY'
            trade = BacktestTrade(
                timestamp=timestamp,
                action=action,
                position_side=self.current_position.side,
                price=price,
                quantity=self.current_position.quantity,
                trade_type='EXIT',
                signal_data={'reason': reason, 'pnl': net_pnl}
            )
            self.trades.append(trade)
            
            logger.debug(f"포지션 청산: {self.current_position.side} @ ${price:.2f} (PnL: ${net_pnl:.2f})")
            
            # 포지션 초기화
            self.current_position = None
            
        except Exception as e:
            logger.error(f"포지션 청산 실패: {e}")
    
    def _update_unrealized_pnl(self, current_price: float):
        """미실현 손익 업데이트"""
        if not self.current_position:
            return
        
        if self.current_position.side == 'LONG':
            self.current_position.unrealized_pnl = (
                (current_price - self.current_position.entry_price) * self.current_position.quantity
            )
        else:  # SHORT
            self.current_position.unrealized_pnl = (
                (self.current_position.entry_price - current_price) * self.current_position.quantity
            )
    
    def _calculate_total_value(self, current_price: float) -> float:
        """총 자산 가치 계산"""
        total_value = self.current_capital
        
        if self.current_position:
            total_value += self.current_position.unrealized_pnl
        
        return total_value
    
    def _generate_result(self, strategy, market_data: pd.DataFrame, symbol: str) -> BacktestResult:
        """백테스트 결과 생성"""
        try:
            # 기본 정보
            start_date = market_data.iloc[0]['timestamp']
            end_date = market_data.iloc[-1]['timestamp']
            final_capital = self.current_capital
            total_return = final_capital - self.initial_capital
            total_return_pct = (total_return / self.initial_capital) * 100
            
            # 거래 분석
            entry_trades = [t for t in self.trades if t.trade_type == 'ENTRY']
            exit_trades = [t for t in self.trades if t.trade_type == 'EXIT']
            
            total_trades = len(exit_trades)  # 완료된 거래만 카운트
            
            if total_trades > 0:
                # 승패 분석
                winning_trades = len([t for t in exit_trades if t.signal_data.get('pnl', 0) > 0])
                losing_trades = total_trades - winning_trades
                win_rate = (winning_trades / total_trades) * 100
                
                # 평균 수익/손실
                wins = [t.signal_data.get('pnl', 0) for t in exit_trades if t.signal_data.get('pnl', 0) > 0]
                losses = [t.signal_data.get('pnl', 0) for t in exit_trades if t.signal_data.get('pnl', 0) < 0]
                
                avg_win = np.mean(wins) if wins else 0.0
                avg_loss = np.mean(losses) if losses else 0.0
            else:
                winning_trades = losing_trades = 0
                win_rate = avg_win = avg_loss = 0.0
            
            # 자본 곡선 DataFrame 생성
            equity_df = pd.DataFrame(self.equity_curve)
            
            # 최대 낙폭 계산
            if not equity_df.empty:
                peak = equity_df['total_value'].expanding().max()
                drawdown = (equity_df['total_value'] - peak) / peak * 100
                max_drawdown_pct = drawdown.min()
                max_drawdown = (peak - equity_df['total_value']).max()
            else:
                max_drawdown = max_drawdown_pct = 0.0
            
            # 샤프 비율 계산 (간단 버전)
            if not equity_df.empty and len(equity_df) > 1:
                returns = equity_df['total_value'].pct_change().dropna()
                if len(returns) > 0 and returns.std() > 0:
                    sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(365 * 24 * 60)  # 연환산
                else:
                    sharpe_ratio = 0.0
            else:
                sharpe_ratio = 0.0
            
            # 전략 이름 추출
            strategy_name = getattr(strategy, '__class__', type(strategy)).__name__
            
            return BacktestResult(
                strategy_name=strategy_name,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                initial_capital=self.initial_capital,
                final_capital=final_capital,
                total_return=total_return,
                total_return_pct=total_return_pct,
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                max_drawdown=max_drawdown,
                max_drawdown_pct=max_drawdown_pct,
                sharpe_ratio=sharpe_ratio,
                trades=self.trades,
                equity_curve=equity_df
            )
            
        except Exception as e:
            logger.error(f"결과 생성 실패: {e}")
            raise