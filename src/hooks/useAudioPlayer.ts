import { useRef, useCallback } from "react"
import { useChatStore } from "@/store/chatStore"

export function useAudioPlayer() {
  const audioCtxRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<AudioWorkletNode | null>(null)
  const isPlayingRef = useRef(false)
  const pendingChunksRef = useRef<Array<{ chunk: string; isLast: boolean }>>([])

  const getAudioContext = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)()
    }
    if (audioCtxRef.current.state === "suspended") {
      audioCtxRef.current.resume()
    }
    return audioCtxRef.current
  }, [])

  const flushPendingChunks = useCallback(() => {
    const pending = pendingChunksRef.current
    pendingChunksRef.current = []
    for (const { chunk, isLast } of pending) {
      sendChunkToProcessor(chunk, isLast)
    }
  }, [])

  const sendChunkToProcessor = useCallback((chunk: string, isLast: boolean) => {
    if (!processorRef.current || !chunk) return
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

    if (isLast) {
      setTimeout(() => {
        isPlayingRef.current = false
        useChatStore.getState().setMouthOpen(false)
        useChatStore.getState().setTtsSpeaking(false)
        useChatStore.getState().setCharacterEmotion("happy")
      }, 500)
    }
  }, [])

  const initProcessor = useCallback(async () => {
    const ctx = getAudioContext()
    if (processorRef.current) return

    try {
      await ctx.audioWorklet.addModule("/tts-pcm-processor.js")
      const processor = new AudioWorkletNode(ctx, "tts-pcm-processor")
      processor.connect(ctx.destination)
      processorRef.current = processor
      flushPendingChunks()
    } catch {
    }
  }, [getAudioContext, flushPendingChunks])

  const ensureProcessor = useCallback(async () => {
    if (!processorRef.current) {
      await initProcessor()
    }
  }, [initProcessor])

  const stop = useCallback(() => {
    try {
      if (processorRef.current) {
        processorRef.current.disconnect()
        processorRef.current = null
      }
      pendingChunksRef.current = []
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
      pendingChunksRef.current.push({ chunk, isLast })
      initProcessor()
      return
    }

    sendChunkToProcessor(chunk, isLast)
  }, [initProcessor, sendChunkToProcessor])

  const resetChunks = useCallback(() => {
    pendingChunksRef.current = []
    ensureProcessor()
    if (processorRef.current) {
      processorRef.current.port.postMessage('reset')
    }
    isPlayingRef.current = false
  }, [ensureProcessor])

  const clearBuffer = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.port.postMessage('reset')
    }
  }, [])

  const isSupported = typeof window !== "undefined" && !!(window.AudioContext || (window as any).webkitAudioContext)

  return {
    isSupported,
    isPlaying: isPlayingRef.current,
    appendChunk,
    resetChunks,
    clearBuffer,
    stop,
  }
}