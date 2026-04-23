import { useCallback } from 'react';
import { useChatStore } from '../store/chatStore';
import { queryDharma } from '../services/api';

export function useChat() {
  const store = useChatStore();

  const sendMessage = useCallback(
    async (query: string) => {
      if (!query.trim() || store.isLoading) return;

      store.addMessage({ role: 'user', content: query });
      store.setLoading(true);
      store.setError(null);

      try {
        const response = await queryDharma({
          query,
          mode: store.mode,
          history: store.getHistory(),
          filter_kanda: store.filterKanda ?? undefined,
        });

        store.addMessage({
          role: 'assistant',
          content: response.answer,
          sources: response.sources,
          mode: response.mode,
        });
      } catch (e: any) {
        const msg =
          e?.response?.data?.detail ??
          'Could not reach the dharmic oracle. Check your connection.';
        store.setError(msg);
      } finally {
        store.setLoading(false);
      }
    },
    [store],
  );

  return {
    messages: store.messages,
    isLoading: store.isLoading,
    error: store.error,
    mode: store.mode,
    setMode: store.setMode,
    clearMessages: store.clearMessages,
    sendMessage,
  };
}
