import math
import os
import sys
import time
import random
import logging
import tempfile
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Optional

import anthropic          # pip install anthropic
import pandas as pd       # pip install pandas
import requests
from ib_insync import *   # pip install ib_insync


def setup_logger():
    """Configure a logger that creates a timestamped log file for each run."""
    logger = logging.getLogger('IBStrategy')
    logger.setLevel(logging.INFO)
    log_filename = datetime.now().strftime("ib_strategy_full_%Y%m%d_%H%M%S.log")
    fh = logging.FileHandler(log_filename, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


@dataclass
class TradeState:
    """Stores some state information for the strategy."""
    last_vix_ma: Optional[float] = None
    last_leverage: Optional[float] = None


class IBCallbackHandler:
    """Handles IB callback events."""
    def __init__(self, ib, logger=None):
        self.ib = ib
        self.logger = logger or self._default_logger()
        self.partial_fills: Dict[str, int] = {}
        self.setup_callbacks()

    def _default_logger(self):
        logger = logging.getLogger('IBCallbackHandler')
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        return logger

    def setup_callbacks(self):
        self.ib.execDetailsEvent += self.on_exec_details
        self.ib.orderStatusEvent += self.on_order_status
        self.ib.commissionReportEvent += self.on_commission
        self.ib.updatePortfolioEvent += self.on_portfolio_update
        self.ib.errorEvent += self.on_error
        self.ib.positionEvent += self.on_position

    def on_exec_details(self, trade: Trade, fill: Fill):
        symbol = trade.contract.symbol
        side = fill.execution.side
        shares = fill.execution.shares
        price = fill.execution.price
        self.partial_fills[symbol] = self.partial_fills.get(symbol, 0) + shares
        self.logger.info(
            f"Fill: {side} {shares} {symbol} @ {price}, accumulated fill: {self.partial_fills[symbol]}"
        )

    def on_order_status(self, trade: Trade):
        status = trade.orderStatus.status
        symbol = trade.contract.symbol
        if status in ['Submitted', 'Filled', 'Cancelled']:
            self.logger.info(f"Order status: {symbol} - {status}")
            if status == 'Filled' and symbol in self.partial_fills:
                self.partial_fills.pop(symbol, None)
        elif status == 'PartiallyFilled':
            filled = trade.orderStatus.filled
            remaining = trade.orderStatus.remaining
            self.logger.info(f"Partially filled: {symbol} - filled: {filled}, remaining: {remaining}")
        else:
            self.logger.debug(f"Order status update: {symbol} - {status}")

    def on_commission(self, trade: Trade, fill: Fill, report: CommissionReport):
        self.logger.debug(
            f"Commission: {report.commission:.2f} {report.currency}, symbol: {trade.contract.symbol}, orderID: {trade.order.orderId}"
        )

    def on_portfolio_update(self, item):
        self.logger.debug(f"Portfolio update: {item.contract.symbol} - current position: {item.position}")

    def on_position(self, position: Position):
        account = position.account
        contract = position.contract
        pos = position.position
        avg_cost = position.avgCost
        self.logger.debug(
            f"Position update: account={account}, symbol={contract.symbol}, quantity={pos}, avgCost={avg_cost}"
        )

    def on_error(self, reqId, errorCode, errorString, contract):
        if contract:
            symbol = getattr(contract, 'symbol', '')
            self.logger.error(f"IB Error: {errorCode} - {errorString}, symbol: {symbol}")
        else:
            self.logger.error(f"IB Error: {errorCode} - {errorString}")


class MarketDataManager:
    """Manages market data retrieval."""
    def __init__(self, ib, vix_ma_window, logger):
        self.ib = ib
        self.vix_ma_window = vix_ma_window
        self.logger = logger
        self._vix_data_cache = None
        self._fx_rate_cache = None
        self._market_price_cache = {}
        self._last_cache_time = None
        self._cache_valid_seconds = 300

    def _is_cache_valid(self):
        if not self._last_cache_time:
            return False
        return (datetime.now() - self._last_cache_time).total_seconds() < self._cache_valid_seconds

    def get_fx_rate(self) -> float:
        if self._fx_rate_cache is not None and self._is_cache_valid():
            return self._fx_rate_cache
        try:
            fx_contract = Forex('USDCAD')
            self.ib.qualifyContracts(fx_contract)
            ticker = self.ib.reqMktData(fx_contract, '', False, False, [])
            timeout = 10
            start_time = time.time()
            while time.time() - start_time < timeout:
                self.ib.sleep(0.5)
                midpoint = ticker.midpoint()
                if midpoint and midpoint > 0:
                    self._fx_rate_cache = midpoint
                    self._last_cache_time = datetime.now()
                    return midpoint
                if ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
                    self._fx_rate_cache = (ticker.bid + ticker.ask) / 2
                    self._last_cache_time = datetime.now()
                    return self._fx_rate_cache
                if ticker.last and ticker.last > 0:
                    self._fx_rate_cache = ticker.last
                    self._last_cache_time = datetime.now()
                    return self._fx_rate_cache
            self.logger.warning("Could not retrieve a valid FX rate (possibly market is closed).")
            raise TimeoutError("Unable to get a valid FX rate")
        except Exception as e:
            self.logger.error(f"Failed to get FX rate: {e}")
            raise

    def get_vix_data(self, days=30):
        if self._vix_data_cache is not None and self._is_cache_valid():
            return self._vix_data_cache
        try:
            vix_contract = Index('VIX', 'CBOE', 'USD')
            self.ib.qualifyContracts(vix_contract)
            bars = self.ib.reqHistoricalData(
                vix_contract,
                endDateTime='',
                durationStr=f'{days} D',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True
            )
            if not bars:
                self.logger.warning("No VIX data returned (could be weekend/holiday).")
                return None
            if len(bars) < self.vix_ma_window:
                msg = f"Not enough VIX data, need at least {self.vix_ma_window} days."
                self.logger.warning(msg)
                return None
            df = pd.DataFrame({'date': [bar.date for bar in bars],
                               'close': [bar.close for bar in bars]})
            self._vix_data_cache = df
            self._last_cache_time = datetime.now()
            return df
        except Exception as e:
            self.logger.error(f"Failed to get VIX data: {e}")
            raise

    def get_market_price(self, contract, timeout=10):
        symbol = contract.symbol
        if symbol in self._market_price_cache and self._is_cache_valid():
            return self._market_price_cache[symbol]
        try:
            ticker = self.ib.reqMktData(contract)
            start_time = time.time()
            while time.time() - start_time < timeout:
                self.ib.sleep(0.5)
                if ticker.midpoint() and ticker.midpoint() > 0:
                    price = ticker.midpoint()
                    self._market_price_cache[symbol] = price
                    self._last_cache_time = datetime.now()
                    return price
                elif ticker.marketPrice() and ticker.marketPrice() > 0:
                    price = ticker.marketPrice()
                    self._market_price_cache[symbol] = price
                    self._last_cache_time = datetime.now()
                    return price
            self.logger.warning(f"Could not retrieve valid price for {symbol} (maybe market is closed).")
            raise TimeoutError(f"Unable to get a valid price for {symbol}")
        except Exception as e:
            self.logger.error(f"Failed to get market price for {symbol}: {e}")
            raise

    def clear_cache(self):
        self._vix_data_cache = None
        self._fx_rate_cache = None
        self._market_price_cache = {}
        self._last_cache_time = None


class PortfolioManager:
    """Manages the portfolio: positions, account info, placing orders, etc."""
    def __init__(self, ib, logger, market_data_manager, contracts, account_id):
        self.ib = ib
        self.logger = logger
        self.market_data = market_data_manager
        self.contracts = contracts
        self.account_id = account_id
        self.last_account_summary = {}
        self.last_positions = {}

    def get_positions(self):
        """Get current positions (filtered)."""
        try:
            all_positions = self.ib.positions()
            filtered = [p for p in all_positions if p.account == self.account_id]
            pos_dict = {}
            for pos in filtered:
                if pos.position != 0:
                    pos_dict[pos.contract.symbol] = {
                        'position': pos.position,
                        'avgCost': pos.avgCost
                    }
            self.last_positions = pos_dict
            return pos_dict
        except Exception as e:
            self.logger.error(f"Failed to get positions: {e}")
            raise

    def get_account_summary(self):
        """Get account summary and store it in memory."""
        try:
            account_items = self.ib.accountSummary(account=self.account_id)
            summary = {}
            key_fields = [
                'NetLiquidation', 'GrossPositionValue', 'AvailableFunds',
                'MaintMarginReq', 'InitMarginReq', 'BuyingPower', 'EquityWithLoanValue'
            ]
            self.logger.info("---- Raw Account Summary Items ----")
            for item in account_items:
                self.logger.info(f"Tag: {item.tag}, Value: {item.value}, Currency: {item.currency}, Account: {item.account}")
                if item.tag in key_fields:
                    try:
                        summary[item.tag] = float(item.value)
                    except (ValueError, TypeError):
                        self.logger.warning(f"Cannot parse {item.tag}: {item.value}")
                        summary[item.tag] = 0
            self.logger.info("---- Parsed Account Summary ----")
            for k, v in summary.items():
                self.logger.info(f"{k} = {v}")
            self.last_account_summary = summary
            return summary
        except Exception as e:
            self.logger.error(f"Failed to get account info: {e}")
            raise

    def check_margin_safety(self, safety_threshold):
        """Check margin safety."""
        try:
            account = self.get_account_summary()
            nlv = account.get('NetLiquidation', 0)
            available = account.get('AvailableFunds', 0)
            maint_margin = account.get('MaintMarginReq', 0)
            init_margin = account.get('InitMarginReq', 0)
            if nlv <= 0:
                return False
            safety_ratio = available / nlv
            margin_usage = maint_margin / nlv
            checks = [
                safety_ratio >= safety_threshold,
                margin_usage < 1.1,
                available > init_margin * 0.3
            ]
            return all(checks)
        except Exception as e:
            self.logger.error(f"Failed to check margin safety: {e}")
            return False

    def execute_order(self, contract, order, max_wait=300):
        """Enhanced order execution with partial fill support."""
        try:
            trade = self.ib.placeOrder(contract, order)
            start_time = time.time()
            last_status = None
            while time.time() - start_time < max_wait:
                if trade.orderStatus.status != last_status:
                    self.logger.info(
                        f"Order status: {contract.symbol} - {trade.orderStatus.status}, filled: {trade.orderStatus.filled}, remaining: {trade.orderStatus.remaining}"
                    )
                    last_status = trade.orderStatus.status
                if trade.isDone():
                    return True
                elif trade.orderStatus.status == "Cancelled":
                    return False
                self.ib.sleep(1)
            if trade.orderStatus.filled > 0:
                self.logger.warning(
                    f"Order partially filled for {contract.symbol}: {trade.orderStatus.filled} shares filled, {trade.orderStatus.remaining} remaining."
                )
                return True
            self.logger.error(f"Order for {contract.symbol} did not complete within {max_wait} seconds.")
            return False
        except Exception as e:
            self.logger.error(f"Order execution failed for {contract.symbol}: {e}")
            return False

    def get_portfolio_leverage(self):
        """Current leverage = GrossPositionValue / NetLiquidation."""
        try:
            account = self.get_account_summary()
            gross_pos_cad = account.get('GrossPositionValue', 0)
            nlv_cad = account.get('NetLiquidation', 0)
            fx_rate = self.market_data.get_fx_rate()
            gross_pos_usd = gross_pos_cad / fx_rate
            nlv_usd = nlv_cad / fx_rate
            if nlv_usd > 0:
                current_leverage = gross_pos_usd / nlv_usd
                self.logger.info(
                    f"Current leverage (USD): {current_leverage:.2f}, total positions: ${gross_pos_usd:,.2f}, net liquidation: ${nlv_usd:,.2f}"
                )
                return current_leverage
            else:
                return 0
        except Exception as e:
            self.logger.error(f"Failed to calculate current leverage: {e}")
            raise

    def emergency_clear_all_positions(self, max_retries=3):
        """
        当检测到杠杆异常时，立即平仓所有持仓，达到账户重置的效果。
        此时直接发出市场订单卖出所有持仓，不执行 margin safety 检查。
        """
        self.logger.error("Initiating emergency clear-out: selling all positions immediately!")
        positions = self.get_positions()
        for symbol, info in positions.items():
            qty = info['position']
            if qty == 0:
                continue
            order_action = 'SELL' if qty > 0 else 'BUY'
            order = MarketOrder(order_action, abs(qty))
            success = False
            for attempt in range(max_retries):
                if self.execute_order(self.contracts[symbol], order):
                    success = True
                    break
                else:
                    self.logger.warning(f"Emergency order for {symbol} failed attempt {attempt+1}. Retrying...")
                    time.sleep(5)
            if not success:
                self.logger.error(f"Emergency order for {symbol} failed after {max_retries} attempts.")
        self.logger.info("Emergency clear-out executed. All positions should be liquidated.")

    def execute_rebalance_three_batches(self, target_positions, fixed_target_leverage, max_retries=3, emergency_threshold=2.5):
        """
        将所有 ticker 随机分成三批，每批下单调整对应仓位，
        每批执行后检查当前杠杆是否介于初始杠杆与固定目标杠杆之间；
        如果发现杠杆超过 emergency_threshold，则立即触发清仓。
        """
        self.logger.info("Starting three-batch rebalancing with random grouping...")
        # 获取初始杠杆值
        initial_leverage = self.get_portfolio_leverage()
        self.logger.info(f"Initial leverage: {initial_leverage:.2f}, fixed target leverage: {fixed_target_leverage:.2f}")

        tickers = list(target_positions.keys())
        random.shuffle(tickers)
        batches = [tickers[i::3] for i in range(3)]

        for batch_index, batch in enumerate(batches):
            self.logger.info(f"Starting batch {batch_index+1} for tickers: {batch}")
            current_positions = self.get_positions()
            for symbol in batch:
                target_qty = target_positions.get(symbol, 0)
                current_qty = current_positions.get(symbol, {}).get('position', 0)
                diff = target_qty - current_qty
                if abs(diff) < 1:
                    continue
                order_action = 'BUY' if diff > 0 else 'SELL'
                order = MarketOrder(order_action, abs(diff))
                success = False
                for attempt in range(max_retries):
                    if self.execute_order(self.contracts[symbol], order):
                        success = True
                        break
                    else:
                        self.logger.warning(f"Order for {symbol} failed attempt {attempt+1}. Retrying...")
                        time.sleep(5)
                if not success:
                    self.logger.error(f"Order for {symbol} failed after {max_retries} attempts.")
            self.logger.info(f"Batch {batch_index+1} executed. Waiting for orders to fill and updating account data...")
            time.sleep(5)
            current_leverage = self.get_portfolio_leverage()
            self.logger.info(f"After batch {batch_index+1}, current leverage: {current_leverage:.2f}")
            if not (initial_leverage <= current_leverage <= fixed_target_leverage):
                self.logger.warning(f"After batch {batch_index+1}, current leverage {current_leverage:.2f} is not between initial {initial_leverage:.2f} and fixed target {fixed_target_leverage:.2f}")
            if current_leverage > emergency_threshold:
                self.logger.error(f"Emergency: current leverage {current_leverage:.2f} exceeds threshold {emergency_threshold:.2f}. Initiating emergency clear-out.")
                self.emergency_clear_all_positions()
                return False
        return True


class IBKRMidFreqStrategy:
    """
    Main strategy class with short-term VIX MA logic.
    # *** NEW CODE ***: Now supports different VIX MA types (SMA / EMA / HMA / etc.)
    """
    def __init__(self,
                 account_id='DU7793356',
                 vix_ma_window=10,
                 leverage_buffer=0.05,
                 safety_threshold=0.15,
                 # *** NEW CODE ***
                 vix_ma_type='SMA'    # 默认用简单移动平均
                 ):
        self.logger = setup_logger()
        self.ib = IB()
        self.trade_state = TradeState()
        self.account_id = account_id
        self.vix_ma_window = vix_ma_window
        self.leverage_buffer = leverage_buffer
        self.safety_threshold = safety_threshold

        # *** NEW CODE ***
        self.vix_ma_type = vix_ma_type  # 记录要使用的 VIX MA 类型

        try:
            self.ib.connect('127.0.0.1', 7497, clientId=123)
            self.logger.info("Successfully connected to IB.")
            self.callback_handler = IBCallbackHandler(self.ib, self.logger)
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            raise

        # 定义组合及对应权重（23只股票）
        self.portfolio = {
            # 核心科技与AI基础设施 (39%)
            "MSFT": {"weight": 0.13},
            "AAPL": {"weight": 0.05},
            "AVGO": {"weight": 0.09},
            "NVDA": {"weight": 0.10},
            "PLTR": {"weight": 0.03},

            # 制造业、电动车与先进工艺 (15%)
            "TSLA": {"weight": 0.02},
            "TSM": {"weight": 0.05},
            "MRVL": {"weight": 0.04},
            "ASML": {"weight": 0.02},
            "MU": {"weight": 0.02},

            # 防务与军工 (13%)
            "RNMBY": {"weight": 0.06},
            "SAABY": {"weight": 0.07},

            # 国防ETF与工业基础 (8%)
            "ITA": {"weight": 0.07},
            "ETN": {"weight": 0.01},

            # 黄金、白银 (12%)
            "GLD": {"weight": 0.10},
            "SLV": {"weight": 0.02},

            # AI 应用/数据基础与企业软件 (10%)
            "ORCL": {"weight": 0.05},
            "VRT": {"weight": 0.02},
            "XLP": {"weight": 0.05}
        }

        self.contracts = {}
        self.initialize_contracts()
        self.market_data = MarketDataManager(self.ib, vix_ma_window, self.logger)
        self.portfolio_manager = PortfolioManager(self.ib, self.logger, self.market_data, self.contracts, account_id=self.account_id)

    def initialize_contracts(self):
        for symbol in self.portfolio.keys():
            try:
                contract = Stock(symbol, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                self.contracts[symbol] = contract
                self.logger.debug(f"Initialized contract for {symbol}")
            except Exception as e:
                self.logger.error(f"Failed to initialize contract {symbol}: {e}")
                raise

    def calculate_ma(self, series: pd.Series, window: int, ma_type: str) -> pd.Series:
        """
        # *** NEW CODE ***
        根据 ma_type 来计算移动平均
        支持: "SMA", "EMA", "HMA" 等（可自行扩展）
        """
        ma_type = ma_type.upper()
        if ma_type == "SMA":
            return series.rolling(window=window).mean()

        elif ma_type == "EMA":
            return series.ewm(span=window, adjust=False).mean()

        elif ma_type == "HMA":
            # Hull Moving Average
            def wma(vals: pd.Series, w: int):
                return vals.rolling(w).apply(
                    lambda x: (x * np.arange(1, w+1)).sum() / np.arange(1, w+1).sum(),
                    raw=True
                )
            import numpy as np
            half_window = max(int(window/2), 1)
            sqrt_window = max(int(np.sqrt(window)), 1)

            wma_half = wma(series, half_window)
            wma_full = wma(series, window)
            hma_pre = 2 * wma_half - wma_full
            hma_final = wma(hma_pre, sqrt_window)
            return hma_final

        else:
            # 默认SMA
            return series.rolling(window=window).mean()

    def get_zone_leverage(self, vix_level):
        return 1.4

    def should_rebalance(self, current_leverage, target_leverage):
        if current_leverage > target_leverage + self.leverage_buffer:
            self.logger.info(f"Current leverage {current_leverage:.2f} > target upper bound {target_leverage + self.leverage_buffer:.2f}")
            return True
        elif current_leverage < target_leverage - self.leverage_buffer:
            self.logger.info(f"Current leverage {current_leverage:.2f} < target lower bound {target_leverage - self.leverage_buffer:.2f}")
            return True
        return False

    def calculate_target_positions(self, target_leverage):
        try:
            account = self.portfolio_manager.get_account_summary()
            nlv_cad = account.get('NetLiquidation', 0)
            fx_rate = self.market_data.get_fx_rate()
            self.logger.info(f"Current USD/CAD rate: {fx_rate}")
            nlv_usd = nlv_cad / fx_rate
            if nlv_usd <= 0:
                raise ValueError("Net liquidation value is invalid or zero.")
            target_positions = {}
            for symbol, details in self.portfolio.items():
                weight = details['weight']
                if weight <= 0:
                    target_positions[symbol] = 0
                    continue
                price = self.market_data.get_market_price(self.contracts[symbol])
                if price <= 0:
                    raise ValueError(f"Price for {symbol} is invalid or zero.")
                target_value = nlv_usd * target_leverage * weight
                shares = math.ceil(target_value / price)
                target_positions[symbol] = shares
                self.logger.debug(f"{symbol} => target shares: {shares}, target value (USD): {target_value:.2f}, price: {price:.2f}")
            return target_positions
        except Exception as e:
            self.logger.error(f"Failed to calculate target positions: {e}")
            raise

    def run_strategy(self):
        """Main strategy logic."""
        try:
            # 1. 获取 VIX 数据
            vix_df = self.market_data.get_vix_data(days=30)
            if vix_df is None or len(vix_df) < self.vix_ma_window:
                self.logger.warning("Not enough VIX data available. Strategy will not rebalance.")
                return

            # 2. 根据 vix_ma_type 计算(比如 10日 EMA/HMA)
            raw_vix_series = vix_df['close']
            vix_ma_series = self.calculate_ma(raw_vix_series, self.vix_ma_window, self.vix_ma_type)
            vix_ma_series.bfill(inplace=True)  # 避免前期空值

            # 3. 取最近一日均线值
            vix_ma = vix_ma_series.iloc[-1]
            self.logger.info(f"VIX {self.vix_ma_type} MA{self.vix_ma_window}: {vix_ma:.2f}")
            self.trade_state.last_vix_ma = float(vix_ma)

            # 4. 根据VIX区间得到目标杠杆
            target_leverage = self.get_zone_leverage(vix_ma)
            self.logger.info(f"Target leverage: {target_leverage:.2f}")
            fixed_target_leverage = target_leverage
            self.target_leverage = target_leverage


            # ===== 新增检查持仓数据完整性的代码 =====
            # 获取账户概要和持仓数据
            account = self.portfolio_manager.get_account_summary()
            positions = self.portfolio_manager.get_positions()
            # 如果账户概要显示有持仓（GrossPositionValue > 0），但持仓数据为空，则中止调仓
            if account.get('GrossPositionValue', 0) > 0 and not positions:
                self.logger.error(
                    "持仓数据获取失败（可能由于超时或多端登录导致），中止调仓操作以防止错误下单。"
                )
                return
            # ============================================
            # 5. 获取当前杠杆
            current_leverage = self.portfolio_manager.get_portfolio_leverage()
            emergency_threshold = 2.5  # 设定紧急杠杆阈值

            # 6. 先检查是否超过紧急杠杆
            if current_leverage > emergency_threshold:
                self.logger.error(f"Emergency: current leverage {current_leverage:.2f} exceeds emergency threshold {emergency_threshold:.2f}. Initiating emergency clear-out.")
                self.portfolio_manager.emergency_clear_all_positions()
                return

            # 7. 判断是否需要 Rebalance
            if self.should_rebalance(current_leverage, target_leverage):
                self.logger.info("Rebalancing is required.")
                if not self.portfolio_manager.check_margin_safety(self.safety_threshold):
                    self.logger.warning("Margin safety check failed. Rebalance aborted.")
                    return
                target_positions = self.calculate_target_positions(target_leverage)
                success = self.portfolio_manager.execute_rebalance_three_batches(
                    target_positions, fixed_target_leverage, emergency_threshold=emergency_threshold
                )
                if success:
                    self.trade_state.last_leverage = target_leverage
                    self.logger.info("Rebalance completed successfully.")
                else:
                    self.logger.error("Rebalance execution failed or emergency clear-out triggered.")
            else:
                self.logger.info("No rebalance needed at this time.")

        except Exception as e:
            self.logger.error(f"Strategy run failed: {e}")
            raise
        finally:
            self.market_data.clear_cache()
            final_positions = self.portfolio_manager.get_positions()
            self.logger.info("==== Final Portfolio Positions ====")
            for sym, info in final_positions.items():
                self.logger.info(f"{sym}: quantity={info['position']}, avgCost={info['avgCost']:.2f}")

    def __del__(self):
        try:
            self.ib.disconnect()
            self.logger.info("Disconnected from IB.")
        except:
            pass


class TelegramLogger:
    """
    Sends messages or files to Telegram.
    If text <= 4096 chars, send as a single message; otherwise send as a .txt file.
    """
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.max_length = 4096
        self.send_message_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self.send_document_url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"

    def send_log(self, log_text: str) -> None:
        if not log_text:
            print("Nothing to send to Telegram.")
            return
        if len(log_text) <= self.max_length:
            payload = {"chat_id": self.chat_id, "text": log_text}
            try:
                response = requests.post(self.send_message_url, json=payload)
                if response.ok:
                    print("Telegram message sent successfully.")
                else:
                    print(f"Failed to send Telegram message: {response.text}")
            except Exception as e:
                print(f"Error while sending Telegram message: {e}")
        else:
            print("Log exceeds 4096 chars. Sending as a file...")
            tmp_file_path = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt") as tmp_file:
                    tmp_file.write(log_text)
                    tmp_file_path = tmp_file.name
                with open(tmp_file_path, 'rb') as file_obj:
                    data = {"chat_id": self.chat_id}
                    files = {"document": file_obj}
                    response = requests.post(self.send_document_url, data=data, files=files)
                if response.ok:
                    print("Telegram log file sent successfully.")
                else:
                    print(f"Failed to send Telegram log file: {response.text}")
            except Exception as e:
                print(f"Error while sending log file to Telegram: {e}")
            finally:
                if tmp_file_path and os.path.exists(tmp_file_path):
                    os.remove(tmp_file_path)


def call_claude_analysis(account_summary: dict, positions: dict, vix_ma: float) -> str:
    api_key = "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"  # 请将此处替换为真实的 API key
    if not api_key:
        print("Warning: ANTHROPIC_API_KEY is not set; skipping Claude call.")
        return ""
    client = anthropic.Anthropic(api_key=api_key)
    summary_text = "\n".join(f"- {k}: {v}" for k, v in account_summary.items())
    pos_text = "\n".join(f"{sym}: qty={info['position']}, avgCost={info['avgCost']:.2f}" for sym, info in positions.items())
    prompt = f"""\ 
Please review my IB account summary, positions, and current VIX MA to ensure my leverage strategy is applied correctly.

Current VIX MA: {vix_ma}

My leverage strategy:
- VIX < 15 => leverage = 2.0
- 15 ≤ VIX ≤ 20 => leverage = 1.6
- 20 < VIX ≤ 25 => leverage = 1.2
- VIX > 25 => leverage = 0.8

Account Summary:
{summary_text}

Positions:
{pos_text}

Please verify if the final leverage usage aligns with the rules and no margin red flags exist.
"""
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        if not response.content:
            return "No content returned from Claude."
        text = "\n\n".join(block.text for block in response.content).strip()
        return text
    except Exception as e:
        print(f"Error calling Claude: {e}")
        return ""


def main():
    strategy = None
    try:
        TELEGRAM_BOT_TOKEN = "7812245345:AAHfTz_NQXA-vADusJ6oXN-55bJU8IC1z1s"
        TELEGRAM_CHAT_ID = "6517275029"
        telegram_logger = TelegramLogger(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

        # *** NEW CODE ***
        # 可以在这里切换 vix_ma_type = 'SMA' / 'EMA' / 'HMA' ...
        strategy = IBKRMidFreqStrategy(
            account_id='U12859754',
            vix_ma_window=10,
            leverage_buffer=0.05,
            safety_threshold=0.15,
            vix_ma_type='HMA'   # <--- 比如改成EMA，抓短周期变动更敏感
        )

        strategy.run_strategy()

        account_data = strategy.portfolio_manager.last_account_summary
        positions_data = strategy.portfolio_manager.last_positions
        vix_ma = strategy.trade_state.last_vix_ma or 0.0
        claude_reply = call_claude_analysis(account_data, positions_data, vix_ma)
        if claude_reply:
            print("\n=== Claude's Analysis ===")
            print(claude_reply)
            telegram_logger.send_log(claude_reply)
    except Exception as e:
        logging.error(f"Error running strategy: {e}")
    finally:
        logging.info("Strategy run finished.")
        if strategy is not None:
            pass


if __name__ == '__main__':
    main()
