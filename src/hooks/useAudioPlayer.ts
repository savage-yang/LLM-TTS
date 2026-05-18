import { useRef, useCallback } from "react"
import { useChatStore } from "@/store/chatStore"

export function useAudioPlayer() {
  const audioCtxRef = useRef<AudioContext | null>(null)
  const sourceRef = useRef<AudioBufferSourceNode | null>(null)
  const chunkBufferRef = useRef<string>("")
  const isPlayingRef = useRef(false)

  const getAudioContext = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)()
    }
    if (audioCtxRef.current.state === "suspended") {
      audioCtxRef.current.resume()
    }
    return audioCtxRef.current
  }, [])

  const stop = useCallback(() => {
    try {
      if (sourceRef.current) {
        try { sourceRef.current.stop() } catch {}
        sourceRef.current.disconnect()
        sourceRef.current = null
      }
      if (isPlayingRef.current) {
        isPlayingRef.current = false
        useChatStore.getState().setMouthOpen(false)
        useChatStore.getState().setTtsSpeaking(false)
        useChatStore.getState().setCharacterEmotion("happy")
      }
    } catch {}
  }, [])

  const playBase64Wav = async (base64Data: string) => {
    try {
      stop()
      const ctx = getAudioContext()
      const binaryStr = atob(base64Data)
      const bytes = new Uint8Array(binaryStr.length)
      for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i)
      }

      const audioBuffer = await ctx.decodeAudioData(bytes.buffer as ArrayBuffer)
      const source = ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(ctx.destination)

      source.onended = () => {
        isPlayingRef.current = false
        useChatStore.getState().setMouthOpen(false)
        useChatStore.getState().setTtsSpeaking(false)
        useChatStore.getState().setCharacterEmotion("happy")
      }

      source.start(0)
      sourceRef.current = source
      isPlayingRef.current = true

      useChatStore.getState().setCharacterEmotion("speaking")
      useChatStore.getState().setMouthOpen(true)
      useChatStore.getState().setTtsSpeaking(true)
    } catch (e) {
      console.error("Audio play error:", e)
      useChatStore.getState().setMouthOpen(false)
      useChatStore.getState().setTtsSpeaking(false)
    }
  }

  const appendChunk = useCallback((chunk: string, isLast: boolean) => {
    chunkBufferRef.current += chunk
    if (isLast && chunkBufferRef.current) {
      const fullBase64 = chunkBufferRef.current
      chunkBufferRef.current = ""
      playBase64Wav(fullBase64)
    }
  }, [])

  const resetChunks = useCallback(() => {
    chunkBufferRef.current = ""
  }, [])

  const isSupported = typeof window !== "undefined" && !!(window.AudioContext || (window as any).webkitAudioContext)

  return {
    isSupported,
    isPlaying: isPlayingRef.current,
    appendChunk,
    resetChunks,
    stop,
    playBase64Wav,
  }
}