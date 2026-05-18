import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { X } from "lucide-react"
import { useChatStore } from "@/store/chatStore"

interface SettingsPanelProps {
  open: boolean
  onClose: () => void
}

export function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const { wsUrl, setWsUrl } = useChatStore()
  const [url, setUrl] = useState(wsUrl)

  const handleSave = () => {
    const trimmed = url.trim()
    if (trimmed) setWsUrl(trimmed)
    onClose()
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 16 }}
            transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 
              w-full max-w-xs z-50
              bg-[#0d1220]/90 backdrop-blur-xl border border-white/[0.06] 
              rounded-2xl p-5 shadow-2xl"
          >
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-[13px] font-medium text-white/60 tracking-wide">
                连接设置
              </h2>
              <button
                onClick={onClose}
                className="p-1 rounded-lg text-white/30 hover:text-white/50 hover:bg-white/[0.05] transition-colors"
              >
                <X size={14} />
              </button>
            </div>

            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="ws://localhost:8765"
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-3.5 py-2.5 
                text-[13px] text-white/80 placeholder-white/20 outline-none
                focus:border-white/15 focus:bg-white/[0.06]
                transition-all duration-300 mb-4"
            />

            <button
              onClick={handleSave}
              className="w-full py-2.5 rounded-xl bg-white/[0.07] border border-white/[0.08] text-white/70 
                hover:bg-white/[0.10] hover:text-white/85 text-[13px]
                transition-all duration-200"
            >
              保存
            </button>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}