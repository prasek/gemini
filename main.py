from api import Geminipy
import gemini
from tabulate import tabulate
from decimal import Decimal
from datetime import datetime
from error import ApiError
import os
import yaml
import csv
import getpass
import util
import locale

locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

FORMAT_TABLE = "table"
FORMAT_CSV= "csv"
 
cmds = [
    ['bal', 'balances and available amounts', lambda con: show_balances(con)],
    ['stat', 'avg. cost basis, gain/loss, perf', lambda con: show_history(con, history=False, stats=True)],
    ['list', 'list open orders', lambda con: show_orders(con)],
    ['tick', 'price quote', lambda con: show_quote(con)],
    ['buy', 'buy in USD quantity including fees', lambda con: buy(con)],
    ['buy btc', 'buy in BTC quantity', lambda con: buy_btc(con)],
    ['sell', 'sell in net USD quantity including fees', lambda con: sell(con)],
    ['sell btc', 'sell in BTC quantity', lambda con: sell_btc(con)],
    ['status', 'order status', lambda con: show_order_status(con)],
    ['cancel', 'cancel an order', lambda con: cancel_order(con)],
    ['cancel all', 'cancel all orders', lambda con: cancel_all(con)],
    ['cancel replace', 'cancel and replace order', lambda con: cancel_and_replace(con)],
    ['history', 'list past trades', lambda con: show_history(con, history=True, stats=True)],
    ['history export', 'export history to CSV', lambda con: show_history(con, history=True, stats=False, format=FORMAT_CSV)],
    ['fees', 'show fees', lambda con: show_fees(con)],
    ['exit', 'exit the console app', lambda con: done()],
]

def show_balances(con):
    try:
        account_value, available_to_trade_usd, available_to_trade_btc = gemini.get_balances(con)

        headers = ["Notational Account Value", "Available to Trade (USD)", "Available to Trade (BTC)"]
        data = [[
                util.fmt_usd(account_value),
                util.fmt_usd(available_to_trade_usd),
                util.fmt_btc(available_to_trade_btc),
                ]]

        print()
        print("BALANCES")
        util.print_sep()
        print(tabulate(data, headers=headers, floatfmt=".8g", stralign="right"))
        util.print_sep()

    except Exception as ex:
        util.print_err(ex)

def show_orders(con):
    try:
        orders = gemini.get_active_orders(con)

        print()
        print("OPEN ORDERS")
        print_orders(orders)

    except Exception as ex:
        util.print_err(ex)

def show_order_status(con):
    try:
        order_id = input("order_id: ")
        status = gemini.get_order_status(con, order_id)

        print()
        print("ORDER STATUS")
        print_orders([status.to_dict()])

    except Exception as ex:
        util.print_err(ex)
        return

def buy(con):
    try:
        side = gemini.SIDE_BUY
        unit = gemini.UNIT_USD
        price, quantity = get_price_quantity(con, side, unit)
        o = gemini.new_order(con, side, price, quantity, unit)

        execute_order(o)

    except Exception as ex:
        util.print_err(ex)

def buy_btc(con):
    try:
        side = gemini.SIDE_BUY
        unit = gemini.UNIT_BTC
        price, quantity = get_price_quantity(con, side, unit)
        o = gemini.new_order(con, side, price, quantity, unit)

        execute_order(o)

    except Exception as ex:
        util.print_err(ex)

def sell(con):
    try:
        side = gemini.SIDE_SELL
        unit = gemini.UNIT_USD
        price, quantity = get_price_quantity(con, side, unit)
        o = gemini.new_order(con, side, price, quantity, unit)

        execute_order(o)

    except Exception as ex:
        util.print_err(ex)

def sell_btc(con):
    try:
        side = gemini.SIDE_SELL
        unit = gemini.UNIT_BTC
        price, quantity = get_price_quantity(con, side, unit)
        o = gemini.new_order(con, side, price, quantity, unit)

        execute_order(o)

    except Exception as ex:
        util.print_err(ex)

def execute_order(o):

    o.prepare()

    if not confirm_order(o):
        return

    try:
        o.execute()
    except ApiError as ex:
        if ex.code == 406  and ex.json['reason'] == 'InsufficientFunds':
            if not confirm_order_msg("Insufficient funds, adjust for max API fee?"):
                return

            o.set_reserve_api_fees(gemini.RESERVE_FEE_MAX)
            o.prepare()

            if not confirm_order(o):
                return

            o.execute()
        else:
            raise

    if o.get_status().is_cancelled() and o.get_maker_or_cancel():
        print()
        print("AUTO CANCELLED - MAKER FEE NOT AVAILABLE!")
        print()

        o.set_maker_or_cancel(False)
        o.prepare()

        if not confirm_order_msg("Accept TAKER fee of {0}??".format(util.fmt_usd(o.get_fee()))):
            return
    
        if not confirm_order(o):
            return

        o.execute()

    print()
    print("OK!")
    print_orders([o.get_status().to_dict()])

def get_price_quantity(con, side, unit):
    print("{0} {1}".format(side.upper(), unit))
    price = get_price(con, side, unit)
    quantity = get_quantity(con, side, unit)
    return price, quantity

def get_price(con, side, unit):
    price = input("Price (USD): ")

    if price == "market":
        bid, ask, spread, last = gemini.get_quote(con)
        max_over_under = input("Max over/under bid/ask (default: 0): ")
        if len(max_over_under) == 0:
            max_over_under = 0
        else:
            if not util.is_float(max_over_under):
                raise Exception("Error: not a valid USD value.")
            max_over_under = float(max_over_under)

        if side == gemini.SIDE_BUY:
            price = str(ask + max_over_under)
        if side == gemini.SIDE_SELL:
            price = str(bid - max_over_under)

    if not util.is_float(price):
        raise Exception("Invalid price.")

    return price

def get_quantity(con, side, unit):
    quantity = input("Quantity ({0}): ".format(unit))

    if quantity == "max":
        account_value, available_to_trade_usd, available_to_trade_btc = gemini.get_balances(con)
        if side == gemini.SIDE_BUY and unit == gemini.UNIT_USD:
            quantity = str(available_to_trade_usd)
        if side == gemini.SIDE_SELL and unit == gemini.UNIT_BTC:
            quantity = str(available_to_trade_btc)

    if not util.is_float(quantity):
        raise Exception("Invalid quantity.")

    return quantity

def confirm_order(o):
    util.print_header("CONFIRM {0}:".format(o.get_side().upper()))
    print(tabulate([["PRICE", "", ""],
                    ["", util.fmt_nbr(o.get_price()), gemini.UNIT_USD],
                    ["", "", ""],
                    ["QUANTITY", "", ""],
                    ["", util.fmt_btc(o.get_btc_amount()), gemini.UNIT_BTC],
                    ["", util.fmt_nbr(o.get_subtotal()), gemini.UNIT_USD],
                    ["", "", ""],
                    ["Subtotal", util.fmt_usd(o.get_subtotal()), gemini.UNIT_USD],
                    ["Fee", util.fmt_usd(o.get_fee()), gemini.UNIT_USD],
                    ["Total", util.fmt_usd(o.get_total()), gemini.UNIT_USD],
                    ], tablefmt="plain", floatfmt=".8g", stralign="right"))
    util.print_sep()

    for warning in o.get_warnings():
        print(warning)

    return confirm_order_msg("Execute Order?")

def confirm_order_msg(msg):
    print()
    ok = input(msg + " (yes/no) ")
    if ok != "yes" and ok != "y":
        print("skipping order")
        return False

    return True

def cancel_and_replace(con):
    try:
        order_id = input("order_id: ")
        o = gemini.get_order(con, order_id)

        if not o.get_status().is_live():
            print("Order is not live.")
            return

        price = get_price(con, o.get_side(), o.get_quantity_unit())
        o.set_price(price)
        o.set_quantity(o.get_status().get_remaining_amount())
        o.prepare()

        if not confirm_order(o):
            return

        o.cancel_and_replace()

        if o.get_status().is_cancelled():
            o.set_maker_or_cancel(False)
            o.prepare()

            if not confirm_order_msg("Accept TAKER fee of {0}??".format(util.fmt_usd(o.get_fee()))):
                return
        
            if not confirm_order(o):
                return

            o.execute()

        print()
        print("ORDER REPLACED")
        print_orders([o.get_status().to_dict()])

    except Exception as ex:
        util.print_err(ex)
        return

def print_orders(orders):
    headers = ["date", "side", "total", "type", "price", "original_amount", "symbol", "executed_amount", "avg_execution_price", "remaining_amount", "is_live", "is_cancelled", "order_id"]
    l = []
    for o in orders:
        price = float(o["price"])
        quantity = float(o["original_amount"])
        total = price * quantity
        o["total"] = util.fmt_usd(total)
        o["price"] = util.fmt_usd(price)
        o["avg_execution_price"] = util.fmt_usd(float(o["avg_execution_price"]))
        o["date"] = util.fmt_date(datetime.fromtimestamp(int(o["timestamp"])))
        item = []
        for h in headers:
            item.append(o[h])
        l.append(item)

    util.print_sep()
    print(tabulate(l, headers=headers, floatfmt=".8g", stralign="right"))
    util.print_sep()

def show_history(con, history=True, stats=True, format=FORMAT_TABLE):
    try:
        symbol = "btcusd"
        res = con.past_trades(symbol=symbol, limit_trades=1000)
        if res.status_code != 200:
            raise ApiError(res)

        orders = res.json()
        headers = ["date", "type", "price", "amount","basis", "current", "gain/loss", "gain/loss %", "symbol", "fee_amount", "order_id"]
        l = []
        buy_total = 0.0
        buy_quantity = 0.0

        bid, ask, spread, last = gemini.get_quote(con)

        for o in orders:
            price = float(o["price"])
            quantity = float(o["amount"])
            fees = float(o["fee_amount"])
            basis = price * quantity + fees
            current = quantity * last
            gain = current - basis
            gain_pct = gain / basis * 100
            dt = datetime.fromtimestamp(o["timestamp"])
            o["date"] = dt.strftime("%m/%d/%Y")
            o["fee_amount"] = util.fmt_usd(fees)
            o["price"] = util.fmt_usd(price)
            o["basis"] = util.fmt_usd(basis)
            o["current"] = util.fmt_usd(current)
            o["symbol"] = symbol
            o["gain/loss"] = util.fmt_usd(gain)
            o["gain/loss %"] = util.fmt_pct(gain_pct)
            o["symbol"] = symbol

            item = []
            for h in headers:
                item.append(o[h])
            l.append(item)

            if o["type"] == "Buy":
                buy_total += basis
                buy_quantity += quantity

        if history:
            if format == FORMAT_TABLE:
                print()
                print("HISTORY")
                util.print_sep()
                print(tabulate(l, headers=headers, floatfmt=".8g", stralign="right"))
                util.print_sep()
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
            #TODO: calc realized and unrealized gain/loss
            avg_cost_basis = buy_total/buy_quantity
            perf = ((last / avg_cost_basis) - 1) * 100
            curr_value = buy_quantity * last
            gain = curr_value - buy_total

            headers = ["gain/loss", "gain/loss %", "avg cost basis/btc", "last price", "cost basis", "current value"]
            stats = [[
                    util.fmt_usd(gain),
                    util.fmt_pct(perf),
                    util.fmt_usd(avg_cost_basis),
                    util.fmt_usd(last),
                    util.fmt_usd(buy_total),
                    util.fmt_usd(curr_value),
                    ]]

            print()
            print("TRADE STATS")
            util.print_sep()
            print(tabulate(stats, headers=headers, stralign="right"))
            util.print_sep()

    except Exception as ex:
        util.print_err(ex)

def show_quote(con):
    try:
        bid, ask, spread, last = gemini.get_quote(con)

        print()
        print("QUOTE")
        util.print_sep()
        print("{0} ASK".format(util.fmt_nbr(ask)))
        print("Spread of {0}, LAST: {1}".format(util.fmt_nbr(spread), format(util.fmt_nbr(last))))
        print("{0} BID".format(util.fmt_nbr(bid)))
        util.print_sep()

        return bid, ask, spread, last

    except Exception as ex:
        util.print_err(ex) 


def cancel_order(con):
    try:
        order_id = input("order_id: ")
        o = gemini.get_order(con, order_id)
        o.get_status().cancel()
        print("Cancelled order_id: {0}".format(order_id))

    except Exception as ex:
        util.print_err(ex)
        return

def cancel_all(con):
    res = con.cancel_all()
    if res.status_code != 200:
        util.print_res(res)
    else:
        print("all orders cancelled")

def show_fees(con):
    try:
        api_maker_fee, api_taker_fee, web_maker_fee, web_taker_fee = gemini.get_fees(con)
        if api_maker_fee < 0:
            return

        web_taker_fee_delta = web_taker_fee - web_maker_fee
        web_fee_headers = ["Web Maker Fee", "Web Taker Fee", "Delta"]
        web_fees = [[
                util.fmt_pct(web_maker_fee),
                util.fmt_pct(web_taker_fee),
                util.fmt_pct(web_taker_fee_delta),
                ]]

        api_taker_fee_delta = api_taker_fee - api_maker_fee
        api_fee_headers = ["API Maker Fee", "API Taker Fee", "Delta"]
        api_fees = [[
                util.fmt_pct(api_maker_fee),
                util.fmt_pct(api_taker_fee),
                util.fmt_pct(api_taker_fee_delta),
                ]]

        print()
        print("FEES")
        util.print_sep()
        print(tabulate(web_fees, headers=web_fee_headers, stralign="right"))
        util.print_sep()
        print(tabulate(api_fees, headers=api_fee_headers, stralign="right"))
        util.print_sep()

    except Exception as ex:
        util.print_err(ex)

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
        util.print_sep()
        print("GEMINI API LOGIN")
        util.print_sep()

        site = input("Which Exchange? [live | sandbox] ")
        live = site == "live"

        api_key = input("api_key: ")
        secret_key = getpass.getpass("secret_key: ")

        ok = len(api_key) > 0 and len (secret_key) > 0
        if not ok:
            filepath = "sandbox.yaml"
            readfile = False
            try:
                if live:
                    filepath = "live.yaml"
                    if os.path.isfile(filepath):
                        perm = oct(os.stat(filepath).st_mode & 0o777)
                        if perm == oct(0o600):
                            readfile = True
                        else:
                            print("\n{0} found, but requires 0o600 permission (got {1}) skipping ...".format(filepath, perm))
                else:
                   readfile = os.path.isfile(filepath)

                if readfile:
                    with open(filepath) as f:
                        creds = yaml.load(f, Loader=yaml.FullLoader)

                        if api_key == '':
                            api_key = creds["api_key"]
                        if secret_key == '':
                            secret_key = creds["secret_key"]

            except Exception as ex:
                print()
                print("Warning: unable to read default creds from " + filepath)
                print("see README.md for how to setup a default " + filepath)
                print()
                print(ex)

        ok = len(api_key) > 0 and len (secret_key) > 0
        if not ok:
            print()
            print("Error: invalid keys.")
            continue

        con = Geminipy(api_key=api_key, secret_key=secret_key, live=live)
        res = con.balances()
        if res.status_code != 200:
            util.print_res(res)
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

def done():
    print("Have a good one!")
    return False

def show_help():
    cmd_table = list(c[0:2] for c in cmds)
    print(tabulate(cmd_table, headers=["command", "info"]))

def main():
    con = init()
    lookup = dict((c[0], c[2]) for c in cmds)

    while True:

        print()
        cmd = input("$ > ")

        if not cmd in lookup:
            show_help()
        else:
            if lookup[cmd](con) is False:
                break

main()
