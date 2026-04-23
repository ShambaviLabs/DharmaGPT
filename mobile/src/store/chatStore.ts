import { create } from 'zustand';
import type { QueryMode, ChatMessage, SourceChunk } from '../services/api';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceChunk[];
  mode?: QueryMode;
  timestamp: Date;
}

interface ChatState {
  messages: Message[];
  mode: QueryMode;
  isLoading: boolean;
  error: string | null;
  filterKanda: string | null;

  setMode: (mode: QueryMode) => void;
  setFilterKanda: (kanda: string | null) => void;
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => void;
  setLoading: (v: boolean) => void;
  setError: (e: string | null) => void;
  clearMessages: () => void;

  // Derived: history for API (last 10 turns)
  getHistory: () => ChatMessage[];
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  mode: 'guidance',
  isLoading: false,
  error: null,
  filterKanda: null,

  setMode: (mode) => set({ mode, messages: [], error: null }),
  setFilterKanda: (filterKanda) => set({ filterKanda }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  clearMessages: () => set({ messages: [], error: null }),

  addMessage: (msg) =>
    set((state) => ({
      messages: [
        ...state.messages,
        { ...msg, id: Date.now().toString(), timestamp: new Date() },
      ],
    })),

  getHistory: () => {
    const msgs = get().messages.slice(-10);
    return msgs.map((m) => ({ role: m.role, content: m.content }));
  },
}));
