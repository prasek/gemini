from api import Geminipy
from decimal import Decimal
from datetime import datetime
from error import ApiError
import util

SIDE_BUY = "buy"
SIDE_SELL = "sell"
TYPE_LIMIT = "exchange limit"
OPTION_MAKER_OR_CANCEL = "maker-or-cancel"
SYMBOL_BTCUSD = "btcusd"
UNIT_BTC = "BTC"
UNIT_USD = "USD"
RESERVE_FEE_ACTUAL = "actual"
RESERVE_FEE_MAX = "max"
RESERVE_FEE_NONE = "none"
MAX_API_MAKER_FEE =  0.0010
MAX_API_TAKER_FEE =  0.0035
MAX_API_TAKER_FEE_DELTA =  MAX_API_TAKER_FEE - MAX_API_MAKER_FEE

def new_order(con, side, price, quantity, unit):
    return Order(con, side=side, price=price, quantity=quantity, quantity_unit=unit)

def get_order(con, order_id):
    status = get_order_status(con, order_id)
    return Order(con, side=status.get_side(), price=status.get_price(), quantity=status.get_original_amount(), quantity_unit=UNIT_BTC, status=status)

def get_order_status(con, order_id):
    res = con.order_status(order_id)
    if res.status_code != 200:
        raise ApiError(res)

    return OrderStatus(con, res.json())

def get_quote(con):
    res = con.pubticker(symbol="btcusd")
    if res.status_code != 200:
        raise ApiError(res)

    tick = res.json()
    ask = float(tick["ask"])
    bid = float(tick["bid"])
    last = float(tick["last"])
    spread = ask - bid

    return bid, ask, spread, last

def get_fees(con):
    # note first monnth of API usage shows 0% maker fees, but limit orders must reserve the
    # normal fee amount so they can be executed after the first month with fees reserved
    res = con.fees()
    if res.status_code != 200:
        raise ApiError(res)
    else:
        fee = res.json()

        api_maker_fee = float(fee["api_maker_fee_bps"]/100)
        api_taker_fee = float(fee["api_taker_fee_bps"]/100)

        web_maker_fee = float(fee["web_maker_fee_bps"]/100)
        web_taker_fee = float(fee["web_taker_fee_bps"]/100)

        return api_maker_fee, api_taker_fee, web_maker_fee, web_taker_fee

def get_balances(con):
    bid, ask, spread, last = get_quote(con)

    res = con.balances()
    if res.status_code != 200:
        raise ApiError(res)
    else:
        headers = ["currency", "amount", "available"]
        balances = res.json()

        account_value = 0.0
        available_to_trade_usd = 0.0
        available_to_trade_btc = 0.0
        l = []
        for b in balances:
            currency = b["currency"]
            amount = float(b["amount"])
            available = float(b["available"])
            if currency == "USD":
                account_value += amount
                available_to_trade_usd = available
            elif currency == "BTC":
                account_value += amount * last
                available_to_trade_btc = available
            else:
                continue

            item = []
            for h in headers:
                item.append(b[h])
            l.append(item)

        return account_value, available_to_trade_usd, available_to_trade_btc

def get_active_orders(con):
    res = con.active_orders()
    if res.status_code != 200:
        raise ApiError(res)

    return res.json()

def is_side(val, side):
    if val.lower() == side:
        return True
    return False

class Order:
    def __init__(self, con, side, price, quantity, quantity_unit=UNIT_USD, status=None):
        self.con = con
        self.side = side
        self.price = float(price)
        self.quantity = float(quantity)
        self.quantity_unit = quantity_unit
        self.status = status

        self.maker_or_cancel = True
        self.reserve_api_fees = RESERVE_FEE_ACTUAL

        self.reset_calculated()

    def reset_calculated(self):
        self.btc_amount = -1.0
        self.subtotal = 0.0
        self.maker_fee = 0.0
        self.taker_fee = 0.0
        self.fee = 0.0
        self.total = 0.0
        self.warnings = []

        self.prepared = False

    def assert_valid(self):
        if not self.price > 0:
            raise Exception("Invalid price: " + self.price)

        if not self.quantity > 0:
            raise Exception("Invalid quantity: " + self.quantity)

        if not (self.quantity_unit == UNIT_BTC or self.quantity_unit == UNIT_USD):
            raise Exception("Invalid quantity unit" + self.quantity_unit)

        if not (self.side == SIDE_BUY or self.side == SIDE_SELL):
            raise Exception("Invalid side" + self.side)

    def assert_prepared(self):
        ok = (
                self.prepared
                and self.btc_amount > 0
                )

        if not ok:
            raise Exception("Not prepared.")

    def get_side(self):
        return self.side

    def set_side(self, side):
        allowed = [SIDE_BUY, SIDE_SELL]
        if not side in allowed:
            raise Exception("Side {0} not in {1}".format(side, allowed))

        self.side = side
        self.reset_calculated()

    def get_price(self):
        return self.price

    def set_price(self, price):
        self.price = float(price)
        self.reset_calculated()

    def get_quantity(self):
        return self.quantity

    def set_quantity(self, quantity):
        self.quantity = float(quantity)
        self.reset_calculated()

    def get_quantity_unit(self):
        return self.quantity_unit

    def set_quantity_unit(self, unit):
        allowed = [UNIT_BTC, UNIT_USD]
        if not unit in allowed:
            raise Exception("Quantity unit {0} not in {1}".format(unit, allowed))

        self.quantity_unit = unit
        self.reset_calculated()

    def get_maker_or_cancel(self):
        return self.maker_or_cancel

    def set_maker_or_cancel(self, required):
        self.maker_or_cancel = bool(required)
        self.reset_calculated()

    def get_reserve_api_fees(self):
        return self.reserve_api_fees

    def set_reserve_api_fees(self, reserve):
        allowed = [RESERVE_FEE_NONE, RESERVE_FEE_ACTUAL, RESERVE_FEE_MAX]
        if not reserve in allowed:
            raise Exception("Reserve type {0} not in {1}".format(reserve, allowed))

        self.reserve_api_fees = reserve
        self.reset_calculated()

    def get_btc_amount(self):
        return self.btc_amount

    def get_subtotal(self):
        return self.subtotal

    def get_maker_fee(self):
        return self.maker_fee

    def get_taker_fee(self):
        return self.taker_fee

    def get_fee(self):
        return self.fee

    def get_total(self):
        return self.total

    def prepare(self):
        self.assert_valid()

        # fees to use/reserve
        api_maker_fee = 0.0
        api_taker_fee = 0.0

        if self.reserve_api_fees == RESERVE_FEE_ACTUAL:
            api_maker_fee, api_taker_fee, web_maker_fee, web_taker_fee = get_fees(self.con)
            api_maker_fee = api_maker_fee / 100
            api_taker_fee = api_taker_fee / 100
        elif self.reserve_api_fees == RESERVE_FEE_MAX:
            api_maker_fee = MAX_API_MAKER_FEE
            api_taker_fee = MAX_API_TAKER_FEE

        # max fee in use
        fee_pct = api_taker_fee
        if self.maker_or_cancel:
            fee_pct = api_maker_fee

        # btc_amount
        if self.quantity_unit == UNIT_BTC:
            self.btc_amount = self.quantity

        elif self.quantity_unit == UNIT_USD:
            if self.side == SIDE_BUY:
                self.subtotal = self.quantity / (1 + fee_pct)
                self.btc_amount= self.subtotal / self.price

            elif self.side == SIDE_SELL:
                self.subtotal = self.quantity / (1 - fee_pct)
                self.btc_amount = self.quantity / self.price

            else:
                raise Exception("Invalid side: " + self.side)

        else:
            raise Exception("Invalid quantity unit: " + self.quantity_unit)

        self.subtotal = self.btc_amount * self.price
        self.fee = self.subtotal * fee_pct
        if self.side == SIDE_SELL:
            self.fee = -self.fee

        self.total = self.subtotal + self.fee

        bid, ask, spread, last = get_quote(self.con)

        self.warnings = []
        if spread > 0.05:
            self.warnings.append("warning: spread: {0}".format(util.fmt_usd(spread)))
        if self.side == SIDE_BUY:
            if self.price > ask:
                self.warnings.append("warning: buy price ({0}) is higher than ask ({1}) - TAKER".format(util.fmt_usd(self.price), util.fmt_usd(ask)))
        if self.side == SIDE_SELL:
            if self.price < bid:
                self.warnings.append("warning: sell price ({0}) is lower than bid ({1}) - TAKER".format(util.fmt_usd(self.price), util.fmt_usd(bid)))

        self.prepared = True

    def get_warnings(self):
        return self.warnings

    def execute(self):
        self.assert_valid()
        self.assert_prepared()

        options = []
        if self.maker_or_cancel:
            options.append(OPTION_MAKER_OR_CANCEL)

        res = self.con.new_order(amount=util.fmt_btc(self.btc_amount), price=self.price, side=self.side, options=options)

        if res.status_code != 200:
            raise ApiError(res)

        self.status = OrderStatus(self.con, res.json())

    def cancel_and_replace(self):
        if self.status == None:
            raise Exception("No order to replace.")

        self.status.cancel()
        self.status.refresh()

        self.quantity = self.status.get_remaining_amount()
        self.quantity_unit = UNIT_BTC

        self.prepare()

        return self.execute()

    def get_status(self):
        return self.status

class OrderStatus:
    def __init__(self, con, data):
        self.con = con
        self.data = data

    def get_order_id(self):
        return int(self.data["order_id"])

    def get_timestamp(self):
        return datetime.fromtimestamp(self.data["timestamp"])

    def get_side(self):
        return self.data["side"]

    def get_type(self):
        return self.data["type"]

    def get_price(self):
        return float(self.data["price"])

    def get_symbol(self):
        return float(self.data["symbol"])

    def get_original_amount(self):
        return float(self.data["original_amount"])

    def get_executed_amount(self):
        return float(self.data["executed_amount"])

    def get_remaining_amount(self):
        return float(self.data["remaining_amount"])

    def get_avg_execution_price(self):
        return float(self.data["avg_execution_price"])

    def is_live(self):
        return bool(self.data["is_live"])

    def is_cancelled(self):
        return bool(self.data["is_cancelled"])

    def get_total(self):
        return self.price() * self.original_amount()

    def refresh(self):
        res = self.con.order_status(self.get_order_id())
        if res.status_code != 200:
            raise ApiError(res)

        self.data = res.json()

    def cancel(self):
        if self.is_cancelled():
            raise Exception("Order already cancelled.")

        res = self.con.cancel_order(self.get_order_id())
        if res.status_code != 200:
            raise ApiError(res)

    def to_dict(self):
        return self.data

