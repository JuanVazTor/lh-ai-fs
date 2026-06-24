import { useState } from 'react'

const TYPE_LABELS = {
  fake_citation: 'Fabricated citation',
  misquote: 'Altered quote',
  fact_contradiction: 'Fact contradiction',
  misapplied_citation: 'Misapplied authority',
  calculation_error: 'Calculation error',
  omission: 'Material omission',
}

const VERDICT_COLORS = {
  contradicted: { bg: '#fdecea', fg: '#b3261e', label: 'Contradicted' },
  unsupported: { bg: '#fdecea', fg: '#b3261e', label: 'Unsupported' },
  supported: { bg: '#e6f4ea', fg: '#137333', label: 'Supported' },
  could_not_verify: { bg: '#fef7e0', fg: '#a56300', label: 'Could not verify' },
}

const CONF_COLORS = { high: '#b3261e', medium: '#a56300', low: '#5f6368' }

function Pill({ children, bg, fg, title }) {
  return (
    <span
      title={title}
      style={{
        background: bg,
        color: fg,
        padding: '2px 10px',
        borderRadius: '999px',
        fontSize: '12px',
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </span>
  )
}

function FlagCard({ flag }) {
  const verdict = VERDICT_COLORS[flag.verdict] || VERDICT_COLORS.could_not_verify
  return (
    <div
      style={{
        border: '1px solid #e0e0e0',
        borderLeft: `4px solid ${verdict.fg}`,
        borderRadius: '8px',
        padding: '16px',
        marginBottom: '14px',
        background: '#fff',
      }}
    >
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '10px' }}>
        <Pill bg="#eef1f5" fg="#1f2937">{TYPE_LABELS[flag.type] || flag.type}</Pill>
        <Pill bg={verdict.bg} fg={verdict.fg}>{verdict.label}</Pill>
        <Pill bg="#f1f3f4" fg={CONF_COLORS[flag.confidence] || '#5f6368'}>
          {flag.confidence} confidence
        </Pill>
        <span style={{ marginLeft: 'auto', fontSize: '12px', color: '#9aa0a6' }}>
          {flag.source_agent}
        </span>
      </div>

      <div style={{ marginBottom: '8px' }}>
        <div style={{ fontSize: '12px', color: '#5f6368', fontWeight: 600 }}>CLAIM IN MOTION</div>
        <div style={{ fontSize: '14px', color: '#202124' }}>{flag.claim_in_msj}</div>
      </div>

      {flag.evidence && (
        <div style={{ marginBottom: '8px' }}>
          <div style={{ fontSize: '12px', color: '#5f6368', fontWeight: 600 }}>
            EVIDENCE {flag.source_document ? `· ${flag.source_document}` : ''}
          </div>
          <blockquote
            style={{
              margin: '4px 0 0',
              padding: '8px 12px',
              background: '#f8f9fa',
              borderLeft: '3px solid #dadce0',
              fontSize: '13px',
              color: '#3c4043',
              fontStyle: 'italic',
            }}
          >
            {flag.evidence}
          </blockquote>
        </div>
      )}

      {flag.confidence_reasoning && (
        <div style={{ fontSize: '12px', color: '#5f6368' }}>
          <strong>Why this confidence:</strong> {flag.confidence_reasoning}
        </div>
      )}
    </div>
  )
}

function App() {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const runAnalysis = async () => {
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const response = await fetch('http://localhost:8002/analyze', { method: 'POST' })
      if (!response.ok) throw new Error(`Server responded with ${response.status}`)
      const data = await response.json()
      setReport(data.report)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const order = { contradicted: 0, unsupported: 1, could_not_verify: 2, supported: 3 }
  const confOrder = { high: 0, medium: 1, low: 2 }
  const flags = report?.flags
    ? [...report.flags].sort(
        (a, b) =>
          (order[a.verdict] ?? 9) - (order[b.verdict] ?? 9) ||
          (confOrder[a.confidence] ?? 9) - (confOrder[b.confidence] ?? 9),
      )
    : []

  return (
    <div style={{ maxWidth: '860px', margin: '40px auto', padding: '0 20px', fontFamily: 'system-ui, sans-serif', color: '#202124' }}>
      <h1 style={{ marginBottom: '4px' }}>BS Detector</h1>
      <p style={{ marginTop: 0, color: '#5f6368' }}>
        Multi-agent verification of a legal brief against its case file
      </p>

      <button
        onClick={runAnalysis}
        disabled={loading}
        style={{
          padding: '10px 24px',
          fontSize: '16px',
          cursor: loading ? 'not-allowed' : 'pointer',
          background: loading ? '#9aa0a6' : '#1a73e8',
          color: '#fff',
          border: 'none',
          borderRadius: '6px',
        }}
      >
        {loading ? 'Analyzing…' : 'Run Analysis'}
      </button>

      {error && (
        <div style={{ marginTop: '20px', padding: '12px', background: '#fdecea', color: '#b3261e', borderRadius: '6px' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {report === null && !loading && !error && (
        <p style={{ marginTop: '20px', color: '#9aa0a6' }}>
          Click “Run Analysis” to verify the Motion for Summary Judgment.
        </p>
      )}

      {report && (
        <div style={{ marginTop: '28px' }}>
          {report.judicial_memo && (
            <section
              style={{
                background: '#f1f6ff',
                border: '1px solid #d2e3fc',
                borderRadius: '8px',
                padding: '18px',
                marginBottom: '28px',
              }}
            >
              <h2 style={{ marginTop: 0, fontSize: '16px' }}>Memo to the Court</h2>
              <p style={{ margin: 0, lineHeight: 1.55, fontSize: '14px' }}>{report.judicial_memo}</p>
            </section>
          )}

          <h2 style={{ fontSize: '18px' }}>
            Findings <span style={{ color: '#9aa0a6', fontWeight: 400 }}>({flags.length})</span>
          </h2>
          {flags.length === 0 && <p style={{ color: '#5f6368' }}>No issues flagged.</p>}
          {flags.map((flag) => (
            <FlagCard key={flag.id} flag={flag} />
          ))}

          <details style={{ marginTop: '24px' }}>
            <summary style={{ cursor: 'pointer', color: '#1a73e8' }}>
              Citations extracted ({report.citations?.length || 0})
            </summary>
            <ul style={{ fontSize: '13px', color: '#3c4043', lineHeight: 1.6 }}>
              {report.citations?.map((c) => (
                <li key={c.id}>
                  <strong>{c.raw_text}</strong> — {c.proposition}
                </li>
              ))}
            </ul>
          </details>

          {report.errors?.length > 0 && (
            <details style={{ marginTop: '12px' }}>
              <summary style={{ cursor: 'pointer', color: '#a56300' }}>
                Pipeline warnings ({report.errors.length})
              </summary>
              <ul style={{ fontSize: '12px', color: '#a56300' }}>
                {report.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

export default App
