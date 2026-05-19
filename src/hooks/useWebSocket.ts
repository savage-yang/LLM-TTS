import { useCallback, useEffect, useRef } from "react"
import { useChatStore } from "@/store/chatStore"
import type { ServerMessage } from "@/types"

interface UseWebSocketOptions {
  onTtsChunk?: (data: string, isLast: boolean) => void
  onTtsStart?: () => void
  onTtsEnd?: (interrupted?: boolean) => void
}

export function useWebSocket(options?: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const connectIdRef = useRef(0)
  const hasReceivedAudioRef = useRef(false)
  const ttsEndedRef = useRef(false)
  const optionsRef = useRef(options)
  optionsRef.current = options
  const {
    wsUrl,
    isConnected,
    setConnected,
    addMessage,
    updateLastAssistantMessage,
    setCharacterEmotion,
    setProcessing,
    setMouthOpen,
    setMode,
    setWakeWord,
    setWordCount,
    setLastRecordedText,
    setSummarizing,
    setTtsSpeaking,
    setIsInterrupted,
    setDialogueIdleTimeout,
    setLastDialogueTime,
  } = useChatStore()

  const connectRef = useRef<() => void>(() => {})
  connectRef.current = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) return

    if (wsRef.current) {
      try { wsRef.current.close() } catch {}
      wsRef.current = null
    }

    const myId = ++connectIdRef.current

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (connectIdRef.current !== myId) return
        setConnected(true)
        ws.send(JSON.stringify({ type: "connect" }))
      }

      ws.onmessage = (event) => {
        if (connectIdRef.current !== myId) return
        try {
          const data: ServerMessage = JSON.parse(event.data)

          switch (data.type) {
            case "tts_start":
              hasReceivedAudioRef.current = false
              ttsEndedRef.current = false
              setIsInterrupted(false)
              setTtsSpeaking(true)
              setCharacterEmotion("speaking")
              optionsRef.current?.onTtsStart?.()
              break

            case "connected":
            case "status":
              if (data.mode) setMode(data.mode)
              if (data.wake_word) setWakeWord(data.wake_word)
              if (data.word_count !== undefined) setWordCount(data.word_count)
              if (data.dialogue_idle_timeout) setDialogueIdleTimeout(data.dialogue_idle_timeout)
              if (data.mode === "dialogue") setLastDialogueTime(Date.now())
              break

            case "mode_change":
              if (data.mode) {
                setMode(data.mode)
                if (data.mode === "listening") {
                  setCharacterEmotion("idle")
                  setMouthOpen(false)
                } else if (data.mode === "dialogue") {
                  setCharacterEmotion(data.reason === "wake_word" ? "happy" : "idle")
                  setMouthOpen(false)
                  setLastDialogueTime(Date.now())
                }
              }
              break

            case "listening_recorded":
              if (data.word_count !== undefined) setWordCount(data.word_count)
              if (data.text) setLastRecordedText(data.text)
              if (data.summarizing) setSummarizing(true)
              break

            case "buffer_audio":
              if (data.data) {
                try {
                  const binaryStr = atob(data.data)
                  const bytes = new Uint8Array(binaryStr.length)
                  for (let i = 0; i < binaryStr.length; i++) {
                    bytes[i] = binaryStr.charCodeAt(i)
                  }
                  const blob = new Blob([bytes], { type: "audio/wav" })
                  const url = URL.createObjectURL(blob)
                  const audio = new Audio(url)
                  audio.play().catch(() => {})
                  setTimeout(() => URL.revokeObjectURL(url), 5000)
                } catch {}
              }
              break

            case "tts_audio_chunk":
              if (data.data && data.is_last !== undefined) {
                hasReceivedAudioRef.current = true
                optionsRef.current?.onTtsChunk?.(data.data, data.is_last)
              }
              break

            case "tts_end":
              ttsEndedRef.current = true
              if (data.interrupted) {
                setTtsSpeaking(false)
                setMouthOpen(false)
                setCharacterEmotion("idle")
                setTimeout(() => {
                  useChatStore.getState().setIsInterrupted(false)
                }, 1500)
              } else {
                // 无论是否收到音频，都重置状态
                setTtsSpeaking(false)
                setMouthOpen(false)
                setCharacterEmotion("happy")
                setTimeout(() => {
                  useChatStore.getState().setLlmBubbleText("")
                  useChatStore.getState().setIsInterrupted(false)
                }, 8000)
              }
              optionsRef.current?.onTtsEnd?.(data.interrupted)
              break

            case "tts_error":
              setTtsSpeaking(false)
              setMouthOpen(false)
              setCharacterEmotion("idle")
              console.error("TTS error:", data.error)
              break

            case "llm_token": {
              if (data.content) {
                setIsInterrupted(false)
                setProcessing(true)
                if (!ttsEndedRef.current) setMouthOpen(true)
                const msgs = useChatStore.getState().messages
                const lastMsg = msgs[msgs.length - 1]
                if (lastMsg?.role === "assistant") {
                  const newContent = lastMsg.content + data.content
                  updateLastAssistantMessage(newContent)
                  useChatStore.getState().setLlmBubbleText(newContent)
                } else {
                  addMessage({
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: data.content,
                    timestamp: Date.now(),
                  })
                  useChatStore.getState().setLlmBubbleText(data.content)
                }
              }
              break
            }

            case "message": {
              const msg = data as ServerMessage
              if (msg.role === "user") {
                ttsEndedRef.current = false
                addMessage({
                  id: crypto.randomUUID(),
                  role: "user",
                  content: msg.content,
                  timestamp: Date.now(),
                })
                setCharacterEmotion("thinking")
                setProcessing(true)
                break
              }

              setIsInterrupted(false)
              if (msg.is_final) {
                setProcessing(false)
                setLastDialogueTime(Date.now())
                setMouthOpen(false)
                if (msg.emotion) {
                  setCharacterEmotion(msg.emotion)
                }
                const msgs = useChatStore.getState().messages
                const lastMsg = msgs[msgs.length - 1]
                if (lastMsg?.role === "assistant") {
                  updateLastAssistantMessage(msg.content)
                } else {
                  addMessage({
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: msg.content,
                    timestamp: Date.now(),
                    emotion: msg.emotion as any,
                  })
                }
              } else {
                setProcessing(true)
                if (!ttsEndedRef.current) setMouthOpen(true)
                if (msg.emotion) {
                  setCharacterEmotion(msg.emotion)
                }
                const msgs = useChatStore.getState().messages
                const lastMsg = msgs[msgs.length - 1]
                if (lastMsg?.role === "assistant") {
                  updateLastAssistantMessage(lastMsg.content + msg.content)
                } else {
                  addMessage({
                    id: crypto.randomUUID(),
                    role: "assistant",
                    content: msg.content,
                    timestamp: Date.now(),
                  })
                }
              }
              break
            }
          }
        } catch {
          console.warn("Failed to parse WS message")
        }
      }

      ws.onclose = () => {
        if (connectIdRef.current !== myId) return
        setConnected(false)
        setProcessing(false)
        setMouthOpen(false)
        reconnectTimer.current = setTimeout(() => connectRef.current(), 3000)
      }

      ws.onerror = () => {
      }
    } catch {
      reconnectTimer.current = setTimeout(() => connectRef.current(), 3000)
    }
  }

  const connect = useCallback(() => {
    connectRef.current()
  }, [])

  const disconnect = useCallback(() => {
    connectIdRef.current++
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
    }
    wsRef.current?.close()
    wsRef.current = null
    setConnected(false)
  }, [setConnected])

  const sendMessage = useCallback(
    (content: string) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
      wsRef.current.send(
        JSON.stringify({ type: "message", content })
      )
    },
    []
  )

  const switchMode = useCallback(
    (mode: "listening" | "dialogue") => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
      wsRef.current.send(
        JSON.stringify({ type: "switch_mode", mode })
      )
    },
    []
  )

  const sendInterrupt = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({ type: "interrupt" }))
  }, [])

  useEffect(() => {
    return () => {
      connectIdRef.current++
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      const ws = wsRef.current
      wsRef.current = null
      if (ws) {
        try { ws.close() } catch {}
      }
    }
  }, [])

  return { connect, disconnect, sendMessage, switchMode, sendInterrupt, isConnected, wsRef }
}