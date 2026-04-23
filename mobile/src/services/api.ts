import axios from 'axios';

const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

export type QueryMode = 'guidance' | 'story' | 'children' | 'scholar';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface SourceChunk {
  text: string;
  citation: string;
  kanda: string | null;
  sarga: number | null;
  score: number;
  source_type: 'text' | 'audio';
  audio_timestamp: string | null;
  url: string | null;
}

export interface QueryRequest {
  query: string;
  mode: QueryMode;
  history?: ChatMessage[];
  language?: string;
  filter_kanda?: string;
}

export interface QueryResponse {
  answer: string;
  sources: SourceChunk[];
  mode: QueryMode;
  language: string;
  query_id: string;
}

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

export async function queryDharma(request: QueryRequest): Promise<QueryResponse> {
  const { data } = await api.post<QueryResponse>('/api/v1/query', request);
  return data;
}

export async function transcribeAudio(
  uri: string,
  fileName: string,
  languageCode: string = 'hi-IN',
  kanda?: string,
): Promise<{ transcript: string; chunks_created: number }> {
  const formData = new FormData();
  formData.append('file', { uri, name: fileName, type: 'audio/mpeg' } as any);
  formData.append('language_code', languageCode);
  if (kanda) formData.append('kanda', kanda);

  const { data } = await api.post('/api/v1/audio/transcribe', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  });
  return data;
}

export async function checkHealth() {
  const { data } = await api.get('/health');
  return data;
}
