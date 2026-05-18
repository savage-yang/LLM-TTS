import { create } from "zustand"
import type { Message, EmotionType, CharacterState } from "@/types"

interface ChatStore {
  messages: Message[]
  characterState: CharacterState
  isConnected: boolean
  isProcessing: boolean
  wsUrl: string

  addMessage: (message: Message) => void
  updateLastAssistantMessage: (content: string) => void
  setCharacterEmotion: (emotion: EmotionType) => void
  setMouthOpen: (open: boolean) => void
  setConnected: (connected: boolean) => void
  setProcessing: (processing: boolean) => void
  setWsUrl: (url: string) => void
  resetMessages: () => void
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  characterState: { emotion: "idle", isMouthOpen: false },
  isConnected: false,
  isProcessing: false,
  wsUrl: "ws://localhost:8765",

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  updateLastAssistantMessage: (content) =>
    set((state) => {
      const msgs = [...state.messages]
      const lastIdx = msgs.length - 1
      if (lastIdx >= 0 && msgs[lastIdx].role === "assistant") {
        msgs[lastIdx] = { ...msgs[lastIdx], content }
      }
      return { messages: msgs }
    }),

  setCharacterEmotion: (emotion) =>
    set((state) => ({
      characterState: { ...state.characterState, emotion },
    })),

  setMouthOpen: (open) =>
    set((state) => ({
      characterState: { ...state.characterState, isMouthOpen: open },
    })),

  setConnected: (connected) => set({ isConnected: connected }),
  setProcessing: (processing) => set({ isProcessing: processing }),
  setWsUrl: (url) => set({ wsUrl: url }),
  resetMessages: () => set({ messages: [] }),
}))