import { useState } from "react"
import { motion } from "framer-motion"
import { Send, Settings, Wifi, WifiOff } from "lucide-react"
import { useChatStore } from "@/store/chatStore"

interface InputBarProps {
  onSend: (content: string) => void
  onSwitchMode: (mode: "listening" | "dialogue") => void
  onOpenSettings: () => void
  onConnect: () => void
  isConnected: boolean
  canConnect: boolean
  currentMode: "listening" | "dialogue"
  isProcessing: boolean
  isSummarizing: boolean
}

export function InputBar({
  onSend,
  onSwitchMode,
  onOpenSettings,
  onConnect,
  isConnected,
  canConnect,
  currentMode,
  isProcessing,
  isSummarizing,
}: InputBarProps) {
  const [input, setInput] = useState("")
  const { mode: storeMode } = useChatStore()
  const mode = storeMode

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || !isConnected) return
    onSend(trimmed)
    setInput("")
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const handleModeToggle = () => {
    if (!isConnected) return
    if (mode === "listening") {
      onSwitchMode("dialogue")
    } else {
      onSwitchMode("listening")
    }
  }

  const isDisabled = !isConnected

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

          <button
            type="button"
            onClick={handleModeToggle}
            disabled={isDisabled}
            className={`p-1.5 px-3 rounded-full border text-[11px] transition-all duration-300
              disabled:opacity-20 disabled:cursor-not-allowed
              ${
                mode === "listening"
                  ? "border-blue-400/15 text-blue-400/50 hover:bg-blue-400/[0.04]"
                  : "border-amber-400/15 text-amber-400/50 hover:bg-amber-400/[0.04]"
              }`}
            title={mode === "listening" ? "点击进入对话模式" : "点击切换监听模式"}
          >
            {mode === "listening" ? "🔊 监听" : "💬 对话"}
          </button>

          <div className="flex-1 relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isSummarizing
                  ? "AI 正在总结监听内容..."
                  : isProcessing
                  ? "AI 正在思考..."
                  : mode === "listening"
                  ? "说「小爱」唤醒我，或直接打字..."
                  : isConnected
                  ? "说点什么..."
                  : "等待连接"
              }
              disabled={isDisabled}
              autoFocus
              className={`w-full bg-white/[0.04] border rounded-2xl px-4 py-2.5 
                text-sm text-white/80 placeholder-white/20 outline-none
                focus:border-white/12 focus:bg-white/[0.06]
                transition-all duration-300
                disabled:opacity-30 disabled:cursor-not-allowed
                ${mode === "listening" ? "border-blue-400/[0.08]" : "border-white/[0.06]"}`}
            />
          </div>

          <button
            type="submit"
            disabled={!input.trim() || isDisabled}
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