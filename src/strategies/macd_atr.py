#!/usr/bin/env python3
"""
MACD + ATR 전략 구현 (수정된 버전)
파일 위치: src/strategies/macd_atr.py
"""

from typing import Dict, Optional, Tuple
from datetime import datetime
import pandas as pd
from abc import ABC, abstractmethod

from src.utils.logger import get_logger

logger = get_logger(__name__)

class Strategy(ABC):
    """전략 인터페이스 (추상 클래스)"""
    
    @abstractmethod
    def generate_signal(self, symbol: str, current_position: Optional[str] = None) -> Dict:
        """
        매매 시그널 생성
        
        Args:
            symbol: 거래 심볼
            current_position: 현재 포지션 ('LONG', 'SHORT', None)
            
        Returns:
            {
                'signal': 'ENTRY_LONG' | 'ENTRY_SHORT' | 'EXIT_LONG' | 'EXIT_SHORT' | 'HOLD',
                'confidence': float (0-1),
                'reason': str,
                'data': dict  # 추가 정보
            }
        """
        pass

class MACDATRStrategy(Strategy):
    """MACD + ATR 기반 매매 전략"""
    
    def __init__(self, supabase_client=None, macd_fast: int = 12, macd_slow: int = 26, 
                 macd_signal: int = 9, atr_period: int = 14, atr_multiplier: float = 2.0):
        """
        MACD + ATR 전략 초기화
        
        Args:
            supabase_client: DB 클라이언트 (실제 트레이딩용, 백테스팅에서는 None)
            macd_fast: MACD 빠른 EMA 기간
            macd_slow: MACD 느린 EMA 기간  
            macd_signal: MACD 시그널 라인 기간
            atr_period: ATR 계산 기간
            atr_multiplier: ATR 필터 배수 (노이즈 필터링용)
        """
        # 변수명 통일: supabase_client로 통일
        self.supabase_client = supabase_client
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        
        logger.info(f"MACDATRStrategy 초기화: MACD({macd_fast},{macd_slow},{macd_signal}), ATR({atr_period})")
    
    def generate_signal(self, symbol: str, current_position: Optional[str] = None, 
                       market_data: Optional[pd.DataFrame] = None) -> Dict:
        """
        매매 시그널 생성 (백테스팅/실시간 호환)
        
        Args:
            symbol: 거래 심볼
            current_position: 현재 포지션 ('LONG', 'SHORT', None)
            market_data: 시장 데이터 (백테스팅용, 실시간에서는 None)
            
        Returns:
            시그널 딕셔너리
        """
        logger.info(f"[DEBUG] {symbol} generate_signal 호출됨 - market_data: {market_data is not None}, position: {current_position}")
        try:
            # 시장 데이터 획득
            if market_data is not None:
                # 백테스팅 모드: 전달받은 데이터 사용
                logger.debug(f"{symbol} 백테스팅 모드: 전달받은 데이터 {len(market_data)}개 사용")
                
            elif self.supabase_client is not None:
                # 실시간 모드: DB에서 조회
                market_data = self.supabase_client.get_latest_market_data(symbol, 100)
                logger.debug(f"{symbol} 실시간 모드: DB에서 {len(market_data) if market_data is not None else 0}개 조회")
                
            else:
                # 둘 다 없으면 에러
                return {
                    'signal': 'HOLD',
                    'confidence': 0.0,
                    'reason': 'market_data와 supabase_client 모두 없음',
                    'debug_info': {'mode': 'error', 'has_data': False, 'has_client': False}
                }
            
            # 데이터 검증
            if market_data is None or len(market_data) < 50:
                return {
                    'signal': 'HOLD',
                    'confidence': 0.0,
                    'reason': '데이터 부족',
                    'debug_info': {'data_length': len(market_data) if market_data is not None else 0}
                }
            
            # 최신 데이터 추출
            latest = market_data.iloc[-1]
            prev = market_data.iloc[-2] if len(market_data) > 1 else latest
            
            # MACD 지표 값
            macd_line = latest.get('macd_12_26_9_line')
            macd_signal_val = latest.get('macd_12_26_9_signal') 
            macd_histogram = latest.get('macd_12_26_9_histogram')
            atr_value = latest.get('atr_14_value')
            
            # 이전 값
            prev_macd_line = prev.get('macd_12_26_9_line')
            prev_macd_signal_val = prev.get('macd_12_26_9_signal')
            prev_macd_histogram = prev.get('macd_12_26_9_histogram')
            
            # 디버그 정보 수집
            debug_info = {
                'current_price': float(latest['close']),
                'macd_line': float(macd_line) if macd_line is not None else None,
                'macd_signal': float(macd_signal_val) if macd_signal_val is not None else None,
                'macd_histogram': float(macd_histogram) if macd_histogram is not None else None,
                'atr_value': float(atr_value) if atr_value is not None else None,
                'prev_macd_line': float(prev_macd_line) if prev_macd_line is not None else None,
                'prev_macd_signal': float(prev_macd_signal_val) if prev_macd_signal_val is not None else None,
                'prev_macd_histogram': float(prev_macd_histogram) if prev_macd_histogram is not None else None,
                'current_position': current_position,
                'data_source': 'backtest' if market_data is not None else 'realtime'
            }
            
            # 지표 값 검증
            if any(x is None for x in [macd_line, macd_signal_val, macd_histogram, atr_value]):
                missing = []
                if macd_line is None: missing.append('MACD_LINE')
                if macd_signal_val is None: missing.append('MACD_SIGNAL')
                if macd_histogram is None: missing.append('MACD_HISTOGRAM')
                if atr_value is None: missing.append('ATR')
                
                return {
                    'signal': 'HOLD',
                    'confidence': 0.0,
                    'reason': f'지표 값 없음: {", ".join(missing)}',
                    'debug_info': debug_info
                }
            
            # 이전 값 검증
            if any(x is None for x in [prev_macd_line, prev_macd_signal_val, prev_macd_histogram]):
                return {
                    'signal': 'HOLD', 
                    'confidence': 0.0,
                    'reason': '이전 지표 값 없음',
                    'debug_info': debug_info
                }
            
            # MACD 크로스오버 확인
            macd_bullish_cross = (prev_macd_line <= prev_macd_signal_val) and (macd_line > macd_signal_val)
            macd_bearish_cross = (prev_macd_line >= prev_macd_signal_val) and (macd_line < macd_signal_val)
            
            # 히스토그램 변화
            histogram_turning_positive = (prev_macd_histogram <= 0) and (macd_histogram > 0)
            histogram_turning_negative = (prev_macd_histogram >= 0) and (macd_histogram < 0)
            
            # ATR 필터 (변동성이 너무 낮으면 제외)
            atr_filter_ok = atr_value > (float(latest['close']) * 0.005)  # 0.5% 이상
            
            # 디버그 정보 추가
            debug_info.update({
                'macd_bullish_cross': macd_bullish_cross,
                'macd_bearish_cross': macd_bearish_cross,
                'histogram_turning_positive': histogram_turning_positive,
                'histogram_turning_negative': histogram_turning_negative,
                'atr_filter_ok': atr_filter_ok,
                'atr_threshold': float(latest['close']) * 0.005
            })
            
            logger.debug(f"{symbol} 시그널 분석: {debug_info}")
            
            # 현재 포지션 없을 때 - 진입 시그널
            if current_position is None:
                # 롱 진입 조건
                if macd_bullish_cross and histogram_turning_positive and atr_filter_ok:
                    return {
                        'signal': 'ENTRY_LONG',
                        'confidence': 0.8,
                        'reason': 'MACD 상향 돌파 + 히스토그램 양전환',
                        'debug_info': debug_info
                    }
                
                # 숏 진입 조건  
                elif macd_bearish_cross and histogram_turning_negative and atr_filter_ok:
                    return {
                        'signal': 'ENTRY_SHORT', 
                        'confidence': 0.8,
                        'reason': 'MACD 하향 돌파 + 히스토그램 음전환',
                        'debug_info': debug_info
                    }
                
                else:
                    reasons = []
                    if not macd_bullish_cross and not macd_bearish_cross:
                        reasons.append('MACD 크로스 없음')
                    if not histogram_turning_positive and not histogram_turning_negative:
                        reasons.append('히스토그램 전환 없음')
                    if not atr_filter_ok:
                        reasons.append('ATR 필터 실패')
                    
                    return {
                        'signal': 'HOLD',
                        'confidence': 0.0,
                        'reason': f"진입 조건 불충족: {', '.join(reasons)}",
                        'debug_info': debug_info
                    }
            
            # 포지션 있을 때 - 청산 시그널
            else:
                if current_position == 'LONG':
                    if macd_bearish_cross or histogram_turning_negative:
                        return {
                            'signal': 'EXIT_LONG',
                            'confidence': 0.7,
                            'reason': 'MACD 하향 전환 또는 히스토그램 음전환',
                            'debug_info': debug_info
                        }
                
                elif current_position == 'SHORT':
                    if macd_bullish_cross or histogram_turning_positive:
                        return {
                            'signal': 'EXIT_SHORT',
                            'confidence': 0.7, 
                            'reason': 'MACD 상향 전환 또는 히스토그램 양전환',
                            'debug_info': debug_info
                        }
                
                return {
                    'signal': 'HOLD',
                    'confidence': 0.0,
                    'reason': f'{current_position} 포지션 유지',
                    'debug_info': debug_info
                }
            
        except Exception as e:
            logger.error(f"{symbol} 시그널 생성 실패: {e}")
            return {
                'signal': 'HOLD',
                'confidence': 0.0,
                'reason': f'오류: {str(e)}',
                'debug_info': {'error': str(e)}
            }
    
    def get_strategy_info(self) -> Dict:
        """전략 정보 반환"""
        return {
            'name': 'MACD_ATR_Strategy',
            'description': 'MACD 크로스오버 + ATR 노이즈 필터 전략',
            'parameters': {
                'macd_fast': self.macd_fast,
                'macd_slow': self.macd_slow,
                'macd_signal': self.macd_signal,
                'atr_period': self.atr_period,
                'atr_multiplier': self.atr_multiplier
            }
        }