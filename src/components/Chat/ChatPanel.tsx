import { useRef, useEffect } from "react"
import { AnimatePresence } from "framer-motion"
import { useChatStore } from "@/store/chatStore"
import { MessageBubble } from "./MessageBubble"
import { TypingIndicator } from "./TypingIndicator"

export function ChatPanel() {
  const { messages, isProcessing } = useChatStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isProcessing])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3">
      <div className="max-w-lg mx-auto">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center pt-8 pb-4">
            <p className="text-white/15 text-sm">开始对话</p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <AnimatePresence>
          {isProcessing && <TypingIndicator />}
        </AnimatePresence>
        <div ref={bottomRef} className="h-1" />
      </div>
    </div>
  )
}