import { useCallback, useEffect, useRef } from "react"
import { useChatStore } from "@/store/chatStore"
import type { ServerMessage } from "@/types"

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
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
    addSummary,
    setSummarizing,
  } = useChatStore()

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        ws.send(JSON.stringify({ type: "connect" }))
      }

      ws.onmessage = (event) => {
        try {
          const data: ServerMessage = JSON.parse(event.data)

          switch (data.type) {
            case "connected":
              if (data.mode) setMode(data.mode)
              if (data.wake_word) setWakeWord(data.wake_word)
              if (data.word_count !== undefined) setWordCount(data.word_count)
              break

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

            case "summary_start":
              setSummarizing(true)
              break

            case "summary":
              if (data.content && data.timestamp) {
                addSummary({
                  id: crypto.randomUUID(),
                  content: data.content,
                  timestamp: data.timestamp,
                })
              }
              setSummarizing(false)
              break

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
                const msgs = useChatStore.getState().messages
                const lastMsg = msgs[msgs.length - 1]
                if (lastMsg?.role === "assistant" && !msg.is_final) {
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
        setConnected(false)
        setProcessing(false)
        setMouthOpen(false)
        reconnectTimer.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch {
      reconnectTimer.current = setTimeout(connect, 3000)
    }
  }, [wsUrl, setConnected, addMessage, updateLastAssistantMessage, setCharacterEmotion, setProcessing, setMouthOpen, setMode, setWakeWord, setWordCount, setLastRecordedText, addSummary, setSummarizing])

  const disconnect = useCallback(() => {
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
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [])

  return { connect, disconnect, sendMessage, switchMode, isConnected }
}