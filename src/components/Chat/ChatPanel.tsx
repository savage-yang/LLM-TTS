import { useRef, useEffect } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { useChatStore } from "@/store/chatStore"
import { MessageBubble } from "./MessageBubble"
import { TypingIndicator } from "./TypingIndicator"

function ChatEmpty() {
  return (
    <div className="flex flex-col items-center justify-center pt-12 pb-8">
      <p className="text-lg text-white/30 font-medium">开始对话</p>
    </div>
  )
}

export function ChatPanel() {
  const { messages, isProcessing } = useChatStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isProcessing])

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5">
      <div className="max-w-lg mx-auto">
        {messages.length === 0 && !isProcessing && <ChatEmpty />}
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