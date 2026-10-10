import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, AlertCircle, ArrowDownToLine, ArrowRight, Check, CheckCircle2,
  ChevronDown, CircleHelp, ClipboardCheck, CloudUpload, FileJson2, FileSpreadsheet,
  Filter, Info, LoaderCircle, RefreshCw, Search, ShieldCheck, SlidersHorizontal,
  Sparkles, Upload, X, Zap
} from 'lucide-react';

const API = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');
const fmt = (value) => new Intl.NumberFormat('en-IN').format(value ?? 0);

function statusClass(status) { return `status status-${String(status || '').toLowerCase()}`; }
function downloadText(text, filename, type = 'text/csv;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
}
function reasonsFor(row) {
  const failed = (row.Violated_Rules || []).map(x => `${x.rule_id}: ${x.reason || x.description || 'Rule failed'}`);
  const schema = (row.Schema_Errors || []).map(x => `Schema: ${x}`);
  const errors = (row.Evaluation_Errors || []).map(x => `${x.rule_id}: ${x.reason || 'Could not evaluate'}`);
  return [...failed, ...schema, ...errors];
}

export default function App() {
  const [apiOnline, setApiOnline] = useState(false);
  const [ruleSets, setRuleSets] = useState([]);
  const [selected, setSelected] = useState([]);
  const [tradeFile, setTradeFile] = useState(null);
  const [ruleFile, setRuleFile] = useState(null);
  const [results, setResults] = useState([]);
  const [summary, setSummary] = useState({ PASS: 0, FAIL: 0, ERROR: 0 });
  const [meta, setMeta] = useState(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [expanded, setExpanded] = useState(null);
  const tradeInput = useRef(null);
  const ruleInput = useRef(null);

  async function loadRules() {
    try {
      const response = await fetch(`${API}/rules`);
      if (!response.ok) throw new Error('Rule API unavailable');
      const data = await response.json();
      const sets = data.rule_sets || [];
      setRuleSets(sets); setApiOnline(true);
      setSelected(old => old.length ? old.filter(id => sets.some(x => x.id === id)) : sets.map(x => x.id));
    } catch { setApiOnline(false); }
  }
  useEffect(() => { loadRules(); }, []);

  const filtered = useMemo(() => results.filter(row => {
    const matchesStatus = statusFilter === 'ALL' || row.Status === statusFilter;
    const text = `${row.Trade_ID} ${reasonsFor(row).join(' ')}`.toLowerCase();
    return matchesStatus && text.includes(search.toLowerCase());
  }), [results, statusFilter, search]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const shown = filtered.slice((page - 1) * pageSize, page * pageSize);
  useEffect(() => setPage(1), [search, statusFilter, pageSize]);

  function notify(type, message) { setNotice({ type, message }); }
  function toggleRule(id) { setSelected(old => old.includes(id) ? old.filter(x => x !== id) : [...old, id]); }

  async function validateTrades() {
    if (!tradeFile) return notify('error', 'Choose a trade CSV before validating.');
    if (!selected.length) return notify('error', 'Select at least one rule set.');
    setBusy('validate'); setNotice(null); setResults([]); setMeta(null);
    try {
      const body = new FormData(); body.append('file', tradeFile); body.append('rule_set_ids', JSON.stringify(selected));
      const response = await fetch(`${API}/impact-matrix`, { method: 'POST', body });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Validation failed.');
      setResults(data.results || []); setSummary(data.summary || {});
      setMeta({ filename: data.filename, trade_count: data.trade_count, rule_set_ids: data.rule_set_ids });
      notify('success', `Validation complete — ${fmt(data.trade_count)} trades processed.`);
    } catch (error) { notify('error', error.message || 'Could not validate this file.'); }
    finally { setBusy(''); }
  }

  async function importRules() {
    if (!ruleFile) return notify('error', 'Choose a JSON rule-set file first.');
    setBusy('import'); setNotice(null);
    try {
      const body = new FormData(); body.append('file', ruleFile);
      const response = await fetch(`${API}/rules`, { method: 'POST', body });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Rule import failed.');
      await loadRules(); setSelected(old => [...new Set([...old, data.id])]); setRuleFile(null);
      if (ruleInput.current) ruleInput.current.value = '';
      notify('success', `${data.id} version ${data.version} registered with ${data.rule_count} rules.`);
    } catch (error) { notify('error', error.message || 'Could not import the JSON file.'); }
    finally { setBusy(''); }
  }

  async function useSample() {
    setBusy('sample'); setNotice(null);
    try {
      const response = await fetch(`${API}/sample-trades`);
      if (!response.ok) throw new Error('Sample trades are not available.');
      const blob = await response.blob();
      const file = new File([blob], 'sample_trades.csv', { type: 'text/csv' });
      setTradeFile(file); if (tradeInput.current) tradeInput.current.value = '';
      notify('success', 'Sample trade dataset loaded. Select Validate to run the matrix.');
    } catch (error) { notify('error', error.message); }
    finally { setBusy(''); }
  }

  async function exportResults() {
    if (!results.length) return;
    try {
      const response = await fetch(`${API}/impact-matrix/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ results }) });
      if (!response.ok) throw new Error('Server export failed.');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'impact_matrix.csv'; a.click(); URL.revokeObjectURL(url);
    } catch {
      const rows = [['Trade_ID','Status','Violated_Rules','Reasons','Schema_Errors','Evaluation_Errors','Skipped_Rules','Passed_Rules']];
      results.forEach(r => rows.push([r.Trade_ID, r.Status, (r.Violated_Rules || []).map(x => `${x.rule_id}: ${x.reason || x.description}`).join('; '), reasonsFor(r).join('; '), (r.Schema_Errors || []).join('; '), (r.Evaluation_Errors || []).map(x => `${x.rule_id}: ${x.reason}`).join('; '), (r.Skipped_Rules || []).join('; '), (r.Passed_Rules || []).join('; ')]));
      const csv = rows.map(row => row.map(v => `"${String(v ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n');
      downloadText(csv, 'impact_matrix.csv');
    }
  }

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand-lockup"><div className="brand-mark"><ShieldCheck size={23}/></div><div><div className="brand-name">REG <span>IRIS</span></div><div className="brand-caption">REGULATORY INTELLIGENCE SYSTEM</div></div></div>
      <div className="topbar-right"><span className={`connection ${apiOnline ? 'online' : 'offline'}`}><span className="connection-dot"/>{apiOnline ? 'API connected' : 'API disconnected'}</span><div className="avatar">RI</div></div>
    </header>

    <main className="main-content">
      <div className="page-heading"><div><div className="eyebrow"><Activity size={14}/> COMPLIANCE WORKSPACE</div><h1>Impact Matrix</h1><p>Validate trade records against configurable regulatory rule sets.</p></div><button className="button button-secondary button-refresh" onClick={loadRules}><RefreshCw size={16}/> Refresh rules</button></div>

      {notice && <div className={`notice notice-${notice.type}`}><span>{notice.type === 'error' ? <AlertCircle size={18}/> : notice.type === 'success' ? <CheckCircle2 size={18}/> : <Info size={18}/>}</span><span>{notice.message}</span><button aria-label="Dismiss notification" onClick={() => setNotice(null)}><X size={16}/></button></div>}

      {!apiOnline && <div className="api-warning"><AlertCircle size={18}/><div><strong>Backend connection unavailable</strong><p>Start the FastAPI service and check the API URL configuration. The dashboard will connect automatically when the API is available.</p></div></div>}

      <section className="workflow-grid">
        <article className="panel input-panel"><div className="panel-heading"><div className="step-icon"><FileSpreadsheet size={18}/></div><div><div className="panel-kicker">STEP 01</div><h2>Trade dataset</h2></div><span className="optional-tag">CSV</span></div>
          <button className={`dropzone ${tradeFile ? 'has-file' : ''}`} onClick={() => tradeInput.current?.click()} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f?.name.toLowerCase().endsWith('.csv')) setTradeFile(f); else notify('error', 'Please select a CSV file.'); }}>
            <div className="drop-icon">{tradeFile ? <CheckCircle2 size={24}/> : <CloudUpload size={25}/>}</div><strong>{tradeFile ? tradeFile.name : 'Upload trade CSV'}</strong><span>{tradeFile ? `${(tradeFile.size / 1024).toFixed(1)} KB · Ready to validate` : 'Drag and drop, or browse files'}</span><span className="browse-label">{tradeFile ? 'Choose a different file' : 'Browse files'}</span>
          </button><input ref={tradeInput} type="file" accept=".csv,text/csv" hidden onChange={e => setTradeFile(e.target.files?.[0] || null)}/>
          <div className="panel-foot"><span><Info size={14}/> Required schema columns are checked</span><button className="text-button" onClick={useSample} disabled={busy === 'sample'}>{busy === 'sample' ? <LoaderCircle className="spin" size={14}/> : <FileSpreadsheet size={14}/>} Use sample dataset</button></div>
        </article>

        <article className="panel rules-panel"><div className="panel-heading"><div className="step-icon"><SlidersHorizontal size={18}/></div><div><div className="panel-kicker">STEP 02</div><h2>Regulatory rule sets</h2></div><span className="count-tag">{selected.length} selected</span></div>
          <div className="rule-list">{ruleSets.length ? ruleSets.map(rule => <label className={`rule-option ${selected.includes(rule.id) ? 'selected' : ''}`} key={rule.id}><input type="checkbox" checked={selected.includes(rule.id)} onChange={() => toggleRule(rule.id)}/><span className="custom-checkbox">{selected.includes(rule.id) && <Check size={13}/>}</span><span className="rule-copy"><strong>{rule.display_name}</strong><small>{rule.description || rule.jurisdiction || 'Regulatory validation rules'}</small><span className="rule-meta">{rule.rule_count} rules <span>·</span> v{rule.version}</span></span><span className="rule-code">{rule.id}</span></label>) : <div className="empty-rules"><LoaderCircle size={18} className="spin"/> Loading available rule sets…</div>}</div>
          <div className="import-box"><div className="import-info"><div className="import-icon"><FileJson2 size={18}/></div><div><strong>Add a rule set</strong><p>Import a JSON file. Existing rule sets and versions are retained.</p></div></div><div className="import-actions"><input ref={ruleInput} type="file" accept=".json,application/json" hidden onChange={e => setRuleFile(e.target.files?.[0] || null)}/><button className="button button-secondary choose-json" onClick={() => ruleInput.current?.click()}><Upload size={15}/>{ruleFile ? ruleFile.name : 'Choose JSON'}</button><button className="button button-primary import-button" disabled={!ruleFile || busy === 'import'} onClick={importRules}>{busy === 'import' ? <LoaderCircle className="spin" size={15}/> : <ArrowRight size={15}/>} Import</button></div><div className="future-note"><Sparkles size={13}/> Import layer is designed to support future text/PDF adapters.</div></div>
        </article>
      </section>

      <section className="run-bar"><div className="run-copy"><div className="run-symbol"><Zap size={19}/></div><div><strong>Ready to validate?</strong><p>Run each selected rule set against every trade in the dataset.</p></div></div><button className="button button-primary validate-button" onClick={validateTrades} disabled={!apiOnline || busy === 'validate' || !tradeFile || !selected.length}>{busy === 'validate' ? <><LoaderCircle className="spin" size={17}/> Validating trades…</> : <><ClipboardCheck size={17}/> Generate Impact Matrix</>}</button></section>

      <section className="results-section"><div className="results-heading"><div><div className="eyebrow"><Activity size={14}/> VALIDATION OUTPUT</div><h2>Impact Matrix results</h2><p>{meta ? `${meta.filename} · ${fmt(meta.trade_count)} trades processed` : 'Your validation results will appear here.'}</p></div><button className="button button-secondary export-button" onClick={exportResults} disabled={!results.length}><ArrowDownToLine size={16}/> Export CSV</button></div>
        <div className="summary-grid"><div className="summary-card summary-total"><div className="summary-top"><span>Total trades</span><FileSpreadsheet size={17}/></div><div className="summary-value">{fmt(results.length)}</div><div className="summary-foot">Records evaluated</div></div><div className="summary-card summary-pass"><div className="summary-top"><span>Passed</span><CheckCircle2 size={17}/></div><div className="summary-value">{fmt(summary.PASS)}</div><div className="summary-foot">No detected violations</div></div><div className="summary-card summary-fail"><div className="summary-top"><span>Failed</span><AlertCircle size={17}/></div><div className="summary-value">{fmt(summary.FAIL)}</div><div className="summary-foot">One or more issues found</div></div><div className="summary-card summary-error"><div className="summary-top"><span>Evaluation errors</span><CircleHelp size={17}/></div><div className="summary-value">{fmt(summary.ERROR)}</div><div className="summary-foot">Requires review</div></div></div>

        <div className="table-panel"><div className="table-toolbar"><div className="table-title"><strong>Trade-level assessment</strong><span className="result-count">{fmt(filtered.length)} records</span></div><div className="table-controls"><label className="search-field"><Search size={15}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search trades or reasons…"/></label><label className="filter-field"><Filter size={14}/><select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="ALL">All statuses</option><option value="PASS">Pass</option><option value="FAIL">Fail</option><option value="ERROR">Error</option></select><ChevronDown size={13}/></label></div></div>
          <div className="table-scroll"><table><thead><tr><th>TRADE ID</th><th>STATUS</th><th>VIOLATIONS</th><th>DETAILS</th></tr></thead><tbody>{shown.map((row, i) => { const issues = reasonsFor(row); return <React.Fragment key={`${row.Trade_ID}-${i}`}><tr><td><span className="trade-id">{row.Trade_ID}</span></td><td><span className={statusClass(row.Status)}><span/>{row.Status}</span></td><td>{issues.length ? <span className={`issue-count ${row.Status === 'ERROR' ? 'issue-error' : 'issue-fail'}`}>{issues.length} {issues.length === 1 ? 'issue' : 'issues'}</span> : <span className="no-issues"><Check size={14}/> None</span>}</td><td><button className="details-button" onClick={() => setExpanded(expanded === `${row.Trade_ID}-${i}` ? null : `${row.Trade_ID}-${i}`)}>{expanded === `${row.Trade_ID}-${i}` ? 'Hide details' : 'View details'} <ChevronDown size={14} className={expanded === `${row.Trade_ID}-${i}` ? 'rotate' : ''}/></button></td></tr>{expanded === `${row.Trade_ID}-${i}` && <tr className="detail-row"><td colSpan="4"><div className="detail-content">{issues.length ? issues.map((issue, n) => <div className="detail-issue" key={n}><AlertCircle size={15}/><span>{issue}</span></div>) : <div className="detail-issue good"><CheckCircle2 size={15}/><span>No violations or schema errors reported for this trade.</span></div>}{row.Skipped_Rules?.length > 0 && <div className="detail-note">Skipped as not applicable: {row.Skipped_Rules.join(', ')}</div>}{row.Passed_Rules?.length > 0 && <div className="detail-note">Passed rules: {row.Passed_Rules.join(', ')}</div>}</div></td></tr>}</React.Fragment>; })}{!shown.length && <tr><td colSpan="4"><div className="empty-state"><div className="empty-state-icon"><FileSpreadsheet size={24}/></div><strong>{results.length ? 'No matching trades' : 'No results yet'}</strong><p>{results.length ? 'Try changing your search or status filter.' : 'Upload a CSV, select one or more rule sets, then generate the matrix.'}</p></div></td></tr>}</tbody></table></div>
          <div className="table-pagination"><span>Showing <strong>{filtered.length ? (page - 1) * pageSize + 1 : 0}–{Math.min(page * pageSize, filtered.length)}</strong> of <strong>{fmt(filtered.length)}</strong></span><div className="pagination-controls"><label>Rows <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}><option value={10}>10</option><option value={25}>25</option><option value={50}>50</option></select></label><button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button><span className="page-indicator">{page} / {pages}</span><button disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</button></div></div>
        </div>
      </section>
      <footer className="footer"><span><ShieldCheck size={15}/> Reg IRIS <span className="footer-dot">·</span> Impact Matrix</span><span>Rule versions are retained for traceability. Review rule definitions before regulatory use.</span></footer>
    </main>
  </div>;
}
