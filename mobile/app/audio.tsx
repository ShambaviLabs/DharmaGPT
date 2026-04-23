import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ActivityIndicator,
  Alert, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as DocumentPicker from 'expo-document-picker';
import { transcribeAudio } from '../src/services/api';

interface UploadedFile {
  name: string;
  chunks: number;
  lang: string;
  status: 'done' | 'error';
}

const LANGUAGES = [
  { code: 'hi-IN', label: 'Hindi' },
  { code: 'te-IN', label: 'Telugu' },
  { code: 'ta-IN', label: 'Tamil' },
  { code: 'sa-IN', label: 'Sanskrit' },
  { code: 'en-IN', label: 'English (Indian)' },
  { code: 'auto',  label: 'Auto-detect' },
];

export default function AudioScreen() {
  const [uploading, setUploading] = useState(false);
  const [lang, setLang] = useState('hi-IN');
  const [uploaded, setUploaded] = useState<UploadedFile[]>([]);

  const pickAndUpload = async () => {
    const result = await DocumentPicker.getDocumentAsync({ type: 'audio/*' });
    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    setUploading(true);
    try {
      const { chunks_created } = await transcribeAudio(asset.uri, asset.name ?? 'audio.mp3', lang);
      setUploaded((prev) => [
        { name: asset.name ?? 'audio.mp3', chunks: chunks_created, lang, status: 'done' },
        ...prev,
      ]);
    } catch {
      Alert.alert('Upload failed', 'Could not transcribe the audio file. Check your connection.');
      setUploaded((prev) => [
        { name: asset.name ?? 'audio.mp3', chunks: 0, lang, status: 'error' },
        ...prev,
      ]);
    } finally {
      setUploading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.title}>Audio Library</Text>
        <Text style={styles.sub}>Upload chantings, pravachanams, discourses</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Language selector */}
        <Text style={styles.sectionLabel}>Transcription language</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
          <View style={styles.langRow}>
            {LANGUAGES.map((l) => (
              <TouchableOpacity
                key={l.code}
                onPress={() => setLang(l.code)}
                style={[styles.langChip, lang === l.code && styles.langChipActive]}
              >
                <Text style={[styles.langLabel, lang === l.code && styles.langLabelActive]}>
                  {l.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>

        {/* Upload button */}
        <TouchableOpacity
          onPress={pickAndUpload}
          disabled={uploading}
          style={[styles.uploadBtn, uploading && styles.uploadBtnDisabled]}
        >
          {uploading ? (
            <View style={styles.uploadRow}>
              <ActivityIndicator color="#fff" size="small" />
              <Text style={styles.uploadText}>Transcribing via Sarvam AI…</Text>
            </View>
          ) : (
            <Text style={styles.uploadText}>📂  Select audio file</Text>
          )}
        </TouchableOpacity>

        <Text style={styles.hint}>
          Powered by Sarvam Saaras v3 · 22 Indian languages · Auto-chunks into searchable passages
        </Text>

        {/* Uploaded files */}
        {uploaded.length > 0 && (
          <>
            <Text style={styles.sectionLabel}>Uploaded this session</Text>
            {uploaded.map((f, i) => (
              <View key={i} style={[styles.fileCard, f.status === 'error' && styles.fileCardError]}>
                <Text style={styles.fileName}>{f.name}</Text>
                <Text style={styles.fileMeta}>
                  {f.status === 'done'
                    ? `✓ ${f.chunks} chunks indexed · ${f.lang}`
                    : '✗ Transcription failed'}
                </Text>
              </View>
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#fff' },
  header: { padding: 16, borderBottomWidth: 0.5, borderBottomColor: '#D3D1C7' },
  title: { fontSize: 20, fontWeight: '600', color: '#2C2C2A' },
  sub: { fontSize: 13, color: '#888780', marginTop: 2 },
  content: { padding: 16, gap: 12 },
  sectionLabel: { fontSize: 13, fontWeight: '500', color: '#5F5E5A', marginBottom: 6 },
  langRow: { flexDirection: 'row', gap: 8 },
  langChip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20,
    borderWidth: 0.5, borderColor: '#D3D1C7', backgroundColor: '#F1EFE8',
  },
  langChipActive: { backgroundColor: '#EF9F27', borderColor: '#EF9F27' },
  langLabel: { fontSize: 13, color: '#5F5E5A' },
  langLabelActive: { color: '#fff', fontWeight: '500' },
  uploadBtn: {
    backgroundColor: '#EF9F27', borderRadius: 12, padding: 16,
    alignItems: 'center', justifyContent: 'center',
  },
  uploadBtnDisabled: { opacity: 0.6 },
  uploadRow: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  uploadText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  hint: { fontSize: 12, color: '#888780', textAlign: 'center', lineHeight: 18 },
  fileCard: {
    padding: 12, borderRadius: 10, borderWidth: 0.5,
    borderColor: '#5DCAA5', backgroundColor: '#E1F5EE', gap: 3,
  },
  fileCardError: { borderColor: '#F09595', backgroundColor: '#FCEBEB' },
  fileName: { fontSize: 14, fontWeight: '500', color: '#2C2C2A' },
  fileMeta: { fontSize: 12, color: '#5F5E5A' },
});
