import billingcore
import requests


def sync_invoices():
    data = requests.get("https://api.example.com/invoices").json()
    return billingcore.__doc__ and data


def report_totals(rows):
    return sum(r.get("amount", 0) for r in rows)
