import React, { useRef } from 'react';
import {
  View, FlatList, Text, ActivityIndicator, StyleSheet, SafeAreaView,
} from 'react-native';
import { ModeSelector } from '../components/ModeSelector';
import { MessageBubble } from '../components/MessageBubble';
import { ChatInput } from '../components/ChatInput';
import { useChat } from '../hooks/useChat';
import type { Message } from '../store/chatStore';

const SUGGESTIONS: Record<string, string[]> = {
  guidance: ['How do I handle betrayal with dignity?', "What does Sita's steadfastness teach us?", 'How to stay devoted when suffering?'],
  story:    ['Retell Hanuman finding Sita in the Ashoka grove', 'How did Hanuman burn Lanka?', "Sita's courageous reply to Ravana"],
  children: ['Tell my child about Hanuman crossing the ocean', 'Why was Hanuman so brave?', 'What did Sita do when Ravana threatened her?'],
  scholar:  ['Chapter structure of Sundara Kanda', "Sanskrit shlokas on anger in Sundara Kanda", "Vibhishana's dharmic stand"],
};

export default function ChatScreen() {
  const { messages, isLoading, error, mode, setMode, sendMessage } = useChat();
  const listRef = useRef<FlatList>(null);

  const showSuggestions = messages.length === 0;

  return (
    <SafeAreaView style={styles.safe}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.logo}>☸</Text>
        <View>
          <Text style={styles.title}>DharmaGPT</Text>
          <Text style={styles.subtitle}>Wisdom from the sacred texts</Text>
        </View>
      </View>

      {/* Mode tabs */}
      <ModeSelector current={mode} onChange={setMode} />

      {/* Messages */}
      <FlatList
        ref={listRef}
        data={messages as Message[]}
        keyExtractor={(m) => m.id}
        renderItem={({ item }) => <MessageBubble message={item} />}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Namaste 🙏</Text>
            <Text style={styles.emptyText}>
              Ask a life question, request a story, or explore the sacred texts.{'\n'}
              Every answer is grounded in the source texts with citations.
            </Text>
            <View style={styles.suggestions}>
              {SUGGESTIONS[mode]?.map((s) => (
                <Text key={s} onPress={() => sendMessage(s)} style={styles.suggestion}>
                  {s}
                </Text>
              ))}
            </View>
          </View>
        }
        ListFooterComponent={
          isLoading ? (
            <View style={styles.typingRow}>
              <ActivityIndicator color="#EF9F27" size="small" />
              <Text style={styles.typingText}>Consulting the texts…</Text>
            </View>
          ) : error ? (
            <Text style={styles.error}>{error}</Text>
          ) : null
        }
      />

      {/* Input */}
      <ChatInput onSend={sendMessage} isLoading={isLoading} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#fff' },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 16, paddingTop: 12, paddingBottom: 8,
    borderBottomWidth: 0.5, borderBottomColor: '#D3D1C7',
  },
  logo: { fontSize: 26, color: '#EF9F27' },
  title: { fontSize: 18, fontWeight: '600', color: '#2C2C2A' },
  subtitle: { fontSize: 12, color: '#888780' },
  list: { paddingVertical: 12, flexGrow: 1 },
  empty: { flex: 1, alignItems: 'center', padding: 24, gap: 12 },
  emptyTitle: { fontSize: 20, fontWeight: '600', color: '#412402' },
  emptyText: { fontSize: 14, color: '#888780', textAlign: 'center', lineHeight: 21 },
  suggestions: { gap: 8, width: '100%' },
  suggestion: {
    fontSize: 13, color: '#854F0B', borderWidth: 0.5, borderColor: '#EF9F27',
    borderRadius: 10, padding: 10, backgroundColor: '#FAEEDA', textAlign: 'center',
  },
  typingRow: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 16 },
  typingText: { fontSize: 13, color: '#888780' },
  error: { color: '#A32D2D', fontSize: 13, padding: 16, textAlign: 'center' },
});
