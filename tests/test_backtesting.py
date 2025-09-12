#!/usr/bin/env python3
"""
백테스팅 시스템 테스트
파일 위치: tests/test_backtesting.py
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from dotenv import load_dotenv

# 루트 디렉토리를 Python 경로에 추가
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.backtesting.backtester import Backtester, BacktestResult
from src.backtesting.performance_analyzer import PerformanceAnalyzer
from src.backtesting.backtest_reporter import BacktestReporter

class TestBacktester:
    """Backtester 단위 테스트"""
    
    @pytest.fixture
    def sample_market_data(self):
        """테스트용 시장 데이터 생성"""
        dates = pd.date_range(start='2025-01-01', periods=100, freq='1H')
        
        # 가상의 시장 데이터 생성 (상승 트렌드)
        np.random.seed(42)  # 재현 가능한 랜덤
        price = 50000.0
        data = []
        
        for i, date in enumerate(dates):
            # 랜덤 워크 + 약간의 상승 편향
            change = np.random.normal(0.001, 0.02)  # 평균 0.1% 상승, 2% 변동성
            price *= (1 + change)
            
            # OHLCV 생성
            high = price * (1 + abs(np.random.normal(0, 0.01)))
            low = price * (1 - abs(np.random.normal(0, 0.01)))
            volume = np.random.uniform(100, 1000)
            
            # 간단한 지표 추가
            data.append({
                'timestamp': date,
                'open': price,
                'high': high,
                'low': low,
                'close': price,
                'volume': volume,
                'macd_12_26_9_line': np.sin(i * 0.1) * 100,  # 가상 MACD
                'macd_12_26_9_signal': np.sin(i * 0.1 - 0.2) * 100,
                'atr_14_value': price * 0.02  # 가상 ATR
            })
        
        return pd.DataFrame(data)
    
    @pytest.fixture
    def mock_strategy(self):
        """테스트용 모의 전략"""
        strategy = Mock()
        
        # 매수/매도 신호를 번갈아가며 생성
        signal_cycle = [
            {'signal': 'ENTRY_LONG', 'confidence': 0.8, 'reason': 'Test buy signal'},
            {'signal': 'HOLD', 'confidence': 0.5, 'reason': 'Test hold'},
            {'signal': 'HOLD', 'confidence': 0.5, 'reason': 'Test hold'},
            {'signal': 'EXIT_LONG', 'confidence': 0.7, 'reason': 'Test sell signal'},
            {'signal': 'HOLD', 'confidence': 0.5, 'reason': 'Test hold'}
        ]
        
        strategy.generate_signal.side_effect = lambda symbol, position: signal_cycle[
            strategy.generate_signal.call_count % len(signal_cycle)
        ]
        
        return strategy
    
    def test_backtester_initialization(self):
        """백테스터 초기화 테스트"""
        backtester = Backtester(initial_capital=10000.0, commission_rate=0.001)
        
        assert backtester.initial_capital == 10000.0
        assert backtester.commission_rate == 0.001
        assert backtester.current_capital == 10000.0
        assert backtester.current_position is None
        assert backtester.trades == []
        assert backtester.equity_curve == []
    
    def test_market_data_validation(self, sample_market_data):
        """시장 데이터 검증 테스트"""
        backtester = Backtester()
        
        # 정상 데이터
        assert backtester._validate_market_data(sample_market_data) is True
        
        # 컬럼 누락 데이터
        invalid_data = sample_market_data.drop(columns=['close'])
        assert backtester._validate_market_data(invalid_data) is False
        
        # 데이터 부족
        short_data = sample_market_data.head(10)
        assert backtester._validate_market_data(short_data) is False
    
    def test_backtest_execution(self, sample_market_data, mock_strategy):
        """백테스트 실행 테스트"""
        backtester = Backtester(initial_capital=10000.0)
        
        result = backtester.run_backtest(mock_strategy, sample_market_data, "BTCUSDT")
        
        # 결과 검증
        assert isinstance(result, BacktestResult)
        assert result.symbol == "BTCUSDT"
        assert result.initial_capital == 10000.0
        assert result.final_capital > 0
        assert len(result.trades) > 0
        assert not result.equity_curve.empty
    
    def test_position_management(self, mock_strategy):
        """포지션 관리 테스트"""
        backtester = Backtester(initial_capital=10000.0)
        
        # 초기 상태
        assert backtester.current_position is None
        
        # 포지션 진입
        signal = {'signal': 'ENTRY_LONG', 'confidence': 0.8, 'reason': 'Test'}
        backtester._open_position(signal, 50000.0, datetime.now())
        
        assert backtester.current_position is not None
        assert backtester.current_position.side == 'LONG'
        assert backtester.current_position.entry_price == 50000.0
        assert len(backtester.trades) == 1
        
        # 포지션 청산
        backtester._close_position(51000.0, datetime.now(), "Test exit")
        
        assert backtester.current_position is None
        assert len(backtester.trades) == 2  # 진입 + 청산
        
        # 수익 확인 (51000 - 50000 = 1000 이익, 수수료 제외)
        assert backtester.current_capital > 10000.0


class TestPerformanceAnalyzer:
    """PerformanceAnalyzer 단위 테스트"""
    
    @pytest.fixture
    def sample_backtest_result(self):
        """테스트용 백테스트 결과"""
        from src.backtesting.backtester import BacktestTrade
        
        # 간단한 자본 곡선 데이터
        equity_data = []
        dates = pd.date_range(start='2025-01-01', periods=30, freq='D')
        
        for i, date in enumerate(dates):
            value = 10000 + i * 100 + np.sin(i * 0.1) * 500  # 상승 + 변동
            equity_data.append({
                'timestamp': date,
                'capital': 9000 + i * 50,
                'unrealized_pnl': np.sin(i * 0.1) * 500,
                'total_value': value,
                'position': 'LONG' if i % 4 < 2 else None
            })
        
        equity_curve = pd.DataFrame(equity_data)
        
        # 거래 내역
        trades = [
            BacktestTrade(
                timestamp=dates[5],
                action='BUY',
                position_side='LONG',
                price=50000.0,
                quantity=0.2,
                trade_type='ENTRY',
                signal_data={'reason': 'Test entry'}
            ),
            BacktestTrade(
                timestamp=dates[10],
                action='SELL',
                position_side='LONG',
                price=51000.0,
                quantity=0.2,
                trade_type='EXIT',
                signal_data={'reason': 'Test exit', 'pnl': 200.0}
            )
        ]
        
        result = BacktestResult(
            strategy_name="TestStrategy",
            symbol="BTCUSDT",
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=10000.0,
            final_capital=12900.0,
            total_return=2900.0,
            total_return_pct=29.0,
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            win_rate=100.0,
            avg_win=200.0,
            avg_loss=0.0,
            max_drawdown=500.0,
            max_drawdown_pct=5.0,
            sharpe_ratio=1.5,
            trades=trades,
            equity_curve=equity_curve
        )
        
        return result
    
    def test_analyzer_initialization(self):
        """분석기 초기화 테스트"""
        analyzer = PerformanceAnalyzer()
        assert analyzer is not None
    
    def test_performance_analysis(self, sample_backtest_result):
        """성과 분석 테스트"""
        analyzer = PerformanceAnalyzer()
        analysis = analyzer.analyze_performance(sample_backtest_result)
        
        # 분석 결과 구조 확인
        assert 'basic_metrics' in analysis
        assert 'risk_metrics' in analysis
        assert 'trade_analysis' in analysis
        assert 'time_analysis' in analysis
        assert 'monthly_returns' in analysis
        assert 'charts' in analysis
        
        # 기본 지표 확인
        basic = analysis['basic_metrics']
        assert 'total_return_pct' in basic
        assert 'annual_return' in basic
        assert 'duration_days' in basic
        
        # 거래 분석 확인
        trade = analysis['trade_analysis']
        assert trade['total_trades'] == 1
        assert trade['winning_trades'] == 1
        assert trade['win_rate'] == 100.0
    
    def test_summary_report_generation(self, sample_backtest_result):
        """요약 리포트 생성 테스트"""
        analyzer = PerformanceAnalyzer()
        analysis = analyzer.analyze_performance(sample_backtest_result)
        
        report = analyzer.generate_summary_report(sample_backtest_result, analysis)
        
        assert isinstance(report, str)
        assert len(report) > 0
        assert "TestStrategy" in report
        assert "BTCUSDT" in report
        assert "29.00%" in report  # 수익률


class TestBacktestReporter:
    """BacktestReporter 단위 테스트"""
    
    @pytest.fixture
    def mock_slack_client(self):
        """Slack 클라이언트 모킹"""
        mock_client = Mock()
        mock_client.send_message.return_value = True
        return mock_client
    
    def test_reporter_initialization(self, mock_slack_client):
        """리포터 초기화 테스트"""
        reporter = BacktestReporter(mock_slack_client)
        
        assert reporter.slack_client == mock_slack_client
        assert reporter.analyzer is not None
    
    def test_report_block_creation(self, mock_slack_client, sample_backtest_result):
        """리포트 블록 생성 테스트"""
        reporter = BacktestReporter(mock_slack_client)
        analysis = reporter.analyzer.analyze_performance(sample_backtest_result)
        
        blocks = reporter._create_main_report_blocks(sample_backtest_result, analysis)
        
        assert isinstance(blocks, list)
        assert len(blocks) > 0
        
        # 헤더 블록 확인
        header_block = blocks[0]
        assert header_block['type'] == 'header'
        assert 'text' in header_block
    
    def test_quick_summary(self, mock_slack_client, sample_backtest_result):
        """간단 요약 전송 테스트"""
        reporter = BacktestReporter(mock_slack_client)
        
        result = reporter.send_quick_summary(sample_backtest_result)
        
        assert result is True
        assert mock_slack_client.send_message.called


class TestBacktestingIntegration:
    """백테스팅 시스템 통합 테스트"""
    
    def setup_method(self):
        """테스트 셋업"""
        # .env 파일 로드
        env_path = project_root / 'config' / '.env'
        if env_path.exists():
            load_dotenv(env_path)
        
        # 실제 환경변수가 설정되어 있는지 확인
        if not os.getenv('SUPABASE_URL') or not os.getenv('SUPABASE_KEY'):
            pytest.skip("Supabase 환경변수가 설정되지 않음")
    
    @pytest.fixture
    def real_strategy(self):
        """실제 전략 인스턴스"""
        from src.strategies.macd_atr import MACDATRStrategy
        return MACDATRStrategy()
    
    def test_end_to_end_backtest(self, real_strategy):
        """실제 데이터를 이용한 종단간 백테스트"""
        try:
            from src.api.supabase_client import SupabaseClient
            
            # Supabase 클라이언트 생성
            supabase_client = SupabaseClient()
            
            # 최근 7일 데이터 조회
            end_time = datetime.now()
            start_time = end_time - timedelta(days=7)
            
            response = supabase_client.client.table('market_data').select('*').eq(
                'symbol', 'BTCUSDT'
            ).gte(
                'timestamp', start_time.isoformat()
            ).order('timestamp', desc=False).limit(1000).execute()
            
            if not response.data or len(response.data) < 100:
                pytest.skip("충분한 시장 데이터가 없음")
            
            # DataFrame 변환
            market_data = pd.DataFrame(response.data)
            market_data['timestamp'] = pd.to_datetime(market_data['timestamp'])
            
            # 백테스트 실행
            backtester = Backtester(initial_capital=10000.0)
            result = backtester.run_backtest(real_strategy, market_data, "BTCUSDT")
            
            # 결과 검증
            assert isinstance(result, BacktestResult)
            assert result.symbol == "BTCUSDT"
            assert result.initial_capital == 10000.0
            assert result.final_capital > 0
            
            # 성과 분석
            analyzer = PerformanceAnalyzer()
            analysis = analyzer.analyze_performance(result)
            
            assert 'basic_metrics' in analysis
            assert 'risk_metrics' in analysis
            
            print(f"✅ 실제 백테스트 완료: 수익률 {result.total_return_pct:.2f}%")
            
        except Exception as e:
            pytest.fail(f"종단간 백테스트 실패: {e}")


if __name__ == "__main__":
    """
    테스트 실행 방법:
    
    1. 단위 테스트만 실행:
       python -m pytest tests/test_backtesting.py::TestBacktester -v
    
    2. 통합 테스트 (실제 데이터 필요):
       python -m pytest tests/test_backtesting.py::TestBacktestingIntegration -v -s
    
    3. 모든 테스트 실행:
       python -m pytest tests/test_backtesting.py -v -s
    
    4. 수동 테스트:
       python tests/test_backtesting.py
    """
    
    # 간단한 수동 테스트
    print("=== 백테스팅 시스템 수동 테스트 ===")
    
    try:
        # 1. 백테스터 기본 테스트
        print("1. Backtester 테스트...")
        backtester = Backtester(initial_capital=10000.0)
        
        # 샘플 데이터 생성
        dates = pd.date_range(start='2025-01-01', periods=50, freq='1H')
        sample_data = []
        price = 50000.0
        
        for date in dates:
            price *= (1 + np.random.normal(0, 0.01))
            sample_data.append({
                'timestamp': date,
                'open': price,
                'high': price * 1.01,
                'low': price * 0.99,
                'close': price,
                'volume': 100.0,
                'macd_12_26_9_line': 0.0,
                'atr_14_value': price * 0.02
            })
        
        market_data = pd.DataFrame(sample_data)
        
        # 모의 전략
        mock_strategy = Mock()
        signals = [
            {'signal': 'ENTRY_LONG', 'confidence': 0.8, 'reason': 'Test'},
            {'signal': 'HOLD', 'confidence': 0.5, 'reason': 'Hold'},
            {'signal': 'EXIT_LONG', 'confidence': 0.7, 'reason': 'Exit'}
        ]
        mock_strategy.generate_signal.side_effect = lambda s, p: signals[
            mock_strategy.generate_signal.call_count % len(signals)
        ]
        
        # 백테스트 실행
        result = backtester.run_backtest(mock_strategy, market_data, "TESTUSDT")
        print(f"   수익률: {result.total_return_pct:.2f}%")
        print("✅ Backtester 테스트 완료")
        
        # 2. 성과 분석기 테스트
        print("2. PerformanceAnalyzer 테스트...")
        analyzer = PerformanceAnalyzer()
        analysis = analyzer.analyze_performance(result)
        
        assert 'basic_metrics' in analysis
        print(f"   분석 카테고리: {list(analysis.keys())}")
        print("✅ PerformanceAnalyzer 테스트 완료")
        
        # 3. 리포터 테스트 (Slack 없이)
        print("3. BacktestReporter 테스트...")
        reporter = BacktestReporter(slack_client=None)
        
        # 요약 리포트 생성
        summary = analyzer.generate_summary_report(result, analysis)
        assert len(summary) > 0
        print("✅ BacktestReporter 테스트 완료")
        
        print("\n=== 모든 수동 테스트 완료 ===")
        
    except Exception as e:
        print(f"❌ 수동 테스트 실패: {e}")
        sys.exit(1)