import { motion, AnimatePresence } from "framer-motion"
import { useChatStore } from "@/store/chatStore"

export function ModeIndicator() {
  const { mode, wordCount } = useChatStore()

  return (
    <AnimatePresence mode="wait">
      {mode === "listening" ? (
        <motion.div
          key="listening"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          className="flex items-center gap-2.5"
        >
          <motion.div
            className="flex gap-1"
            animate={{ opacity: [0.5, 0.95, 0.5] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <div className="w-1.5 h-4 rounded-full bg-blue-400/65" />
            <div className="w-1.5 h-6.5 rounded-full bg-blue-400/65" />
            <div className="w-1.5 h-4 rounded-full bg-blue-400/65" />
          </motion.div>
          <span className="text-lg text-blue-300/80 tracking-wider font-semibold">
            监听中
          </span>
          {wordCount > 0 && (
            <span className="text-sm text-white/35 font-medium">
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
          className="flex items-center gap-2.5"
        >
          <motion.div
            className="w-2.5 h-2.5 rounded-full bg-amber-400/65"
            animate={{ scale: [1, 1.4, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          />
          <span className="text-lg text-amber-300/80 tracking-wider font-semibold">
            对话中
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  )
}