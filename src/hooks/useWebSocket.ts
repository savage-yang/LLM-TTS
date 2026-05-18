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

          if (data.type === "message") {
            if (data.is_final) {
              setProcessing(false)
              setMouthOpen(false)
            } else {
              setProcessing(true)
              setMouthOpen(true)
              if (data.emotion) {
                setCharacterEmotion(data.emotion)
              }
            }

            const msgs = useChatStore.getState().messages
            const lastMsg = msgs[msgs.length - 1]
            if (lastMsg?.role === "assistant" && !data.is_final) {
              updateLastAssistantMessage(lastMsg.content + data.content)
            } else if (data.is_final) {
              addMessage({
                id: crypto.randomUUID(),
                role: "assistant",
                content: data.content,
                timestamp: Date.now(),
                emotion: data.emotion,
              })
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
  }, [wsUrl, setConnected, addMessage, updateLastAssistantMessage, setCharacterEmotion, setProcessing, setMouthOpen])

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

      addMessage({
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: Date.now(),
      })

      setCharacterEmotion("thinking")
      setProcessing(true)

      wsRef.current.send(
        JSON.stringify({ type: "message", content })
      )
    },
    [addMessage, setCharacterEmotion, setProcessing]
  )

  useEffect(() => {
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [])

  return { connect, disconnect, sendMessage, isConnected }
}