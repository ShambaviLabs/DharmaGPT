import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Linking, StyleSheet } from 'react-native';
import type { Message } from '../store/chatStore';

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === 'user';
  const hasSources = message.sources && message.sources.length > 0;

  return (
    <View style={[styles.wrapper, isUser && styles.wrapperUser]}>
      <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAI]}>
        <Text style={[styles.text, isUser && styles.textUser]}>{message.content}</Text>
      </View>

      {hasSources && (
        <TouchableOpacity
          onPress={() => setShowSources((v) => !v)}
          style={styles.sourcesToggle}
        >
          <Text style={styles.sourcesToggleText}>
            {showSources ? 'Hide sources' : `${message.sources!.length} source${message.sources!.length > 1 ? 's' : ''} →`}
          </Text>
        </TouchableOpacity>
      )}

      {showSources && message.sources && (
        <View style={styles.sourcesBox}>
          {message.sources.map((s, i) => (
            <TouchableOpacity
              key={i}
              onPress={() => s.url && Linking.openURL(s.url)}
              style={styles.sourceItem}
              disabled={!s.url}
            >
              <Text style={styles.sourceCitation}>{s.citation}</Text>
              {s.source_type === 'audio' && s.audio_timestamp && (
                <Text style={styles.sourceTimestamp}>🔊 {s.audio_timestamp}</Text>
              )}
              <Text style={styles.sourceScore}>Relevance: {Math.round(s.score * 100)}%</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { marginVertical: 6, marginHorizontal: 16, alignItems: 'flex-start' },
  wrapperUser: { alignItems: 'flex-end' },
  bubble: {
    maxWidth: '85%', padding: 12, borderRadius: 16,
    borderBottomLeftRadius: 4,
  },
  bubbleUser: {
    backgroundColor: '#F1EFE8', borderBottomLeftRadius: 16, borderBottomRightRadius: 4,
  },
  bubbleAI: { backgroundColor: '#FAEEDA' },
  text: { fontSize: 15, lineHeight: 22, color: '#412402' },
  textUser: { color: '#2C2C2A' },
  sourcesToggle: { marginTop: 4, marginLeft: 4 },
  sourcesToggleText: { fontSize: 12, color: '#854F0B', textDecorationLine: 'underline' },
  sourcesBox: {
    marginTop: 6, padding: 10, backgroundColor: '#fff8f0',
    borderRadius: 10, borderWidth: 0.5, borderColor: '#EF9F27',
    maxWidth: '85%', gap: 8,
  },
  sourceItem: { gap: 2 },
  sourceCitation: { fontSize: 12, color: '#633806', fontWeight: '500' },
  sourceTimestamp: { fontSize: 11, color: '#854F0B' },
  sourceScore: { fontSize: 11, color: '#888780' },
});
