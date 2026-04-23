import React, { useState, useRef } from 'react';
import {
  View, TextInput, TouchableOpacity, Text,
  ActivityIndicator, StyleSheet, Platform,
} from 'react-native';
import { Audio } from 'expo-av';
import * as DocumentPicker from 'expo-document-picker';
import * as Haptics from 'expo-haptics';
import { transcribeAudio } from '../services/api';

interface Props {
  onSend: (text: string) => void;
  isLoading: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, isLoading, placeholder }: Props) {
  const [text, setText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);

  const handleSend = () => {
    const q = text.trim();
    if (!q || isLoading) return;
    onSend(q);
    setText('');
  };

  const startRecording = async () => {
    try {
      await Audio.requestPermissionsAsync();
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY,
      );
      recordingRef.current = recording;
      setIsRecording(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (e) {
      console.warn('Recording error:', e);
    }
  };

  const stopRecording = async () => {
    if (!recordingRef.current) return;
    setIsRecording(false);
    setIsTranscribing(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    try {
      await recordingRef.current.stopAndUnloadAsync();
      const uri = recordingRef.current.getURI();
      if (uri) {
        const { transcript } = await transcribeAudio(uri, 'recording.m4a');
        setText(transcript);
      }
    } catch (e) {
      console.warn('Transcription error:', e);
    } finally {
      setIsTranscribing(false);
      recordingRef.current = null;
    }
  };

  const pickAudioFile = async () => {
    const result = await DocumentPicker.getDocumentAsync({ type: 'audio/*' });
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];
    setIsTranscribing(true);
    try {
      const { transcript } = await transcribeAudio(asset.uri, asset.name ?? 'audio.mp3');
      setText(transcript);
    } catch (e) {
      console.warn('File transcription error:', e);
    } finally {
      setIsTranscribing(false);
    }
  };

  const busy = isLoading || isTranscribing;

  return (
    <View style={styles.container}>
      <View style={styles.row}>
        <TextInput
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder={placeholder ?? 'Ask a dharmic question…'}
          placeholderTextColor="#888780"
          multiline
          maxLength={1000}
          returnKeyType="default"
          editable={!busy}
        />
        <TouchableOpacity
          onPress={handleSend}
          disabled={!text.trim() || busy}
          style={[styles.sendBtn, (!text.trim() || busy) && styles.sendBtnDisabled]}
        >
          {isLoading ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.sendIcon}>↑</Text>
          )}
        </TouchableOpacity>
      </View>

      <View style={styles.secondRow}>
        {/* Voice input */}
        <TouchableOpacity
          onPressIn={startRecording}
          onPressOut={stopRecording}
          disabled={busy}
          style={[styles.audioBtn, isRecording && styles.audioBtnActive]}
        >
          <Text style={styles.audioBtnText}>
            {isTranscribing ? '…' : isRecording ? '● REC' : '🎙 Hold'}
          </Text>
        </TouchableOpacity>

        {/* Upload audio file */}
        <TouchableOpacity onPress={pickAudioFile} disabled={busy} style={styles.uploadBtn}>
          <Text style={styles.uploadText}>📂 Upload audio</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderTopWidth: 0.5, borderTopColor: '#D3D1C7',
    padding: 12, backgroundColor: '#fff', gap: 8,
  },
  row: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 },
  input: {
    flex: 1, minHeight: 40, maxHeight: 100, fontSize: 15, color: '#2C2C2A',
    borderWidth: 0.5, borderColor: '#D3D1C7', borderRadius: 12,
    paddingHorizontal: 12, paddingVertical: 8, backgroundColor: '#F1EFE8',
  },
  sendBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: '#EF9F27', alignItems: 'center', justifyContent: 'center',
  },
  sendBtnDisabled: { opacity: 0.4 },
  sendIcon: { color: '#fff', fontSize: 18, fontWeight: '700' },
  secondRow: { flexDirection: 'row', gap: 8 },
  audioBtn: {
    flex: 1, height: 34, borderRadius: 8, borderWidth: 1,
    borderColor: '#EF9F27', alignItems: 'center', justifyContent: 'center',
  },
  audioBtnActive: { backgroundColor: '#FAEEDA' },
  audioBtnText: { fontSize: 13, color: '#633806', fontWeight: '500' },
  uploadBtn: {
    flex: 1, height: 34, borderRadius: 8, borderWidth: 1,
    borderColor: '#D3D1C7', alignItems: 'center', justifyContent: 'center',
  },
  uploadText: { fontSize: 13, color: '#5F5E5A' },
});
