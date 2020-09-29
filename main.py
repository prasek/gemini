import os
from gemini import Geminipy
from tabulate import tabulate
from decimal import Decimal
import yaml

fee_pct =           0.0010
taker_fee_delta =   0.0025
usd_fmt = "${:,.2f}" 
nbr_fmt = "{:,.2f}" 
btc_fmt = "{:.8f}"

def init():
    os.system('clear')

    api_key = ''
    secret_key = ''

    live = False

    print()
    print("-----------------------")
    print("GEMINI API LOGIN")
    print("-----------------------")
    site = input("Which Exchange? [live | sandbox] ")


    api_key = input("api_key: ")
    secret_key = input("secret_key: ")

    os.system('clear')

    if site == "live":
        live = True
        print()
        print("***************************")
        print("****      GEMINI       ****")
        print("****   LIVE EXCHANGE   ****")
        print("***************************")
    else:
        print("***************************")
        print("****      GEMINI       ****")
        print("****      SANDBOX      ****")
        print("***************************")
        with open(r'test.yaml') as file:
            creds = yaml.load(file, Loader=yaml.FullLoader)

            if not live and api_key == '':
                api_key = creds["api_key"]
            if not live and secret_key == '':
                secret_key = creds["secret_key"]

    print()
    print("help or ? for commands")

    return Geminipy(api_key=api_key, secret_key=secret_key, live=live)
    
def print_orders(orders):
    headers = ["symbol", "side", "type", "price", "original_amount", "symbol", "total", "executed_amount", "remaining_amount", "order_id"]
    l = []
    for o in orders: 
        price = float(o["price"])
        quantity = float(o["original_amount"])
        total = price * quantity
        o["total"] = "{0} USD".format(usd_fmt.format(total))
        item = []
        for h in headers:
            item.append(o[h])
        l.append(item)

    #print(l)
    #print()
    print(tabulate(l, headers=headers, floatfmt=".8g"))

def print_tick(tick):
    print()
    print("QUOTE")
    headers = ["bid", "ask", "spread", "last"]
    print_list([tick], headers)

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

def is_float(s):
    try :
        float(s)
        return True
    except :
        return False

def get_price_quantity(side, quantity_unit):
        print(side.upper())
        price = input("Price (USD): ")
        quantity = input("Quantity ({0}): ".format(quantity_unit))

        if not is_float(price) or not is_float(quantity):
            print("invalid price or quantity")
            return None, None

        return price, quantity


def execute_order(side, price, quantity, subtotal, fee, total):
    print()
    print("QUOTE")
    tick = con.pubticker(symbol="btcusd").json()
    ask = float(tick["ask"])
    bid = float(tick["bid"])
    last = float(tick["last"])
    prc = float(price)
    spread = ask - bid
    print("--------------------")
    print("{0} ASK".format(nbr_fmt.format(ask)))
    print("Spread of {0}, LAST: {1}".format(nbr_fmt.format(spread), format(nbr_fmt.format(last))))
    print("{0} BID".format(nbr_fmt.format(bid)))
    print("--------------------")
    print()
    print("**************************")
    print("CONFIRM {0}:".format(side.upper()))
    print("**************************")

    print(tabulate([["PRICE", "", ""], 
                    [nbr_fmt.format(float(price)), "", "USD"],
                    ["", "", ""],
                    ["QUANTITY", "", ""],
                    [btc_fmt.format(float(quantity)), "", "BTC"],
                    [nbr_fmt.format(subtotal), "", "USD"], 
                    ["", "", ""],
                    ["Subtotal", usd_fmt.format(subtotal), "USD"], 
                    ["Fee", usd_fmt.format(fee), "USD"],
                    ["Total", usd_fmt.format(total), "USD"],
                    ], tablefmt="plain", floatfmt=".8g"))
    print("--------------------")

    if spread > 0.05:
        print("WARNING: Spread: {0}".format(usd_fmt.format(spread)))
    if side == "buy":
        if prc > ask:
            print("WARNING: Buy price ({0}) is higher than ask ({1}) - TAKER".format(usd_fmt.format(prc), usd_fmt.format(ask)))
        if prc < (bid * .9):
            print("WARNING: Buy price ({0}) is > 10% under current bid ({1})".format(usd_fmt.format(prc), usd_fmt.format(ask)))
    if side == "sell":
        if prc < bid:
            print("WARNING: Sell price ({0}) is lower than bid ({1}) - TAKER".format(usd_fmt.format(prc), usd_fmt.format(bid)))
        if prc > (ask * 1.1):
            print("WARNING: Sell price ({0}) is > 10% over the current ask ({1})".format(usd_fmt.format(prc), usd_fmt.format(bid)))

    ok = input("Execute Order? (yes/no) ")
    if ok != "yes" and ok != "y":
        print("skipping order")
        return False

    res = con.new_order(amount=amount_btc, price=price, side=side, options=["maker-or-cancel"])
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

        extra_fee = subtotal * taker_fee_delta

        ok = input("Resubmit order with additional TAKER fee of {0}?? (yes/no) ".format(usd_fmt.format(extra_fee)))
        if ok != "yes" and ok != "y":
            print("skipping order")
            return False

        res = con.new_order(amount=amount_btc, price=price, side=side)
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

def print_help():
        cmds = [
                ["buy", "buy in USD quantity (including fee)"],
                ["buy btc", "buy in BTC quantity"],
                ["sell", "buy in USD quantity (including fee)"],
                ["sell btc", "sell in BTC quantity"],
                ["list", "list open orders"],
                ["tick", "price quote"],
                ["cancel", "cancel order id"],
                ["cancel all", "cancel all open orders"],
                ["bal", "balances and available amounts"],
                ["exit", "exit the console app"],
                ]
        print(tabulate(cmds, headers=["command", "info"]))

con = init()
cmd = ''
while True:

    print()
    cmd = input("$ > ")

    if cmd == 'buy':
        side = 'buy'
        quantity_unit = "USD"

        price, amount_usd = get_price_quantity(side, quantity_unit)
        if price is None or amount_usd is None:
            continue

        subtotal = float(amount_usd) / (1 + fee_pct)
        fee = subtotal * fee_pct
        total = subtotal + fee

        amount_btc = btc_fmt.format(subtotal / float(price))

        execute_order(side, 
                price=price, 
                quantity=amount_btc, 
                subtotal=subtotal, 
                fee=fee, 
                total=total)

    elif cmd == 'buy btc':
        side = 'buy'
        quantity_unit = "BTC"

        price, amount_btc = get_price_quantity(side, quantity_unit)
        if price is None or amount_btc is None:
            continue

        subtotal = float(amount_btc) * float(price)
        fee = subtotal * fee_pct
        total = subtotal + fee

        execute_order(side, 
                price=price, 
                quantity=amount_btc, 
                subtotal=subtotal, 
                fee=fee, 
                total=total)

    elif cmd == 'sell':
        side = 'sell'
        quantity_unit = "USD"

        price, amount_usd = get_price_quantity(side, quantity_unit)
        if price is None or amount_usd is None:
            continue

        subtotal = float(amount_usd) / (1 - fee_pct)
        fee = subtotal * fee_pct
        total = subtotal - fee
        
        amount_btc = btc_fmt.format((float(subtotal) / float(price)))

        execute_order(side, 
                price=price, 
                quantity=amount_btc, 
                subtotal=subtotal, 
                fee=fee, 
                total=total)

    elif cmd == 'sell btc':
        side = 'sell'
        quantity_unit = "BTC"

        price, amount_btc = get_price_quantity(side, quantity_unit)
        if price is None or amount_btc is None:
            continue

        subtotal = float(amount_btc) * float(price)
        fee = subtotal * fee_pct
        total = subtotal - fee

        execute_order(side, 
                price=price, 
                quantity=amount_btc, 
                subtotal=subtotal, 
                fee=fee, 
                total=total)

    elif cmd == 'cancel':
        order_id = input("order_id: ")
        if not order_id.isnumeric():
            print("invalid order_id")
            continue

        res = con.cancel_order(order_id)

        if res.status_code != 200:
            print(res.json())
        else:
            print("Cancelled order_id: {0}".format(order_id))

    elif cmd == 'cancel all':
        res = con.cancel_all()
        print("all orders cancelled")

    elif cmd == 'tick':
        res = con.pubticker(symbol="btcusd")
        if res.status_code != 200:
            print("ERROR STATUS: {0}".format(res.status_code))
            print(res.json())
            continue

        tick = res.json()
        tick["spread"] = float(tick["ask"]) - float(tick["bid"])
        print_tick(tick)

    elif cmd == 'list':
        res = con.active_orders()
        if res.status_code != 200:
            print("ERROR STATUS: {0}".format(res.status_code))
            print(res.json())
            continue

        print_orders(res.json())

    elif cmd == 'bal':
        res = con.balances()
        if res.status_code != 200:
            print("ERROR STATUS: {0}".format(res.status_code))
            print(res.json())
            continue
        print_list(res.json(), ["type", "currency", "amount", "available"])

    elif cmd == 'quit' or cmd == 'q' or cmd == 'exit':
        print("Have a good one!")
        break

    elif cmd == 'help' or cmd == '?':
        print_help()

    else:
        print_help()

