import { motion } from "framer-motion"
import type { Message } from "@/types"

interface MessageBubbleProps {
  message: Message
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user"

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-5`}
    >
      <div
        className={`max-w-[85%] px-5 py-3.5 rounded-2xl ${
          isUser
            ? "bg-blue-500/18 border border-blue-400/22 text-white/95"
            : "bg-white/[0.06] border border-white/[0.10] text-white/80"
        } ${isUser ? "rounded-br-md" : "rounded-bl-md"}`}
      >
        <p className="text-[17px] leading-relaxed whitespace-pre-wrap">
          {message.content}
        </p>
      </div>
    </motion.div>
  )
}