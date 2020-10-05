from gemini import Geminipy
from tabulate import tabulate
from decimal import Decimal
from datetime import datetime
import os
import yaml
import csv
import getpass
import locale

SIDE_BUY = "buy"
SIDE_SELL = "sell"
TYPE_LIMIT = "exchange limit"
OPTION_MAKER_OR_CANCEL = "maker-or-cancel"
SYMBOL_BTCUSD = "btcusd"
FORMAT_TABLE = "table"
FORMAT_CSV= "csv"
UNIT_BTC = "BTC"
UNIT_USD = "USD"
MAX_API_MAKER_FEE =  0.0010
MAX_API_TAKER_FEE =  0.0035
MAX_API_TAKER_FEE_DELTA =  MAX_API_TAKER_FEE - MAX_API_MAKER_FEE
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

def show_help():
        cmds = [
                ["bal", "balances and available amounts - [alt: balances]"],
                ["stat", "avg. cost basis, gain/loss, performance"],
                ["list", "list open orders - [alt: orders, active]"],
                ["tick", "price quote - [alt: quote]"],
                ["buy", "buy in USD quantity (including fee)"],
                ["buy btc", "buy in BTC quantity"],
                ["sell", "buy in USD quantity (including fee)"],
                ["sell btc", "sell in BTC quantity"],
                ["status", "order status"],
                ["cancel", "cancel order"],
                ["cancel all", "cancel all open orders"],
                ["cancel replace", "cancel and replace an order"],
                ["past", "list past trades - [alt: history]"],
                ["export history", "export history to csv"],
                ["fees", "show fees"],
                ["exit", "exit the console app"],
                ]
        print(tabulate(cmds, headers=["command", "info"]))

def new_order(con, side, price, quantity, quantity_unit):
    return Order(con, side=side, price=price, quantity=quantity, quantity_unit=UNIT_BTC)

def get_order(con, order_id):
    status = get_order_status(con, order_id)
    return Order(con, side=status.get_side(), price=status.get_price(), quantity=status.get_original_amount(), quantity_unit=UNIT_BTC, status=status)

def get_order_status(con, order_id):
    res = con.order_status(order_id)
    if res.status_code != 200:
        raise Exception(result_to_dict(res))

    return OrderStatus(con, res.json())

class Order:
    def __init__(self, con, side, price, quantity, quantity_unit=UNIT_USD, status=None):
        self.con = con
        self.side = side
        self.price = price
        self.quantity = quantity
        self.quantity_unit = quantity_unit
        self.status = status

        self.maker_or_cancel = True

        self.reset_calculated()

    def reset_calculated(self):
        self.btc_amount = -1.0
        self.subtotal = 0.0
        self.maker_fee = 0.0
        self.taker_fee = 0.0
        self.fee = 0.0
        self.total = 0.0

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
        if not (side == SIDE_BUY or side == SIDE_SELL):
            raise Exception("Invalid side: " + side)

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
        if not (unit == UNIT_BTC or unit == UNIT_USD):
            raise Exception("Invalid quantity unit: " + unit)

        self.quantity_unit = unit
        self.reset_calculated()

    def get_maker_or_cancel(self):
        return self.maker_or_cancel

    def set_maker_or_cancel(self, required):
        self.maker_or_cancel = bool(required)
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

        if self.quantity_unit == UNIT_BTC:
            self.btc_amount = self.quantity
        elif self.quantity_unit == UNIT_USD:
            self.btc_amount = self.quantity / self.price
        else:
            raise Exception("Invalid quantity unit: " + self.quantity_unit)

        self.subtotal = self.btc_amount * self.price

        api_maker_fee, api_taker_fee, web_maker_fee, web_taker_fee = get_fees(self.con)
        if api_maker_fee < 0:
            raise Exception("invalid api_fees" + api_maker_fee)

        self.maker_fee = self.subtotal * api_maker_fee
        self.taker_fee = self.subtotal * api_taker_fee

        if self.maker_or_cancel:
            self.fee = self.maker_fee
        else:
            self.fee = self.taker_fee

        self.total = self.subtotal + self.fee
        self.prepared = True

    def execute(self):
        self.assert_valid()
        self.assert_prepared()

        options = []
        if self.maker_or_cancel:
            options.append(OPTION_MAKER_OR_CANCEL)

        res = self.con.new_order(amount=self.btc_amount, price=self.price, side=self.side, options=options)

        if res.status_code != 200:
            raise Exception(result_to_dict(res))

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
            raise Exception(result_to_dict(res))

        self.data = res.json()

    def cancel(self):
        if self.is_cancelled():
            raise Exception("Order already cancelled.")

        res = self.con.cancel_order(self.get_order_id())
        if res.status_code != 200:
            raise Exception(result_to_dict(res))

    def to_dict(self):
        return self.data

def result_to_dict(res):
    return {"code": res.status_code, "json": res.json()}

def print_err(err):
    print("ERROR: {0}".format(err))

def show_balances(con):
    account_value, available_to_trade_usd, available_to_trade_btc = get_balances(con)

    headers = ["Notational Account Value", "Available to Trade (USD)", "Available to Trade (BTC)"]
    data = [[
            fmt_usd(account_value),
            fmt_usd(available_to_trade_usd),
            fmt_btc(available_to_trade_btc),
            ]]

    print()
    print("BALANCES")
    print_sep()
    print(tabulate(data, headers=headers, floatfmt=".8g", stralign="right"))
    print_sep()

def get_balances(con):
    bid, ask, spread, last = get_quote(con)
    if bid < 0:
        print("Error: bid unavailable")
        return

    res = con.balances()
    if res.status_code != 200:
        print("ERROR STATUS: {0}".format(res.status_code))
        print(res.json())
        return -1, -1, -1
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

def show_orders(con):
    res = con.active_orders()
    if res.status_code != 200:
        print("ERROR STATUS: {0}".format(res.status_code))
        print(res.json())
    else:
        print()
        print("OPEN ORDERS")
        orders = res.json()
        print_orders(orders)

def show_order_status(con):
    try:
        order_id = input("order_id: ")
        status = get_order_status(con, order_id)

        print()
        print("ORDER STATUS")
        print_orders([status.to_dict()])

    except Exception as err:
        print_err(err)
        return

def cancel_and_replace(con):
    try:
        order_id = input("order_id: ")
        order = get_order(con, order_id)

        if not order.status.is_live():
            print("Order is not live.")
            return

        price = input("new price: ")
        order.set_price(price)
        order.set_quantity(order.status.get_remaining_amount())
        order.prepare()
        print_sep()
        print("Side: " + order.get_side())
        print("Price: " + fmt_usd(order.get_price()))
        print("Quantity: " + fmt_btc(order.get_quantity()))
        print("Subtotal: " + fmt_usd(order.get_subtotal()))
        print("Fee: " + fmt_usd(order.get_fee()))
        print("Total: " + fmt_usd(order.get_total()))
        print_sep()

        print()
        ok = input("Execute Order? (yes/no) ")
        if ok != "yes" and ok != "y":
            print("skipping order")
            return

        order.cancel_and_replace()

        print()
        print("ORDER REPLACED")
        print_orders([order.status.to_dict()])

    except Exception as err:
        print_err(err)
        return

def print_orders(orders):
        headers = ["date", "side", "total", "type", "price", "original_amount", "symbol", "executed_amount", "avg_execution_price", "remaining_amount", "is_live", "is_cancelled", "order_id"]
        l = []
        for o in orders:
            price = float(o["price"])
            quantity = float(o["original_amount"])
            total = price * quantity
            o["total"] = fmt_usd(total)
            o["price"] = fmt_usd(price)
            o["avg_execution_price"] = fmt_usd(float(o["avg_execution_price"]))
            o["date"] = fmt_date(datetime.fromtimestamp(int(o["timestamp"])))
            item = []
            for h in headers:
                item.append(o[h])
            l.append(item)

        print_sep()
        print(tabulate(l, headers=headers, floatfmt=".8g", stralign="right"))
        print_sep()

def show_history(con, history=True, stats=True, format=FORMAT_TABLE):
    symbol = "btcusd"
    res = con.past_trades(symbol=symbol, limit_trades=1000)
    if res.status_code != 200:
        print("ERROR STATUS: {0}".format(res.status_code))
        print(res.json())
    else:
        orders = res.json()
        headers = ["date", "type", "total", "price", "amount", "symbol", "fee_amount", "order_id"]
        l = []
        buy_total = 0.0
        buy_quantity = 0.0

        for o in orders:
            price = float(o["price"])
            quantity = float(o["amount"])
            fees = float(o["fee_amount"])
            total = price * quantity + fees
            dt = datetime.fromtimestamp(o["timestamp"])
            o["date"] = dt.strftime("%m/%d/%Y")
            o["total"] = fmt_usd(total)
            o["fee_amount"] = fmt_usd(fees)
            o["price"] = fmt_usd(price)
            o["symbol"] = symbol
            item = []
            for h in headers:
                item.append(o[h])
            l.append(item)

            if o["type"] == "Buy":
                buy_total += total
                buy_quantity += quantity

        if history:
            if format == FORMAT_TABLE:
                print()
                print("HISTORY")
                print_sep()
                print(tabulate(l, headers=headers, floatfmt=".8g", stralign="right"))
                print_sep()
            elif format == FORMAT_CSV:
                filename = input("Filename (defauilt: history.csv):")
                if len(filename) == 0:
                    filename = "history.csv"

                print()
                print("writing history to " + filename)

                with open(filename, 'w', newline='') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=headers, delimiter='\t', extrasaction='ignore')

                    writer.writeheader()
                    for o in orders:
                        writer.writerow(o)
                print("done.")
            else:
                print("Invalid format: " + format)

        if stats:
            avg_cost_basis = buy_total/buy_quantity
            bid, ask, spread, last = get_quote(con)
            perf = ((last / avg_cost_basis) - 1) * 100
            curr_value = buy_quantity * last
            gain = curr_value - buy_total

            headers = ["gain/loss", "gain/loss %", "avg cost basis/btc", "last price", "cost basis", "current value"]
            stats = [[
                    fmt_usd(gain),
                    fmt_pct(perf),
                    fmt_usd(avg_cost_basis),
                    fmt_usd(last),
                    fmt_usd(buy_total),
                    fmt_usd(curr_value),
                    ]]

            print()
            print("TRADE STATS")
            print_sep()
            print(tabulate(stats, headers=headers, stralign="right"))
            print_sep()

def get_quote(con):
    res = con.pubticker(symbol="btcusd")
    if res.status_code != 200:
        print("ERROR STATUS: {0}".format(res.status_code))
        print(res.json())
        return -1, -1, -1, -1

    tick = res.json()
    ask = float(tick["ask"])
    bid = float(tick["bid"])
    last = float(tick["last"])
    spread = ask - bid

    return bid, ask, spread, last

def show_quote(con):
    bid, ask, spread, last = get_quote(con)
    if bid < 0:
        return

    print()
    print("QUOTE")
    print_sep()
    print("{0} ASK".format(fmt_nbr(ask)))
    print("Spread of {0}, LAST: {1}".format(fmt_nbr(spread), format(fmt_nbr(last))))
    print("{0} BID".format(fmt_nbr(bid)))
    print_sep()

    return bid, ask, spread, last


def buy(con):
    side = 'buy'
    quantity_unit = "USD"

    price, amount_usd = get_price_quantity(con, side, quantity_unit)
    if price is None or amount_usd is None:
        return

    subtotal = float(amount_usd) / (1 + MAX_API_MAKER_FEE)
    fee = subtotal * MAX_API_MAKER_FEE
    total = subtotal + fee

    amount_btc = fmt_btc(subtotal / float(price))

    execute_order(con,
            side,
            price=price,
            quantity=amount_btc,
            subtotal=subtotal,
            fee=fee,
            total=total)

def buy_btc(con):
    side = 'buy'
    quantity_unit = "BTC"

    price, amount_btc = get_price_quantity(con, side, quantity_unit)
    if price is None or amount_btc is None:
        return

    subtotal = float(amount_btc) * float(price)
    fee = subtotal * MAX_API_MAKER_FEE
    total = subtotal + fee

    execute_order(con,
            side,
            price=price,
            quantity=amount_btc,
            subtotal=subtotal,
            fee=fee,
            total=total)

def sell(con):
    side = 'sell'
    quantity_unit = "USD"

    price, amount_usd = get_price_quantity(con, side, quantity_unit)
    if price is None or amount_usd is None:
        return

    subtotal = float(amount_usd) / (1 - MAX_API_MAKER_FEE)
    fee = subtotal * MAX_API_MAKER_FEE
    total = subtotal - fee

    amount_btc = fmt_btc((float(subtotal) / float(price)))

    execute_order(con,
            side,
            price=price,
            quantity=amount_btc,
            subtotal=subtotal,
            fee=fee,
            total=total)

def sell_btc(con):
    side = 'sell'
    quantity_unit = "BTC"

    price, amount_btc = get_price_quantity(con, side, quantity_unit)
    if price is None or amount_btc is None:
        return

    subtotal = float(amount_btc) * float(price)
    fee = subtotal * MAX_API_MAKER_FEE
    total = subtotal - fee

    execute_order(con,
            side,
            price=price,
            quantity=amount_btc,
            subtotal=subtotal,
            fee=fee,
            total=total)

def get_price_quantity(con, side, quantity_unit):
        print(side.upper())
        quantity = input("Quantity ({0}): ".format(quantity_unit))
        price = input("Price (USD): ")

        if price == "market":
            bid, ask, spread, last = get_quote(con)
            max_over_under = input("Max over/under bid/ask (default: 0): ")
            if len(max_over_under) == 0:
                max_over_under = 0
            else:
                if not is_float(max_over_under):
                    print("Error: not a valid USD value.")
                    return None, None
                max_over_under = float(max_over_under)
            if max_over_under < 0:
                print("Error: must be > 0.")
                return None, None

            if side == "buy":
                price = str(ask + max_over_under)
            if side == "sell":
                price = str(bid - max_over_under)

        if quantity == "max":
            account_value, available_to_trade_usd, available_to_trade_btc = get_balances(con)
            if side == "buy" and quantity_unit == "USD":
                quantity = str(available_to_trade_usd)
            if side == "sell" and quantity_unit == "BTC":
                quantity = str(available_to_trade_btc)

        if not is_float(price) or not is_float(quantity):
            print("invalid price or quantity")
            return None, None

        return price, quantity

def execute_order(con, side, price, quantity, subtotal, fee, total):

    bid, ask, spread, last = show_quote(con)

    print_header("CONFIRM {0}:".format(side.upper()))

    print(tabulate([["PRICE", "", ""],
                    ["", fmt_nbr(float(price)), "USD"],
                    ["", "", ""],
                    ["QUANTITY", "", ""],
                    ["", fmt_btc(float(quantity)), "BTC"],
                    ["", fmt_nbr(subtotal), "USD"],
                    ["", "", ""],
                    ["Subtotal", fmt_usd(subtotal), "USD"],
                    ["Fee", fmt_usd(fee), "USD"],
                    ["Total", fmt_usd(total), "USD"],
                    ], tablefmt="plain", floatfmt=".8g", stralign="right"))
    print_sep()

    prc = float(price)
    if spread > 0.05:
        print("WARNING: Spread: {0}".format(fmt_usd(spread)))
    if side == "buy":
        if prc > ask:
            print("WARNING: Buy price ({0}) is higher than ask ({1}) - TAKER".format(fmt_usd(prc), fmt_usd(ask)))
        if prc < (bid * .9):
            print("WARNING: Buy price ({0}) is > 10% under current bid ({1})".format(fmt_usd(prc), fmt_usd(ask)))
    if side == "sell":
        if prc < bid:
            print("WARNING: Sell price ({0}) is lower than bid ({1}) - TAKER".format(fmt_usd(prc), fmt_usd(bid)))
        if prc > (ask * 1.1):
            print("WARNING: Sell price ({0}) is > 10% over the current ask ({1})".format(fmt_usd(prc), fmt_usd(bid)))

    ok = input("Execute Order? (yes/no) ")
    if ok != "yes" and ok != "y":
        print("skipping order")
        return False

    res = con.new_order(amount=quantity, price=price, side=side, options=["maker-or-cancel"])
    order = res.json()

    if res.status_code != 200:
        print()
        print("Error status: {0}".format(res.status_code))
        print(res.json())
        print("Error status: {0}".format(res.status_code))
        return False

    elif order["is_cancelled"]:
        print()
        print("AUTO CANCELLED - MAKER FEE NOT AVAILABLE!")
        print()

        extra_fee = subtotal * MAX_API_TAKER_FEE_DELTA

        ok = input("Resubmit order with additional TAKER fee of {0}?? (yes/no) ".format(fmt_usd(extra_fee)))
        if ok != "yes" and ok != "y":
            print("skipping order")
            return False

        res = con.new_order(amount=quantity, price=price, side=side)
        order = res.json()

        if res.status_code != 200:
            print()
            print("Error status: {0}".format(res.status_code))
            print(res.json())
            print("Error status: {0}".format(res.status_code))
            return False

    print()
    print("OK!")
    print_orders([res.json()])

def cancel_order(con):
    order_id = input("order_id: ")
    try:
        order = get_order(con, order_id)
        order.status.cancel()
    except Exception as err:
        print_err(err)
        return

    print("Cancelled order_id: {0}".format(order_id))

def cancel_all(con):
    res = con.cancel_all()
    if res.status_code != 200:
        print(res.json())
    else:
        print("all orders cancelled")

def get_fees(con):
    # note first monnth of API usage shows 0% maker fees, but limit orders must reserve the
    # normal fee amount so they can be executed after the first month with fees reserved
    res = con.fees()
    if res.status_code != 200:
        print("ERROR STATUS: {0}".format(res.status_code))
        print(res.json())
        return -1, -1, -1, -1
    else:
        fee = res.json()

        api_maker_fee = float(fee["api_maker_fee_bps"]/100)
        api_taker_fee = float(fee["api_taker_fee_bps"]/100)

        web_maker_fee = float(fee["web_maker_fee_bps"]/100)
        web_taker_fee = float(fee["web_taker_fee_bps"]/100)

        return api_maker_fee, api_taker_fee, web_maker_fee, web_taker_fee

def show_fees(con):
        api_maker_fee, api_taker_fee, web_maker_fee, web_taker_fee = get_fees(con)
        if api_maker_fee < 0:
            return

        web_taker_fee_delta = web_taker_fee - web_maker_fee
        web_fee_headers = ["Web Maker Fee", "Web Taker Fee", "Delta"]
        web_fees = [[
                fmt_pct(web_maker_fee),
                fmt_pct(web_taker_fee),
                fmt_pct(web_taker_fee_delta),
                ]]

        api_taker_fee_delta = api_taker_fee - api_maker_fee
        api_fee_headers = ["API Maker Fee", "API Taker Fee", "Delta"]
        api_fees = [[
                fmt_pct(api_maker_fee),
                fmt_pct(api_taker_fee),
                fmt_pct(api_taker_fee_delta),
                ]]

        print()
        print("FEES")
        print_sep()
        print(tabulate(web_fees, headers=web_fee_headers, stralign="right"))
        print_sep()
        print(tabulate(api_fees, headers=api_fee_headers, stralign="right"))
        print_sep()

def print_list(items, headers):
    l = []
    for o in items:
        item = []
        for h in headers:
            item.append(o[h])
        l.append(item)

    #print(l)
    #print()
    print(tabulate(l, headers=headers, floatfmt=".8g"))
    #print(tabulate(l, headers=headers))

def print_sep():
    print("-----------------------------------------------------------------------------")

def print_header(title):
    print()
    print("**********************************")
    print(title)
    print("**********************************")

def fmt_usd(val):
    return locale.currency(val, grouping=True)

def fmt_btc(val):
    return "{:.8f}".format(val)

def fmt_nbr(val):
    return "{:,.2f}".format(val)

def fmt_pct(val):
    return "{:.2f}%".format(val)

def fmt_date(dt):
    return dt.strftime("%m/%d/%Y")

def is_float(s):
    try :
        float(s)
        return True
    except :
        return False

def init():
    os.system('clear')

    api_key = ''
    secret_key = ''
    live = False
    first = True

    while True:
        if first:
            first = False
        else:
            print()
            again = input("Try again? (yes/no) ")
            if again != "yes" and again != "y":
                exit()

        print()
        print_sep()
        print("GEMINI API LOGIN")
        print_sep()

        site = input("Which Exchange? [live | sandbox] ")
        live = site == "live"

        api_key = input("api_key: ")
        secret_key = getpass.getpass("secret_key: ")

        ok = len(api_key) > 0 and len (secret_key) > 0
        if not live and not ok:
            # load the default sandbox creds if avail
            try:
                with open(r'sandbox.yaml') as file:
                    creds = yaml.load(file, Loader=yaml.FullLoader)

                    if not live and api_key == '':
                        api_key = creds["api_key"]
                    if not live and secret_key == '':
                        secret_key = creds["secret_key"]
            except:
                print()
                print("Warning: unable to read default creds from sandbox.yaml")
                print(" - see README.md for how to setup a default sandbox.yaml")

        ok = len(api_key) > 0 and len (secret_key) > 0
        if not ok:
            print()
            print("Error: invalid keys.")
            continue

        con = Geminipy(api_key=api_key, secret_key=secret_key, live=live)
        res = con.balances()
        if res.status_code != 200:
            print()
            print("ERROR STATUS: {0}".format(res.status_code))
            print(res.json())
            continue

        #got keys
        os.system('clear')
        print()

        if live:
            print("***************************")
            print("****      GEMINI       ****")
            print("****   LIVE EXCHANGE   ****")
            print("***************************")
        else:
            print("***************************")
            print("****      GEMINI       ****")
            print("****      SANDBOX      ****")
            print("***************************")

        show_balances(con)
        show_history(con, history=False, stats=True)
        show_orders(con)
        show_quote(con)

        print()
        print("help or ? for commands")

        return con

def main():
    con = init()
    cmd = ''
    while True:

        print()
        cmd = input("$ > ")

        if cmd == 'buy':
            buy(con)

        elif cmd == 'buy btc':
            buy_btc(con)

        elif cmd == 'sell':
            sell(con)

        elif cmd == 'sell btc':
            sell_btc(con)

        elif cmd == 'cancel':
            cancel_order(con)

        elif cmd == 'cancel all':
            cancel_all(con)

        elif cmd == 'cancel replace':
            cancel_and_replace(con)

        elif cmd == 'tick' or cmd == 'quote':
            show_quote(con)

        elif cmd == 'list' or cmd == 'orders' or cmd == 'active':
            show_orders(con)

        elif cmd == 'status':
            show_order_status(con)

        elif cmd == 'past' or cmd == 'history':
            show_history(con, history=True, stats=True)

        elif cmd == 'export history':
            show_history(con, history=True, stats=False, format=FORMAT_CSV)

        elif cmd == 'stat' or cmd == 'stats':
            show_history(con, history=False, stats=True)

        elif cmd == 'bal' or cmd == 'balances':
            show_balances(con)

        elif cmd == 'fees':
            show_fees(con)

        elif cmd == 'quit' or cmd == 'q' or cmd == 'exit':
            print("Have a good one!")
            break

        else:
            show_help()

main()
