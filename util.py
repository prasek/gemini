from error import ApiError
import traceback
import locale
import datetime as dt

debug = False

DATETIME_FMT = "%m/%d/%Y"

def fmt_usd(val):
    return locale.currency(val, grouping=True)

def fmt_btc(val):
    return "{:.8f}".format(val)

def fmt_btc_long(val):
    return "{:.10f}".format(val)

def fmt_nbr(val):
    return "{:,.2f}".format(val)

def fmt_pct(val):
    return "{:.2f}%".format(val)

def fmt_date(val):
    return val.strftime(DATETIME_FMT)

def to_date(val):
    return dt.datetime.strptime(val, DATETIME_FMT)

def is_float(s):
    try :
        float(s)
        return True
    except :
        return False

def is_int(s):
    try :
        int(s)
        return True
    except :
        return False

def print_res(res):
    json = res.json()
    print("\nERROR: [{0}] {1}: {2}".format(res.status_code, json['reason'], json['message']))

def print_err(ex):
    if type(ex) is ApiError:
        print_res(ex.res)
    else:
        print("\nERROR: {0}".format(ex))

    if debug:
        traceback.print_exception(type(ex), ex, ex.__traceback__)

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

