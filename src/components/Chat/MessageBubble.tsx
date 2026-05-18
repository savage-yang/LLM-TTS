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
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}
    >
      <div
        className={`max-w-[72%] px-4 py-2.5 rounded-2xl ${
          isUser
            ? "bg-white/[0.07] text-white/85"
            : "bg-white/[0.03] border border-white/[0.05] text-white/70"
        } ${isUser ? "rounded-br-md" : "rounded-bl-md"}`}
      >
        <p className="text-[13px] leading-relaxed whitespace-pre-wrap">
          {message.content}
        </p>
      </div>
    </motion.div>
  )
}