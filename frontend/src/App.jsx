import { useCallback, useEffect, useState } from 'react';
import { apiRequest, formatMoney } from './api.js';

const organizations = [
  { slug: 'northwind', name: 'Northwind Ventures' },
  { slug: 'bluebird', name: 'Bluebird Capital' },
];
const labels = {
  suggested: 'Suggested', needs_review: 'Needs review', reconciled: 'Reconciled', ignored: 'Ignored',
  open: 'Open', partially_funded: 'Partially funded', funded: 'Funded',
};

export default function App() {
  const [organization, setOrganization] = useState('northwind');
  const [transactions, setTransactions] = useState([]);
  const [lineItems, setLineItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [tx, items] = await Promise.all([
        apiRequest('/transactions/', organization),
        apiRequest('/line-items/', organization),
      ]);
      setTransactions(tx);
      setLineItems(items);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [organization]);

  useEffect(() => { refresh(); }, [refresh]);

  async function upload(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setBusy(true);
    setSummary(null);
    setError('');
    const body = new FormData();
    body.append('file', file);
    try {
      setSummary(await apiRequest('/import/', organization, { method: 'POST', body }));
      await refresh();
    } catch (err) {
      if (err.data?.errors) setSummary(err.data);
      else setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function act(path) {
    setBusy(true);
    setError('');
    try {
      await apiRequest(path, organization, { method: 'POST' });
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <header className="page-header">
        <div><h1>Ledgerly</h1><p>Bank reconciliation for capital calls</p></div>
        <label>Organization
          <select value={organization} onChange={(event) => setOrganization(event.target.value)}>
            {organizations.map((org) => <option key={org.slug} value={org.slug}>{org.name}</option>)}
          </select>
        </label>
      </header>

      <section className="panel upload-panel">
        <div><h2>Import a bank statement</h2><p>Choose a CSV with date, description, amount, type, and reference columns.</p></div>
        <label className="button">{busy ? 'Working…' : 'Choose CSV'}
          <input type="file" accept=".csv,text/csv" onChange={upload} disabled={busy} />
        </label>
      </section>

      {summary && <section className="panel" aria-live="polite">
        <h2>{summary.file_rejected ? 'File rejected' : 'Import summary'}</h2>
        <p>{summary.imported} imported · {summary.duplicates} duplicates</p>
        {summary.errors?.length > 0 && <ul>{summary.errors.map((item, i) =>
          <li key={String(item.line) + i}>Line {item.line}: {item.message}</li>)}</ul>}
      </section>}
      {error && <div className="error" role="alert">{error} <button onClick={refresh}>Retry</button></div>}

      <section className="panel">
        <div className="section-heading">
          <div><h2>Transactions</h2><p>Newest first. Review proposed matches before approval.</p></div>
          <button onClick={refresh} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
        </div>
        {loading ? <p className="state">Loading transactions…</p> :
          transactions.length === 0 ? <p className="state">No transactions yet. Import a statement to begin.</p> :
          <div className="table-scroll"><table><thead><tr>
            <th>Date / description</th><th>Amount</th><th>Status</th><th>Suggested investor / reference</th><th>Match reason</th><th>Actions</th>
          </tr></thead><tbody>
            {transactions.map((row) => <tr key={row.id}>
              <td>{row.date}<br /><strong>{row.description}</strong><small>Bank reference: {row.reference}</small></td>
              <td>{formatMoney(row.amount)}<small>{row.type}</small></td>
              <td>{labels[row.status]}</td>
              <td>{row.matches.length ? row.matches.map((match) =>
                <div className="match" key={match.id}>{match.investor_name}<small>{match.expected_reference}</small></div>) : '—'}</td>
              <td>{row.review_reason && <p>{row.review_reason}</p>}
                {row.matches.map((match) => <p key={match.id}>{match.reason}</p>)}</td>
              <td className="actions">
                {row.matches.filter((match) => match.status === 'proposed').map((match) =>
                  <div key={match.id}>
                    <button disabled={busy} onClick={() => act('/matches/' + match.id + '/approve/')}>Approve</button>{' '}
                    <button disabled={busy} onClick={() => act('/matches/' + match.id + '/reject/')}>Reject</button>
                  </div>)}
                {['suggested', 'needs_review'].includes(row.status) &&
                  <button disabled={busy} onClick={() => act('/transactions/' + row.id + '/ignore/')}>Ignore</button>}
              </td>
            </tr>)}
          </tbody></table></div>}
      </section>

      <section className="panel">
        <div className="section-heading"><div><h2>Capital call line items</h2><p>Called, funded, remaining, and status.</p></div></div>
        {loading ? <p className="state">Loading line items…</p> :
          lineItems.length === 0 ? <p className="state">No line items for this organization.</p> :
          <div className="table-scroll"><table><thead><tr>
            <th>Investor / call</th><th>Reference</th><th>Amount called</th><th>Funded</th><th>Remaining</th><th>Status</th>
          </tr></thead><tbody>
            {lineItems.map((item) => <tr key={item.id}>
              <td><strong>{item.investor_name}</strong><small>Call #{item.call_number} · due {item.due_date}</small></td>
              <td>{item.expected_reference}</td><td>{formatMoney(item.amount_called)}</td>
              <td>{formatMoney(item.amount_funded)}</td><td>{formatMoney(item.remaining)}</td><td>{labels[item.status]}</td>
            </tr>)}
          </tbody></table></div>}
      </section>
    </main>
  );
}
