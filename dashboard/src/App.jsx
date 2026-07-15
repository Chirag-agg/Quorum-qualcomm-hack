import React, { useState, useEffect, useRef } from 'react';
import './index.css';

const API_BASE = 'http://localhost:8000';
const WS_BASE = 'ws://localhost:8000/ws/dashboard';

function App() {
  const [session, setSession] = useState({
    prompt: '',
    state: 'IDLE',
    devices: {
      phone: { status: 'SLEEPING', tokenString: '', latency_ms: 0, decision: '' },
      laptop: { status: 'SLEEPING', tokenString: '', latency_ms: 0, decision: '' },
      tablet: { status: 'SLEEPING', tokenString: '', latency_ms: 0, decision: '' }
    },
    timeline: [],
    metrics: { latency_ms: 0, tokens_per_sec: 0, devices_used: 0, escalations: 0 },
    history: [],
    currentAnswer: '',
    consensusScore: 0
  });

  const [promptInput, setPromptInput] = useState('');
  const [scenario, setScenario] = useState('Hard Question');
  const [demoMode, setDemoMode] = useState(false);
  const wsRef = useRef(null);
  
  // Ref to automatically scroll timeline to bottom
  const timelineRef = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE}/session`)
      .then(res => res.json())
      .then(data => {
        setSession(prev => ({ ...prev, ...data }));
        setPromptInput(data.prompt);
      })
      .catch(err => console.error("Hydration failed:", err));

    const ws = new WebSocket(WS_BASE);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      
      setSession(prev => {
        const next = { ...prev };
        // Deep copy devices to ensure React re-renders properly
        next.devices = {
            phone: { ...next.devices.phone },
            laptop: { ...next.devices.laptop },
            tablet: { ...next.devices.tablet }
        };

        if (msg.type === "init") {
          next.state = msg.state;
          next.timeline = msg.logs;
        } else if (msg.type === "device_connected") {
          if (next.devices[msg.device_id] && next.devices[msg.device_id].status === 'OFFLINE') {
            next.devices[msg.device_id].status = 'SLEEPING';
          }
        } else if (msg.source_device) {
          const dev = msg.source_device;
          const payload = msg.data;
          
          if (payload.type === "state_update") {
            next.devices[dev].status = payload.payload.status;
          } else if (payload.type === "token_stream") {
            next.devices[dev].tokenString += payload.payload.token;
            next.devices[dev].status = 'REASONING'; // visually show activity
          } else if (payload.type === "final_answer") {
             const score = payload.payload.quorum_score;
             next.devices[dev].decision = score >= 0.85 ? "LOCAL" : "ESCALATE";
             next.devices[dev].status = 'DONE';
          }
        } else if (msg.type === "consensus_result") {
          next.currentAnswer = msg.result.answer;
          next.consensusScore = msg.result.quorum_score || 0;
          fetch(`${API_BASE}/session`)
            .then(res => res.json())
            .then(data => {
                setSession(prev2 => {
                    const merged = { ...prev2, ...data, currentAnswer: msg.result.answer, consensusScore: msg.result.quorum_score };
                    // Preserve token strings which aren't currently returned by /session
                    Object.keys(merged.devices).forEach(d => {
                        merged.devices[d].tokenString = prev2.devices[d].tokenString;
                    });
                    return merged;
                });
            });
        }
        
        return next;
      });
    };

    const interval = setInterval(() => {
        setSession(currentSession => {
            if (currentSession.state !== 'IDLE' && currentSession.state !== 'DONE') {
                 fetch(`${API_BASE}/session`)
                    .then(res => res.json())
                    .then(data => {
                        setSession(prev2 => {
                            const merged = { ...prev2, ...data };
                            Object.keys(merged.devices).forEach(d => {
                                merged.devices[d].tokenString = prev2.devices[d].tokenString;
                            });
                            return merged;
                        });
                    });
            }
            return currentSession;
        });
    }, 1000);

    return () => {
        ws.close();
        clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (timelineRef.current) {
        timelineRef.current.scrollTop = timelineRef.current.scrollHeight;
    }
  }, [session.timeline]);

  const handleAskQuorum = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    
    setSession(prev => {
      const next = { ...prev, state: 'SCOUTING', timeline: [], currentAnswer: '', consensusScore: 0 };
      next.metrics = { latency_ms: 0, tokens_per_sec: 0, devices_used: 0, escalations: 0 };
      next.devices = {
          phone: { ...next.devices.phone },
          laptop: { ...next.devices.laptop },
          tablet: { ...next.devices.tablet }
      };
      
      Object.keys(next.devices).forEach(d => {
        next.devices[d].tokenString = '';
        next.devices[d].decision = '';
        next.devices[d].latency_ms = 0;
        next.devices[d].status = d === 'phone' ? 'SCOUT' : 'SLEEPING';
      });
      return next;
    });

    wsRef.current.send(JSON.stringify({
      type: "start_inference",
      payload: { prompt: promptInput || "What is the capital of France?", scenario }
    }));
  };

  const isPending = session.state === 'IDLE' && session.metrics.latency_ms === 0;

  const flowSteps = ["Question", "Scout", "Escalation", "Consensus", "Answer"];
  const getActiveStep = () => {
      if (session.state === 'IDLE') return "Question";
      if (session.state === 'SCOUTING') return "Scout";
      if (session.state === 'ESCALATING') return "Escalation";
      if (session.state === 'CONSENSUS') return "Consensus";
      if (session.state === 'DONE') return "Answer";
      return "Question";
  };
  const activeStep = getActiveStep();

  return (
    <div className="dashboard-container">
      <div className="top-bar">
        <div className="logo-area">
          <div className="logo-title">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L2 7L12 12L22 7L12 2Z" fill="currentColor"/>
                <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Quorum
          </div>
          <div className="cloud-referee">Cloud Referee: Not Used</div>
        </div>
        
        <div className="flow-indicator">
            {flowSteps.map((step, idx) => (
                <React.Fragment key={step}>
                    <div className={`flow-step ${activeStep === step || (session.state === 'DONE' && step === 'Answer') ? 'active' : ''}`}>
                        {step}
                    </div>
                    {idx < flowSteps.length - 1 && <div className="flow-arrow">→</div>}
                </React.Fragment>
            ))}
        </div>

        <div className="controls">
          <button className="demo-mode-toggle" onClick={() => setDemoMode(!demoMode)}>
            ⚙ Demo Mode
          </button>
          <select 
            className={`scenario-select ${demoMode ? 'visible' : ''}`}
            value={scenario} 
            onChange={e => setScenario(e.target.value)}
          >
            <option value="Easy Question">Easy (No Esc)</option>
            <option value="Hard Question">Hard (Escalation)</option>
            <option value="Disagreement">Disagreement</option>
          </select>
          <input 
            type="text" 
            placeholder="Type your prompt..." 
            value={promptInput}
            onChange={e => setPromptInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAskQuorum()}
          />
          <button className="ask-btn" onClick={handleAskQuorum}>Ask Quorum</button>
        </div>

        <div className={`system-indicator ${session.state}`}>
          SYSTEM: {session.state}
        </div>
      </div>

      <div className="grid-layout">
        <div className="left-column">
          <div className="card">
            <div className="card-title">Swarm Devices</div>
            <div className="device-cards">
              {Object.entries(session.devices).map(([id, dev]) => (
                <div key={id} className={`device-card ${dev.status === 'REASONING' ? 'active-card' : ''}`}>
                  <div className="device-header">
                    <span style={{textTransform: 'uppercase'}}>{id}</span>
                    <span className={`device-status ${dev.status}`}>{dev.status}</span>
                  </div>
                  
                  <div className="token-stream-box">
                      {dev.tokenString || <span style={{opacity: 0.5}}>Waiting for stream...</span>}
                  </div>

                  <div className="device-metrics">
                    <div className="metric-row">
                      <span className="metric-label">Latency</span>
                      <span className="metric-value">
                        {dev.latency_ms > 0 ? `${dev.latency_ms} ms` : (dev.status === 'REASONING' ? '...' : '--')}
                      </span>
                    </div>
                  </div>
                  {dev.decision && (
                    <div className={`decision-box ${dev.decision}`}>
                      Decision: {dev.decision}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-title">Live Metrics</div>
            <div className="metrics-grid">
              <div className="metric-box">
                <div className="label">Total Latency</div>
                <div className={`value ${isPending ? 'placeholder' : ''}`}>
                    {isPending ? '--' : `${session.metrics.latency_ms} ms`}
                </div>
              </div>
              <div className="metric-box">
                <div className="label">Tokens / Sec</div>
                <div className={`value ${isPending ? 'placeholder' : ''}`}>
                    {isPending ? '--' : session.metrics.tokens_per_sec}
                </div>
              </div>
              <div className="metric-box">
                <div className="label">Devices Used</div>
                <div className={`value ${isPending ? 'placeholder' : ''}`}>
                    {isPending ? '--' : session.metrics.devices_used}
                </div>
              </div>
              <div className="metric-box">
                <div className="label">Escalations</div>
                <div className={`value ${isPending ? 'placeholder' : ''}`}>
                    {isPending ? '--' : session.metrics.escalations}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="right-column">
          
          {session.currentAnswer && (
              <div className="current-answer-card">
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                      <div className="current-answer-title">Current Answer</div>
                      {session.consensusScore > 0 && (
                          <div className="consensus-badge">Consensus: {Math.round(session.consensusScore * 100)}%</div>
                      )}
                  </div>
                  <div className="current-answer-value">
                      {session.currentAnswer}
                  </div>
              </div>
          )}

          <div className="card" style={{ flex: 1 }}>
            <div className="card-title">Timeline Ledger</div>
            <div className="timeline" ref={timelineRef}>
              {session.timeline.map((event, idx) => {
                const eventClass = `event-${event.event.replace(/ /g, '-')}`;
                return (
                  <div key={idx} className={`timeline-event ${eventClass}`}>
                    <div className="timeline-time">{event.timestamp}</div>
                    <div className="timeline-content">
                      <div className="timeline-title">{event.event}</div>
                      {event.details && Object.keys(event.details).length > 0 && (
                        <div className="timeline-details">
                          {Object.entries(event.details).map(([k, v]) => `${k}: ${v}`).join(' | ')}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              {session.timeline.length === 0 && (
                  <div style={{color: 'var(--color-text-light)', fontStyle: 'italic', padding: '12px'}}>Waiting for inference to start...</div>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-title">Historical Runs</div>
            <table className="history-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Devices</th>
                  <th>Escalated</th>
                  <th>Latency</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {session.history.map((run, idx) => (
                  <tr key={idx}>
                    <td>#{run.id}</td>
                    <td>{run.devices}</td>
                    <td>{run.escalated ? 'Yes' : 'No'}</td>
                    <td>{run.latency_ms} ms</td>
                    <td style={{maxWidth: '120px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>
                        {run.result}
                    </td>
                  </tr>
                ))}
                {session.history.length === 0 && (
                    <tr>
                        <td colSpan="5" style={{textAlign: 'center', color: '#64748B'}}>No historical runs yet</td>
                    </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
