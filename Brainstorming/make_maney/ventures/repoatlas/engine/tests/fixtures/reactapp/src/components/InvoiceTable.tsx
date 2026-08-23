import { useEffect, useState } from "react";

export function InvoiceTable() {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    fetch("/api/invoices").then(r => r.json()).then(setRows);
  }, []);
  return <table>{rows.length}</table>;
}
