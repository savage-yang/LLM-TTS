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
            className="fixed inset-0 bg-black/45 backdrop-blur-sm z-40"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 16 }}
            transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 
              w-full max-w-xs z-50
              bg-[#1e2840]/97 backdrop-blur-xl border border-white/[0.12] 
              rounded-2xl p-7 shadow-2xl"
          >
            <div className="flex items-center justify-between mb-7">
              <h2 className="text-lg font-semibold text-white/70 tracking-wide">
                连接设置
              </h2>
              <button
                onClick={onClose}
                className="p-2 rounded-lg text-white/40 hover:text-white/70 hover:bg-white/[0.07] transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="ws://localhost:8765"
              className="w-full bg-white/[0.06] border border-white/[0.13] rounded-xl px-4 py-3.5 
                text-[16px] text-white/90 placeholder-white/28 outline-none
                focus:border-white/20 focus:bg-white/[0.08]
                transition-all duration-300 mb-6"
            />

            <button
              onClick={handleSave}
              className="w-full py-3.5 rounded-xl bg-white/[0.09] border border-white/[0.13] text-white/85 
                hover:bg-white/[0.13] hover:text-white/95 text-[16px] font-semibold
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