import { create } from "zustand"
import type { Message, EmotionType, CharacterState, AppMode, SummaryItem } from "@/types"

interface ChatStore {
  messages: Message[]
  summaries: SummaryItem[]
  characterState: CharacterState
  mode: AppMode
  isConnected: boolean
  isProcessing: boolean
  isSummarizing: boolean
  wsUrl: string
  wakeWord: string
  wordCount: number
  lastRecordedText: string

  addMessage: (message: Message) => void
  updateLastAssistantMessage: (content: string) => void
  setCharacterEmotion: (emotion: EmotionType) => void
  setMouthOpen: (open: boolean) => void
  setConnected: (connected: boolean) => void
  setProcessing: (processing: boolean) => void
  setMode: (mode: AppMode) => void
  setWakeWord: (word: string) => void
  setWordCount: (count: number) => void
  setLastRecordedText: (text: string) => void
  addSummary: (summary: SummaryItem) => void
  setSummarizing: (v: boolean) => void
  setWsUrl: (url: string) => void
  resetMessages: () => void
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  summaries: [],
  characterState: { emotion: "idle", isMouthOpen: false },
  mode: "listening",
  isConnected: false,
  isProcessing: false,
  isSummarizing: false,
  wsUrl: "ws://localhost:8765/ws",
  wakeWord: "小爱",
  wordCount: 0,
  lastRecordedText: "",

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
  setMode: (mode) => set({ mode }),
  setWakeWord: (word) => set({ wakeWord: word }),
  setWordCount: (count) => set({ wordCount: count }),
  setLastRecordedText: (text) => set({ lastRecordedText: text }),
  addSummary: (summary) =>
    set((state) => ({ summaries: [summary, ...state.summaries] })),
  setSummarizing: (v) => set({ isSummarizing: v }),
  setWsUrl: (url) => set({ wsUrl: url }),
  resetMessages: () => set({ messages: [] }),
}))