#!/usr/bin/env python3
"""
Supabase 클라이언트 모듈
파일 위치: src/api/supabase_client.py
"""

import os
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from supabase import create_client, Client
import pandas as pd

# 기본 로거 (나중에 수정될 예정)
logger = logging.getLogger(__name__)

class SupabaseClient:
    """Supabase 데이터베이스 연동 클라이언트"""
    
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """
        Supabase 클라이언트 초기화
        
        Args:
            url: Supabase 프로젝트 URL
            key: Supabase anon key
        """
        self.url = url or os.getenv('SUPABASE_URL')
        self.key = key or os.getenv('SUPABASE_KEY')
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY가 필요합니다")
        
        # Supabase 클라이언트 생성
        self.client: Client = create_client(self.url, self.key)
        
        # 데이터베이스 검증
        if not self._validate_database():
            raise Exception("데이터베이스 검증 실패. 스키마를 확인하거나 생성하세요.")
        
        logger.info("Supabase 클라이언트 초기화 완료")
    
    def _validate_database(self) -> bool:
        """
        데이터베이스 구조 검증
        
        Returns:
            검증 성공 여부
        """
        try:
            logger.info("데이터베이스 구조 검증 시작")
            
            # 1. 연결 테스트
            if not self._test_connection():
                logger.error("데이터베이스 연결 실패")
                return False
            
            # 2. 필수 테이블 존재 확인
            required_tables = [
                'strategies', 'traders', 'positions', 
                'trades', 'market_data', 'system_logs'
            ]
            
            missing_tables = []
            for table in required_tables:
                if not self._check_table_exists(table):
                    missing_tables.append(table)
            
            if missing_tables:
                logger.warning(f"누락된 테이블: {missing_tables}")
                self._suggest_schema_creation(missing_tables)
                return False
            
            # 3. 중요 컬럼 확인 (system_logs의 module_name)
            if not self._check_column_exists('system_logs', 'module_name'):
                logger.warning("system_logs 테이블에 module_name 컬럼이 없습니다")
                self._suggest_schema_update()
                return False
            
            logger.info("데이터베이스 구조 검증 완료")
            return True
            
        except Exception as e:
            logger.error(f"데이터베이스 검증 중 에러: {e}")
            return False
    
    def _test_connection(self) -> bool:
        """데이터베이스 연결 테스트"""
        try:
            # 간단한 쿼리로 연결 테스트
            response = self.client.table('strategies').select('id').limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"연결 테스트 실패: {e}")
            return False
    
    def _check_table_exists(self, table_name: str) -> bool:
        """테이블 존재 확인"""
        try:
            response = self.client.table(table_name).select('*').limit(1).execute()
            return True
        except Exception as e:
            # 테이블이 없으면 예외 발생
            logger.debug(f"테이블 '{table_name}' 확인 결과: {str(e)}")
            return False
    
    def _check_column_exists(self, table_name: str, column_name: str) -> bool:
        """특정 컬럼 존재 확인"""
        try:
            response = self.client.table(table_name).select(column_name).limit(1).execute()
            return True
        except Exception as e:
            logger.debug(f"컬럼 '{table_name}.{column_name}' 확인 결과: {str(e)}")
            return False
    
    def _suggest_schema_creation(self, missing_tables: List[str]):
        """스키마 생성 안내"""
        schema_file = Path('config/database_schema.sql')
        
        logger.error("=" * 50)
        logger.error("📋 데이터베이스 테이블 생성 필요")
        logger.error(f"누락된 테이블: {', '.join(missing_tables)}")
        logger.error("")
        
        if schema_file.exists():
            logger.error("🔧 해결 방법:")
            logger.error(f"1. Supabase Dashboard → SQL Editor 이동")
            logger.error(f"2. {schema_file.absolute()} 파일 내용 복사")
            logger.error(f"3. SQL Editor에서 실행")
        else:
            logger.error("⚠️ database_schema.sql 파일을 찾을 수 없습니다")
            logger.error("프로젝트 루트의 config 폴더를 확인하세요")
        
        logger.error("=" * 50)
    
    def _suggest_schema_update(self):
        """스키마 업데이트 안내"""
        logger.error("=" * 50)
        logger.error("🔄 데이터베이스 스키마 업데이트 필요")
        logger.error("")
        logger.error("다음 SQL을 Supabase에서 실행하세요:")
        logger.error("ALTER TABLE system_logs ADD COLUMN module_name VARCHAR(100);")
        logger.error("UPDATE system_logs SET module_name = 'unknown' WHERE module_name IS NULL;")
        logger.error("ALTER TABLE system_logs ALTER COLUMN module_name SET NOT NULL;")
        logger.error("=" * 50)
    
    def get_database_info(self) -> Dict:
        """
        데이터베이스 정보 조회 (디버깅용)
        
        Returns:
            데이터베이스 상태 정보
        """
        info = {
            'connection': False,
            'tables': {},
            'total_records': 0
        }
        
        try:
            # 연결 테스트
            info['connection'] = self._test_connection()
            
            # 각 테이블 레코드 수 조회
            tables = ['strategies', 'traders', 'positions', 'trades', 'market_data', 'system_logs']
            total_records = 0
            
            for table in tables:
                try:
                    response = self.client.table(table).select('id', count='exact').execute()
                    count = response.count or 0
                    info['tables'][table] = {
                        'exists': True,
                        'records': count
                    }
                    total_records += count
                except Exception:
                    info['tables'][table] = {
                        'exists': False,
                        'records': 0
                    }
            
            info['total_records'] = total_records
            
        except Exception as e:
            logger.error(f"데이터베이스 정보 조회 실패: {e}")
        
        return info
    
    def save_log(self, module_name: str, level: str, message: str, 
                 trader_id: Optional[int] = None, data: Optional[Dict] = None) -> bool:
        """
        시스템 로그 저장
        
        Args:
            module_name: 모듈명
            level: 로그 레벨
            message: 로그 메시지
            trader_id: 트레이더 ID (옵션)
            data: 추가 데이터 (옵션)
            
        Returns:
            저장 성공 여부
        """
        try:
            log_data = {
                'module_name': module_name,
                'level': level,
                'message': message,
                'trader_id': trader_id,
                'data': data,
                'created_at': datetime.now().isoformat()
            }
            
            response = self.client.table('system_logs').insert(log_data).execute()
            
            if response.data:
                return True
            else:
                logger.error(f"로그 저장 실패: {response}")
                return False
                
        except Exception as e:
            logger.error(f"로그 저장 중 에러: {e}")
            return False
    
    def save_market_data(self, symbol: str, timestamp: datetime, 
                        ohlcv: Dict, indicators: Optional[Dict] = None) -> bool:
        """
        시장 데이터 저장
        
        Args:
            symbol: 거래 심볼
            timestamp: 시간
            ohlcv: OHLCV 데이터 {'open', 'high', 'low', 'close', 'volume'}
            indicators: 지표 데이터 (옵션)
            
        Returns:
            저장 성공 여부
        """
        try:
            market_data = {
                'symbol': symbol,
                'timestamp': timestamp.isoformat(),
                'open': float(ohlcv['open']),
                'high': float(ohlcv['high']),
                'low': float(ohlcv['low']),
                'close': float(ohlcv['close']),
                'volume': float(ohlcv['volume'])
            }
            
            # 지표 데이터 추가
            if indicators:
                market_data.update(indicators)
            
            # upsert 사용 (중복 시간 데이터는 업데이트)
            response = self.client.table('market_data').upsert(
                market_data,
                on_conflict='symbol,timestamp'
            ).execute()
            
    def save_market_data(self, symbol: str, timestamp: datetime, 
                        ohlcv: Dict, indicators: Optional[Dict] = None) -> bool:
        """
        시장 데이터 단일 저장 (Upsert 방식)
        
        Args:
            symbol: 거래 심볼
            timestamp: 시간
            ohlcv: OHLCV 데이터 {'open', 'high', 'low', 'close', 'volume'}
            indicators: 지표 데이터 (옵션)
            
        Returns:
            저장 성공 여부
        """
        data = {
            'symbol': symbol,
            'timestamp': timestamp,
            'open': ohlcv['open'],
            'high': ohlcv['high'],
            'low': ohlcv['low'],
            'close': ohlcv['close'],
            'volume': ohlcv['volume']
        }
        
        if indicators:
            data.update(indicators)
        
                    return self.save_market_data_batch([data])
    
    def save_market_data_with_retry(self, data_list: List[Dict]) -> bool:
        """
        시장 데이터 저장 (3단계 재시도)
        
        Args:
            data_list: 저장할 시장 데이터 리스트
            
        Returns:
            저장 성공 여부
        """
        try:
            # 1차 시도: 단순 저장
            return self.save_market_data_batch(data_list)
            
        except Exception as e:
            logger.warning(f"시장 데이터 저장 실패 (1차), 재시도: {e}")
            
            try:
                # 2차 시도: 단순 재시도
                return self.save_market_data_batch(data_list)
                
            except Exception as e2:
                logger.warning(f"시장 데이터 저장 실패 (2차), 재연결 후 시도: {e2}")
                
                try:
                    # 3차 시도: 재연결 후 저장
                    if self.reconnect():
                        return self.save_market_data_batch(data_list)
                    else:
                        raise Exception("재연결 실패")
                        
                except Exception as e3:
                    logger.error(f"시장 데이터 저장 최종 실패: {e3}")
                    raise Exception(f"시장 데이터 저장 최종 실패 (3차 시도 모두 실패): {e3}")
    
    def get_latest_market_data(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        """
        최신 시장 데이터 조회
        
        Args:
            symbol: 거래 심볼
            limit: 조회할 개수
            
        Returns:
            시장 데이터 DataFrame
        """
        try:
            response = self.client.table('market_data').select('*').eq(
                'symbol', symbol
            ).order('timestamp', desc=True).limit(limit).execute()
            
            if response.data:
                df = pd.DataFrame(response.data)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.sort_values('timestamp').reset_index(drop=True)
                return df
            else:
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"시장 데이터 조회 중 에러: {e}")
            return pd.DataFrame()
    
    def get_missing_candles_count(self, symbol: str, required_count: int = 200) -> int:
        """
        부족한 캔들 개수 확인 (연속성 고려)
        
        Args:
            symbol: 거래 심볼
            required_count: 필요한 캔들 개수
            
        Returns:
            부족한 캔들 개수
        """
        try:
            missing_ranges = self.get_missing_time_ranges(symbol, required_count)
            total_missing = sum(
                int((end_time - start_time).total_seconds() / 60) + 1
                for start_time, end_time in missing_ranges
            )
            
            logger.debug(f"{symbol} 캔들 부족 개수: {total_missing}")
            return total_missing
            
        except Exception as e:
            logger.error(f"캔들 개수 조회 중 에러: {e}")
            return required_count  # 에러시 전체 개수 반환
    
    def get_missing_time_ranges(self, symbol: str, required_count: int = 200) -> List[tuple]:
        """
        누락된 시간 구간 탐지
        
        Args:
            symbol: 거래 심볼
            required_count: 필요한 캔들 개수
            
        Returns:
            누락된 시간 구간 리스트 [(start_time, end_time), ...]
        """
        try:
            from datetime import timedelta
            
            # 현재 시각에서 필요한 시간 범위 계산 (1분 간격)
            now = datetime.now()
            # 분/초를 0으로 맞춤 (정확한 1분 간격을 위해)
            current_minute = now.replace(second=0, microsecond=0)
            start_time = current_minute - timedelta(minutes=required_count - 1)
            
            logger.debug(f"{symbol} 필요 시간 범위: {start_time} ~ {current_minute}")
            
            # 해당 시간 범위의 기존 데이터 조회
            response = self.client.table('market_data').select(
                'timestamp'
            ).eq('symbol', symbol).gte(
                'timestamp', start_time.isoformat()
            ).lte(
                'timestamp', current_minute.isoformat()
            ).order('timestamp', desc=False).execute()
            
            existing_times = []
            if response.data:
                existing_times = [
                    datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')).replace(tzinfo=None)
                    for row in response.data
                ]
            
            # 필요한 모든 시간 생성 (1분 간격)
            required_times = []
            current = start_time
            while current <= current_minute:
                required_times.append(current)
                current += timedelta(minutes=1)
            
            # 누락된 시간 찾기
            existing_times_set = set(existing_times)
            missing_times = [t for t in required_times if t not in existing_times_set]
            
            if not missing_times:
                logger.debug(f"{symbol} 모든 캔들 데이터 존재")
                return []
            
            # 연속된 누락 구간으로 그룹화
            missing_ranges = []
            if missing_times:
                missing_times.sort()
                range_start = missing_times[0]
                range_end = missing_times[0]
                
                for i in range(1, len(missing_times)):
                    # 다음 시간이 연속인지 확인 (1분 차이)
                    if missing_times[i] - missing_times[i-1] == timedelta(minutes=1):
                        range_end = missing_times[i]
                    else:
                        # 연속이 끊어지면 이전 구간 저장하고 새 구간 시작
                        missing_ranges.append((range_start, range_end))
                        range_start = missing_times[i]
                        range_end = missing_times[i]
                
                # 마지막 구간 추가
                missing_ranges.append((range_start, range_end))
            
            logger.debug(f"{symbol} 누락 구간 {len(missing_ranges)}개: {missing_ranges}")
            return missing_ranges
            
        except Exception as e:
            logger.error(f"누락 구간 탐지 중 에러: {e}")
            # 에러시 전체 구간을 누락으로 처리
            now = datetime.now().replace(second=0, microsecond=0)
            start_time = now - timedelta(minutes=required_count - 1)
            return [(start_time, now)]
    
    def get_latest_candle_time(self, symbol: str) -> Optional[datetime]:
        """
        해당 심볼의 가장 최근 캔들 시간 조회
        
        Args:
            symbol: 거래 심볼
            
        Returns:
            최근 캔들 시간 (없으면 None)
        """
        try:
            response = self.client.table('market_data').select(
                'timestamp'
            ).eq('symbol', symbol).order(
                'timestamp', desc=True
            ).limit(1).execute()
            
            if response.data:
                timestamp_str = response.data[0]['timestamp']
                # ISO 형식 문자열을 datetime으로 변환
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')).replace(tzinfo=None)
            
            return None
            
        except Exception as e:
            logger.error(f"최근 캔들 시간 조회 중 에러: {e}")
            return None
    
    def save_trade(self, trader_id: int, trade_data: Dict) -> bool:
        """
        거래 내역 저장
        
        Args:
            trader_id: 트레이더 ID
            trade_data: 거래 데이터
            
        Returns:
            저장 성공 여부
        """
        try:
            trade_record = {
                'trader_id': trader_id,
                **trade_data,
                'created_at': datetime.now().isoformat()
            }
            
            response = self.client.table('trades').insert(trade_record).execute()
            return len(response.data) > 0
            
        except Exception as e:
            logger.error(f"거래 내역 저장 중 에러: {e}")
            return False
    
    def update_trader_pnl(self, trader_id: int, total_pnl: float) -> bool:
        """
        트레이더 총 손익 업데이트
        
        Args:
            trader_id: 트레이더 ID
            total_pnl: 총 손익
            
        Returns:
            업데이트 성공 여부
        """
        try:
            response = self.client.table('traders').update({
                'total_pnl': total_pnl,
                'updated_at': datetime.now().isoformat()
            }).eq('id', trader_id).execute()
            
            return len(response.data) > 0
            
        except Exception as e:
            logger.error(f"트레이더 PnL 업데이트 중 에러: {e}")
            return False
    
    def get_trader_info(self, trader_id: int) -> Optional[Dict]:
        """
        트레이더 정보 조회
        
        Args:
            trader_id: 트레이더 ID
            
        Returns:
            트레이더 정보 딕셔너리
        """
        try:
            response = self.client.table('traders').select('*').eq(
                'id', trader_id
            ).single().execute()
            
            return response.data if response.data else None
            
        except Exception as e:
            logger.error(f"트레이더 정보 조회 중 에러: {e}")
            return None
    
    def get_active_traders(self) -> List[Dict]:
        """
        활성화된 트레이더 목록 조회
        
        Returns:
            활성 트레이더 리스트
        """
        try:
            response = self.client.table('traders').select('*').eq(
                'is_active', True
            ).execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"활성 트레이더 조회 중 에러: {e}")
            return []
    
    def _execute_query(self, query: str) -> Any:
        """
        원시 SQL 쿼리 실행 - 내부용
        
        Args:
            query: SQL 쿼리
            
        Returns:
            쿼리 결과
        """
        try:
            # Supabase RPC 기능 사용
            response = self.client.rpc('execute_sql', {'query': query}).execute()
            return response.data
            
        except Exception as e:
            logger.error(f"쿼리 실행 중 에러: {e}")
            return None