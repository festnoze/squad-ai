import { NgModule } from "@angular/core";
import { RouterModule, Routes } from "@angular/router";
import { InvoiceListComponent } from "./invoice/invoice.component";

const routes: Routes = [
  { path: "invoices", component: InvoiceListComponent },
  { path: "admin", loadChildren: () => import("./admin/admin.module") },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule],
})
export class AppRoutingModule {}
