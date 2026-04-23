import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useChatStore } from '../src/store/chatStore';
import { useRouter } from 'expo-router';

const TEXTS = [
  {
    name: 'Sundara Kanda',
    desc: 'Hanuman's journey to Lanka — 68 sargas',
    kanda: 'Sundara Kanda',
    url: 'https://www.valmikiramayan.net',
    color: '#854F0B',
    bg: '#FAEEDA',
    loaded: true,
  },
  { name: 'Bala Kanda',      desc: 'Birth of Rama — 77 sargas',  kanda: 'Bala Kanda',      url: 'https://www.valmikiramayan.net', color: '#0F6E56', bg: '#E1F5EE', loaded: false },
  { name: 'Ayodhya Kanda',   desc: 'The exile — 119 sargas',     kanda: 'Ayodhya Kanda',   url: 'https://www.valmikiramayan.net', color: '#185FA5', bg: '#E6F1FB', loaded: false },
  { name: 'Aranya Kanda',    desc: 'Forest years — 75 sargas',   kanda: 'Aranya Kanda',    url: 'https://www.valmikiramayan.net', color: '#3B6D11', bg: '#EAF3DE', loaded: false },
  { name: 'Kishkindha Kanda',desc: 'Alliance — 67 sargas',       kanda: 'Kishkindha Kanda',url: 'https://www.valmikiramayan.net', color: '#533AB7', bg: '#EEEDFE', loaded: false },
  { name: 'Yuddha Kanda',    desc: 'The great war — 128 sargas', kanda: 'Yuddha Kanda',    url: 'https://www.valmikiramayan.net', color: '#993C1D', bg: '#FAECE7', loaded: false },
  { name: 'Uttara Kanda',    desc: 'Epilogue — 111 sargas',      kanda: 'Uttara Kanda',    url: 'https://www.valmikiramayan.net', color: '#72243E', bg: '#FBEAF0', loaded: false },
  { name: 'Bhagavad Gita',   desc: '18 chapters · 700 shlokas',  kanda: null,              url: 'https://www.sacred-texts.com',  color: '#633806', bg: '#FAEEDA', loaded: false },
];

export default function LibraryScreen() {
  const setFilterKanda = useChatStore((s) => s.setFilterKanda);
  const router = useRouter();

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.title}>Sacred Texts</Text>
        <Text style={styles.sub}>Tap a text to filter answers to that source</Text>
      </View>
      <ScrollView contentContainerStyle={styles.list}>
        {TEXTS.map((t) => (
          <TouchableOpacity
            key={t.name}
            style={[styles.card, { backgroundColor: t.bg, borderColor: t.color }]}
            onPress={() => {
              setFilterKanda(t.kanda);
              router.push('/');
            }}
          >
            <View style={styles.cardRow}>
              <View style={{ flex: 1 }}>
                <Text style={[styles.cardName, { color: t.color }]}>{t.name}</Text>
                <Text style={styles.cardDesc}>{t.desc}</Text>
              </View>
              {t.loaded && (
                <View style={[styles.badge, { borderColor: t.color }]}>
                  <Text style={[styles.badgeText, { color: t.color }]}>Indexed</Text>
                </View>
              )}
            </View>
            <TouchableOpacity onPress={() => Linking.openURL(t.url)}>
              <Text style={[styles.link, { color: t.color }]}>Read source →</Text>
            </TouchableOpacity>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#fff' },
  header: { padding: 16, borderBottomWidth: 0.5, borderBottomColor: '#D3D1C7' },
  title: { fontSize: 20, fontWeight: '600', color: '#2C2C2A' },
  sub: { fontSize: 13, color: '#888780', marginTop: 2 },
  list: { padding: 16, gap: 12 },
  card: {
    borderRadius: 12, borderWidth: 0.5, padding: 14, gap: 8,
  },
  cardRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardName: { fontSize: 15, fontWeight: '600' },
  cardDesc: { fontSize: 13, color: '#5F5E5A', marginTop: 2 },
  badge: {
    borderWidth: 0.5, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3,
  },
  badgeText: { fontSize: 11, fontWeight: '500' },
  link: { fontSize: 12, textDecorationLine: 'underline' },
});
