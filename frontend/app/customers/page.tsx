"use client";

import { useEffect, useState } from "react";
import { RefreshCw, Upload } from "lucide-react";
import { api, type Customer } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  async function loadCustomers() {
    setLoading(true);
    setMessage("");
    try {
      setCustomers(await api.getCustomers());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load customers.");
    } finally {
      setLoading(false);
    }
  }

  async function uploadCsv() {
    if (!file) return;
    setMessage("");
    try {
      const result = await api.uploadCustomers(file);
      setMessage(`Imported ${result.customers_created} customers and ${result.purchases_created} purchases.`);
      setFile(null);
      await loadCustomers();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed.");
    }
  }

  useEffect(() => {
    loadCustomers();
  }, []);

  return (
    <main className="mx-auto max-w-7xl px-5 py-7">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Customers</h1>
          <p className="text-sm text-slate-500">{customers.length} records</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input className="w-72" type="file" accept=".csv" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          <Button variant="secondary" onClick={uploadCsv} disabled={!file}>
            <Upload size={16} />
            Upload CSV
          </Button>
          <Button variant="ghost" size="icon" title="Refresh customers" onClick={loadCustomers}>
            <RefreshCw size={16} />
          </Button>
        </div>
      </div>

      {message ? <div className="mb-4 rounded-md border border-line bg-white px-4 py-3 text-sm text-slate-700">{message}</div> : null}

      <div className="surface overflow-hidden rounded-lg">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] border-collapse text-sm">
            <thead className="border-b border-line bg-mist text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Customer</th>
                <th className="px-4 py-3 font-semibold">Consent</th>
                <th className="px-4 py-3 font-semibold">LTV</th>
                <th className="px-4 py-3 font-semibold">Engagement</th>
                <th className="px-4 py-3 font-semibold">Purchases</th>
                <th className="px-4 py-3 font-semibold">Latest Products</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-4 py-6 text-slate-500" colSpan={6}>
                    Loading customers...
                  </td>
                </tr>
              ) : customers.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-slate-500" colSpan={6}>
                    No customers found.
                  </td>
                </tr>
              ) : (
                customers.map((customer) => (
                  <tr key={customer.id} className="border-b border-line bg-white last:border-0">
                    <td className="px-4 py-3">
                      <p className="font-medium text-ink">
                        {customer.first_name} {customer.last_name}
                      </p>
                      <p className="text-xs text-slate-500">{customer.email}</p>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {customer.unsubscribed ? <Badge tone="rose">Unsubscribed</Badge> : null}
                        {customer.email_opt_in ? <Badge tone="teal">Email</Badge> : null}
                        {customer.sms_opt_in ? <Badge tone="cobalt">SMS</Badge> : null}
                      </div>
                    </td>
                    <td className="px-4 py-3">${customer.lifetime_value.toFixed(2)}</td>
                    <td className="px-4 py-3">{customer.engagement_score.toFixed(0)}</td>
                    <td className="px-4 py-3">{customer.purchase_summary.purchase_count}</td>
                    <td className="px-4 py-3 text-slate-600">{customer.purchase_summary.latest_products.join(", ")}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
