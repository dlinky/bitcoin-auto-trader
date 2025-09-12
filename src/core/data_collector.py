#!/usr/bin/env python3
"""
데이터 수집 및 지표 계산 모듈
파일 위치: src/core/data_collector.py
"""

import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from src.utils.logger import get_logger

logger = get_logger(__name__)

class DataCollector:
    """시장 데이터 수집 및 지표 계산"""
    
    def __init__(self, binance_client, supabase_client, symbols: List[str] = ['BTCUSDT']):
        """
        DataCollector 초기화
        
        Args:
            binance_client: BinanceClient 인스턴스
            supabase_client: SupabaseClient 인스턴스
            symbols: 수집할 심볼 리스트
        """
        self.binance_client = binance_client
        self.db_client = supabase_client
        self.symbols = symbols
        
        logger.info(f"DataCollector 초기화 완료 - 대상 심볼: {symbols}")
    
    def ensure_historical_data(self, symbol: str, required_count: int = 200) -> bool:
        """
        과거 데이터 보완 (프로그램 시작시 실행)
        
        Args:
            symbol: 거래 심볼
            required_count: 필요한 캔들 개수
            
        Returns:
            데이터 보완 성공 여부
        """
        try:
            logger.info(f"{symbol} 과거 데이터 보완 시작 (필요: {required_count}개)")
            
            # 누락된 시간 구간 확인
            missing_ranges = self.db_client.get_missing_time_ranges(symbol, required_count)
            
            if not missing_ranges:
                logger.info(f"{symbol} 모든 과거 데이터 존재")
                return True
            
            logger.info(f"{symbol} 누락 구간 {len(missing_ranges)}개 발견")
            
            # 각 누락 구간별로 데이터 수집
            total_collected = 0
            for i, (start_time, end_time) in enumerate(missing_ranges, 1):
                logger.info(f"{symbol} 누락 구간 {i}/{len(missing_ranges)} 처리: {start_time} ~ {end_time}")
                
                # 해당 구간 데이터 수집 및 처리
                collected_count = self._collect_candles_by_range(symbol, start_time, end_time)
                total_collected += collected_count
                
                logger.debug(f"{symbol} 구간 처리 완료: {collected_count}개")
            
            logger.info(f"{symbol} 과거 데이터 보완 완료: {total_collected}개 수집")
            return True
            
        except Exception as e:
            logger.error(f"{symbol} 과거 데이터 보완 실패: {e}")
            return False
    
    def collect_latest_data(self, symbol: str) -> bool:
        """
        최신 데이터 1개 수집 (매분 실행)
        
        Args:
            symbol: 거래 심볼
            
        Returns:
            수집 성공 여부
        """
        try:
            logger.debug(f"{symbol} 최신 데이터 수집 시작")
            
            # 최신 1분봉 데이터 수집 (재시도 포함)
            candles_with_indicators = self._collect_and_calculate_with_retry(symbol, limit=1)
            
            if not candles_with_indicators:
                logger.error(f"{symbol} 최신 데이터 수집 실패")
                return False
            
            # DB 저장 (3단계 재시도)
            success = self.db_client.save_market_data_with_retry(candles_with_indicators)
            
            if success:
                logger.debug(f"{symbol} 최신 데이터 저장 완료")
                return True
            else:
                logger.error(f"{symbol} 최신 데이터 저장 실패")
                return False
                
        except Exception as e:
            logger.error(f"{symbol} 최신 데이터 수집 중 에러: {e}")
            return False
    
    def collect_all_symbols_concurrent(self) -> Dict[str, bool]:
        """
        모든 심볼의 최신 데이터를 동시 수집
        
        Returns:
            심볼별 수집 성공 여부 딕셔너리
        """
        results = {}
        
        try:
            logger.info(f"전체 심볼 동시 데이터 수집 시작: {self.symbols}")
            start_time = time.time()
            
            # 동시 계산 (병렬 처리)
            calculated_data = {}
            with ThreadPoolExecutor(max_workers=min(len(self.symbols), 3)) as executor:
                # 각 심볼별 계산 작업 제출
                future_to_symbol = {
                    executor.submit(self._collect_and_calculate_with_retry, symbol, 1): symbol
                    for symbol in self.symbols
                }
                
                # 계산 결과 수집
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        data = future.result(timeout=8)  # 8초 타임아웃
                        calculated_data[symbol] = data
                        logger.debug(f"{symbol} 계산 완료")
                    except Exception as e:
                        logger.error(f"{symbol} 계산 실패: {e}")
                        calculated_data[symbol] = None
            
            # DB 저장 (순차 처리)
            for symbol in self.symbols:
                if calculated_data[symbol]:
                    try:
                        success = self.db_client.save_market_data_with_retry(calculated_data[symbol])
                        results[symbol] = success
                        if success:
                            logger.debug(f"{symbol} 저장 완료")
                        else:
                            logger.error(f"{symbol} 저장 실패")
                    except Exception as e:
                        logger.error(f"{symbol} 저장 중 에러: {e}")
                        results[symbol] = False
                else:
                    results[symbol] = False
            
            elapsed_time = time.time() - start_time
            success_count = sum(results.values())
            
            logger.info(f"전체 수집 완료: {success_count}/{len(self.symbols)}개 성공 ({elapsed_time:.1f}초)")
            return results
            
        except Exception as e:
            logger.error(f"전체 심볼 수집 중 에러: {e}")
            return {symbol: False for symbol in self.symbols}
    
    def _collect_candles_by_range(self, symbol: str, start_time: datetime, end_time: datetime) -> int:
        """
        특정 시간 구간의 캔들 데이터 수집
        
        Args:
            symbol: 거래 심볼
            start_time: 시작 시간
            end_time: 종료 시간
            
        Returns:
            수집된 캔들 개수
        """
        try:
            # 필요한 캔들 개수 계산
            minutes_needed = int((end_time - start_time).total_seconds() / 60) + 1
            
            # 바이낸스에서 해당 구간 데이터 수집
            # 바이낸스는 최대 1000개까지 한번에 조회 가능
            limit = min(minutes_needed, 1000)
            
            # 종료 시간 기준으로 역순 조회
            df = self.binance_client.get_klines(symbol, '1m', limit)
            
            if df.empty:
                logger.warning(f"{symbol} 구간 데이터 없음: {start_time} ~ {end_time}")
                return 0
            
            # 해당 시간 구간에 해당하는 데이터만 필터링
            df = df[
                (df['timestamp'] >= start_time) & 
                (df['timestamp'] <= end_time)
            ].copy()
            
            if df.empty:
                logger.warning(f"{symbol} 필터링 후 데이터 없음: {start_time} ~ {end_time}")
                return 0
            
            # 지표 계산
            indicators_data = self._calculate_indicators_for_df(df, symbol)
            
            # DB 저장용 데이터 변환
            candles_with_indicators = []
            for _, row in df.iterrows():
                candle_data = {
                    'symbol': symbol,
                    'timestamp': row['timestamp'],
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume']
                }
                
                # 해당 시간의 지표 값 추가
                timestamp_key = row['timestamp']
                if timestamp_key in indicators_data:
                    candle_data.update(indicators_data[timestamp_key])
                
                candles_with_indicators.append(candle_data)
            
            # DB 저장
            if candles_with_indicators:
                self.db_client.save_market_data_with_retry(candles_with_indicators)
            
            return len(candles_with_indicators)
            
        except Exception as e:
            logger.error(f"{symbol} 구간 수집 실패 ({start_time} ~ {end_time}): {e}")
            return 0
    
    def _collect_and_calculate_with_retry(self, symbol: str, limit: int = 200) -> Optional[List[Dict]]:
        """
        데이터 수집 및 지표 계산 (재시도 포함)
        
        Args:
            symbol: 거래 심볼
            limit: 수집할 캔들 개수
            
        Returns:
            지표가 포함된 캔들 데이터 리스트
        """
        for attempt in range(2):  # 2회 시도
            try:
                # 바이낸스에서 데이터 수집
                df = self.binance_client.get_klines(symbol, '1m', limit)
                
                if df.empty:
                    raise ValueError(f"{symbol} 캔들 데이터가 없습니다")
                
                # 지표 계산용으로 더 많은 데이터 필요한 경우
                if limit < 50 and len(df) < 50:
                    # 최신 데이터 계산을 위해 200개 데이터로 지표 계산
                    df_for_indicators = self.binance_client.get_klines(symbol, '1m', 200)
                    indicators_data = self._calculate_indicators_for_df(df_for_indicators, symbol)
                    
                    # 원래 요청한 개수만큼만 반환 데이터 준비
                    result_data = []
                    for _, row in df.tail(limit).iterrows():
                        candle_data = {
                            'symbol': symbol,
                            'timestamp': row['timestamp'],
                            'open': row['open'],
                            'high': row['high'],
                            'low': row['low'],
                            'close': row['close'],
                            'volume': row['volume']
                        }
                        
                        # 지표 값 추가
                        if row['timestamp'] in indicators_data:
                            candle_data.update(indicators_data[row['timestamp']])
                        
                        result_data.append(candle_data)
                    
                    return result_data
                
                else:
                    # 충분한 데이터가 있는 경우 바로 계산
                    indicators_data = self._calculate_indicators_for_df(df, symbol)
                    
                    result_data = []
                    for _, row in df.tail(limit).iterrows():
                        candle_data = {
                            'symbol': symbol,
                            'timestamp': row['timestamp'],
                            'open': row['open'],
                            'high': row['high'],
                            'low': row['low'],
                            'close': row['close'],
                            'volume': row['volume']
                        }
                        
                        if row['timestamp'] in indicators_data:
                            candle_data.update(indicators_data[row['timestamp']])
                        
                        result_data.append(candle_data)
                    
                    return result_data
                
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"{symbol} 데이터 수집/계산 실패 (1차), 재시도: {e}")
                    time.sleep(1)  # 1초 대기 후 재시도
                else:
                    logger.error(f"{symbol} 데이터 수집/계산 최종 실패: {e}")
                    return None
        
        return None
    
    def _calculate_indicators_for_df(self, df: pd.DataFrame, symbol: str) -> Dict[datetime, Dict]:
        """
        DataFrame에 대한 지표 계산
        
        Args:
            df: OHLCV 데이터 DataFrame
            symbol: 심볼명 (로깅용)
            
        Returns:
            {timestamp: {지표명: 값}} 딕셔너리
        """
        try:
            if len(df) < 50:
                logger.warning(f"{symbol} 지표 계산을 위한 데이터 부족: {len(df)}개")
                return {}
            
            # MACD 계산 (12, 26, 9)
            macd = df.ta.macd(fast=12, slow=26, signal=9)
            
            # ATR 계산 (14)
            atr = df.ta.atr(length=14)
            
            # 결과 딕셔너리 생성
            indicators_data = {}
            for i in range(len(df)):
                timestamp = df.iloc[i]['timestamp']
                
                indicator_values = {}
                
                # MACD 값들 추가 (NaN 체크)
                if macd is not None and len(macd.columns) >= 3:
                    macd_line = macd.iloc[i, 0] if not pd.isna(macd.iloc[i, 0]) else None
                    macd_histogram = macd.iloc[i, 1] if not pd.isna(macd.iloc[i, 1]) else None
                    macd_signal = macd.iloc[i, 2] if not pd.isna(macd.iloc[i, 2]) else None
                    
                    if macd_line is not None:
                        indicator_values['macd_12_26_9_line'] = float(macd_line)
                    if macd_histogram is not None:
                        indicator_values['macd_12_26_9_histogram'] = float(macd_histogram)
                    if macd_signal is not None:
                        indicator_values['macd_12_26_9_signal'] = float(macd_signal)
                
                # ATR 값 추가 (NaN 체크)
                if atr is not None and i < len(atr) and not pd.isna(atr.iloc[i]):
                    indicator_values['atr_14_value'] = float(atr.iloc[i])
                
                if indicator_values:  # 지표 값이 있는 경우만 추가
                    indicators_data[timestamp] = indicator_values
            
            logger.debug(f"{symbol} 지표 계산 완료: {len(indicators_data)}개 시점")
            return indicators_data
            
        except Exception as e:
            logger.error(f"{symbol} 지표 계산 실패: {e}")
            return {}