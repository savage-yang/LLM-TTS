import { motion, AnimatePresence } from "framer-motion"
import { useChatStore } from "@/store/chatStore"

function LoadingCircle() {
  return (
    <div className="flex items-center gap-2 px-5 py-3.5">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          className="w-2.5 h-2.5 rounded-full bg-gray-400"
          animate={{
            y: [0, -5, 0],
            opacity: [0.3, 0.7, 0.3],
          }}
          transition={{
            duration: 1,
            repeat: Infinity,
            delay: i * 0.18,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  )
}

export function SpeechBubble() {
  const llmBubbleText = useChatStore((s) => s.llmBubbleText)
  const isInterrupted = useChatStore((s) => s.isInterrupted)

  const showBubble = llmBubbleText || isInterrupted

  return (
    <AnimatePresence>
      {showBubble && (
        <motion.div
          initial={{ opacity: 0, scale: 0.8, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.8, y: 10 }}
          transition={{ type: "spring", damping: 20, stiffness: 300 }}
          className="absolute top-0 left-full ml-3 z-20 min-w-[320px] max-w-[400px]"
        >
          <div className="relative">
            <div className="bg-white/95 text-gray-800 rounded-2xl shadow-lg border border-gray-200/50">
              {isInterrupted ? (
                <LoadingCircle />
              ) : (
                <p className="text-sm leading-relaxed font-medium break-words px-5 py-3.5">
                  {llmBubbleText}
                </p>
              )}
            </div>
            {/* 气泡尾巴指向左侧（机器人方向） */}
            <div className="absolute top-1/2 -left-2 w-0 h-0 -translate-y-1/2 border-t-[8px] border-t-transparent border-b-[8px] border-b-transparent border-r-[10px] border-r-white/95" />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}