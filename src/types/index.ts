export type EmotionType = "idle" | "listening" | "thinking" | "speaking" | "happy"

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

export interface ServerMessage {
  type: "message"
  content: string
  is_final: boolean
  emotion?: EmotionType
}

export interface ClientMessage {
  type: "message"
  content: string
}

export interface ClientConnect {
  type: "connect"
  client_id?: string
}