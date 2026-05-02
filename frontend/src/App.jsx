import { useState } from 'react'

const cardStyle = {
  border: '1px solid #ddd',
  borderRadius: '8px',
  padding: '16px',
  marginTop: '16px',
  background: '#fff',
}

const badgeStyle = (severity) => ({
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: '999px',
  fontSize: '12px',
  fontWeight: 700,
  background: severity === 'high' ? '#fee2e2' : severity === 'medium' ? '#fef3c7' : '#e0f2fe',
  color: severity === 'high' ? '#991b1b' : severity === 'medium' ? '#92400e' : '#075985',
})

function App() {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showRaw, setShowRaw] = useState(false)

  const runAnalysis = async () => {
    setLoading(true)
    setError(null)
    setReport(null)

    try {
      const response = await fetch('http://localhost:8002/analyze', {
        method: 'POST',
      })

      if (!response.ok) {
        throw new Error(`Server responded with ${response.status}`)
      }

      const data = await response.json()
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: '1100px', margin: '40px auto', padding: '0 20px', fontFamily: 'Inter, system-ui, sans-serif', color: '#111827' }}>
      <header style={{ marginBottom: '24px' }}>
        <h1 style={{ marginBottom: '4px' }}>BS Detector</h1>
        <p style={{ color: '#4b5563' }}>Structured verification report for Rivera v. Harmon Construction Group</p>
      </header>

      <button
        onClick={runAnalysis}
        disabled={loading}
        style={{
          padding: '10px 24px',
          fontSize: '16px',
          cursor: loading ? 'not-allowed' : 'pointer',
          border: '1px solid #111827',
          borderRadius: '6px',
          background: loading ? '#e5e7eb' : '#111827',
          color: loading ? '#6b7280' : '#fff',
        }}
      >
        {loading ? 'Analyzing...' : 'Run Analysis'}
      </button>

      {error && (
        <div style={{ ...cardStyle, color: '#991b1b', background: '#fef2f2' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {report && <ReportView report={report} showRaw={showRaw} setShowRaw={setShowRaw} />}

      {report === null && !loading && !error && (
        <p style={{ marginTop: '20px', color: '#6b7280' }}>
          Click "Run Analysis" to analyze the case documents.
        </p>
      )}
    </div>
  )
}

function ReportView({ report, showRaw, setShowRaw }) {
  return (
    <main style={{ marginTop: '24px' }}>
      <section style={{ ...cardStyle, background: '#f9fafb' }}>
        <h2>Judicial Memo</h2>
        <p style={{ lineHeight: 1.6 }}>{report.judicial_memo || 'No memo generated.'}</p>
      </section>

      <section style={cardStyle}>
        <h2>Key Findings</h2>
        {report.flags?.length ? report.flags.map((flag) => <FlagCard key={flag.id} flag={flag} />) : <p>No flags produced.</p>}
      </section>

      <section style={cardStyle}>
        <h2>Citation Verification</h2>
        <Table
          rows={report.citation_verifications || []}
          columns={[
            ['citation_id', 'Citation'],
            ['status', 'Status'],
            ['confidence_label', 'Confidence'],
            ['reasoning', 'Reasoning'],
          ]}
        />
      </section>

      <section style={cardStyle}>
        <h2>Quote Checks</h2>
        <Table
          rows={report.quote_checks || []}
          columns={[
            ['citation_id', 'Citation'],
            ['status', 'Status'],
            ['quote', 'Quote'],
            ['reasoning', 'Reasoning'],
          ]}
        />
      </section>

      <section style={cardStyle}>
        <h2>Cross-Document Consistency</h2>
        <Table
          rows={report.consistency_findings || []}
          columns={[
            ['claim_id', 'Claim'],
            ['status', 'Status'],
            ['confidence_label', 'Confidence'],
            ['source_evidence', 'Evidence'],
          ]}
        />
      </section>

      {!!report.agent_errors?.length && (
        <section style={{ ...cardStyle, background: '#fff7ed' }}>
          <h2>Agent Errors</h2>
          {report.agent_errors.map((error) => (
            <p key={`${error.agent}-${error.message}`}><strong>{error.agent}:</strong> {error.message}</p>
          ))}
        </section>
      )}

      <section style={cardStyle}>
        <button onClick={() => setShowRaw(!showRaw)}>
          {showRaw ? 'Hide Raw JSON' : 'Show Raw JSON'}
        </button>
        {showRaw && (
          <pre style={{ marginTop: '16px', background: '#f3f4f6', padding: '16px', overflow: 'auto', borderRadius: '6px' }}>
            {JSON.stringify(report, null, 2)}
          </pre>
        )}
      </section>
    </main>
  )
}

function FlagCard({ flag }) {
  return (
    <article style={{ borderTop: '1px solid #e5e7eb', padding: '14px 0' }}>
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={badgeStyle(flag.severity)}>{flag.severity}</span>
        <strong>{flag.title}</strong>
        <span style={{ color: '#6b7280' }}>{flag.status} · {Math.round(flag.confidence * 100)}%</span>
      </div>
      <p>{flag.details}</p>
      <p style={{ color: '#4b5563' }}>{flag.reasoning}</p>
    </article>
  )
}

function Table({ rows, columns }) {
  if (!rows.length) return <p style={{ color: '#6b7280' }}>No records.</p>

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {columns.map(([key, label]) => (
              <th key={key} style={{ textAlign: 'left', borderBottom: '1px solid #d1d5db', padding: '8px' }}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map(([key]) => (
                <td key={key} style={{ verticalAlign: 'top', borderBottom: '1px solid #f3f4f6', padding: '8px' }}>{String(row[key] || '')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default App
