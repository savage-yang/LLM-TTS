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
      console.log("[AudioPlayer] TTS PCM processor initialized")
    } catch (e) {
      console.error("[AudioPlayer] Failed to initialize processor:", e)
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

  const playBase64Wav = async (base64Data: string) => {
    // 保留原有的WAV播放功能作为备用
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
    if (!chunk) return

    // 初始化processor（如果尚未初始化）
    if (!processorRef.current) {
      initProcessor()
    }

    if (processorRef.current) {
      // 将base64音频块转换为PCM16数据
      const binaryStr = atob(chunk)
      const bytes = new Uint8Array(binaryStr.length)
      for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i)
      }

      // 发送PCM数据到AudioWorklet进行实时播放
      processorRef.current.port.postMessage(bytes.buffer, [bytes.buffer])

      if (!isPlayingRef.current) {
        isPlayingRef.current = true
        useChatStore.getState().setCharacterEmotion("speaking")
        useChatStore.getState().setMouthOpen(true)
        useChatStore.getState().setTtsSpeaking(true)
      }
    }

    if (isLast) {
      // 发送完成信号
      setTimeout(() => {
        isPlayingRef.current = false
        useChatStore.getState().setMouthOpen(false)
        useChatStore.getState().setTtsSpeaking(false)
        useChatStore.getState().setCharacterEmotion("happy")
      }, 500) // 延迟500ms确保最后一块音频播放完成
    }
  }, [initProcessor])

  const resetChunks = useCallback(() => {
    stop()
  }, [stop])

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