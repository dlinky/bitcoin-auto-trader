#!/usr/bin/env python3
"""
MACD + ATR 전략 구현
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
    
    def __init__(self, supabase_client, macd_fast: int = 12, macd_slow: int = 26, 
                 macd_signal: int = 9, atr_period: int = 14, atr_multiplier: float = 2.0):
        """
        MACD + ATR 전략 초기화
        
        Args:
            supabase_client: DB 클라이언트
            macd_fast: MACD 빠른 EMA 기간
            macd_slow: MACD 느린 EMA 기간  
            macd_signal: MACD 시그널 라인 기간
            atr_period: ATR 계산 기간
            atr_multiplier: ATR 필터 배수 (노이즈 필터링용)
        """
        self.db_client = supabase_client
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        
        logger.info(f"MACDATRStrategy 초기화: MACD({macd_fast},{macd_slow},{macd_signal}), ATR({atr_period})")
    
    def generate_signal(self, symbol: str, current_position: Optional[str] = None) -> Dict:
        """
        매매 시그널 생성
        
        Args:
            symbol: 거래 심볼
            current_position: 현재 포지션 상태
            
        Returns:
            매매 시그널 딕셔너리
        """
        try:
            logger.debug(f"{symbol} 시그널 분석 시작 (현재 포지션: {current_position})")
            
            # 최근 지표 데이터 가져오기 (최소 3개 - 현재, 이전, 그 전)
            indicators_data = self._get_latest_indicators(symbol, limit=3)
            
            if len(indicators_data) < 2:
                logger.warning(f"{symbol} 지표 데이터 부족: {len(indicators_data)}개")
                return self._create_hold_signal("지표 데이터 부족")
            
            # 현재와 이전 지표값
            current = indicators_data[-1]  # 가장 최근
            previous = indicators_data[-2]  # 이전
            
            # MACD 크로스오버 확인
            crossover_type = self._check_macd_crossover(current, previous)
            
            # ATR 필터 적용
            atr_filter_passed = self._check_atr_filter(current)
            
            # 시그널 생성 로직
            signal_info = self._determine_signal(
                crossover_type, 
                atr_filter_passed, 
                current_position,
                current,
                previous
            )
            
            logger.debug(f"{symbol} 시그널 생성 완료: {signal_info['signal']}")
            return signal_info
            
        except Exception as e:
            logger.error(f"{symbol} 시그널 생성 중 에러: {e}")
            return self._create_hold_signal(f"에러 발생: {str(e)}")
    
    def _get_latest_indicators(self, symbol: str, limit: int = 3) -> list:
        """
        최신 지표 데이터 조회
        
        Args:
            symbol: 거래 심볼
            limit: 조회할 데이터 개수
            
        Returns:
            지표 데이터 리스트
        """
        try:
            # market_data에서 최신 지표 데이터 조회
            response = self.db_client.client.table('market_data').select(
                'timestamp, close, macd_12_26_9_line, macd_12_26_9_signal, macd_12_26_9_histogram, atr_14_value'
            ).eq('symbol', symbol).order(
                'timestamp', desc=True
            ).limit(limit).execute()
            
            if not response.data:
                logger.warning(f"{symbol} 지표 데이터 없음")
                return []
            
            # 시간 순으로 정렬 (오래된 것부터)
            data = response.data[::-1]
            
            # None 값이 있는 데이터 필터링
            valid_data = []
            for row in data:
                if (row['macd_12_26_9_line'] is not None and 
                    row['macd_12_26_9_signal'] is not None and 
                    row['atr_14_value'] is not None):
                    valid_data.append(row)
            
            logger.debug(f"{symbol} 지표 데이터 조회: {len(valid_data)}개")
            return valid_data
            
        except Exception as e:
            logger.error(f"{symbol} 지표 데이터 조회 실패: {e}")
            return []
    
    def _check_macd_crossover(self, current: Dict, previous: Dict) -> str:
        """
        MACD 크로스오버 확인
        
        Args:
            current: 현재 지표값
            previous: 이전 지표값
            
        Returns:
            'GOLDEN' (골든크로스), 'DEAD' (데드크로스), 'NONE' (변화없음)
        """
        try:
            curr_macd = float(current['macd_12_26_9_line'])
            curr_signal = float(current['macd_12_26_9_signal'])
            prev_macd = float(previous['macd_12_26_9_line'])
            prev_signal = float(previous['macd_12_26_9_signal'])
            
            # 이전: MACD < Signal, 현재: MACD > Signal → 골든크로스
            if prev_macd <= prev_signal and curr_macd > curr_signal:
                logger.debug("MACD 골든크로스 감지")
                return 'GOLDEN'
            
            # 이전: MACD > Signal, 현재: MACD < Signal → 데드크로스
            elif prev_macd >= prev_signal and curr_macd < curr_signal:
                logger.debug("MACD 데드크로스 감지")
                return 'DEAD'
            
            else:
                return 'NONE'
                
        except (ValueError, TypeError) as e:
            logger.error(f"MACD 크로스오버 확인 실패: {e}")
            return 'NONE'
    
    def _check_atr_filter(self, current: Dict) -> bool:
        """
        ATR 필터 확인 (노이즈 필터링)
        
        Args:
            current: 현재 지표값
            
        Returns:
            ATR 필터 통과 여부
        """
        try:
            atr_value = float(current['atr_14_value'])
            close_price = float(current['close'])
            
            # ATR이 종가의 일정 비율 이상이어야 유의미한 움직임으로 판단
            # 예: ATR이 종가의 0.5% 이상
            atr_ratio = (atr_value / close_price) * 100
            min_atr_ratio = 0.3  # 최소 0.3%
            
            filter_passed = atr_ratio >= min_atr_ratio
            
            logger.debug(f"ATR 필터: {atr_ratio:.3f}% (최소: {min_atr_ratio}%) - {'통과' if filter_passed else '차단'}")
            return filter_passed
            
        except (ValueError, TypeError) as e:
            logger.error(f"ATR 필터 확인 실패: {e}")
            return False
    
    def _determine_signal(self, crossover_type: str, atr_filter_passed: bool, 
                         current_position: Optional[str], current: Dict, previous: Dict) -> Dict:
        """
        최종 매매 시그널 결정
        
        Args:
            crossover_type: MACD 크로스오버 타입
            atr_filter_passed: ATR 필터 통과 여부
            current_position: 현재 포지션
            current: 현재 지표값
            previous: 이전 지표값
            
        Returns:
            시그널 정보 딕셔너리
        """
        # ATR 필터 통과하지 못하면 HOLD
        if not atr_filter_passed:
            return self._create_hold_signal("ATR 필터 미통과 (노이즈 필터링)")
        
        # 크로스오버 없으면 HOLD
        if crossover_type == 'NONE':
            return self._create_hold_signal("MACD 크로스오버 없음")
        
        # 포지션 상태에 따른 시그널 결정
        if current_position is None or current_position == 'NONE':
            # 포지션 없는 상태
            if crossover_type == 'GOLDEN':
                return self._create_entry_signal('LONG', crossover_type, current, previous)
            elif crossover_type == 'DEAD':
                return self._create_entry_signal('SHORT', crossover_type, current, previous)
        
        elif current_position == 'LONG':
            # 롱 포지션 보유 중
            if crossover_type == 'DEAD':
                return self._create_exit_signal('LONG', crossover_type, current, previous)
            else:
                return self._create_hold_signal("롱 포지션 유지")
        
        elif current_position == 'SHORT':
            # 숏 포지션 보유 중
            if crossover_type == 'GOLDEN':
                return self._create_exit_signal('SHORT', crossover_type, current, previous)
            else:
                return self._create_hold_signal("숏 포지션 유지")
        
        return self._create_hold_signal("조건 불충족")
    
    def _create_entry_signal(self, direction: str, crossover_type: str, 
                           current: Dict, previous: Dict) -> Dict:
        """진입 시그널 생성"""
        signal_type = f'ENTRY_{direction}'
        confidence = self._calculate_confidence(crossover_type, current, previous)
        
        reason = f"MACD {'골든크로스' if crossover_type == 'GOLDEN' else '데드크로스'} + ATR 필터 통과"
        
        return {
            'signal': signal_type,
            'confidence': confidence,
            'reason': reason,
            'data': {
                'crossover_type': crossover_type,
                'macd_line': current['macd_12_26_9_line'],
                'macd_signal': current['macd_12_26_9_signal'],
                'atr_value': current['atr_14_value'],
                'timestamp': current['timestamp']
            }
        }
    
    def _create_exit_signal(self, direction: str, crossover_type: str, 
                          current: Dict, previous: Dict) -> Dict:
        """청산 시그널 생성"""
        signal_type = f'EXIT_{direction}'
        confidence = self._calculate_confidence(crossover_type, current, previous)
        
        reason = f"MACD {'골든크로스' if crossover_type == 'GOLDEN' else '데드크로스'} - {direction} 포지션 청산"
        
        return {
            'signal': signal_type,
            'confidence': confidence,
            'reason': reason,
            'data': {
                'crossover_type': crossover_type,
                'macd_line': current['macd_12_26_9_line'],
                'macd_signal': current['macd_12_26_9_signal'],
                'atr_value': current['atr_14_value'],
                'timestamp': current['timestamp']
            }
        }
    
    def _create_hold_signal(self, reason: str) -> Dict:
        """대기 시그널 생성"""
        return {
            'signal': 'HOLD',
            'confidence': 0.0,
            'reason': reason,
            'data': {}
        }
    
    def _calculate_confidence(self, crossover_type: str, current: Dict, previous: Dict) -> float:
        """
        시그널 신뢰도 계산
        
        Args:
            crossover_type: 크로스오버 타입
            current: 현재 지표값
            previous: 이전 지표값
            
        Returns:
            신뢰도 (0.0 ~ 1.0)
        """
        try:
            # 기본 신뢰도
            base_confidence = 0.7
            
            # MACD 히스토그램 강도로 신뢰도 조정
            curr_histogram = float(current['macd_12_26_9_histogram'])
            prev_histogram = float(previous['macd_12_26_9_histogram'])
            
            # 히스토그램이 강화되고 있으면 신뢰도 증가
            histogram_strength = abs(curr_histogram) - abs(prev_histogram)
            if histogram_strength > 0:
                base_confidence += min(0.2, histogram_strength * 0.1)
            
            # ATR로 변동성 확인 (높은 변동성 = 높은 신뢰도)
            atr_value = float(current['atr_14_value'])
            close_price = float(current['close'])
            volatility_ratio = (atr_value / close_price) * 100
            
            if volatility_ratio > 1.0:  # 1% 이상 변동성
                base_confidence += 0.1
            elif volatility_ratio < 0.3:  # 0.3% 미만 변동성
                base_confidence -= 0.1
            
            # 0.0 ~ 1.0 범위로 제한
            confidence = max(0.0, min(1.0, base_confidence))
            
            logger.debug(f"신뢰도 계산: {confidence:.2f} (히스토그램 강도: {histogram_strength:.4f}, 변동성: {volatility_ratio:.3f}%)")
            
            return confidence
            
        except (ValueError, TypeError) as e:
            logger.error(f"신뢰도 계산 실패: {e}")
            return 0.5  # 기본값
    
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