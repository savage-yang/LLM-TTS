import { useState, useEffect, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { AiCharacter } from "@/components/AiCharacter/AiCharacter"
import { ChatPanel } from "@/components/Chat/ChatPanel"
import { ModeIndicator } from "@/components/ModeIndicator/ModeIndicator"
import { SettingsPanel } from "@/components/Settings/SettingsPanel"
import { useWebSocket } from "@/hooks/useWebSocket"
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition"
import { useAudioPlayer } from "@/hooks/useAudioPlayer"
import { useChatStore } from "@/store/chatStore"
import { Wifi, WifiOff, Settings, MessageSquare, X, Mic } from "lucide-react"

function App() {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [micEnabled, setMicEnabled] = useState(false)

  const { isSupported: audioSupported, appendChunk: onTtsChunk, resetChunks: onTtsStart, stop: stopTts } = useAudioPlayer()
  const { connect, disconnect, sendMessage, switchMode, isConnected, wsRef } = useWebSocket({
    onTtsChunk,
    onTtsStart,
    onTtsEnd: () => {},
  })

  const { isSupported: micSupported, isRecording: isMicListening, startRecording, stopRecording } = useSpeechRecognition({
    wsRef,
    isConnected,
  })

  const mode = useChatStore((s) => s.mode)
  const isProcessing = useChatStore((s) => s.isProcessing)
  const isSummarizing = useChatStore((s) => s.isSummarizing)
  const isTtsSpeaking = useChatStore((s) => s.isTtsSpeaking)

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [])

  const handleActivateMic = useCallback(async () => {
    if (!micSupported) return
    await startRecording()
    setMicEnabled(true)
  }, [micSupported, startRecording])

  useEffect(() => {
    if (!isConnected && micEnabled) {
      stopRecording()
      setMicEnabled(false)
    }
  }, [isConnected])

  const handleSend = (content: string) => {
    if (isTtsSpeaking) {
      stopTts()
    }
    sendMessage(content)
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-[#1a2234] font-['Nunito',sans-serif] overflow-hidden relative">
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] bg-blue-400/[0.06] rounded-full blur-[180px]" />
        <div className="absolute top-1/4 left-1/3 w-[300px] h-[300px] bg-indigo-400/[0.04] rounded-full blur-[120px]" />
      </div>

      {/* Center area */}
      <div className="flex-1 flex flex-col items-center justify-center relative z-10 px-6">
        {/* Top-right status */}
        <div className="absolute top-5 right-6 flex items-center gap-3">
          <div className="flex items-center gap-2.5 px-4 py-2 rounded-full bg-white/[0.06] border border-white/[0.12] shadow-sm">
            <div
              className={`w-2.5 h-2.5 rounded-full transition-colors duration-300 ${
                isConnected ? "bg-emerald-400" : "bg-white/35"
              }`}
            />
            <span className="text-sm text-white/70 tracking-wide font-medium">
              {isConnected ? "已连接" : "未连接"}
            </span>
          </div>
          {audioSupported && isTtsSpeaking && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-cyan-400/[0.08] border border-cyan-400/[0.18]"
            >
              <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
              <span className="text-sm text-cyan-300/80 font-medium">Qwen TTS</span>
            </motion.div>
          )}
        </div>

        {/* Character */}
        <AiCharacter />

        {/* Mode indicator */}
        <div className="mt-3 mb-8">
          <ModeIndicator />
        </div>

        {/* Mic button / status + mode toggle */}
        <div className="flex items-center gap-4 mt-3">
          {!micEnabled ? (
            <motion.button
              onClick={handleActivateMic}
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              className="flex items-center gap-3 px-7 py-3.5 rounded-full 
                bg-gradient-to-r from-blue-500/25 to-cyan-500/20 
                border-2 border-blue-400/40 text-blue-100 text-lg font-semibold
                shadow-xl shadow-blue-500/15 hover:shadow-blue-500/30 hover:border-blue-400/55
                transition-all duration-300 cursor-pointer"
            >
              <Mic size={22} />
              启用麦克风
            </motion.button>
          ) : (
            <div className={`flex items-center gap-3 px-4 py-2.5 rounded-full border-2 text-base font-semibold transition-all duration-300 ${
              isMicListening
                ? "border-emerald-400/35 text-emerald-300/90 bg-emerald-400/[0.10]"
                : "border-white/[0.14] text-white/45 bg-white/[0.04]"
            }`}>
              <motion.div
                className="w-3 h-3 rounded-full"
                animate={
                  isMicListening
                    ? { scale: [1, 1.5, 1], opacity: [0.4, 1, 0.4] }
                    : { scale: [1] }
                }
                transition={{
                  duration: isMicListening ? 1.2 : 0,
                  repeat: isMicListening ? Infinity : 0,
                  ease: "easeInOut",
                }}
                style={{
                  backgroundColor: isMicListening
                    ? "rgba(52, 211, 153, 0.9)"
                    : "rgba(255,255,255,0.20)",
                }}
              />
              <span>{isMicListening ? "🎤 正在聆听" : "麦克风"}</span>
            </div>
          )}

          <button
            onClick={() => switchMode(mode === "listening" ? "dialogue" : "listening")}
            disabled={!isConnected}
            className={`px-5 py-2.5 rounded-full border-2 text-base font-semibold transition-all duration-300
              disabled:opacity-25 disabled:cursor-not-allowed
              ${
                mode === "listening"
                  ? "border-blue-400/28 text-blue-300/80 hover:bg-blue-400/[0.07]"
                  : "border-amber-400/28 text-amber-300/80 hover:bg-amber-400/[0.07]"
              }`}
          >
            {mode === "listening" ? "🔊 监听模式" : "💬 对话模式"}
          </button>
        </div>

        {/* Hint - bright white text */}
        <p className="mt-6 text-lg text-white/50 max-w-lg text-center leading-relaxed font-medium">
          {!micEnabled
            ? "👆 点击上方「启用麦克风」按钮开始语音交互（ASR+VAD+LLM+TTS）"
            : mode === "listening"
              ? isMicListening
                ? "正在持续监听，说出「小爱」即可唤醒我进入对话模式"
                : "等待麦克风权限..."
              : isProcessing
                ? "正在思考回复..."
                : "对话模式中，可以直接说话或点击右下角查看消息记录"}
        </p>
      </div>

      {/* Bottom bar */}
      <div className="relative z-10 pb-8 pt-3">
        <div className="max-w-lg mx-auto flex items-center justify-between px-10">
          <button
            onClick={() => !isConnected && connect()}
            className={`p-3 rounded-full transition-all duration-300 ${
              isConnected
                ? "text-emerald-400/60"
                : "text-white/30 hover:text-white/55 hover:bg-white/[0.06]"
            }`}
            title={isConnected ? "已连接" : "重新连接"}
          >
            {isConnected ? <Wifi size={22} /> : <WifiOff size={22} />}
          </button>

          <button
            onClick={() => setChatOpen(!chatOpen)}
            className={`p-3 rounded-full transition-all duration-300 ${
              chatOpen
                ? "text-blue-300/90 bg-blue-400/[0.12]"
                : "text-white/32 hover:text-white/60 hover:bg-white/[0.06]"
            }`}
            title="查看对话记录"
          >
            <MessageSquare size={22} />
          </button>

          <button
            onClick={() => setSettingsOpen(true)}
            className="p-3 rounded-full text-white/30 
              hover:text-white/55 hover:bg-white/[0.06]
              transition-all duration-200"
            title="设置"
          >
            <Settings size={22} />
          </button>
        </div>
      </div>

      {/* Chat overlay panel */}
      <AnimatePresence>
        {chatOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40"
              onClick={() => setChatOpen(false)}
            />
            <motion.div
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", damping: 28, stiffness: 300 }}
              className="fixed top-0 right-0 bottom-0 w-full max-w-md z-50 
                bg-[#1c2538]/97 backdrop-blur-xl border-l border-white/[0.10] 
                shadow-2xl flex flex-col overflow-hidden"
            >
              <div className="flex items-center justify-between px-6 py-5 border-b border-white/[0.09]">
                <h3 className="text-lg font-semibold text-white/75">对话记录</h3>
                <button
                  onClick={() => setChatOpen(false)}
                  className="p-2 rounded-lg text-white/40 hover:text-white/65 hover:bg-white/[0.07] transition-colors"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="flex-1 min-h-0">
                <ChatPanel />
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Settings */}
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  )
}

export default App