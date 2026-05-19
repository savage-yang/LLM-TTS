import { useCallback, useEffect, useRef } from "react"
import { useChatStore } from "@/store/chatStore"
import type { ServerMessage } from "@/types"

interface UseWebSocketOptions {
  onTtsChunk?: (data: string, isLast: boolean) => void
  onTtsStart?: () => void
  onTtsEnd?: () => void
}

export function useWebSocket(options?: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const connectIdRef = useRef(0)
  const hasReceivedAudioRef = useRef(false)
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
  } = useChatStore()

  const connectRef = useRef<() => void>(() => {})
  connectRef.current = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) return

    // 先关闭旧连接
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
            case "connected":
            case "status":
              if (data.mode) setMode(data.mode)
              if (data.wake_word) setWakeWord(data.wake_word)
              if (data.word_count !== undefined) setWordCount(data.word_count)
              break

            case "mode_change":
              if (data.mode) {
                setMode(data.mode)
                if (data.mode === "listening") {
                  setCharacterEmotion("idle")
                  setMouthOpen(false)
                } else if (data.mode === "dialogue") {
                  setCharacterEmotion(data.reason === "wake_word" ? "happy" : "idle")
                }
              }
              break

            case "listening_recorded":
              if (data.word_count !== undefined) setWordCount(data.word_count)
              if (data.text) setLastRecordedText(data.text)
              if (data.summarizing) setSummarizing(true)
              break

            case "tts_start":
              hasReceivedAudioRef.current = false
              setTtsSpeaking(true)
              setCharacterEmotion("speaking")
              optionsRef.current?.onTtsStart?.()
              break

            case "tts_audio_chunk":
              if (data.data && data.is_last !== undefined) {
                hasReceivedAudioRef.current = true
                optionsRef.current?.onTtsChunk?.(data.data, data.is_last)
              }
              break

            case "tts_end":
              if (!hasReceivedAudioRef.current) {
                setTtsSpeaking(false)
                setMouthOpen(false)
                setCharacterEmotion("happy")
              }
              // TTS 播放完毕，清除对话气泡
              setTimeout(() => {
                useChatStore.getState().setLlmBubbleText("")
              }, 3000)
              optionsRef.current?.onTtsEnd?.()
              break

            case "tts_error":
              setTtsSpeaking(false)
              setMouthOpen(false)
              setCharacterEmotion("idle")
              console.error("TTS error:", data.error)
              break

            case "llm_token": {
              // LLM 流式 token：实时显示生成中的文本
              if (data.content) {
                setProcessing(true)
                setMouthOpen(true)
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

              if (msg.is_final) {
                setProcessing(false)
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
                setMouthOpen(true)
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
        // 不要在此处调用 ws.close()，让 onclose 统一处理
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

  return { connect, disconnect, sendMessage, switchMode, isConnected, wsRef }
}