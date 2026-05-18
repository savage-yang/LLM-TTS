import { useState, useRef } from "react"
import { motion } from "framer-motion"
import { Send, Settings, Wifi, WifiOff } from "lucide-react"

interface InputBarProps {
  onSend: (content: string) => void
  onOpenSettings: () => void
  onConnect: () => void
  isConnected: boolean
  canConnect: boolean
}

export function InputBar({
  onSend,
  onOpenSettings,
  onConnect,
  isConnected,
  canConnect,
}: InputBarProps) {
  const [input, setInput] = useState("")

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || !isConnected) return
    onSend(trimmed)
    setInput("")
  }

  return (
    <motion.div
      initial={{ y: 30, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, delay: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <form onSubmit={handleSubmit} className="max-w-lg mx-auto px-6 pb-5">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={canConnect ? onConnect : undefined}
            className={`p-2 rounded-full transition-all duration-300 ${
              isConnected
                ? "text-emerald-400/60"
                : canConnect
                ? "text-white/15 hover:text-white/30"
                : "text-white/10"
            }`}
            title={isConnected ? "已连接" : "点击连接"}
          >
            {isConnected ? <Wifi size={15} /> : <WifiOff size={15} />}
          </button>

          <div className="flex-1 relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={isConnected ? "说点什么..." : "等待连接"}
              disabled={!isConnected}
              autoFocus
              className="w-full bg-white/[0.04] border border-white/[0.06] rounded-2xl px-4 py-2.5 
                text-sm text-white/80 placeholder-white/20 outline-none
                focus:border-white/12 focus:bg-white/[0.06]
                transition-all duration-300
                disabled:opacity-30 disabled:cursor-not-allowed"
            />
          </div>

          <button
            type="submit"
            disabled={!input.trim() || !isConnected}
            className="p-2.5 rounded-full text-white/30 
              hover:text-white/50 hover:bg-white/[0.04]
              disabled:opacity-20 disabled:cursor-not-allowed
              transition-all duration-200"
          >
            <Send size={15} />
          </button>

          <button
            type="button"
            onClick={onOpenSettings}
            className="p-2 rounded-full text-white/15 
              hover:text-white/35 hover:bg-white/[0.04]
              transition-all duration-200"
          >
            <Settings size={15} />
          </button>
        </div>
      </form>
    </motion.div>
  )
}