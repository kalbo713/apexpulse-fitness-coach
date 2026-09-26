import React, { useState, useRef, useEffect } from 'react';
import WorkoutModal from './WorkoutModal';
import CyclingModal from './CyclingModal';

export interface MessagePart {
  kind?: 'text' | 'a2ui';
  text?: string;
  data?: any;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent';
  text: string;
  parts?: MessagePart[];
  timestamp: string;
}

export const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome-1',
      sender: 'agent',
      text: '👋 Welcome to ApexPulse! I am your AI Fitness & Fasting Coach. I specialize in functional longevity with your single 15 lb kettlebell, Zone 2 cycling, step tracking, and 16/8 fasting optimization. How can I guide your training today?',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }
  ]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isWorkoutModalOpen, setIsWorkoutModalOpen] = useState(false);
  const [isCyclingModalOpen, setIsCyclingModalOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-scroll chat on new messages
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  // Copy helper
  const handleCopy = async (id: string, text: string) => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 1500);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  // Helper to parse Markdown links and bare URLs into clickable anchor tags and YouTube video cards
  const formatMarkdownContent = (text: string): string => {
    if (!text) return '';
    let html = text;

    const isYouTubeUrl = (url: string) => /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\/.+$/i.test(url);

    const createVideoCard = (title: string, url: string) => {
      const cleanTitle = (title || 'Exercise Video Tutorial').trim();
      return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="yt-video-card" style="display:flex;align-items:center;gap:0.85rem;background:linear-gradient(135deg, rgba(255,87,34,0.12) 0%, rgba(22,31,54,0.85) 100%);border:1px solid rgba(255,87,34,0.35);border-radius:12px;padding:0.75rem 1rem;margin:0.6rem 0;text-decoration:none;color:#fff;box-shadow:0 4px 14px rgba(0,0,0,0.25);">
        <div style="width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg, #FF5722, #FF9100);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
          <span style="color:#fff;font-size:20px;">▶</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:0.15rem;flex:1;min-width:0;">
          <div style="font-weight:700;font-size:0.92rem;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${cleanTitle}</div>
          <div style="font-size:0.75rem;color:#FF8A65;font-weight:500;">YouTube Video Guide ↗</div>
        </div>
      </a>`;
    };

    // 1. Markdown links [Text](URL)
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/gi, (_match, linkText, url) => {
      if (isYouTubeUrl(url)) {
        return createVideoCard(linkText, url);
      }
      return `<a href="${url}" target="_blank" rel="noopener noreferrer" style="color:#FF8A65;text-decoration:underline;font-weight:600;">${linkText}</a>`;
    });

    // 2. Bare URLs
    html = html.replace(/(^|[\s(])(https?:\/\/[^\s<"'\)]+)(?=[)\s]|$)/gi, (_match, prefix, url) => {
      if (isYouTubeUrl(url)) {
        return `${prefix}${createVideoCard('Exercise Video Tutorial', url)}`;
      }
      return `${prefix}<a href="${url}" target="_blank" rel="noopener noreferrer" style="color:#FF8A65;text-decoration:underline;font-weight:600;">${url}</a>`;
    });

    // 3. Formatting
    html = html
      .replace(/^### (.*$)/gim, '<h3 style="margin:0.5rem 0 0.25rem 0;font-size:1.05rem;color:#fff;">$1</h3>')
      .replace(/^## (.*$)/gim, '<h2 style="margin:0.6rem 0 0.3rem 0;font-size:1.15rem;color:#fff;">$1</h2>')
      .replace(/^# (.*$)/gim, '<h1 style="margin:0.7rem 0 0.35rem 0;font-size:1.25rem;color:#fff;">$1</h1>')
      .replace(/\*\*(.*?)\*\*/g, '<strong style="color:#fff;font-weight:600;">$1</strong>')
      .replace(/`([^`]+)`/g, '<code style="background:rgba(0,0,0,0.3);padding:0.15rem 0.35rem;border-radius:4px;color:#00E5FF;font-family:monospace;">$1</code>')
      .replace(/^\* (.*$)/gim, '<li style="margin-bottom:0.25rem;">$1</li>')
      .replace(/^- (.*$)/gim, '<li style="margin-bottom:0.25rem;">$1</li>');

    html = html.replace(/(<li.*?>.*?<\/li>)+/gs, (match) => `<ul style="margin:0.4rem 0 0.6rem 1.2rem;">${match}</ul>`);
    html = html.replace(/\n\n+/g, '</p><p style="margin-bottom:0.5rem;">');
    return `<p style="margin:0 0 0.5rem 0;">${html}</p>`;
  };

  // Edit helper: fills input and focuses
  const handleEdit = (text: string) => {
    setInputText(text);
    if (inputRef.current) {
      inputRef.current.focus();
      inputRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  // Stop helper: triggers AbortController
  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  };

  // Send message
  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend !== undefined ? textToSend : inputText).trim();
    if (!text || isLoading) return;

    const userMessageId = `user-${Date.now()}`;
    const userMsg: ChatMessage = {
      id: userMessageId,
      sender: 'user',
      text: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setIsLoading(true);

    // Set up AbortController with 45s timeout
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), 45000);

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, user_id: 'apex-user' }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      const data = await response.json();
      const parts: MessagePart[] = data.parts || [];
      const textParts = parts
        .filter((p) => p.kind === 'text' || p.text)
        .map((p) => p.text || '')
        .join('\n\n')
        .trim();

      const agentMessageId = `agent-${Date.now()}`;
      const agentMsg: ChatMessage = {
        id: agentMessageId,
        sender: 'agent',
        text: textParts || '(Completed turn with A2UI component response)',
        parts: parts,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, agentMsg]);
    } catch (err: any) {
      clearTimeout(timeoutId);
      const isAbort = err.name === 'AbortError';
      const errorMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        sender: 'agent',
        text: isAbort ? '⚠️ Request stopped by user or timed out.' : `⚠️ Error: ${err.message || 'Connection failed'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
      if (inputRef.current) {
        inputRef.current.focus();
      }
    }
  };

  const handleWorkoutSubmit = (formattedMessage: string) => {
    handleSendMessage(formattedMessage);
  };

  return (
    <div className="chat-app-root" style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg-dark, #090d16)', color: '#fff' }}>
      {/* App Header */}
      <header style={{ padding: '0.85rem 1.5rem', background: 'rgba(16, 22, 38, 0.95)', borderBottom: '1px solid rgba(255,255,255,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: 'linear-gradient(135deg, #FF5722, #FF9100)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>
            ⚡
          </div>
          <div>
            <h1 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0 }}>ApexPulse Coach</h1>
            <span style={{ fontSize: '0.7rem', color: '#00E676' }}>● Live (Age 59 · 15 lb Kettlebell · 16/8 Fasting)</span>
          </div>
        </div>
      </header>

      {/* Main Chat Scroll Area */}
      <div ref={chatContainerRef} style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', maxWidth: 900, width: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
        {/* Quick Actions Grid */}
        <div style={{ background: 'rgba(22, 31, 54, 0.85)', padding: '1.2rem', borderRadius: 14, border: '1px solid rgba(255,255,255,0.08)' }}>
          <h3 style={{ fontSize: '1rem', marginBottom: '0.6rem', color: '#FF8A65' }}>⚡ Quick Coaching Actions</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.5rem' }}>
            <button
              onClick={() => handleSendMessage('Show my daily, weekly, and yearly step tracking summary card via A2UI.')}
              className="quick-btn"
              style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', padding: '0.6rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left' }}
            >
              🚶 Step Analytics Card
            </button>
            <button
              onClick={() => handleEdit('Log my steps: [Enter Number]')}
              className="quick-btn"
              style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', padding: '0.6rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left' }}
            >
              👟 Log Steps
            </button>
            <button
              onClick={() => handleSendMessage('Check my fasting window and protein goals based on my current profile.')}
              className="quick-btn"
              style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', padding: '0.6rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left' }}
            >
              🥩 Protein & Fasting Check
            </button>
            <button
              onClick={() => setIsWorkoutModalOpen(true)}
              className="quick-btn"
              style={{ background: '#161f36', border: '1px solid rgba(255,87,34,0.4)', color: '#FF8A65', padding: '0.6rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left', fontWeight: 600 }}
            >
              🏋️‍♂️ Log Strength Workout
            </button>
            <button
              onClick={() => setIsCyclingModalOpen(true)}
              className="quick-btn"
              style={{ background: '#161f36', border: '1px solid rgba(255,87,34,0.4)', color: '#FF8A65', padding: '0.6rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left', fontWeight: 600 }}
            >
              🚴 Log Cycling Ride
            </button>
            <button
              onClick={() => handleSendMessage('Show me a summary of all workouts logged today and check my fasting window.')}
              className="quick-btn"
              style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', padding: '0.6rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left' }}
            >
              📊 Today's Workout Summary
            </button>
          </div>
        </div>

        {/* Message Thread */}
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              flexDirection: msg.sender === 'user' ? 'row-reverse' : 'row',
              gap: '0.75rem',
              maxWidth: '88%',
              alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            {/* Avatar */}
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                background: msg.sender === 'user' ? '#161f36' : 'linear-gradient(135deg, #FF5722, #FF9100)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '14px',
                flexShrink: 0,
              }}
            >
              {msg.sender === 'user' ? '👤' : '⚡'}
            </div>

            {/* Bubble & Controls Wrapper */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', width: '100%' }}>
              <div
                style={{
                  padding: '0.85rem 1.15rem',
                  borderRadius: 14,
                  background: msg.sender === 'user' ? 'linear-gradient(135deg, #FF5722, #FF9100)' : 'rgba(22, 31, 54, 0.95)',
                  color: '#fff',
                  lineHeight: 1.5,
                  fontSize: '0.92rem',
                  border: msg.sender === 'user' ? 'none' : '1px solid rgba(255,255,255,0.08)',
                  wordBreak: 'break-word',
                }}
                dangerouslySetInnerHTML={{ __html: formatMarkdownContent(msg.text) }}
              />

              {/* Message Controls */}
              <div
                style={{
                  display: 'flex',
                  gap: '0.4rem',
                  justifyContent: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                {msg.sender === 'user' ? (
                  <>
                    {/* User Controls: Copy, Edit, Stop */}
                    <button
                      type="button"
                      onClick={() => handleCopy(msg.id, msg.text)}
                      className={`action-btn ${copiedId === msg.id ? 'copied' : ''}`}
                      style={{
                        background: '#161f36',
                        border: '1px solid rgba(255,255,255,0.1)',
                        color: copiedId === msg.id ? '#00E676' : '#94A3B8',
                        borderRadius: 6,
                        padding: '0.2rem 0.5rem',
                        fontSize: '0.72rem',
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.25rem',
                      }}
                    >
                      <span>{copiedId === msg.id ? '✓ Copied' : '📋 Copy'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleEdit(msg.text)}
                      style={{
                        background: '#161f36',
                        border: '1px solid rgba(255,255,255,0.1)',
                        color: '#94A3B8',
                        borderRadius: 6,
                        padding: '0.2rem 0.5rem',
                        fontSize: '0.72rem',
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.25rem',
                      }}
                    >
                      <span>✏️ Edit</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleStop}
                      style={{
                        background: '#161f36',
                        border: '1px solid rgba(255,82,82,0.3)',
                        color: '#ff8a80',
                        borderRadius: 6,
                        padding: '0.2rem 0.5rem',
                        fontSize: '0.72rem',
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.25rem',
                      }}
                    >
                      <span>⏹️ Stop</span>
                    </button>
                  </>
                ) : (
                  /* Agent Control: Copy */
                  <button
                    type="button"
                    onClick={() => handleCopy(msg.id, msg.text)}
                    className={`action-btn ${copiedId === msg.id ? 'copied' : ''}`}
                    style={{
                      background: '#161f36',
                      border: '1px solid rgba(255,255,255,0.1)',
                      color: copiedId === msg.id ? '#00E676' : '#94A3B8',
                      borderRadius: 6,
                      padding: '0.2rem 0.5rem',
                      fontSize: '0.72rem',
                      cursor: 'pointer',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                    }}
                  >
                    <span>{copiedId === msg.id ? '✓ Copied' : '📋 Copy'}</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}

        {isLoading && (
          <div style={{ display: 'flex', gap: '0.75rem', alignSelf: 'flex-start' }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: 'linear-gradient(135deg, #FF5722, #FF9100)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              ⚡
            </div>
            <div style={{ padding: '0.85rem 1.15rem', borderRadius: 14, background: 'rgba(22, 31, 54, 0.95)', color: '#FF8A65', fontSize: '0.9rem' }}>
              Thinking & consulting biometrics...
            </div>
          </div>
        )}
      </div>

      {/* Input Form Bar */}
      <div style={{ padding: '1rem 1.5rem', background: 'rgba(16, 22, 38, 0.95)', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendMessage();
          }}
          style={{ maxWidth: 900, margin: '0 auto', display: 'flex', gap: '0.75rem' }}
        >
          <input
            ref={inputRef}
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Ask coach, log 15 lb workout, or check fasting window..."
            style={{
              flex: 1,
              background: '#101626',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 12,
              padding: '0.85rem 1.15rem',
              color: '#fff',
              outline: 'none',
              fontSize: '0.95rem',
            }}
          />
          <button
            type="submit"
            disabled={isLoading || !inputText.trim()}
            style={{
              background: 'linear-gradient(135deg, #FF5722, #FF9100)',
              color: '#fff',
              border: 'none',
              borderRadius: 12,
              padding: '0.85rem 1.4rem',
              fontWeight: 600,
              cursor: isLoading || !inputText.trim() ? 'not-allowed' : 'pointer',
              opacity: isLoading || !inputText.trim() ? 0.6 : 1,
            }}
          >
            Send
          </button>
        </form>
      </div>

      {/* Log Strength Workout Modal */}
      <WorkoutModal
        isOpen={isWorkoutModalOpen}
        onClose={() => setIsWorkoutModalOpen(false)}
        onSubmit={handleWorkoutSubmit}
      />

      {/* Log Cycling Ride Modal */}
      <CyclingModal
        isOpen={isCyclingModalOpen}
        onClose={() => setIsCyclingModalOpen(false)}
        onSubmit={(formattedMessage) => handleSendMessage(formattedMessage)}
      />
    </div>
  );
};

export default ChatInterface;
