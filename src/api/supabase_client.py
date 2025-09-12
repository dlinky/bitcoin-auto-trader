#!/usr/bin/env python3
"""
Supabase 클라이언트 모듈 (새로 작성)
파일 위치: src/api/supabase_client.py
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
from supabase import create_client, Client
import pandas as pd

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
        """데이터베이스 구조 검증"""
        try:
            logger.info("데이터베이스 구조 검증 시작")
            
            # 연결 테스트
            if not self._test_connection():
                logger.error("데이터베이스 연결 실패")
                return False
            
            # 필수 테이블 확인
            required_tables = ['strategies', 'traders', 'positions', 'trades', 'market_data', 'system_logs']
            missing_tables = []
            
            for table in required_tables:
                if not self._check_table_exists(table):
                    missing_tables.append(table)
            
            if missing_tables:
                logger.warning(f"누락된 테이블: {missing_tables}")
                self._suggest_schema_creation(missing_tables)
                return False
            
            # system_logs의 module_name 컬럼 확인
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
        except Exception:
            return False
    
    def _check_column_exists(self, table_name: str, column_name: str) -> bool:
        """컬럼 존재 확인"""
        try:
            response = self.client.table(table_name).select(column_name).limit(1).execute()
            return True
        except Exception:
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
            logger.error("1. Supabase Dashboard → SQL Editor 이동")
            logger.error(f"2. {schema_file.absolute()} 파일 내용 복사")
            logger.error("3. SQL Editor에서 실행")
        else:
            logger.error("⚠️ database_schema.sql 파일을 찾을 수 없습니다")
        
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
    
    def reconnect(self) -> bool:
        """Supabase 클라이언트 재연결"""
        try:
            logger.info("Supabase 재연결 시도")
            
            # 새로운 클라이언트 인스턴스 생성
            self.client = create_client(self.url, self.key)
            
            # 연결 테스트
            if self._test_connection():
                logger.info("Supabase 재연결 성공")
                return True
            else:
                logger.error("Supabase 재연결 후 연결 테스트 실패")
                return False
                
        except Exception as e:
            logger.error(f"Supabase 재연결 실패: {e}")
            return False
    
    # ===========================================
    # 로그 관련 메서드
    # ===========================================
    
    def save_log(self, module_name: str, level: str, message: str, 
                 trader_id: Optional[int] = None, data: Optional[Dict] = None) -> bool:
        """시스템 로그 저장"""
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
            return len(response.data) > 0
                
        except Exception as e:
            logger.error(f"로그 저장 중 에러: {e}")
            return False
    
    # ===========================================
    # 시장 데이터 관련 메서드
    # ===========================================
    
    def save_market_data_batch(self, market_data_list: List[Dict]) -> bool:
        """
        시장 데이터 배치 저장 (Upsert 방식)
        
        Args:
            market_data_list: 시장 데이터 리스트
            [
                {
                    'symbol': 'BTCUSDT',
                    'timestamp': datetime,
                    'open': 95000.0,
                    'high': 95100.0,
                    'low': 94900.0,
                    'close': 95050.0,
                    'volume': 1234.56,
                    'macd_12_26_9_line': 123.45,  # 지표 (옵션)
                    'atr_14_value': 67.89         # 지표 (옵션)
                }
            ]
            
        Returns:
            저장 성공 여부
        """
        try:
            if not market_data_list:
                logger.warning("저장할 시장 데이터가 없습니다")
                return True
            
            # 데이터 형식 변환
            processed_data = []
            for data in market_data_list:
                processed_row = {
                    'symbol': data['symbol'],
                    'timestamp': data['timestamp'].isoformat() if isinstance(data['timestamp'], datetime) else data['timestamp'],
                    'open': float(data['open']),
                    'high': float(data['high']),
                    'low': float(data['low']),
                    'close': float(data['close']),
                    'volume': float(data['volume'])
                }
                
                # 지표 데이터 추가 (있는 경우만)
                for key, value in data.items():
                    if key not in ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']:
                        if value is not None:
                            processed_row[key] = float(value)
                
                processed_data.append(processed_row)
            
            # Upsert로 배치 저장
            response = self.client.table('market_data').upsert(
                processed_data,
                on_conflict='symbol,timestamp'
            ).execute()
            
            success_count = len(response.data) if response.data else 0
            logger.info(f"시장 데이터 배치 저장 완료: {success_count}개")
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"시장 데이터 배치 저장 중 에러: {e}")
            return False
    
    def save_market_data(self, symbol: str, timestamp: datetime, 
                        ohlcv: Dict, indicators: Optional[Dict] = None) -> bool:
        """시장 데이터 단일 저장"""
        try:
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
            
        except Exception as e:
            logger.error(f"시장 데이터 단일 저장 실패: {e}")
            return False
    
    def save_market_data_with_retry(self, data_list: List[Dict]) -> bool:
        """시장 데이터 저장 (3단계 재시도)"""
        try:
            # 1차 시도
            return self.save_market_data_batch(data_list)
            
        except Exception as e:
            logger.warning(f"시장 데이터 저장 실패 (1차), 재시도: {e}")
            
            try:
                # 2차 시도
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
                    raise Exception(f"시장 데이터 저장 최종 실패: {e3}")
    
    def get_latest_market_data(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        """최신 시장 데이터 조회"""
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
    
    def get_missing_time_ranges(self, symbol: str, required_count: int = 200) -> List[tuple]:
        """누락된 시간 구간 탐지"""
        try:
            # 현재 시각에서 필요한 시간 범위 계산
            now = datetime.now()
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
            
            # 필요한 모든 시간 생성
            required_times = []
            current = start_time
            while current <= current_minute:
                required_times.append(current)
                current += timedelta(minutes=1)
            
            # 누락된 시간 찾기
            existing_times_set = set(existing_times)
            missing_times = [t for t in required_times if t not in existing_times_set]
            
            if not missing_times:
                return []
            
            # 연속된 누락 구간으로 그룹화
            missing_ranges = []
            if missing_times:
                missing_times.sort()
                range_start = missing_times[0]
                range_end = missing_times[0]
                
                for i in range(1, len(missing_times)):
                    if missing_times[i] - missing_times[i-1] == timedelta(minutes=1):
                        range_end = missing_times[i]
                    else:
                        missing_ranges.append((range_start, range_end))
                        range_start = missing_times[i]
                        range_end = missing_times[i]
                
                # 마지막 구간 추가
                missing_ranges.append((range_start, range_end))
            
            logger.debug(f"{symbol} 누락 구간 {len(missing_ranges)}개")
            return missing_ranges
            
        except Exception as e:
            logger.error(f"누락 구간 탐지 중 에러: {e}")
            # 에러시 전체 구간을 누락으로 처리
            now = datetime.now().replace(second=0, microsecond=0)
            start_time = now - timedelta(minutes=required_count - 1)
            return [(start_time, now)]
    
    def get_latest_candle_time(self, symbol: str) -> Optional[datetime]:
        """해당 심볼의 가장 최근 캔들 시간 조회"""
        try:
            response = self.client.table('market_data').select(
                'timestamp'
            ).eq('symbol', symbol).order(
                'timestamp', desc=True
            ).limit(1).execute()
            
            if response.data:
                timestamp_str = response.data[0]['timestamp']
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')).replace(tzinfo=None)
            
            return None
            
        except Exception as e:
            logger.error(f"최근 캔들 시간 조회 중 에러: {e}")
            return None
    
    # ===========================================
    # 거래 및 트레이더 관련 메서드
    # ===========================================
    
    def save_trade(self, trader_id: int, trade_data: Dict) -> bool:
        """거래 내역 저장"""
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
        """트레이더 총 손익 업데이트"""
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
        """트레이더 정보 조회"""
        try:
            response = self.client.table('traders').select('*').eq(
                'id', trader_id
            ).single().execute()
            
            return response.data if response.data else None
            
        except Exception as e:
            logger.error(f"트레이더 정보 조회 중 에러: {e}")
            return None
    
    def get_active_traders(self) -> List[Dict]:
        """활성화된 트레이더 목록 조회"""
        try:
            response = self.client.table('traders').select('*').eq(
                'is_active', True
            ).execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"활성 트레이더 조회 중 에러: {e}")
            return []
    
    # ===========================================
    # 유틸리티 메서드
    # ===========================================
    
    def get_database_info(self) -> Dict:
        """데이터베이스 정보 조회 (디버깅용)"""
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