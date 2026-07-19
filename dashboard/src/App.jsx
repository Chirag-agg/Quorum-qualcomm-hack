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
      laptop: { status: 'SLEEPING', tokenString: '', latency_ms: 0, decision: '' }
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
  
  const timelineRef = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE}/session`)
      .then(res => res.json())
      .then(data => {
        setSession(prev => ({ ...prev, ...data }));
        setPromptInput(data.prompt);
      })
      .catch(err => console.error("Hydration failed:", err));

    let ws = null;
    let reconnectTimeout = null;

    const connectWebSocket = () => {
      ws = new WebSocket(WS_BASE);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        
        setSession(prev => {
          const next = { ...prev };
          next.devices = {
              phone: { ...next.devices.phone },
              laptop: { ...next.devices.laptop }
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
              next.devices[dev].status = 'REASONING';
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

      ws.onclose = () => {
        console.log("WebSocket disconnected. Reconnecting...");
        reconnectTimeout = setTimeout(connectWebSocket, 1000);
      };
    };

    connectWebSocket();

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
        if (ws) {
            ws.onclose = null;
            ws.close();
        }
        clearTimeout(reconnectTimeout);
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
      const next = { ...prev, state: 'SCOUTING', timeline: [], currentAnswer: '', consensusScore: 0, prompt: promptInput };
      next.metrics = { latency_ms: 0, tokens_per_sec: 0, devices_used: 0, escalations: 0 };
      next.devices = {
          phone: { ...next.devices.phone },
          laptop: { ...next.devices.laptop }
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
      
      {/* ROW 1: HEADER */}
      <div className="block-header bento-card glass">
        <div className="logo-title">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L2 7L12 12L22 7L12 2Z" fill="var(--crimson-hot)"/>
            <path d="M2 17L12 22L22 17" stroke="var(--crimson)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2 12L12 17L22 12" stroke="var(--crimson)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Quorum
        </div>
        <div className="controls">
          <input 
            type="text" 
            placeholder="Type your prompt..." 
            value={promptInput}
            onChange={e => setPromptInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAskQuorum()}
          />
          <button className="ask-btn" onClick={handleAskQuorum}>Ask Quorum</button>
        </div>
      </div>

      {/* ROW 2: PROMPT (Col 1) */}
      <div className="block-prompt bento-card">
        <div className="bento-title">Prompt</div>
        <div className="prompt-text">
          {session.prompt || <span style={{color: 'var(--muted)', fontStyle: 'italic'}}>Awaiting prompt...</span>}
        </div>
      </div>

      {/* ROW 2: FINAL ANSWER (Col 2 span 2) */}
      <div className="block-answer bento-card">
        <div className="bento-title" style={{color: 'rgba(255,255,255,0.7)', margin: 0}}>Quorum Consensus</div>
        {session.currentAnswer ? (
            <>
                <div className="current-answer-value">
                   {session.currentAnswer}
                </div>
                {session.consensusScore > 0 && (
                    <div className="consensus-badge">
                       Consensus Reached ({Math.round(session.consensusScore * 100)}%)
                    </div>
                )}
            </>
        ) : (
            <div className="current-answer-value" style={{color: 'var(--muted)', fontSize: '28px', marginTop: '32px'}}>
                Waiting for inference...
            </div>
        )}
      </div>

      {/* ROW 3: METRICS (Col 1) */}
      <div className="block-metrics">
         <div className="mini-metric">
            <div className="label">Latency</div>
            <div className="value">{isPending ? '--' : `${session.metrics.latency_ms} ms`}</div>
         </div>
         <div className="mini-metric">
            <div className="label">Tokens / Sec</div>
            <div className="value">{isPending ? '--' : session.metrics.tokens_per_sec}</div>
         </div>
         <div className="mini-metric">
            <div className="label">Devices Used</div>
            <div className="value">{isPending ? '--' : session.metrics.devices_used}</div>
         </div>
         <div className="mini-metric">
            <div className="label">Escalations</div>
            <div className="value">{isPending ? '--' : session.metrics.escalations}</div>
         </div>
      </div>

      {/* ROW 3: DEVICES (Col 2 span 2) */}
      <div className="block-devices">
        {Object.entries(session.devices).map(([id, dev]) => (
            <div key={id} className={`device-bento ${dev.status === 'REASONING' ? 'active-card' : ''}`}>
                 <div className="device-header">
                    <span style={{textTransform: 'capitalize'}}>{id}</span>
                    <span className={`device-status ${dev.status}`}>{dev.status}</span>
                 </div>
                 <div className="token-stream-box">
                    {dev.tokenString}
                 </div>
                 <div className="metric-row">
                     <span>Latency</span>
                     <span className="metric-value">
                        {dev.latency_ms > 0 ? `${dev.latency_ms} ms` : (dev.status === 'REASONING' ? '...' : '--')}
                     </span>
                 </div>
                 {dev.decision && (
                     <div className={`decision-box ${dev.decision}`}>
                         {dev.decision === 'LOCAL' ? 'Local Confidence High' : 'Low Confidence - Escalate'}
                     </div>
                 )}
            </div>
        ))}
      </div>

      {/* ROW 4: TIMELINE (Col 1 span all) */}
      <div className="block-timeline bento-card">
          <div className="bento-title">Timeline Ledger</div>
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
                  <div style={{color: 'var(--muted)', fontStyle: 'italic', padding: '16px'}}>Waiting for inference to start...</div>
              )}
          </div>
      </div>

    </div>
  );
}

export default App;
