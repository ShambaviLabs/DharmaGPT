import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from 'react-native';
import type { QueryMode } from '../services/api';

const MODES: { key: QueryMode; label: string; emoji: string; color: string }[] = [
  { key: 'guidance', label: 'Life Guidance', emoji: '🪔', color: '#854F0B' },
  { key: 'story',    label: 'Story',         emoji: '📖', color: '#0F6E56' },
  { key: 'children', label: 'Children',      emoji: '🌸', color: '#993556' },
  { key: 'scholar',  label: 'Scholar',       emoji: '📜', color: '#185FA5' },
];

interface Props {
  current: QueryMode;
  onChange: (mode: QueryMode) => void;
}

export function ModeSelector({ current, onChange }: Props) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.scroll}>
      <View style={styles.row}>
        {MODES.map((m) => {
          const active = current === m.key;
          return (
            <TouchableOpacity
              key={m.key}
              onPress={() => onChange(m.key)}
              style={[styles.chip, active && { backgroundColor: m.color, borderColor: m.color }]}
              activeOpacity={0.7}
            >
              <Text style={styles.emoji}>{m.emoji}</Text>
              <Text style={[styles.label, active && styles.labelActive]}>{m.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flexGrow: 0 },
  row: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingVertical: 10 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 14, paddingVertical: 7,
    borderRadius: 20, borderWidth: 1, borderColor: '#D3D1C7',
    backgroundColor: '#F1EFE8',
  },
  emoji: { fontSize: 14 },
  label: { fontSize: 13, color: '#5F5E5A', fontWeight: '500' },
  labelActive: { color: '#fff' },
});
