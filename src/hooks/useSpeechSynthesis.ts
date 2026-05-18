import { useState, useRef, useCallback } from "react"
import { useChatStore } from "@/store/chatStore"

export function useSpeechSynthesis() {
  const [isSpeaking, setIsSpeaking] = useState(false)
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null)

  const speak = useCallback((text: string) => {
    if (!("speechSynthesis" in window)) return

    cancel()

    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = "zh-CN"
    utterance.rate = 1.1
    utterance.pitch = 1.05
    utterance.volume = 1

    utterance.onstart = () => {
      setIsSpeaking(true)
      useChatStore.getState().setCharacterEmotion("speaking")
      useChatStore.getState().setMouthOpen(true)
    }

    utterance.onend = () => {
      setIsSpeaking(false)
      useChatStore.getState().setMouthOpen(false)
      useChatStore.getState().setCharacterEmotion("happy")
    }

    utterance.onerror = () => {
      setIsSpeaking(false)
      useChatStore.getState().setMouthOpen(false)
    }

    utteranceRef.current = utterance
    window.speechSynthesis.speak(utterance)
  }, [])

  const cancel = useCallback(() => {
    window.speechSynthesis.cancel()
    utteranceRef.current = null
    setIsSpeaking(false)
    useChatStore.getState().setMouthOpen(false)
  }, [])

  const isSupported = typeof window !== "undefined" && "speechSynthesis" in window

  return {
    isSupported,
    isSpeaking,
    speak,
    cancel,
  }
}