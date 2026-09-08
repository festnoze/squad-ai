import { Component } from "@angular/core";
import { InvoiceService } from "./invoice.service";

@Component({
  selector: "app-invoice-list",
  template: "<ul></ul>",
})
export class InvoiceListComponent {
  constructor(private readonly invoices: InvoiceService) {}
}
