from error import ApiError
import traceback
import locale

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

def print_err(ex):
    if type(ex) is ApiError:
        print("ERROR: [{0}] {1}: {2}".format(ex.code, ex.json['reason'], ex.json['message']))
    else:
        print("ERROR: {0}".format(ex))
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

