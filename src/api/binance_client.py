import time
import logging
from typing import Dict, List, Optional, Tuple
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
import pandas as pd
from decimal import Decimal, ROUND_DOWN
from src.utils.logger import get_logger
from datetime import datetime, timedelta

logger = get_logger(__name__)

try:
    from binance.um_futures import UMFutures  # 최신 버전
except ImportError:
    try:
        from binance.futures import BinanceFuturesClient as UMFutures  # 구버전
    except ImportError:
        from binance.client import Client as UMFutures  # fallback

class BinanceClient:
    def __init__(self, api_key: str, secret_key: str, testnet: bool = False):
        """
        BinanceClient 초기화
        
        Args:
            api_key: API 키
            secret_key: API 시크릿
            testnet: 테스트넷 사용 여부
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = testnet
        
        # 현물 클라이언트 (기존)
        self.client = Client(
            api_key=api_key,
            api_secret=secret_key,
            testnet=testnet
        )
        
        # 선물 클라이언트 추가
        try:
            if hasattr(UMFutures, '__call__'):  # UMFutures가 클래스인 경우
                self.futures_client = UMFutures(
                    api_key=api_key,
                    api_secret=secret_key,
                    base_url='https://testnet.binancefuture.com' if testnet else 'https://fapi.binance.com'
                )
            else:  # fallback to regular Client
                self.futures_client = Client(
                    api_key=api_key,
                    api_secret=secret_key,
                    testnet=testnet
                )
            
            logger.info(f"BinanceClient 초기화 완료 (testnet: {testnet}) - 현물 + 선물 클라이언트")
            
        except Exception as e:
            logger.warning(f"선물 클라이언트 초기화 실패, 현물 클라이언트만 사용: {e}")
            self.futures_client = self.client
    
    def _retry_request(self, func, *args, **kwargs):
        """
        API 요청 재시도 로직 (1회 재시도)
        
        Args:
            func: 실행할 함수
            *args, **kwargs: 함수 파라미터
            
        Returns:
            API 응답 결과
            
        Raises:
            Exception: 재시도 후에도 실패시
        """
        for attempt in range(2):  # 최대 2번 시도 (원본 + 재시도 1회)
            try:
                result = func(*args, **kwargs)
                if attempt > 0:  # 재시도로 성공한 경우
                    logger.info(f"API 요청 재시도 성공: {func.__name__}")
                return result
                
            except (BinanceAPIException, BinanceRequestException, Exception) as e:
                if attempt == 0:  # 첫번째 시도 실패
                    logger.warning(f"API 요청 실패, 재시도 중: {func.__name__} - {str(e)}")
                    time.sleep(1)  # 1초 대기 후 재시도
                else:  # 재시도도 실패
                    logger.error(f"API 요청 최종 실패: {func.__name__} - {str(e)}")
                    raise e
    
    def get_klines(self, symbol: str, interval: str = '1m', limit: int = 100) -> pd.DataFrame:
        """
        캔들스틱 데이터 조회
        
        Args:
            symbol: 거래 심볼 (예: 'BTCUSDT')
            interval: 시간 간격 (예: '1m', '5m', '1h')
            limit: 조회할 캔들 개수
            
        Returns:
            OHLCV 데이터가 포함된 DataFrame
        """
        logger.debug(f"캔들 데이터 조회 시작: {symbol} {interval} {limit}개")
        
        def _get_klines():
            return self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
        
        klines = self._retry_request(_get_klines)
        
        # DataFrame으로 변환
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # 필요한 컬럼만 선택하고 타입 변환
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        
        logger.debug(f"캔들 데이터 조회 완료: {symbol} {len(df)}개")
        return df
    
    def get_klines_bulk(self, symbol: str, interval: str = '1m', 
                       start_time: datetime = None, end_time: datetime = None,
                       total_count: int = None) -> pd.DataFrame:
        """
        대용량 캔들 데이터 수집 (시간 범위 기반, 수정된 버전)
        
        Args:
            symbol: 거래 심볼
            interval: 시간 간격 ('1m', '5m', '1h' 등)
            start_time: 시작 시간 (None이면 현재에서 역산)
            end_time: 종료 시간 (None이면 현재)
            total_count: 총 필요 개수 (None이면 시간 범위로 계산)
            
        Returns:
            전체 캔들 데이터 DataFrame
        """
        import time
        
        try:
            # 시간 범위 설정
            if end_time is None:
                end_time = datetime.now()
            
            if start_time is None and total_count is not None:
                # 개수 기반으로 시작 시간 계산
                if interval == '1m':
                    start_time = end_time - timedelta(minutes=total_count)
                elif interval == '5m':
                    start_time = end_time - timedelta(minutes=total_count * 5)
                elif interval == '1h':
                    start_time = end_time - timedelta(hours=total_count)
                else:
                    raise ValueError(f"지원하지 않는 interval: {interval}")
            
            if start_time is None:
                raise ValueError("start_time 또는 total_count 중 하나는 필수입니다")
            
            logger.info(f"{symbol} 대용량 데이터 수집: {start_time} ~ {end_time}")
            
            all_data = []
            current_start = start_time
            batch_count = 0
            max_limit = 1000  # 바이낸스 제한
            
            while current_start < end_time:
                batch_count += 1
                
                # API 호출 제한 준수
                time.sleep(0.1)  # 100ms 대기
                
                # 배치 종료 시간 계산
                if interval == '1m':
                    batch_end = min(current_start + timedelta(minutes=max_limit-1), end_time)
                elif interval == '5m':
                    batch_end = min(current_start + timedelta(minutes=(max_limit-1)*5), end_time)
                elif interval == '1h':
                    batch_end = min(current_start + timedelta(hours=max_limit-1), end_time)
                
                logger.debug(f"배치 {batch_count}: {current_start} ~ {batch_end}")
                
                # 시간 범위 기반 조회 사용
                batch_df = self.get_klines_by_time_range(
                    symbol=symbol,
                    interval=interval,
                    start_time=current_start,
                    end_time=batch_end,
                    max_count=max_limit
                )
                
                if batch_df.empty:
                    logger.debug(f"배치 {batch_count}: 데이터 없음")
                    break
                
                all_data.append(batch_df)
                logger.debug(f"배치 {batch_count}: {len(batch_df)}개 (누적: {sum(len(df) for df in all_data)}개)")
                
                # 다음 배치 시작점 설정
                current_start = batch_df['timestamp'].max() + timedelta(minutes=1)
                
                # 진행상황 로깅 (매 10배치마다)
                if batch_count % 10 == 0:
                    total_collected = sum(len(df) for df in all_data)
                    logger.info(f"{symbol} 수집 진행: {total_collected}개 ({batch_count}번의 API 호출)")
            
            # 전체 데이터 결합
            if all_data:
                result_df = pd.concat(all_data, ignore_index=True)
                
                # 시간순 정렬 (오래된 것부터)
                result_df = result_df.sort_values('timestamp').reset_index(drop=True)
                
                # 중복 제거 (같은 시간의 캔들이 있을 수 있음)
                result_df = result_df.drop_duplicates(subset=['timestamp']).reset_index(drop=True)
                
                logger.info(f"{symbol} 대용량 수집 완료: {len(result_df)}개 ({batch_count}번의 API 호출)")
                return result_df
            else:
                logger.warning(f"{symbol} 수집된 데이터 없음")
                return pd.DataFrame()
        
        except Exception as e:
            logger.error(f"{symbol} 대용량 수집 실패: {e}")
            return pd.DataFrame()
    
    def get_klines_by_count(self, symbol: str, interval: str = '1m', count: int = 200) -> pd.DataFrame:
        """
        개수 기반 캔들 데이터 수집 (대용량 지원)
        
        Args:
            symbol: 거래 심볼
            interval: 시간 간격
            count: 필요한 캔들 개수
            
        Returns:
            캔들 데이터 DataFrame
        """
        if count <= 1000:
            # 1000개 이하면 기존 메서드 사용
            return self.get_klines(symbol, interval, count)
        else:
            # 1000개 초과면 대용량 수집 사용
            return self.get_klines_bulk(symbol, interval, total_count=count)
    
    def get_klines_by_time_range(self, symbol: str, interval: str, 
                                start_time: datetime, end_time: datetime) -> pd.DataFrame:
        """
        시간 범위 기반 캔들 데이터 조회 (선물 우선, 현물 fallback)
        """
        try:
            # 1차: 선물 클라이언트로 시도
            try:
                if hasattr(self.futures_client, 'klines'):
                    # UMFutures 방식
                    klines = self.futures_client.klines(
                        symbol=symbol,
                        interval=interval,
                        startTime=int(start_time.timestamp() * 1000),
                        endTime=int(end_time.timestamp() * 1000),
                        limit=1000
                    )
                else:
                    # 기존 Client 방식
                    klines = self.futures_client.futures_klines(
                        symbol=symbol,
                        interval=interval,
                        startTime=int(start_time.timestamp() * 1000),
                        endTime=int(end_time.timestamp() * 1000),
                        limit=1000
                    )
                
                logger.debug(f"{symbol} 선물 API로 {len(klines)}개 조회 성공")
                
            except Exception as futures_error:
                logger.warning(f"{symbol} 선물 API 실패, 현물 API 시도: {futures_error}")
                
                # 2차: 현물 클라이언트로 시도
                klines = self.client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    startTime=int(start_time.timestamp() * 1000),
                    endTime=int(end_time.timestamp() * 1000),
                    limit=1000
                )
                
                logger.debug(f"{symbol} 현물 API로 {len(klines)}개 조회 성공")
            
            if not klines:
                logger.warning(f"{symbol} 캔들 데이터 없음")
                return pd.DataFrame()
            
            # DataFrame 변환
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # 데이터 타입 변환
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float) 
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            
            # 필요한 컬럼만 선택
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            
            logger.info(f"{symbol} 시간 범위 조회 완료: {len(df)}개")
            return df
            
        except Exception as e:
            logger.error(f"{symbol} 시간 범위 조회 실패: {e}")
            return pd.DataFrame()

    def get_position_info(self, symbol: str) -> Dict:
        """
        포지션 정보 조회
        
        Args:
            symbol: 거래 심볼
            
        Returns:
            포지션 정보 딕셔너리
        """
        logger.debug(f"포지션 정보 조회: {symbol}")
        
        def _get_position():
            positions = self.client.futures_position_information(symbol=symbol)
            return positions[0] if positions else {}
        
        position = self._retry_request(_get_position)
        
        # 포지션 정보 정리
        result = {
            'symbol': position.get('symbol', ''),
            'size': float(position.get('positionAmt', 0)),
            'entry_price': float(position.get('entryPrice', 0)),
            'unrealized_pnl': float(position.get('unRealizedProfit', 0)),
            'side': 'LONG' if float(position.get('positionAmt', 0)) > 0 else 'SHORT' if float(position.get('positionAmt', 0)) < 0 else 'NONE'
        }
        
        logger.debug(f"포지션 정보: {symbol} - {result['side']} {result['size']}")
        return result
    
    def place_market_order(self, symbol: str, side: str, quantity: float) -> Dict:
        """
        시장가 주문 실행
        
        Args:
            symbol: 거래 심볼
            side: 주문 방향 ('BUY' 또는 'SELL')
            quantity: 주문 수량
            
        Returns:
            주문 결과 딕셔너리
        """
        logger.info(f"시장가 주문 실행: {symbol} {side} {quantity}")
        
        def _place_order():
            return self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity
            )
        
        order_result = self._retry_request(_place_order)
        
        # 주문 결과 정리
        result = {
            'order_id': order_result.get('orderId'),
            'symbol': order_result.get('symbol'),
            'side': order_result.get('side'),
            'quantity': float(order_result.get('origQty', 0)),
            'price': float(order_result.get('avgPrice', 0)) if order_result.get('avgPrice') else 0,
            'status': order_result.get('status'),
            'time': pd.to_datetime(order_result.get('updateTime'), unit='ms')
        }
        
        logger.info(f"주문 완료: {symbol} {side} {result['quantity']} @ {result['price']}")
        return result
    
    def get_account_balance(self) -> Dict:
        """
        계좌 잔고 조회
        
        Returns:
            USDT 잔고 정보
        """
        logger.debug("계좌 잔고 조회")
        
        def _get_balance():
            return self.client.futures_account_balance()
        
        balances = self._retry_request(_get_balance)
        
        # USDT 잔고 찾기
        usdt_balance = next((b for b in balances if b['asset'] == 'USDT'), {})
        
        result = {
            'balance': float(usdt_balance.get('balance', 0)),
            'available': float(usdt_balance.get('availableBalance', 0))
        }
        
        logger.debug(f"USDT 잔고: {result['available']}")
        return result
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """
        심볼 정보 조회 (최소 주문 단위 등)
        
        Args:
            symbol: 거래 심볼
            
        Returns:
            심볼 정보 딕셔너리
        """
        logger.debug(f"심볼 정보 조회: {symbol}")
        
        exchange_info = self.client.futures_exchange_info()
        symbols = exchange_info.get('symbols', [])
        symbol_info = next((s for s in symbols if s['symbol'] == symbol), {})
        
        # 최소 주문 단위 찾기
        filters = symbol_info.get('filters', [])
        lot_size_filter = next((f for f in filters if f['filterType'] == 'LOT_SIZE'), {})
        
        result = {
            'symbol': symbol_info.get('symbol', ''),
            'min_qty': float(lot_size_filter.get('minQty', 0)),
            'step_size': float(lot_size_filter.get('stepSize', 0)),
            'status': symbol_info.get('status', '')
        }
        
        logger.debug(f"심볼 정보: {symbol} - 최소수량: {result['min_qty']}")
        return result
    
    def calculate_quantity(self, symbol: str, usdt_amount: float, price: float) -> float:
        """
        USDT 금액을 기준으로 주문 수량 계산
        
        Args:
            symbol: 거래 심볼
            usdt_amount: 투자할 USDT 금액
            price: 현재 가격
            
        Returns:
            계산된 주문 수량
        """
        symbol_info = self.get_symbol_info(symbol)
        step_size = symbol_info['step_size']
        min_qty = symbol_info['min_qty']
        
        # 수량 계산
        quantity = usdt_amount / price
        
        # step_size에 맞춰 반올림 (소수점 자리수 계산)
        if step_size < 1:
            precision = len(str(step_size).split('.')[1]) if '.' in str(step_size) else 0
            quantity = float(Decimal(str(quantity)).quantize(Decimal(str(step_size)), rounding=ROUND_DOWN))
        else:
            quantity = int(quantity // step_size) * step_size
        
        # 최소 주문 수량 확인
        if quantity < min_qty:
            raise ValueError(f"계산된 수량 {quantity}이 최소 주문 수량 {min_qty}보다 작습니다")
        
        logger.debug(f"주문 수량 계산: {usdt_amount} USDT @ {price} = {quantity}")
        return quantity