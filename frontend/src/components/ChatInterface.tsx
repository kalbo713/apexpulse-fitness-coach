import React, { useState, useRef, useEffect, useCallback } from 'react';
import WorkoutModal from './WorkoutModal';
import CyclingModal from './CyclingModal';

export interface MessagePart {
  kind?: 'text' | 'a2ui';
  text?: string;
  data?: any;
}

export interface AttachedImageState {
  id: string;
  base64: string;
  mimeType: string;
  name: string;
  size: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent';
  text: string;
  image?: string;
  images?: string[];
  parts?: MessagePart[];
  timestamp: string;
}

export interface ChatSessionMeta {
  session_id: string;
  title: string;
  category?: 'Workouts' | 'Nutrition' | 'Recovery' | 'General' | string;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
}

const DEFAULT_WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome-1',
  sender: 'agent',
  text: '👋 Welcome to ApexPulse! I am your AI Fitness & Fasting Coach. I specialize in functional longevity, strength & mobility routines (kettlebell, dumbbells, balance board, calf stretcher, yoga mat), Zone 2 cycling, step tracking, and 16/8 fasting optimization. How can I guide your training today?',
  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
};

interface CategoryConfigItem {
  key: string;
  icon: string;
  label: string;
}

const CATEGORY_CONFIG: CategoryConfigItem[] = [
  { key: 'Workouts', icon: '🏋️‍♂️', label: 'Workouts' },
  { key: 'Nutrition', icon: '🥩', label: 'Nutrition' },
  { key: 'Recovery', icon: '🧘', label: 'Recovery' },
  { key: 'General', icon: '💬', label: 'General' },
];

export const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([DEFAULT_WELCOME_MESSAGE]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isWorkoutModalOpen, setIsWorkoutModalOpen] = useState(false);
  const [isCyclingModalOpen, setIsCyclingModalOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [attachedImages, setAttachedImages] = useState<AttachedImageState[]>([]);

  // Chat Session & Categorized Sidebar State
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      return window.innerWidth <= 768;
    }
    return false;
  });

  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(() => {
    try {
      if (typeof window !== 'undefined' && window.innerWidth <= 768) {
        return false;
      }
      const saved = localStorage.getItem('apex_sidebar_collapsed');
      return saved !== 'true';
    } catch {
      return true;
    }
  });

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth <= 768;
      setIsMobile(mobile);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem('apex_collapsed_cats') || '{}');
    } catch {
      return {};
    }
  });
  const [isLoadingSession, setIsLoadingSession] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const formatFileSize = (bytes: number): string => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const MAX_IMAGES = 5;

  const processImageFiles = async (files: File[]) => {
    const validFiles = files.filter((f) => f.type && f.type.startsWith('image/'));
    if (validFiles.length === 0) {
      alert('Please select valid image files (PNG, JPG, WebP, etc.).');
      return;
    }

    const currentCount = attachedImages.length;
    if (currentCount >= MAX_IMAGES) {
      alert(`Maximum ${MAX_IMAGES} images allowed per message. Please remove an image before adding more.`);
      return;
    }

    const availableSlots = MAX_IMAGES - currentCount;
    const filesToProcess = validFiles.slice(0, availableSlots);
    if (validFiles.length > availableSlots) {
      alert(`You can attach up to ${MAX_IMAGES} images per message. Added ${availableSlots} image(s), ignored remaining.`);
    }

    const newImages: AttachedImageState[] = await Promise.all(
      filesToProcess.map((file) => {
        return new Promise<AttachedImageState>((resolve) => {
          const reader = new FileReader();
          reader.onload = (e) => {
            resolve({
              id: `img-${Date.now()}-${Math.random().toString(36).substr(2, 6)}`,
              base64: (e.target?.result as string) || '',
              mimeType: file.type || 'image/jpeg',
              name: file.name || 'attached_image.png',
              size: formatFileSize(file.size),
            });
          };
          reader.readAsDataURL(file);
        });
      })
    );

    setAttachedImages((prev) => {
      const combined = [...prev, ...newImages];
      return combined.slice(0, MAX_IMAGES);
    });
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      processImageFiles(files);
    }
    if (e.target) e.target.value = '';
  };

  const removeAttachedImage = (id: string) => {
    setAttachedImages((prev) => prev.filter((img) => img.id !== id));
  };

  const clearAllAttachedImages = () => {
    setAttachedImages([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (items) {
      const imageFiles: File[] = [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].type && items[i].type.indexOf('image') !== -1) {
          const file = items[i].getAsFile();
          if (file) {
            imageFiles.push(file);
          }
        }
      }
      if (imageFiles.length > 0) {
        if (attachedImages.length >= MAX_IMAGES) {
          alert(`Maximum ${MAX_IMAGES} images allowed per message. Please remove an image before adding more.`);
          e.preventDefault();
          return;
        }
        processImageFiles(imageFiles);
        e.preventDefault();
      }
    }
  };

  // Auto-scroll chat on new messages
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, isLoading, isLoadingSession]);

  // Fetch session list from backend
  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch('/sessions?user_id=apex-user');
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Toggle Sidebar
  const toggleSidebar = () => {
    setIsSidebarOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('apex_sidebar_collapsed', next ? 'false' : 'true');
      } catch {}
      return next;
    });
  };

  // Toggle Category Dropdown Collapse
  const toggleCategoryCollapse = (catKey: string) => {
    setCollapsedCategories((prev) => {
      const updated = { ...prev, [catKey]: !prev[catKey] };
      try {
        localStorage.setItem('apex_collapsed_cats', JSON.stringify(updated));
      } catch {}
      return updated;
    });
  };

  // Start a New Chat
  const handleNewChat = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
    }
    if (isMobile) {
      setIsSidebarOpen(false);
    }
    try {
      const res = await fetch('/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'apex-user', title: 'New Chat', category: 'General' }),
      });
      if (res.ok) {
        const data = await res.json();
        setCurrentSessionId(data.session?.session_id || `session_${Date.now()}`);
      } else {
        setCurrentSessionId(`session_${Date.now()}`);
      }
    } catch (err) {
      setCurrentSessionId(`session_${Date.now()}`);
    }
    setMessages([DEFAULT_WELCOME_MESSAGE]);
    fetchSessions();
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  // Load a historical chat session
  const handleSelectSession = async (sessionId: string) => {
    if (sessionId === currentSessionId && messages.length > 1) return;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
    }
    if (isMobile) {
      setIsSidebarOpen(false);
    }
    setCurrentSessionId(sessionId);
    setIsLoadingSession(true);

    try {
      const res = await fetch(`/sessions/${sessionId}?user_id=apex-user`);
      if (!res.ok) throw new Error('Failed to load session history');
      const data = await res.json();
      const session = data.session;
      const msgs = (session && session.messages) || [];

      if (msgs.length === 0) {
        setMessages([DEFAULT_WELCOME_MESSAGE]);
      } else {
        const formattedMsgs: ChatMessage[] = msgs.map((m: any, idx: number) => ({
          id: `hist-${sessionId}-${idx}-${Date.now()}`,
          sender: m.role === 'user' ? 'user' : 'agent',
          text: m.text || '',
          parts: m.parts || (m.role === 'agent' && m.text ? [{ kind: 'text', text: m.text }] : undefined),
          timestamp: m.timestamp
            ? new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }));
        setMessages(formattedMsgs);
      }
    } catch (err: any) {
      console.error('Error loading session:', err);
      setMessages([
        {
          id: `err-${Date.now()}`,
          sender: 'agent',
          text: `⚠️ Failed to load session history: ${err.message}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsLoadingSession(false);
    }
  };

  // Delete a historical session
  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    try {
      await fetch(`/sessions/${sessionId}?user_id=apex-user`, { method: 'DELETE' });
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      if (currentSessionId === sessionId) {
        handleNewChat();
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  };

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

  // Helper to parse Markdown links, bare URLs, and headings
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
    const currentImages = [...attachedImages];
    if ((!text && currentImages.length === 0) || isLoading) return;

    const userText = text || `Please analyze ${currentImages.length === 1 ? 'this attached image' : `these ${currentImages.length} attached images`}.`;
    const userMessageId = `user-${Date.now()}`;
    const userMsg: ChatMessage = {
      id: userMessageId,
      sender: 'user',
      text: userText,
      image: currentImages[0]?.base64,
      images: currentImages.map((img) => img.base64),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setAttachedImages([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setIsLoading(true);

    // Set up AbortController with 45s timeout
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), 45000);

    try {
      const payload: any = {
        message: userText,
        user_id: 'apex-user',
        session_id: currentSessionId,
      };
      if (currentImages.length > 0) {
        payload.images = currentImages.map((img) => img.base64);
        payload.image = currentImages[0].base64;
        payload.mime_type = currentImages[0].mimeType;
      }

      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      const data = await response.json();
      if (data.session_id && data.session_id !== currentSessionId) {
        setCurrentSessionId(data.session_id);
      }

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
      fetchSessions();
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

  // Group sessions by category
  const groupedSessions: Record<string, ChatSessionMeta[]> = {
    Workouts: [],
    Nutrition: [],
    Recovery: [],
    General: [],
  };

  sessions.forEach((s) => {
    const cat = s.category && groupedSessions[s.category] ? s.category : 'General';
    groupedSessions[cat].push(s);
  });

  return (
    <div className="chat-app-root" style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg-dark, #090d16)', color: '#fff' }}>
      {/* App Header */}
      <header style={{ padding: '0.85rem 1.5rem', background: 'rgba(16, 22, 38, 0.95)', borderBottom: '1px solid rgba(255,255,255,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Sidebar Toggle Button */}
          <button
            onClick={toggleSidebar}
            title={isSidebarOpen ? 'Collapse Chat History' : 'Expand Chat History'}
            style={{
              background: 'rgba(22, 31, 54, 0.9)',
              border: '1px solid rgba(255,255,255,0.12)',
              color: '#fff',
              width: 36,
              height: 36,
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              fontSize: '1.1rem',
              transition: 'all 0.2s',
            }}
          >
            {isSidebarOpen ? '◀' : '☰'}
          </button>

          <div style={{ width: 36, height: 36, borderRadius: 8, background: 'linear-gradient(135deg, #FF5722, #FF9100)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>
            ⚡
          </div>
          <div>
            <h1 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0 }}>ApexPulse Coach</h1>
            <span style={{ fontSize: '0.7rem', color: '#00E676' }}>● Live (Age 59 · Strength & Mobility · 16/8 Fasting 1PM-9PM)</span>
          </div>
        </div>
      </header>

      {/* Main Layout Container */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', position: 'relative', width: '100%' }}>
        {/* Mobile Backdrop Overlay */}
        {isMobile && isSidebarOpen && (
          <div
            onClick={() => setIsSidebarOpen(false)}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              width: '100%',
              height: '100%',
              background: 'rgba(0, 0, 0, 0.65)',
              backdropFilter: 'blur(3px)',
              zIndex: 35,
              cursor: 'pointer',
            }}
          />
        )}

        {/* Collapsible Left-hand History Sidebar (Desktop side-by-side, Mobile overlay drawer) */}
        <aside
          style={{
            position: isMobile ? 'absolute' : 'relative',
            top: 0,
            left: 0,
            bottom: 0,
            height: '100%',
            width: isMobile ? (isSidebarOpen ? 280 : 0) : (isSidebarOpen ? 290 : 0),
            minWidth: isMobile ? 0 : (isSidebarOpen ? 290 : 0),
            maxWidth: isMobile ? '85vw' : undefined,
            opacity: isSidebarOpen ? 1 : 0,
            transform: isMobile ? (isSidebarOpen ? 'translateX(0)' : 'translateX(-100%)') : undefined,
            background: 'rgba(16, 22, 38, 0.98)',
            backdropFilter: 'blur(20px)',
            borderRight: !isMobile && isSidebarOpen ? '1px solid rgba(255,255,255,0.08)' : 'none',
            boxShadow: isMobile && isSidebarOpen ? '6px 0 28px rgba(0, 0, 0, 0.75)' : 'none',
            display: 'flex',
            flexDirection: 'column',
            transition: 'transform 0.28s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.2s ease, width 0.25s ease',
            zIndex: isMobile ? 40 : 15,
            flexShrink: 0,
            overflow: 'hidden',
            pointerEvents: isSidebarOpen ? 'auto' : (isMobile ? 'none' : 'none'),
          }}
        >
          {/* Top Actions: New Chat Button */}
          <div style={{ padding: '1rem 0.85rem 0.6rem 0.85rem' }}>
            <button
              onClick={handleNewChat}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.6rem',
                background: 'linear-gradient(135deg, rgba(255, 87, 34, 0.16) 0%, rgba(255, 145, 0, 0.12) 100%)',
                border: '1px solid rgba(255, 87, 34, 0.45)',
                borderRadius: 12,
                padding: '0.75rem 1rem',
                color: '#fff',
                fontWeight: 700,
                fontSize: '0.95rem',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
            >
              <span>➕</span>
              <span>New Chat</span>
            </button>
          </div>

          {/* Sidebar Section Title */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.4rem 1rem 0.4rem 1rem' }}>
            <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748B' }}>
              Categories & History
            </span>
            <button
              onClick={fetchSessions}
              title="Refresh history"
              style={{ background: 'transparent', border: 'none', color: '#64748B', cursor: 'pointer', fontSize: '0.85rem' }}
            >
              🔄
            </button>
          </div>

          {/* Categorized Saved Sessions List */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '0.4rem 0.65rem 1rem 0.65rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem',
            }}
          >
            {sessions.length === 0 ? (
              <div style={{ color: '#64748B', fontSize: '0.8rem', padding: '1.5rem 0.5rem', textAlign: 'center' }}>
                No saved chats yet.<br />Start a conversation!
              </div>
            ) : (
              CATEGORY_CONFIG.map(({ key, icon, label }) => {
                const catSessions = groupedSessions[key] || [];
                const isCollapsed = !!collapsedCategories[key];

                return (
                  <div key={key} style={{ display: 'flex', flexDirection: 'column' }}>
                    {/* Collapsible Category Header Bar */}
                    <div
                      onClick={() => toggleCategoryCollapse(key)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.45rem 0.6rem',
                        borderRadius: 8,
                        cursor: 'pointer',
                        color: '#94A3B8',
                        fontSize: '0.74rem',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                        background: 'rgba(255, 255, 255, 0.03)',
                        border: '1px solid rgba(255, 255, 255, 0.05)',
                        transition: 'all 0.18s ease',
                        userSelect: 'none',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
                        e.currentTarget.style.color = '#fff';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
                        e.currentTarget.style.color = '#94A3B8';
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <span style={{ fontSize: '14px' }}>{icon}</span>
                        <span>{label}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <span
                          style={{
                            fontSize: '0.68rem',
                            background: 'rgba(255, 255, 255, 0.08)',
                            padding: '0.1rem 0.45rem',
                            borderRadius: 10,
                            color: '#CBD5E1',
                            fontWeight: 600,
                            fontFamily: 'monospace',
                          }}
                        >
                          {catSessions.length}
                        </span>
                        <span
                          style={{
                            fontSize: '12px',
                            transition: 'transform 0.2s ease',
                            transform: isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)',
                            color: '#64748B',
                          }}
                        >
                          ▼
                        </span>
                      </div>
                    </div>

                    {/* Category Sessions List */}
                    {!isCollapsed && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginTop: '0.3rem', paddingLeft: '0.25rem' }}>
                        {catSessions.length === 0 ? (
                          <div style={{ fontSize: '0.72rem', color: '#64748B', padding: '0.35rem 0.6rem', fontStyle: 'italic' }}>
                            No chats in this category
                          </div>
                        ) : (
                          catSessions.map((s) => {
                            const isActive = s.session_id === currentSessionId;
                            return (
                              <div
                                key={s.session_id}
                                onClick={() => handleSelectSession(s.session_id)}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'space-between',
                                  padding: '0.6rem 0.7rem',
                                  borderRadius: 8,
                                  background: isActive
                                    ? 'linear-gradient(135deg, rgba(255, 87, 34, 0.18) 0%, rgba(22, 31, 54, 0.95) 100%)'
                                    : 'transparent',
                                  border: isActive ? '1px solid rgba(255, 87, 34, 0.5)' : '1px solid transparent',
                                  color: isActive ? '#fff' : '#94A3B8',
                                  fontSize: '0.85rem',
                                  cursor: 'pointer',
                                  transition: 'all 0.18s ease',
                                  position: 'relative',
                                }}
                                onMouseEnter={(e) => {
                                  if (!isActive) e.currentTarget.style.background = 'rgba(255, 255, 255, 0.04)';
                                }}
                                onMouseLeave={(e) => {
                                  if (!isActive) e.currentTarget.style.background = 'transparent';
                                }}
                              >
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: 0 }}>
                                  <span style={{ fontSize: '14px', color: '#FF8A65', flexShrink: 0 }}>💬</span>
                                  <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
                                    <span
                                      style={{
                                        whiteSpace: 'nowrap',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        fontSize: '0.84rem',
                                        fontWeight: isActive ? 600 : 400,
                                        color: isActive ? '#fff' : '#E2E8F0',
                                      }}
                                      title={s.title}
                                    >
                                      {s.title}
                                    </span>
                                    <span style={{ fontSize: '0.68rem', color: '#64748B' }}>
                                      {s.message_count ? `${s.message_count} msgs` : 'New'}
                                    </span>
                                  </div>
                                </div>

                                <button
                                  onClick={(e) => handleDeleteSession(e, s.session_id)}
                                  title="Delete conversation"
                                  style={{
                                    background: 'transparent',
                                    border: 'none',
                                    color: '#64748B',
                                    cursor: 'pointer',
                                    padding: '0.2rem',
                                    fontSize: '0.8rem',
                                    borderRadius: 4,
                                    display: 'flex',
                                    alignItems: 'center',
                                  }}
                                  onMouseEnter={(e) => (e.currentTarget.style.color = '#ff5252')}
                                  onMouseLeave={(e) => (e.currentTarget.style.color = '#64748B')}
                                >
                                  🗑️
                                </button>
                              </div>
                            );
                          })
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </aside>

        {/* Chat Main Workspace */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', position: 'relative', width: '100%', minWidth: 0 }}>
          {/* Main Chat Scroll Area */}
          <div ref={chatContainerRef} style={{ flex: 1, overflowY: 'auto', padding: isMobile ? '1rem 0.75rem' : '1.5rem', maxWidth: 900, width: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
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
                  onClick={() => handleSendMessage('Show my master biometrics dashboard card with cardiovascular, recovery, sleep, and body composition metrics via A2UI.')}
                  className="quick-btn"
                  style={{ background: '#161f36', border: '1px solid rgba(255,87,34,0.3)', color: '#fff', padding: '0.6rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left' }}
                >
                  ❤️ Biometrics Summary Card
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
                  🏋️‍♂️ Log Strength & Mobility
                </button>
                <button
                  onClick={() => setIsCyclingModalOpen(true)}
                  className="quick-btn"
                  style={{ background: '#161f36', border: '1px solid rgba(255,87,34,0.4)', color: '#FF8A65', padding: '0.6rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left', fontWeight: 600 }}
                >
                  🚴 Log Cycling Ride
                </button>
                <button
                  onClick={() => handleSendMessage("Show me a summary of all workouts logged today and check my fasting window.")}
                  className="quick-btn"
                  style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', padding: '0.6rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left' }}
                >
                  📊 Today's Workout Summary
                </button>
              </div>
            </div>

            {/* Session Loading Indicator */}
            {isLoadingSession && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem', color: '#94A3B8', gap: '0.5rem' }}>
                <span>🔄</span>
                <span>Loading conversation history...</span>
              </div>
            )}

            {/* Message Thread */}
            {!isLoadingSession &&
              messages.map((msg) => (
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
                    >
                      {((msg.images && msg.images.length > 0) || msg.image) && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', marginBottom: '0.55rem' }}>
                          {(msg.images && msg.images.length > 0 ? msg.images : [msg.image!]).map((imgSrc, idx) => (
                            <img
                              key={idx}
                              src={imgSrc}
                              alt="Attached Thumbnail"
                              style={{
                                maxWidth: '160px',
                                maxHeight: '130px',
                                borderRadius: 8,
                                objectFit: 'cover',
                                display: 'block',
                                border: '1px solid rgba(255,255,255,0.2)',
                                boxShadow: '0 4px 10px rgba(0,0,0,0.3)',
                              }}
                            />
                          ))}
                        </div>
                      )}
                      <div dangerouslySetInnerHTML={{ __html: formatMarkdownContent(msg.text) }} />
                    </div>

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
          <div style={{ padding: isMobile ? '0.75rem 0.85rem' : '1rem 1.5rem', background: 'rgba(16, 22, 38, 0.95)', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            {/* Quick Prompt Suggestion Buttons */}
            <div style={{ maxWidth: 900, margin: '0 auto 0.65rem auto' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center', padding: '0.25rem 0' }}>
                <button
                  type="button"
                  onClick={() => handleSendMessage('Show my daily, weekly, and yearly step tracking summary card via A2UI.')}
                  style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 20, padding: '0.35rem 0.8rem', fontSize: '0.78rem', fontWeight: 500, color: '#94A3B8', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', transition: 'all 0.18s ease' }}
                >
                  🚶 Step Analytics Card
                </button>
                <button
                  type="button"
                  onClick={() => handleSendMessage('Show my master biometrics dashboard card with cardiovascular, recovery, sleep, and body composition metrics via A2UI.')}
                  style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 20, padding: '0.35rem 0.8rem', fontSize: '0.78rem', fontWeight: 500, color: '#94A3B8', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', transition: 'all 0.18s ease' }}
                >
                  ❤️ Biometrics Summary Card
                </button>
                <button
                  type="button"
                  onClick={() => setIsWorkoutModalOpen(true)}
                  style={{ background: '#161f36', border: '1px solid rgba(255,87,34,0.35)', borderRadius: 20, padding: '0.35rem 0.8rem', fontSize: '0.78rem', fontWeight: 500, color: '#FF8A65', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', transition: 'all 0.18s ease' }}
                >
                  🏋️‍♂️ Log Strength & Mobility
                </button>
                <button
                  type="button"
                  onClick={() => setIsCyclingModalOpen(true)}
                  style={{ background: '#161f36', border: '1px solid rgba(255,87,34,0.35)', borderRadius: 20, padding: '0.35rem 0.8rem', fontSize: '0.78rem', fontWeight: 500, color: '#FF8A65', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', transition: 'all 0.18s ease' }}
                >
                  🚴 Log Cycling
                </button>
                <button
                  type="button"
                  onClick={() => { setInputText('Log my steps: '); inputRef.current?.focus(); }}
                  style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 20, padding: '0.35rem 0.8rem', fontSize: '0.78rem', fontWeight: 500, color: '#94A3B8', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', transition: 'all 0.18s ease' }}
                >
                  👟 Log Steps
                </button>
                <button
                  type="button"
                  onClick={() => handleSendMessage('What is my current fasting status?')}
                  style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 20, padding: '0.35rem 0.8rem', fontSize: '0.78rem', fontWeight: 500, color: '#94A3B8', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', transition: 'all 0.18s ease' }}
                >
                  ⏱️ Fasting Timer
                </button>
                <button
                  type="button"
                  onClick={() => handleSendMessage('Calculate my protein target for 200 lbs across meals in my 8-hour window.')}
                  style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 20, padding: '0.35rem 0.8rem', fontSize: '0.78rem', fontWeight: 500, color: '#94A3B8', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', transition: 'all 0.18s ease' }}
                >
                  🍗 Protein Breakdown
                </button>
                <button
                  type="button"
                  onClick={() => handleSendMessage('Suggest a high-protein post-workout meal to hit 60g protein.')}
                  style={{ background: '#161f36', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 20, padding: '0.35rem 0.8rem', fontSize: '0.78rem', fontWeight: 500, color: '#94A3B8', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', transition: 'all 0.18s ease' }}
                >
                  🥗 Post-Workout Meal
                </button>
              </div>
            </div>

            {/* Dynamic Horizontal Image Gallery Container (Up to 5 images) */}
            {attachedImages.length > 0 && (
              <div
                style={{
                  maxWidth: 900,
                  margin: '0 auto 0.65rem auto',
                  background: 'rgba(22, 31, 54, 0.95)',
                  border: '1px solid rgba(255, 87, 34, 0.35)',
                  borderRadius: 14,
                  padding: '0.65rem 0.85rem',
                  boxShadow: '0 4px 18px rgba(0, 0, 0, 0.35), 0 0 12px rgba(255, 87, 34, 0.12)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem', paddingBottom: '0.35rem', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                    <span style={{ fontSize: '14px', color: '#FF8A65' }}>🖼️</span>
                    <span style={{ fontSize: '0.76rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#FF8A65' }}>Attached Photos</span>
                    <span style={{ background: 'rgba(255,87,34,0.2)', border: '1px solid rgba(255,87,34,0.4)', color: '#fff', fontSize: '0.68rem', padding: '0.1rem 0.45rem', borderRadius: 10, fontFamily: 'monospace' }}>
                      {attachedImages.length}/5
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={clearAllAttachedImages}
                    style={{ background: 'transparent', border: 'none', color: '#94A3B8', fontSize: '0.72rem', fontWeight: 600, cursor: 'pointer' }}
                  >
                    Clear All
                  </button>
                </div>
                <div style={{ display: 'flex', gap: '0.65rem', overflowX: 'auto', padding: '0.25rem 0.1rem' }}>
                  {attachedImages.map((img) => (
                    <div
                      key={img.id}
                      style={{
                        position: 'relative',
                        width: 68,
                        height: 68,
                        borderRadius: 10,
                        border: '1.5px solid rgba(255, 87, 34, 0.5)',
                        background: 'rgba(13, 19, 34, 0.95)',
                        flexShrink: 0,
                        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
                      }}
                      title={`${img.name} (${img.size})`}
                    >
                      <img src={img.base64} alt={img.name} style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: 8, display: 'block' }} />
                      <button
                        type="button"
                        onClick={() => removeAttachedImage(img.id)}
                        style={{
                          position: 'absolute',
                          top: -6,
                          right: -6,
                          width: 20,
                          height: 20,
                          borderRadius: '50%',
                          background: '#ff5252',
                          border: '1.5px solid #fff',
                          color: '#fff',
                          fontSize: 13,
                          fontWeight: 700,
                          lineHeight: 1,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          cursor: 'pointer',
                          boxShadow: '0 2px 6px rgba(0,0,0,0.4)',
                        }}
                        title="Remove photo"
                      >
                        &times;
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage();
              }}
              style={{ maxWidth: 900, margin: '0 auto', display: 'flex', gap: '0.75rem', alignItems: 'center' }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                style={{
                  background: '#101626',
                  border: '1px solid rgba(255,255,255,0.1)',
                  color: '#94A3B8',
                  borderRadius: 12,
                  width: 44,
                  height: 44,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  fontSize: '1.2rem',
                  flexShrink: 0,
                  transition: 'all 0.2s',
                }}
                title="Attach Photos (Up to 5: meal, workout form, equipment, or biometrics)"
              >
                📷
              </button>
              <input
                ref={inputRef}
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onPaste={handlePaste}
                placeholder="Ask coach, log workout, paste images, or check fasting window..."
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
                disabled={isLoading || (!inputText.trim() && attachedImages.length === 0)}
                style={{
                  background: 'linear-gradient(135deg, #FF5722, #FF9100)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 12,
                  padding: '0.85rem 1.4rem',
                  fontWeight: 600,
                  cursor: isLoading || (!inputText.trim() && attachedImages.length === 0) ? 'not-allowed' : 'pointer',
                  opacity: isLoading || (!inputText.trim() && attachedImages.length === 0) ? 0.6 : 1,
                }}
              >
                Send
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* Log Strength & Mobility Workout Modal */}
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
