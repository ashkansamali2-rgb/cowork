import React from 'react';

export default function Terminal({ outputs, onClear }) {
    return (
        <div className="terminal-container">
            <div className="terminal-header">
                <div className="toolbar">
                    <button className="toolbar-btn">Copy</button>
                    <button className="toolbar-btn" onClick={onClear}>Clear</button>
                    <button className="toolbar-btn">Settings</button>
                </div>
            </div>
            <div className="terminal-body">
                {outputs.map((out, i) => (
                    <div key={i} className="terminal-message">
                        {out.source === 'user' ? (
                            <span className="user-prompt">~/cowork &gt; </span>
                        ) : (
                            <span className="jarvis-prompt">[JARVIS] </span>
                        )}
                        <span className={out.source === 'user' ? 'user-text' : 'jarvis-text'}>
                            {out.text}
                        </span>
                        {i !== outputs.length - 1 && <div className="separator">---</div>}
                    </div>
                ))}
                {/* Placeholder for streaming effect */}
                <div className="streaming-cursor"></div>
            </div>
        </div>
    );
}
