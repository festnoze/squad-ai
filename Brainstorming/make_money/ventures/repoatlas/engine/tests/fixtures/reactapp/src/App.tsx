import { BrowserRouter, Route, Routes } from "react-router-dom";
import { InvoiceTable } from "./components/InvoiceTable";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/dashboard" element={<InvoiceTable />} />
        <Route path="/settings" element={<div>settings</div>} />
      </Routes>
    </BrowserRouter>
  );
}
