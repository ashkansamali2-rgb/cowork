import { useState } from 'react';
import Terminal from './components/Terminal';
import './App.css';

function App() {
  const [inputStr, setInputStr] = useState('');
  const [outputs, setOutputs] = useState([
    { source: 'jarvis', text: 'Initializing Cantivia Web UI... connected.' }
  ]);

  const handleClear = () => {
    setOutputs([]);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!inputStr.trim()) return;
    setOutputs([...outputs, { source: 'user', text: inputStr }]);
    const currentInput = inputStr;
    setInputStr('');

    // Simulate streaming after a short delay
    setTimeout(() => {
      setOutputs(prev => [...prev, { source: 'jarvis', text: `Simulating response computation for "${currentInput}"...` }]);
    }, 500);
  };

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2 className="gradient-text brand">CLI WEB</h2>
        </div>
        <div className="sidebar-content">
          <div className="sidebar-item active">History</div>
          <div className="sidebar-item">Saved Snippets</div>
          <div className="sidebar-item">Settings</div>
        </div>
      </aside>

      {/* Main Container */}
      <main className="main-content">
        <div className="main-wrapper gradient-border-wrapper">
          <div className="main-inner">
            <Terminal outputs={outputs} onClear={handleClear} />

            {/* Input Area */}
            <form className="input-area" onSubmit={handleSubmit}>
              <span className="input-prompt">~/cowork &gt; </span>
              <input
                type="text"
                className="cli-input"
                autoFocus
                value={inputStr}
                onChange={e => setInputStr(e.target.value)}
                placeholder="Type a command..."
              />
            </form>
          </div>
        </div>

        {/* Status Bar */}
        <footer className="status-bar">
          <span className="status-item">[connected]</span>
          <span className="status-item">cli-web v1.0.0</span>
          <span className="status-item">~/cowork</span>
        </footer>
      </main>
    </div>
  )
}

export default App;
