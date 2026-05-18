import { motion, AnimatePresence } from "framer-motion"
import { useChatStore } from "@/store/chatStore"

export function ModeIndicator() {
  const { mode, wakeWord, wordCount } = useChatStore()

  return (
    <AnimatePresence mode="wait">
      {mode === "listening" ? (
        <motion.div
          key="listening"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          className="flex items-center gap-1.5"
        >
          <motion.div
            className="flex gap-0.5"
            animate={{ opacity: [0.4, 0.9, 0.4] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <div className="w-0.5 h-2.5 rounded-full bg-blue-400/50" />
            <div className="w-0.5 h-3.5 rounded-full bg-blue-400/50" />
            <div className="w-0.5 h-2.5 rounded-full bg-blue-400/50" />
          </motion.div>
          <span className="text-[10px] text-blue-400/40 tracking-wider">
            监听中
          </span>
          {wordCount > 0 && (
            <span className="text-[9px] text-white/15">
              ({wordCount}字)
            </span>
          )}
        </motion.div>
      ) : (
        <motion.div
          key="dialogue"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          className="flex items-center gap-1.5"
        >
          <motion.div
            className="w-1.5 h-1.5 rounded-full bg-amber-400/50"
            animate={{ scale: [1, 1.3, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          />
          <span className="text-[10px] text-amber-400/40 tracking-wider">
            对话中
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  )
}