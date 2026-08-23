import { Injectable } from "@angular/core";

@Injectable({ providedIn: "root" })
export class InvoiceService {
  load() {
    return fetch("/api/invoices").then(r => r.json());
  }
}
