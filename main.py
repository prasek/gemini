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


def load_order(con, order_id):
    res = con.order_status(order_id)
    if res.status_code != 200:
        return False, res

    order_status = res.json()

    side = order_status["side"]
    price = float(order_status["price"])
    quantity = float(order_status["remaining_amount"])

    o = Order(con, side=side, price=price,quantity=quantity, quantity_unit=UNIT_BTC, order_status=order_status)
    o.set_order_status(order_status)

    return True, o

class Order:
    def __init__(self, con, side, price, quantity, quantity_unit=UNIT_USD, order_status=None):
        self.con = con
        self.user_side = side
        self.user_price = price
        self.user_quantity = quantity
        self.user_quantity_unit = quantity_unit
        self.btc_amount = -1.0
        self.subtotal = 0.0
        self.maker_fee = 0.0
        self.taker_fee = 0.0
        self.fee = 0.0
        self.total = 0.0

        self.maker_or_cancel = True
        self.prepared = False

    def is_valid(self):
        ok = (
                self.user_price > 0
                and self.user_quantity > 0
                and (self.user_quantity_unit == UNIT_BTC or self.user_quantity_unit == UNIT_USD)
                and (self.user_side == SIDE_BUY or self.user_side == SIDE_SELL)
                )

        return ok

    def is_prepared(self):
        ok = (
                self.prepared
                and self.btc_amount > 0
                )

        return ok

    def set_price(self, price):
        if not is_float(price):
            return False, {"error": "new price is not float"}
        self.user_price = float(price)
        self.prepared = False

        return True, None

    def set_maker_or_cancel(self, required):
        self.maker_or_cancel = bool(required)
        self.prepared = False

    def prepare(self):
        self.price = self.user_price

        if self.user_quantity_unit == UNIT_USD:
            self.btc_amount = self.user_quantity / self.price
        elif self.user_quantity_unit == UNIT_BTC:
            self.btc_amount = self.user_quantity
        else:
            raise Exception("invalid quantity unit" + self.user_quantity_unit)

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

    def cancel_and_replace(self):
        res = self.con.cancel_order(self.order_id)
        if res.status_code != 200:
            return False, res

        res = self.con.order_status(self.order_id)
        if res.status_code != 200:
            return False, res

        order_status = res.json()

        side = order_status["side"]
        remaining_amount = float(order_status["remaining_amount"])

        self.user_quantity = remaining_amount
        self.user_quantity_unit = UNIT_BTC

        self.prepare()

        return self.execute()

    def execute(self):
        if not self.is_valid():
            raise Exception("Error: order not valid")

        if not self.is_prepared():
            raise Exception("Error: order not prepared")

        options = []
        if self.maker_or_cancel:
            options.append(OPTION_MAKER_OR_CANCEL)

        res = self.con.new_order(amount=self.btc_amount, price=self.user_price, side=self.user_side, options=options)

        if res.status_code != 200:
            return False, res

        order_status = res.json()
        self.set_order_status(order_status)
        return True, res

    def set_order_status(self, o):
        self.order_id = int(o["order_id"])
        self.timestamp = o["timestamp"]
        self.side = o["side"]
        self.type = o["type"]
        self.price = float(o["price"])
        self.original_amount = float(o["original_amount"])
        self.total = self.price * self.original_amount
        self.symbol = o["symbol"]
        self.executed_amount = float(o["executed_amount"])
        self.avg_execution_price = float(o["avg_execution_price"])
        self.remaining_amount = float(o["remaining_amount"])
        self.is_live = o["is_live"]
        self.is_cancelled = o["is_cancelled"]

    def reset_order_status(self):
        self.order_id = -1
        self.timestamp = 0
        self.side = SIDE_BUY
        self.type = TYPE_LIMIT
        self.price = -1.0
        self.original_amount = 0.0
        self.symbol = SYMBOL_BTCUSD
        self.executed_amount = 0.0
        self.avg_execution_price = 0.0
        self.remaining_amount = 0.0
        self.is_live = False
        self.is_cancelled = False

    def get_order_status(self):
        o = {}
        o["order_id"] = self.order_id
        o["timestamp"] = self.timestamp
        o["side"] = self.side
        o["total"] = self.total
        o["type"] = self.type
        o["price"] = self.price
        o["original_amount"] = self.original_amount
        o["symbol"] = self.symbol
        o["executed_amount"] = self.executed_amount
        o["avg_execution_price"] = self.avg_execution_price
        o["remaining_amount"] = self.remaining_amount
        o["is_live"] = self.is_live
        o["is_cancelled"] = self.is_cancelled
        return o


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
    order_id = input("order_id: ")
    ok, o = load_order(con, order_id)
    if not ok:
        print("ERROR STATUS: {0}".format(o.status_code))
        print(o.json())
        return

    print()
    print("ORDER STATUS")
    print_orders([o.get_order_status()])

def cancel_and_replace(con):
    order_id = input("order_id: ")
    ok, o = load_order(con, order_id)
    if not ok:
        print("ERROR STATUS: {0}".format(o.status_code))
        print(o.json())
        return

    if not o.is_live:
        print("Order is not live.")
        return

    price = input("new price: ")
    o.set_price(price)
    o.prepare()
    print_sep()
    print("Side: " + o.user_side)
    print("Price: " + fmt_usd(o.user_price))
    print("Quantity: " + fmt_btc(o.user_quantity))
    print("Subtotal: " + fmt_usd(o.subtotal))
    print("Fee: " + fmt_usd(o.fee))
    print("Total: " + fmt_usd(o.total))
    print_sep()

    print()
    ok = input("Execute Order? (yes/no) ")
    if ok != "yes" and ok != "y":
        print("skipping order")
        return False

    ok, res = o.cancel_and_replace()
    if not ok:
        print("ERROR STATUS: {0}".format(o.status_code))
        print(o.json())
        return

    print()
    print("ORDER REPLACED")
    print_orders([o.get_order_status()])

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
    if not order_id.isnumeric():
        print("invalid order_id")
        return

    res = con.cancel_order(order_id)
    if res.status_code != 200:
        print(res.json())
    else:
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
