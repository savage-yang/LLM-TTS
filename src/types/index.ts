export type EmotionType = "idle" | "listening" | "thinking" | "speaking" | "happy"

export type AppMode = "listening" | "dialogue"

export type MessageRole = "user" | "assistant"

export interface Message {
  id: string
  role: MessageRole
  content: string
  timestamp: number
  emotion?: EmotionType
}

export interface CharacterState {
  emotion: EmotionType
  isMouthOpen: boolean
}

export type ServerMessageType =
  | "message"
  | "connected"
  | "mode_change"
  | "listening_recorded"
  | "status"
  | "tts_start"
  | "tts_audio_chunk"
  | "tts_end"
  | "tts_error"
  | "llm_token"
  | "buffer_audio"

export interface ServerMessage {
  type: ServerMessageType
  role?: MessageRole
  content: string
  is_final?: boolean
  emotion?: EmotionType
  mode?: AppMode
  reason?: string
  wake_word?: string
  word_count?: number
  summarizing?: boolean
  text?: string
  timestamp?: string
  status?: string
  tts_enabled?: boolean
  chunk_id?: number
  total_chunks?: number
  data?: string
  is_last?: boolean
  error?: string
  modules_loaded?: boolean
  summary_interval?: number
  dialogue_idle_timeout?: number
  interrupted?: boolean
}

export interface ClientMessage {
  type: "message" | "connect" | "switch_mode" | "interrupt"
  content?: string
  client_id?: string
  mode?: AppMode
}