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

export interface SummaryItem {
  id: string
  content: string
  timestamp: string
}

export interface CharacterState {
  emotion: EmotionType
  isMouthOpen: boolean
}

export interface ServerMessage {
  type: "message" | "connected" | "mode_change" | "listening_recorded"
    | "summary_start" | "summary" | "status"
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
}

export interface ClientMessage {
  type: "message" | "connect" | "switch_mode"
  content?: string
  client_id?: string
  mode?: AppMode
}