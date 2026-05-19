import { motion, AnimatePresence } from "framer-motion"
import { useChatStore } from "@/store/chatStore"

export function SpeechBubble() {
  const llmBubbleText = useChatStore((s) => s.llmBubbleText)

  return (
    <AnimatePresence>
      {llmBubbleText && (
        <motion.div
          initial={{ opacity: 0, scale: 0.8, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.8, y: 10 }}
          transition={{ type: "spring", damping: 20, stiffness: 300 }}
          className="absolute top-20 right-6 z-20 max-w-xs"
        >
          {/* 漫画风格对话气泡 */}
          <div className="relative">
            {/* 气泡主体 */}
            <div className="bg-white/95 text-gray-800 px-5 py-3.5 rounded-2xl shadow-lg border border-gray-200/50">
              <p className="text-sm leading-relaxed font-medium break-words">
                {llmBubbleText}
              </p>
            </div>
            {/* 气泡尾巴 - 指向左下方（机器人方向） */}
            <div className="absolute -bottom-2.5 left-6 w-0 h-0 border-l-[10px] border-l-transparent border-r-[10px] border-r-transparent border-t-[10px] border-t-white/95" />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
