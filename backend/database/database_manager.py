"""
Supabase 데이터베이스 매니저
모든 거래 데이터의 CRUD 작업 담당
"""

import os
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date, timedelta
from dataclasses import asdict
import json

try:
    from supabase import create_client, Client
except ImportError:
    print("supabase 패키지가 설치되지 않았습니다. 'pip install supabase' 실행해주세요.")
    exit(1)

from backend.database.models import (
    Trade, Position, TradingSession, RiskEvent, SystemLog, 
    Configuration, PerformanceMetric, CREATE_TABLES_SQL
)

class DatabaseManager:
    """
    Supabase 데이터베이스 관리 클래스
    - 거래 기록 저장/조회
    - 포지션 추적
    - 리스크 이벤트 기록
    - 성과 지표 계산
    - 시스템 로그 관리
    """
    
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        """
        데이터베이스 매니저 초기화
        
        Args:
            supabase_url: Supabase URL (환경변수에서 자동 로드)
            supabase_key: Supabase API Key (환경변수에서 자동 로드)
        """
        self.logger = logging.getLogger(__name__)
        
        # 환경변수에서 설정 로드
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_ANON_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase URL과 API Key가 필요합니다. .env 파일을 확인해주세요.")
        
        # Supabase 클라이언트 초기화
        try:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            self.logger.info("Supabase 데이터베이스 연결 성공")
        except Exception as e:
            self.logger.error(f"Supabase 연결 실패: {e}")
            raise
    
    def initialize_database(self) -> bool:
        """
        데이터베이스 테이블 초기화
        
        Returns:
            bool: 초기화 성공 여부
        """
        try:
            # 테이블 생성 실행
            # Supabase는 SQL 직접 실행을 지원하지 않으므로 
            # 웹 대시보드에서 직접 CREATE_TABLES_SQL을 실행해야 함
            self.logger.info("데이터베이스 테이블 확인 중...")
            
            # 테이블 존재 여부 확인 (간단한 SELECT 쿼리로)
            test_tables = ['trades', 'positions', 'trading_sessions']
            
            for table in test_tables:
                try:
                    result = self.supabase.table(table).select("*").limit(1).execute()
                    self.logger.info(f"테이블 '{table}' 확인 완료")
                except Exception as e:
                    self.logger.error(f"테이블 '{table}' 없음 또는 접근 불가: {e}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"데이터베이스 초기화 실패: {e}")
            return False
    
    # ========== 거래 기록 관리 ==========
    
    def save_trade(self, trade: Trade) -> Optional[str]:
        """
        거래 기록 저장
        
        Args:
            trade: 저장할 거래 정보
            
        Returns:
            str: 저장된 거래 ID
        """
        try:
            trade_data = self._prepare_trade_data(trade)
            
            result = self.supabase.table('trades').insert(trade_data).execute()
            
            if result.data:
                trade_id = result.data[0]['id']
                self.logger.info(f"거래 기록 저장 성공: {trade_id}")
                return trade_id
            else:
                self.logger.error("거래 기록 저장 실패: 응답 데이터 없음")
                return None
                
        except Exception as e:
            self.logger.error(f"거래 기록 저장 실패: {e}")
            return None
    
    def update_trade(self, trade_id: str, updates: Dict[str, Any]) -> bool:
        """거래 기록 업데이트"""
        try:
            updates['updated_at'] = datetime.now().isoformat()
            
            result = self.supabase.table('trades').update(updates).eq('id', trade_id).execute()
            
            if result.data:
                self.logger.info(f"거래 기록 업데이트 성공: {trade_id}")
                return True
            else:
                self.logger.error(f"거래 기록 업데이트 실패: {trade_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"거래 기록 업데이트 실패: {e}")
            return False
    
    def get_trades(self, trader_id: str = "default", 
                   symbol: Optional[str] = None,
                   start_date: Optional[datetime] = None,
                   end_date: Optional[datetime] = None,
                   limit: int = 100) -> List[Dict[str, Any]]:
        """거래 기록 조회"""
        try:
            query = self.supabase.table('trades').select("*").eq('trader_id', trader_id)
            
            if symbol:
                query = query.eq('symbol', symbol)
            
            if start_date:
                query = query.gte('created_at', start_date.isoformat())
            
            if end_date:
                query = query.lte('created_at', end_date.isoformat())
            
            result = query.order('created_at', desc=True).limit(limit).execute()
            
            return result.data or []
            
        except Exception as e:
            self.logger.error(f"거래 기록 조회 실패: {e}")
            return []
    
    # ========== 포지션 관리 ==========
    
    def save_position(self, position: Position) -> Optional[str]:
        """포지션 정보 저장"""
        try:
            position_data = self._prepare_position_data(position)
            
            result = self.supabase.table('positions').insert(position_data).execute()
            
            if result.data:
                position_id = result.data[0]['id']
                self.logger.info(f"포지션 기록 저장 성공: {position_id}")
                return position_id
            else:
                self.logger.error("포지션 기록 저장 실패")
                return None
                
        except Exception as e:
            self.logger.error(f"포지션 기록 저장 실패: {e}")
            return None
    
    def update_position(self, position_id: str, updates: Dict[str, Any]) -> bool:
        """포지션 정보 업데이트"""
        try:
            updates['updated_at'] = datetime.now().isoformat()
            
            result = self.supabase.table('positions').update(updates).eq('id', position_id).execute()
            
            return bool(result.data)
            
        except Exception as e:
            self.logger.error(f"포지션 업데이트 실패: {e}")
            return False
    
    def get_active_positions(self, trader_id: str = "default") -> List[Dict[str, Any]]:
        """활성 포지션 조회"""
        try:
            result = self.supabase.table('positions')\
                .select("*")\
                .eq('trader_id', trader_id)\
                .eq('is_active', True)\
                .order('created_at', desc=True)\
                .execute()
            
            return result.data or []
            
        except Exception as e:
            self.logger.error(f"활성 포지션 조회 실패: {e}")
            return []
    
    # ========== 거래 세션 관리 ==========
    
    def create_trading_session(self, session: TradingSession) -> Optional[str]:
        """거래 세션 생성"""
        try:
            session_data = self._prepare_session_data(session)
            
            result = self.supabase.table('trading_sessions').insert(session_data).execute()
            
            if result.data:
                session_id = result.data[0]['id']
                self.logger.info(f"거래 세션 생성 성공: {session_id}")
                return session_id
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"거래 세션 생성 실패: {e}")
            return None
    
    def end_trading_session(self, session_id: str, final_stats: Dict[str, Any]) -> bool:
        """거래 세션 종료"""
        try:
            updates = {
                **final_stats,
                'is_active': False,
                'ended_at': datetime.now().isoformat()
            }
            
            result = self.supabase.table('trading_sessions').update(updates).eq('id', session_id).execute()
            
            return bool(result.data)
            
        except Exception as e:
            self.logger.error(f"거래 세션 종료 실패: {e}")
            return False
    
    # ========== 리스크 이벤트 기록 ==========
    
    def log_risk_event(self, event: RiskEvent) -> Optional[str]:
        """리스크 이벤트 기록"""
        try:
            event_data = self._prepare_risk_event_data(event)
            
            result = self.supabase.table('risk_events').insert(event_data).execute()
            
            if result.data:
                event_id = result.data[0]['id']
                self.logger.info(f"리스크 이벤트 기록: {event.event_type}")
                return event_id
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"리스크 이벤트 기록 실패: {e}")
            return None
    
    def get_recent_risk_events(self, trader_id: str = "default", hours: int = 24) -> List[Dict[str, Any]]:
        """최근 리스크 이벤트 조회"""
        try:
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            result = self.supabase.table('risk_events')\
                .select("*")\
                .eq('trader_id', trader_id)\
                .gte('created_at', cutoff_time)\
                .order('created_at', desc=True)\
                .execute()
            
            return result.data or []
            
        except Exception as e:
            self.logger.error(f"리스크 이벤트 조회 실패: {e}")
            return []
    
    # ========== 시스템 로그 관리 ==========
    
    def log_system_event(self, log: SystemLog) -> bool:
        """시스템 로그 기록"""
        try:
            log_data = self._prepare_log_data(log)
            
            result = self.supabase.table('system_logs').insert(log_data).execute()
            
            return bool(result.data)
            
        except Exception as e:
            self.logger.error(f"시스템 로그 기록 실패: {e}")
            return False
    
    # ========== 성과 지표 관리 ==========
    
    def save_daily_metrics(self, metrics: PerformanceMetric) -> bool:
        """일일 성과 지표 저장"""
        try:
            metrics_data = self._prepare_metrics_data(metrics)
            
            # 같은 날짜의 기존 데이터 확인
            existing = self.supabase.table('performance_metrics')\
                .select("id")\
                .eq('trader_id', metrics.trader_id)\
                .eq('metric_date', metrics.metric_date.date() if metrics.metric_date else date.today())\
                .execute()
            
            if existing.data:
                # 업데이트
                result = self.supabase.table('performance_metrics')\
                    .update(metrics_data)\
                    .eq('id', existing.data[0]['id'])\
                    .execute()
            else:
                # 신규 생성
                result = self.supabase.table('performance_metrics').insert(metrics_data).execute()
            
            return bool(result.data)
            
        except Exception as e:
            self.logger.error(f"성과 지표 저장 실패: {e}")
            return False
    
    def get_performance_summary(self, trader_id: str = "default", 
                              days: int = 30) -> Dict[str, Any]:
        """성과 요약 조회"""
        try:
            cutoff_date = (date.today() - timedelta(days=days)).isoformat()
            
            result = self.supabase.table('performance_metrics')\
                .select("*")\
                .eq('trader_id', trader_id)\
                .gte('metric_date', cutoff_date)\
                .order('metric_date', desc=True)\
                .execute()
            
            metrics = result.data or []
            
            if not metrics:
                return {}
            
            # 요약 통계 계산
            total_pnl = sum(m['daily_pnl'] for m in metrics)
            total_trades = sum(m['total_trades_today'] for m in metrics)
            winning_trades = sum(m['winning_trades_today'] for m in metrics)
            
            return {
                'period_days': days,
                'total_pnl': total_pnl,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'win_rate': (winning_trades / total_trades * 100) if total_trades > 0 else 0,
                'avg_daily_pnl': total_pnl / len(metrics),
                'best_day': max(m['daily_pnl'] for m in metrics),
                'worst_day': min(m['daily_pnl'] for m in metrics),
                'max_drawdown': max(m['max_drawdown'] for m in metrics),
                'current_balance': metrics[0]['account_balance'] if metrics else 0,
                'data_points': len(metrics)
            }
            
        except Exception as e:
            self.logger.error(f"성과 요약 조회 실패: {e}")
            return {}
    
    # ========== 설정 관리 ==========
    
    def save_configuration(self, config: Configuration) -> bool:
        """설정 저장"""
        try:
            config_data = self._prepare_config_data(config)
            
            # 기존 동일한 설정이 있는지 확인
            existing = self.supabase.table('configurations')\
                .select("id")\
                .eq('trader_id', config.trader_id)\
                .eq('config_type', config.config_type)\
                .eq('config_name', config.config_name)\
                .eq('is_active', True)\
                .execute()
            
            if existing.data:
                # 기존 설정을 비활성화
                self.supabase.table('configurations')\
                    .update({'is_active': False})\
                    .eq('id', existing.data[0]['id'])\
                    .execute()
            
            # 새 설정 저장
            result = self.supabase.table('configurations').insert(config_data).execute()
            
            return bool(result.data)
            
        except Exception as e:
            self.logger.error(f"설정 저장 실패: {e}")
            return False
    
    def get_configuration(self, trader_id: str, config_type: str, config_name: str) -> Optional[Dict[str, Any]]:
        """설정 조회"""
        try:
            result = self.supabase.table('configurations')\
                .select("*")\
                .eq('trader_id', trader_id)\
                .eq('config_type', config_type)\
                .eq('config_name', config_name)\
                .eq('is_active', True)\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            if result.data:
                config = result.data[0]
                # JSON 문자열을 딕셔너리로 파싱
                if isinstance(config.get('config_data'), str):
                    config['config_data'] = json.loads(config['config_data'])
                return config
            else:
                return None
            
        except Exception as e:
            self.logger.error(f"설정 조회 실패: {e}")
            return None
    
    # ========== 유틸리티 메서드 ==========
    
    def _prepare_trade_data(self, trade: Trade) -> Dict[str, Any]:
        """거래 데이터 준비"""
        data = asdict(trade)
        
        # None 값 제거 및 datetime 변환
        cleaned_data = {}
        for key, value in data.items():
            if key == 'id' and value is None:
                continue
            elif key in ['created_at', 'updated_at'] and value:
                cleaned_data[key] = value.isoformat() if isinstance(value, datetime) else value
            elif value is not None:
                cleaned_data[key] = value
        
        # 기본값 설정
        if 'created_at' not in cleaned_data:
            cleaned_data['created_at'] = datetime.now().isoformat()
        if 'updated_at' not in cleaned_data:
            cleaned_data['updated_at'] = datetime.now().isoformat()
        
        return cleaned_data
    
    def _prepare_position_data(self, position: Position) -> Dict[str, Any]:
        """포지션 데이터 준비"""
        data = asdict(position)
        
        cleaned_data = {}
        for key, value in data.items():
            if key == 'id' and value is None:
                continue
            elif key in ['created_at', 'updated_at', 'closed_at'] and value:
                cleaned_data[key] = value.isoformat() if isinstance(value, datetime) else value
            elif value is not None:
                cleaned_data[key] = value
        
        # 기본값 설정
        if 'created_at' not in cleaned_data:
            cleaned_data['created_at'] = datetime.now().isoformat()
        if 'updated_at' not in cleaned_data:
            cleaned_data['updated_at'] = datetime.now().isoformat()
        
        return cleaned_data
    
    def _prepare_session_data(self, session: TradingSession) -> Dict[str, Any]:
        """세션 데이터 준비"""
        data = asdict(session)
        
        cleaned_data = {}
        for key, value in data.items():
            if key == 'id' and value is None:
                continue
            elif key in ['started_at', 'ended_at'] and value:
                cleaned_data[key] = value.isoformat() if isinstance(value, datetime) else value
            elif value is not None:
                cleaned_data[key] = value
        
        # 기본값 설정
        if 'started_at' not in cleaned_data:
            cleaned_data['started_at'] = datetime.now().isoformat()
        
        return cleaned_data
    
    def _prepare_risk_event_data(self, event: RiskEvent) -> Dict[str, Any]:
        """리스크 이벤트 데이터 준비"""
        data = asdict(event)
        
        cleaned_data = {}
        for key, value in data.items():
            if key == 'id' and value is None:
                continue
            elif key == 'created_at' and value:
                cleaned_data[key] = value.isoformat() if isinstance(value, datetime) else value
            elif value is not None:
                cleaned_data[key] = value
        
        # 기본값 설정
        if 'created_at' not in cleaned_data:
            cleaned_data['created_at'] = datetime.now().isoformat()
        
        return cleaned_data
    
    def _prepare_log_data(self, log: SystemLog) -> Dict[str, Any]:
        """로그 데이터 준비"""
        data = asdict(log)
        
        cleaned_data = {}
        for key, value in data.items():
            if key == 'id' and value is None:
                continue
            elif key == 'created_at' and value:
                cleaned_data[key] = value.isoformat() if isinstance(value, datetime) else value
            elif key == 'data' and value:
                cleaned_data[key] = json.dumps(value) if not isinstance(value, str) else value
            elif value is not None:
                cleaned_data[key] = value
        
        # 기본값 설정
        if 'created_at' not in cleaned_data:
            cleaned_data['created_at'] = datetime.now().isoformat()
        
        return cleaned_data
    
    def _prepare_metrics_data(self, metrics: PerformanceMetric) -> Dict[str, Any]:
        """성과 지표 데이터 준비"""
        data = asdict(metrics)
        
        cleaned_data = {}
        for key, value in data.items():
            if key == 'id' and value is None:
                continue
            elif key == 'metric_date' and value:
                if isinstance(value, datetime):
                    cleaned_data[key] = value.date().isoformat()
                elif isinstance(value, date):
                    cleaned_data[key] = value.isoformat()
                else:
                    cleaned_data[key] = value
            elif key == 'created_at' and value:
                cleaned_data[key] = value.isoformat() if isinstance(value, datetime) else value
            elif value is not None:
                cleaned_data[key] = value
        
        # 기본값 설정
        if 'metric_date' not in cleaned_data:
            cleaned_data['metric_date'] = date.today().isoformat()
        if 'created_at' not in cleaned_data:
            cleaned_data['created_at'] = datetime.now().isoformat()
        
        return cleaned_data
    
    def _prepare_config_data(self, config: Configuration) -> Dict[str, Any]:
        """설정 데이터 준비"""
        data = asdict(config)
        
        cleaned_data = {}
        for key, value in data.items():
            if key == 'id' and value is None:
                continue
            elif key in ['created_at', 'updated_at'] and value:
                cleaned_data[key] = value.isoformat() if isinstance(value, datetime) else value
            elif key == 'config_data' and value:
                cleaned_data[key] = json.dumps(value) if not isinstance(value, str) else value
            elif value is not None:
                cleaned_data[key] = value
        
        # 기본값 설정
        if 'created_at' not in cleaned_data:
            cleaned_data['created_at'] = datetime.now().isoformat()
        if 'updated_at' not in cleaned_data:
            cleaned_data['updated_at'] = datetime.now().isoformat()
        
        return cleaned_data
    
    # ========== 통계 및 분석 메서드 ==========
    
    def get_trading_statistics(self, trader_id: str = "default", 
                             days: int = 30) -> Dict[str, Any]:
        """거래 통계 조회"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            # 거래 데이터 조회
            trades = self.supabase.table('trades')\
                .select("*")\
                .eq('trader_id', trader_id)\
                .gte('created_at', cutoff_date)\
                .order('created_at', desc=True)\
                .execute().data or []
            
            if not trades:
                return {'message': '거래 데이터 없음'}
            
            # 통계 계산
            total_trades = len(trades)
            filled_trades = [t for t in trades if t['status'] == 'FILLED']
            
            # 기본 통계
            stats = {
                'period_days': days,
                'total_trades': total_trades,
                'filled_trades': len(filled_trades),
                'cancelled_trades': len([t for t in trades if t['status'] == 'CANCELLED']),
                'success_rate': (len(filled_trades) / total_trades * 100) if total_trades > 0 else 0,
            }
            
            if filled_trades:
                # 거래량 통계
                total_volume = sum(float(t['executed_quantity']) * float(t['executed_price']) for t in filled_trades)
                avg_trade_size = total_volume / len(filled_trades)
                
                stats.update({
                    'total_volume': total_volume,
                    'average_trade_size': avg_trade_size,
                    'largest_trade': max(float(t['executed_quantity']) * float(t['executed_price']) for t in filled_trades),
                    'smallest_trade': min(float(t['executed_quantity']) * float(t['executed_price']) for t in filled_trades),
                })
                
                # 심볼별 통계
                symbols = {}
                for trade in filled_trades:
                    symbol = trade['symbol']
                    if symbol not in symbols:
                        symbols[symbol] = {'count': 0, 'volume': 0}
                    symbols[symbol]['count'] += 1
                    symbols[symbol]['volume'] += float(trade['executed_quantity']) * float(trade['executed_price'])
                
                stats['symbols'] = symbols
            
            return stats
            
        except Exception as e:
            self.logger.error(f"거래 통계 조회 실패: {e}")
            return {'error': str(e)}
    
    def cleanup_old_data(self, days_to_keep: int = 90) -> Dict[str, int]:
        """오래된 데이터 정리"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
            
            cleanup_results = {}
            
            # 오래된 시스템 로그 삭제
            logs_result = self.supabase.table('system_logs')\
                .delete()\
                .lt('created_at', cutoff_date)\
                .execute()
            
            cleanup_results['deleted_logs'] = len(logs_result.data) if logs_result.data else 0
            
            # 오래된 리스크 이벤트 삭제 (WARNING 레벨 이하만)
            risk_result = self.supabase.table('risk_events')\
                .delete()\
                .lt('created_at', cutoff_date)\
                .in_('risk_level', ['LOW', 'MEDIUM'])\
                .execute()
            
            cleanup_results['deleted_risk_events'] = len(risk_result.data) if risk_result.data else 0
            
            # 비활성 포지션 중 오래된 것들 삭제
            positions_result = self.supabase.table('positions')\
                .delete()\
                .eq('is_active', False)\
                .lt('updated_at', cutoff_date)\
                .execute()
            
            cleanup_results['deleted_positions'] = len(positions_result.data) if positions_result.data else 0
            
            self.logger.info(f"데이터 정리 완료: {cleanup_results}")
            return cleanup_results
            
        except Exception as e:
            self.logger.error(f"데이터 정리 실패: {e}")
            return {'error': str(e)}
    
    def health_check(self) -> Dict[str, Any]:
        """데이터베이스 상태 확인"""
        try:
            health = {
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'tables': {}
            }
            
            # 각 테이블 상태 확인
            tables = ['trades', 'positions', 'trading_sessions', 'risk_events', 'system_logs', 'performance_metrics']
            
            for table in tables:
                try:
                    result = self.supabase.table(table).select("count", count="exact").execute()
                    health['tables'][table] = {
                        'accessible': True,
                        'count': result.count
                    }
                except Exception as e:
                    health['tables'][table] = {
                        'accessible': False,
                        'error': str(e)
                    }
                    health['status'] = 'degraded'
            
            return health
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }