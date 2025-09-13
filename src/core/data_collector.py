#!/usr/bin/env python3
"""
데이터 수집 및 지표 계산 모듈 (다중 심볼 지원 수정)
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
    """시장 데이터 수집 및 지표 계산 (다중 심볼 지원)"""
    
    def __init__(self, binance_client, supabase_client, symbols: Optional[List[str]] = None):
        """
        DataCollector 초기화
        
        Args:
            binance_client: BinanceClient 인스턴스
            supabase_client: SupabaseClient 인스턴스
            symbols: 수집할 심볼 리스트 (None이면 기본값 사용)
        """
        self.binance_client = binance_client
        self.db_client = supabase_client
        
        # 심볼 설정 (하드코딩 제거)
        if symbols is None:
            # 기본 심볼 목록
            self.symbols = ['BTCUSDT']
            logger.info("기본 심볼 사용: ['BTCUSDT']")
        else:
            self.symbols = symbols
            logger.info(f"사용자 지정 심볼: {symbols}")
        
        logger.info(f"DataCollector 초기화 완료 - 대상 심볼: {self.symbols}")
    
    def add_symbol(self, symbol: str):
        """심볼 추가"""
        if symbol not in self.symbols:
            self.symbols.append(symbol)
            logger.info(f"심볼 추가: {symbol}, 현재 심볼 목록: {self.symbols}")
    
    def remove_symbol(self, symbol: str):
        """심볼 제거"""
        if symbol in self.symbols:
            self.symbols.remove(symbol)
            logger.info(f"심볼 제거: {symbol}, 현재 심볼 목록: {self.symbols}")
    
    def set_symbols(self, symbols: List[str]):
        """심볼 목록 설정"""
        self.symbols = symbols
        logger.info(f"심볼 목록 변경: {symbols}")
    
    def ensure_historical_data(self, symbol: str, required_count: int = 200) -> bool:
        """
        과거 데이터 보완 (새로운 효율적 방식)
        
        Args:
            symbol: 거래 심볼
            required_count: 필요한 캔들 개수
            
        Returns:
            데이터 보완 성공 여부
        """
        try:
            logger.info(f"{symbol} 과거 데이터 보완 시작 (필요: {required_count}개)")
            
            # 효율적인 수집 전략 얻기
            strategy = self.db_client.get_collection_strategy(symbol, required_count)
            
            logger.info(f"{symbol} 수집 전략: {strategy['strategy']}, "
                       f"기존: {strategy['existing_count']}개, "
                       f"필요: {strategy['total_needed']}개")
            
            if strategy['strategy'] == 'up_to_date':
                logger.info(f"{symbol} 데이터가 최신 상태")
                return True
            
            # 청크별 데이터 수집
            total_collected = 0
            
            for i, chunk in enumerate(strategy['chunks'], 1):
                logger.info(f"{symbol} 청크 {i}/{len(strategy['chunks'])} 수집: "
                           f"{chunk['start_time']} ({chunk['count']}개)")
                
                collected_count = self._collect_chunk(symbol, chunk['start_time'], chunk['count'])
                total_collected += collected_count
                
                logger.debug(f"{symbol} 청크 {i} 완료: {collected_count}개")
                
                # 청크 간 간격 (API 제한 방지)
                if i < len(strategy['chunks']):
                    time.sleep(0.1)
            
            logger.info(f"{symbol} 과거 데이터 보완 완료: {total_collected}개 수집")
            return total_collected > 0
            
        except Exception as e:
            logger.error(f"{symbol} 과거 데이터 보완 실패: {e}")
            return False
    
    def _collect_chunk(self, symbol: str, start_time: datetime, count: int) -> int:
        """
        특정 시작점에서 지정된 개수만큼 수집 (근본적 수정)
        
        Args:
            symbol: 거래 심볼
            start_time: 시작 시간
            count: 수집할 개수
            
        Returns:
            실제 수집된 개수
        """
        try:
            end_time = start_time + timedelta(minutes=count-1)
            
            logger.debug(f"{symbol} 청크 수집: {start_time} ~ {end_time} ({count}개)")
            
            # 시간 범위 기반 수집 사용
            if count <= 1000:
                # 1000개 이하면 단일 호출
                df = self.binance_client.get_klines_by_time_range(
                    symbol=symbol,
                    interval='1m',
                    start_time=start_time,
                    end_time=end_time
                )
            else:
                # 1000개 초과면 대용량 수집
                df = self.binance_client.get_klines_bulk(
                    symbol=symbol,
                    interval='1m',
                    start_time=start_time,
                    end_time=end_time
                )
            
            if df.empty:
                logger.warning(f"{symbol} 청크 데이터 없음: {start_time} ~ {end_time}")
                return 0
            
            logger.debug(f"{symbol} 청크 수집 완료: {len(df)}개")
            
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
                
                # 지표 값 추가
                if row['timestamp'] in indicators_data:
                    candle_data.update(indicators_data[row['timestamp']])
                
                candles_with_indicators.append(candle_data)
            
            # DB 저장 (upsert 방식)
            if candles_with_indicators:
                logger.info(f"[DATACOLLECTOR] 저장 시도: {len(candles_with_indicators)}개")
                success = self.db_client.save_market_data_with_retry(candles_with_indicators)
                logger.info(f"[DATACOLLECTOR] 저장 결과: {success}")
                if success:
                    logger.debug(f"{symbol} 청크 저장 완료: {len(candles_with_indicators)}개")
                    return len(candles_with_indicators)
                else:
                    logger.error(f"[DATACOLLECTOR] {symbol} 청크 저장 실패")
                    return 0
            
            return 0
            
        except Exception as e:
            logger.error(f"{symbol} 청크 수집 실패: {e}")
            return 0
    
    def ensure_historical_data_all_symbols(self, required_count: int = 200) -> Dict[str, bool]:
        """
        모든 심볼의 과거 데이터 보완
        
        Args:
            required_count: 필요한 캔들 개수
            
        Returns:
            심볼별 보완 성공 여부
        """
        results = {}
        
        logger.info(f"전체 심볼 과거 데이터 보완 시작: {self.symbols}")
        
        for symbol in self.symbols:
            try:
                success = self.ensure_historical_data(symbol, required_count)
                results[symbol] = success
                
                if success:
                    logger.info(f"{symbol} 과거 데이터 보완 성공")
                else:
                    logger.error(f"{symbol} 과거 데이터 보완 실패")
                    
                # 심볼 간 간격 (API 제한 방지)
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"{symbol} 과거 데이터 보완 중 에러: {e}")
                results[symbol] = False
        
        success_count = sum(results.values())
        logger.info(f"전체 과거 데이터 보완 완료: {success_count}/{len(self.symbols)}개 성공")
        
        return results
    
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
    
    def collect_latest_data_for_symbol(self, symbol: str) -> bool:
        """
        특정 심볼의 최신 데이터 수집 (외부 호출용)
        
        Args:
            symbol: 거래 심볼
            
        Returns:
            수집 성공 여부
        """
        return self.collect_latest_data(symbol)
    
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
    
    def collect_specific_symbols(self, symbols: List[str]) -> Dict[str, bool]:
        """
        특정 심볼들의 최신 데이터 수집
        
        Args:
            symbols: 수집할 심볼 리스트
            
        Returns:
            심볼별 수집 성공 여부
        """
        results = {}
        
        try:
            logger.info(f"특정 심볼 데이터 수집: {symbols}")
            
            for symbol in symbols:
                success = self.collect_latest_data(symbol)
                results[symbol] = success
                
                # 심볼 간 간격 (API 제한 방지)
                if len(symbols) > 1:
                    time.sleep(0.1)
            
            success_count = sum(results.values())
            logger.info(f"특정 심볼 수집 완료: {success_count}/{len(symbols)}개 성공")
            
            return results
            
        except Exception as e:
            logger.error(f"특정 심볼 수집 중 에러: {e}")
            return {symbol: False for symbol in symbols}
    
    def _collect_candles_by_range(self, symbol: str, start_time: datetime, end_time: datetime) -> int:
        """
        특정 시간 구간의 캔들 데이터 수집 (get_klines_by_count 사용)
        
        Args:
            symbol: 거래 심볼
            start_time: 시작 시간
            end_time: 종료 시간
            
        Returns:
            수집된 캔들 개수
        """
        try:
            # 필요한 캔들 개수 계산
            total_minutes = int((end_time - start_time).total_seconds() / 60) + 1
            logger.info(f"{symbol} 구간 수집 시작: {start_time} ~ {end_time} ({total_minutes}분)")
            
            # 기존: get_klines (1000개 제한)
            # df = self.binance_client.get_klines(symbol, '1m', limit)
            
            # 수정: get_klines_by_count (자동 대용량 처리)
            df = self.binance_client.get_klines_by_count(symbol, '1m', total_minutes)
            
            if df.empty:
                logger.warning(f"{symbol} 구간 데이터 없음: {start_time} ~ {end_time}")
                return 0
            
            # 시간 범위 필터링 (정확한 범위만)
            df = df[
                (df['timestamp'] >= start_time) & 
                (df['timestamp'] <= end_time)
            ].copy()
            
            if df.empty:
                logger.warning(f"{symbol} 필터링 후 데이터 없음: {start_time} ~ {end_time}")
                return 0
            
            logger.info(f"{symbol} 구간 수집 완료: {len(df)}개")
            
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
        데이터 수집 및 지표 계산 (get_klines_by_count 사용)
        
        Args:
            symbol: 거래 심볼
            limit: 수집할 캔들 개수
            
        Returns:
            지표가 포함된 캔들 데이터 리스트
        """
        for attempt in range(2):  # 2회 시도
            try:
                # 기존: get_klines (1000개 제한)
                # df = self.binance_client.get_klines(symbol, '1m', limit)
                
                # 수정: get_klines_by_count (자동 대용량 처리)
                df = self.binance_client.get_klines_by_count(symbol, '1m', limit)
                
                if df.empty:
                    raise ValueError(f"{symbol} 캔들 데이터가 없습니다")
                
                # 지표 계산용으로 더 많은 데이터 필요한 경우
                if limit < 50 and len(df) < 50:
                    # 최신 데이터 계산을 위해 200개 데이터로 지표 계산
                    df_for_indicators = self.binance_client.get_klines_by_count(symbol, '1m', 200)
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
    
    def get_symbols(self) -> List[str]:
        """현재 설정된 심볼 목록 반환"""
        return self.symbols.copy()
    
    def get_symbol_count(self) -> int:
        """현재 설정된 심볼 개수 반환"""
        return len(self.symbols)