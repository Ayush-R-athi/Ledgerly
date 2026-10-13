import { useCallback, useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ArrowUpRight,
  Building2,
  Check,
  ChevronDown,
  CircleAlert,
  FileSpreadsheet,
  Landmark,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import { apiRequest, formatMoney } from "./api.js";

const organizations = [
  { id: "northwind", name: "Northwind Ventures", initials: "NV" },
  { id: "bluebird", name: "Bluebird Capital", initials: "BC" },
];

const statusLabels = {
  suggested: "Suggested",
  needs_review: "Needs review",
  reconciled: "Reconciled",
  ignored: "Ignored",
  open: "Open",
  partially_funded: "Partially funded",
  funded: "Funded",
};

export default function App() {
  const [organization, setOrganization] = useState("northwind");
  const [transactions, setTransactions] = useState([]);
  const [lineItems, setLineItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [importSummary, setImportSummary] = useState(null);
  const [actionId, setActionId] = useState(null);

  const refresh = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const [tx, items] = await Promise.all([
        apiRequest("/transactions/", organization),
        apiRequest("/line-items/", organization),
      ]);
      setTransactions(tx);
      setLineItems(items);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [organization]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function uploadStatement(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    setImportSummary(null);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const summary = await apiRequest("/import/", organization, {
        method: "POST",
        body,
      });
      setImportSummary(summary);
      await refresh();
    } catch (err) {
      if (err.data?.errors) setImportSummary(err.data);
      else setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  async function runAction(key, path) {
    setActionId(key);
    setError("");
    try {
      await apiRequest(path, organization, { method: "POST" });
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionId(null);
    }
  }

  const activeOrg = organizations.find((item) => item.id === organization);
  const reviewCount = transactions.filter(
    (item) => item.status === "needs_review",
  ).length;
  const reconciledCount = transactions.filter(
    (item) => item.status === "reconciled",
  ).length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#top" aria-label="Ledgerly home">
          <span className="brand-icon">
            <Landmark size={20} strokeWidth={2.3} />
          </span>
          <span>ledgerly</span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <button
          className="workspace-switch"
          onClick={() =>
            setOrganization(
              organization === "northwind" ? "bluebird" : "northwind",
            )
          }
        >
          <span className="org-mark">{activeOrg?.initials}</span>
          <span className="workspace-copy">
            <strong>{activeOrg?.name}</strong>
            <small>General partner</small>
          </span>
          <ChevronDown size={16} />
        </button>
        <nav className="side-nav" aria-label="Main navigation">
          <a className="nav-item active" href="#reconciliation">
            <ArrowDownToLine size={17} /> Reconciliation
          </a>
          <a className="nav-item" href="#capital-calls">
            <Building2 size={17} /> Capital calls
          </a>
        </nav>
        <div className="sidebar-foot">
          <ShieldCheck size={15} /> Organization data is scoped
        </div>
      </aside>

      <main id="top" className="main-content">
        <header className="topbar">
          <div className="breadcrumbs">
            Fund operations <span>/</span> Reconciliation
          </div>
          <div className="topbar-right">
            <span className="secure-dot" /> Demo workspace{" "}
            <span className="avatar">AS</span>
          </div>
        </header>

        <section className="page-heading" id="reconciliation">
          <div>
            <div className="eyebrow">CASH MANAGEMENT</div>
            <h1>Bank reconciliation</h1>
            <p>
              Match incoming wires to your capital calls and keep funding on
              track.
            </p>
          </div>
          <label
            className={`button primary upload-button ${uploading ? "disabled" : ""}`}
          >
            {uploading ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <Upload size={17} />
            )}
            {uploading ? "Uploading…" : "Import statement"}
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={uploadStatement}
              disabled={uploading}
            />
          </label>
        </section>

        {error && (
          <div className="alert error-alert">
            <CircleAlert size={18} />
            <span>{error}</span>
            <button onClick={refresh} aria-label="Retry">
              <RefreshCw size={15} />
            </button>
          </div>
        )}

        {importSummary && (
          <section className="import-summary" aria-live="polite">
            <div className="summary-title">
              <FileSpreadsheet size={19} />
              <strong>
                {importSummary.file_rejected
                  ? "Import rejected"
                  : "Import complete"}
              </strong>
              <button
                className="icon-button"
                onClick={() => setImportSummary(null)}
                aria-label="Dismiss import summary"
              >
                <X size={17} />
              </button>
            </div>
            <div className="summary-stats">
              <span>
                <b>{importSummary.imported}</b> imported
              </span>
              <span>
                <b>{importSummary.duplicates}</b> duplicates skipped
              </span>
              <span>
                <b>{importSummary.errors?.length || 0}</b> row errors
              </span>
            </div>
            {importSummary.errors?.length > 0 && (
              <ul className="row-errors">
                {importSummary.errors.map((item, index) => (
                  <li key={`${item.line}-${index}`}>
                    <b>Line {item.line}:</b> {item.message}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <section className="stat-grid" aria-label="Reconciliation summary">
          <article className="stat-card">
            <div className="stat-label">Statement transactions</div>
            <div className="stat-value">{transactions.length}</div>
            <div className="stat-foot">
              <ArrowDownToLine size={14} /> Imported across this workspace
            </div>
          </article>
          <article className="stat-card">
            <div className="stat-label">Needs your review</div>
            <div className="stat-value">{reviewCount}</div>
            <div className="stat-foot review-foot">
              <CircleAlert size={14} /> Resolve before close
            </div>
          </article>
          <article className="stat-card">
            <div className="stat-label">Reconciled</div>
            <div className="stat-value">{reconciledCount}</div>
            <div className="stat-foot">
              <Check size={14} /> Approved matches
            </div>
          </article>
        </section>

        <section className="panel transaction-panel">
          <div className="panel-heading">
            <div>
              <h2>Bank transactions</h2>
              <p>Review suggested matches and reconcile incoming payments.</p>
            </div>
            <button
              className="button secondary refresh-button"
              onClick={refresh}
              disabled={loading}
            >
              <RefreshCw size={15} className={loading ? "spin" : ""} /> Refresh
            </button>
          </div>
          {loading ? (
            <div className="state-box">
              <LoaderCircle className="spin" size={20} /> Loading transactions…
            </div>
          ) : transactions.length === 0 ? (
            <div className="state-box empty-state">
              <span className="empty-icon">
                <FileSpreadsheet size={21} />
              </span>
              <strong>No transactions yet</strong>
              <span>
                Import a bank statement CSV to see matching suggestions here.
              </span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="transaction-table">
                <thead>
                  <tr>
                    <th>TRANSACTION</th>
                    <th>AMOUNT</th>
                    <th>STATUS</th>
                    <th>SUGGESTED MATCH</th>
                    <th>REASON</th>
                    <th>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <div className="transaction-date">
                          {new Date(`${row.date}T00:00:00`).toLocaleDateString(
                            "en-US",
                            { month: "short", day: "numeric", year: "numeric" },
                          )}
                        </div>
                        <div className="transaction-description">
                          {row.description}
                        </div>
                        <div className="bank-ref">Ref {row.reference}</div>
                      </td>
                      <td>
                        <span
                          className={
                            row.type === "debit" ? "amount debit" : "amount"
                          }
                        >
                          {formatMoney(row.amount)}
                        </span>
                        <small className="cell-subtitle">{row.type}</small>
                      </td>
                      <td>
                        <span className={`status-badge status-${row.status}`}>
                          <i />
                          {statusLabels[row.status]}
                        </span>
                      </td>
                      <td>
                        {row.matches.length ? (
                          row.matches.map((match) => (
                            <div className="match-candidate" key={match.id}>
                              <strong>{match.investor_name}</strong>
                              <span>{match.expected_reference}</span>
                            </div>
                          ))
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="reason-cell">
                        {row.review_reason && (
                          <div className="match-reason">
                            {row.review_reason}
                          </div>
                        )}
                        {row.matches.length ? (
                          row.matches.map((match) => (
                            <div key={match.id} className="match-reason">
                              {match.reason}
                            </div>
                          ))
                        ) : !row.review_reason ? (
                          <span>—</span>
                        ) : null}
                      </td>
                      <td>
                        <div className="actions-cell">
                          {row.matches
                            .filter((match) => match.status === "proposed")
                            .map((match) => (
                              <div className="action-pair" key={match.id}>
                                <button
                                  className="icon-action approve"
                                  title="Approve match"
                                  disabled={actionId !== null}
                                  onClick={() =>
                                    runAction(
                                      `approve-${match.id}`,
                                      `/matches/${match.id}/approve/`,
                                    )
                                  }
                                >
                                  {actionId === `approve-${match.id}` ? (
                                    <LoaderCircle className="spin" size={15} />
                                  ) : (
                                    <Check size={15} />
                                  )}
                                </button>
                                <button
                                  className="icon-action reject"
                                  title="Reject match"
                                  disabled={actionId !== null}
                                  onClick={() =>
                                    runAction(
                                      `reject-${match.id}`,
                                      `/matches/${match.id}/reject/`,
                                    )
                                  }
                                >
                                  {actionId === `reject-${match.id}` ? (
                                    <LoaderCircle className="spin" size={15} />
                                  ) : (
                                    <X size={15} />
                                  )}
                                </button>
                              </div>
                            ))}
                          {["suggested", "needs_review"].includes(
                            row.status,
                          ) && (
                            <button
                              className="text-action"
                              disabled={actionId !== null}
                              onClick={() =>
                                runAction(
                                  `ignore-${row.id}`,
                                  `/transactions/${row.id}/ignore/`,
                                )
                              }
                            >
                              Ignore
                            </button>
                          )}
                          {row.status === "reconciled" && (
                            <span className="done-label">
                              <Check size={13} /> Done
                            </span>
                          )}
                          {row.status === "ignored" && (
                            <span className="muted">—</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel line-items-panel" id="capital-calls">
          <div className="panel-heading">
            <div>
              <h2>Capital call line items</h2>
              <p>Funding progress for {activeOrg?.name}.</p>
            </div>
            <span className="call-count">{lineItems.length} line items</span>
          </div>
          {loading ? (
            <div className="state-box compact-state">
              Loading capital calls…
            </div>
          ) : lineItems.length === 0 ? (
            <div className="state-box compact-state">
              No line items are available for this organization.
            </div>
          ) : (
            <div className="table-wrap">
              <table className="line-table">
                <thead>
                  <tr>
                    <th>INVESTOR</th>
                    <th>CALL / DUE</th>
                    <th>REFERENCE</th>
                    <th>AMOUNT CALLED</th>
                    <th>FUNDED</th>
                    <th>REMAINING</th>
                    <th>STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {lineItems.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.investor_name}</strong>
                        <div className="cell-subtitle">
                          Capital call #{item.call_number}
                        </div>
                      </td>
                      <td>
                        {item.call_date}
                        <div className="cell-subtitle">Due {item.due_date}</div>
                      </td>
                      <td>
                        <span className="reference-pill">
                          {item.expected_reference}
                        </span>
                      </td>
                      <td>{formatMoney(item.amount_called)}</td>
                      <td className="funded-amount">
                        {formatMoney(item.amount_funded)}
                      </td>
                      <td>{formatMoney(item.remaining)}</td>
                      <td>
                        <span className={`status-badge status-${item.status}`}>
                          <i />
                          {statusLabels[item.status]}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <footer className="page-footer">
          <span>
            Ledgerly <span className="footer-dot">·</span> Fund operations
          </span>
          <span>
            Amounts shown in USD <ArrowUpRight size={13} />
          </span>
        </footer>
      </main>
    </div>
  );
}
