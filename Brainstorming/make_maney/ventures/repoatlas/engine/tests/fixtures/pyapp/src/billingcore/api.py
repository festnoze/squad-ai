from fastapi import APIRouter

from billingcore.core import InvoiceEngine

router = APIRouter()
engine = InvoiceEngine()


@router.get("/invoices")
def list_invoices():
    return engine.list_all()


@router.post("/invoices/{invoice_id}/retry")
def retry_invoice(invoice_id: int):
    return engine.retry(invoice_id)
