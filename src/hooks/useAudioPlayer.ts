import { useRef, useCallback } from "react"
import { useChatStore } from "@/store/chatStore"

export function useAudioPlayer() {
  const audioCtxRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<AudioWorkletNode | null>(null)
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

  const initProcessor = useCallback(async () => {
    const ctx = getAudioContext()
    if (processorRef.current) return

    try {
      await ctx.audioWorklet.addModule("/tts-pcm-processor.js")
      const processor = new AudioWorkletNode(ctx, "tts-pcm-processor")
      processor.connect(ctx.destination)
      processorRef.current = processor
    } catch {
    }
  }, [getAudioContext])

  const stop = useCallback(() => {
    try {
      if (processorRef.current) {
        processorRef.current.disconnect()
        processorRef.current = null
      }
      if (isPlayingRef.current) {
        isPlayingRef.current = false
        useChatStore.getState().setMouthOpen(false)
        useChatStore.getState().setTtsSpeaking(false)
        useChatStore.getState().setCharacterEmotion("happy")
      }
    } catch {}
  }, [])

  const appendChunk = useCallback((chunk: string, isLast: boolean) => {
    if (!chunk) return

    if (!processorRef.current) {
      initProcessor()
    }

    if (processorRef.current) {
      const binaryStr = atob(chunk)
      const bytes = new Uint8Array(binaryStr.length)
      for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i)
      }
      processorRef.current.port.postMessage(bytes.buffer, [bytes.buffer])

      if (!isPlayingRef.current) {
        isPlayingRef.current = true
        useChatStore.getState().setCharacterEmotion("speaking")
        useChatStore.getState().setMouthOpen(true)
        useChatStore.getState().setTtsSpeaking(true)
      }
    }

    if (isLast) {
      setTimeout(() => {
        isPlayingRef.current = false
        useChatStore.getState().setMouthOpen(false)
        useChatStore.getState().setTtsSpeaking(false)
        useChatStore.getState().setCharacterEmotion("happy")
      }, 500)
    }
  }, [initProcessor])

  const resetChunks = useCallback(() => {
    // 重置 AudioWorklet 缓冲区
    if (processorRef.current) {
      processorRef.current.port.postMessage('reset')
    }
    stop()
  }, [stop])

  const isSupported = typeof window !== "undefined" && !!(window.AudioContext || (window as any).webkitAudioContext)

  return {
    isSupported,
    isPlaying: isPlayingRef.current,
    appendChunk,
    resetChunks,
    stop,
  }
}