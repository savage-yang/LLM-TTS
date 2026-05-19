import { useState, useEffect, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { AiCharacter } from "@/components/AiCharacter/AiCharacter"
import { ChatPanel } from "@/components/Chat/ChatPanel"
import { ModeIndicator } from "@/components/ModeIndicator/ModeIndicator"
import { SettingsPanel } from "@/components/Settings/SettingsPanel"
import { ListeningSummaryPanel } from "@/components/ListeningSummary/ListeningSummaryPanel"
import { useWebSocket } from "@/hooks/useWebSocket"
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition"
import { useAudioPlayer } from "@/hooks/useAudioPlayer"
import { useChatStore } from "@/store/chatStore"
import { Wifi, WifiOff, Settings, MessageSquare, ScrollText, X, Mic } from "lucide-react"

function App() {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [micEnabled, setMicEnabled] = useState(false)
  const [micError, setMicError] = useState<string | null>(null)

  const { isSupported: audioSupported, appendChunk: onTtsChunk, resetChunks: onTtsStart, clearBuffer } = useAudioPlayer()
  const { connect, disconnect, sendMessage, switchMode, sendInterrupt, isConnected, wsRef } = useWebSocket({
    onTtsChunk,
    onTtsStart,
    onTtsEnd: (interrupted) => { if (interrupted) clearBuffer() },
  })

  const { isSupported: micSupported, isRecording: isMicListening, startRecording, stopRecording } = useSpeechRecognition({
    wsRef,
    isConnected,
  })

  const mode = useChatStore((s) => s.mode)
  const isProcessing = useChatStore((s) => s.isProcessing)
  const isTtsSpeaking = useChatStore((s) => s.isTtsSpeaking)
  const dialogueIdleTimeout = useChatStore((s) => s.dialogueIdleTimeout)
  const lastDialogueTime = useChatStore((s) => s.lastDialogueTime)
  const [dialogueCountdown, setDialogueCountdown] = useState(dialogueIdleTimeout)

  useEffect(() => {
    if (mode !== "dialogue") {
      setDialogueCountdown(dialogueIdleTimeout)
      return
    }
    const updateCountdown = () => {
      const elapsed = Math.floor((Date.now() - lastDialogueTime) / 1000)
      const remaining = Math.max(0, dialogueIdleTimeout - elapsed)
      setDialogueCountdown(remaining)
    }
    updateCountdown()
    const timer = setInterval(updateCountdown, 1000)
    return () => clearInterval(timer)
  }, [mode, dialogueIdleTimeout, lastDialogueTime])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [])

  const handleActivateMic = useCallback(async () => {
    if (!micSupported) return
    setMicError(null)
    const result = await startRecording()
    if (result.ok === true) {
      setMicEnabled(true)
      playPrologue()
    } else {
      setMicError(result.reason)
    }
  }, [micSupported, startRecording])

  const playPrologue = useCallback(async () => {
    try {
      const res = await fetch(`http://${window.location.hostname}:8765/api/prologue`)
      if (!res.ok) return
      const blob = await res.blob()
      const arrayBuffer = await blob.arrayBuffer()
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
      if (ctx.state === "suspended") ctx.resume()
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer)
      const source = ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(ctx.destination)
      source.start(0)
    } catch {}
  }, [])

  useEffect(() => {
    if (!isConnected && micEnabled) {
      stopRecording()
      setMicEnabled(false)
    }
  }, [isConnected])

  return (
    <div className="h-screen w-screen flex flex-col bg-[#1a2234] font-['Nunito',sans-serif] overflow-hidden relative">
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] bg-blue-400/[0.06] rounded-full blur-[180px]" />
        <div className="absolute top-1/4 left-1/3 w-[300px] h-[300px] bg-indigo-400/[0.04] rounded-full blur-[120px]" />
      </div>

      {/* ===== Top bar: status + mic + mode ===== */}
      <div className="relative z-10 pt-2 pb-0">
        <div className="max-w-lg mx-auto flex items-center justify-center gap-3 px-6">
          {/* Connection status */}
          <div className="flex items-center gap-2.5 px-4 py-2 rounded-full bg-white/[0.06] border border-white/[0.12]">
            <div
              className={`w-2.5 h-2.5 rounded-full transition-colors duration-300 ${
                isConnected ? "bg-emerald-400" : "bg-white/35"
              }`}
            />
            <span className="text-sm text-white/70 tracking-wide font-medium">
              {isConnected ? "已连接" : "未连接"}
            </span>
            {audioSupported && isTtsSpeaking && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="ml-2 flex items-center gap-1.5"
              >
                <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                <span className="text-xs text-cyan-300/80 font-medium">TTS</span>
              </motion.div>
            )}
          </div>

          {/* Mic + Mode */}
          <div className="flex items-center gap-3">
            {!micEnabled ? (
              <motion.button
                onClick={handleActivateMic}
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.96 }}
                className="flex items-center gap-2 px-5 py-2 rounded-full
                  bg-gradient-to-r from-blue-500/25 to-cyan-500/20
                  border-2 border-blue-400/40 text-blue-100 text-sm font-semibold
                  shadow-lg shadow-blue-500/15 hover:shadow-blue-500/30 hover:border-blue-400/55
                  transition-all duration-300 cursor-pointer"
              >
                <Mic size={18} />
                启用麦克风
              </motion.button>
            ) : (
              <div className={`flex items-center gap-2 px-4 py-2 rounded-full border-2 text-sm font-semibold transition-all duration-300 ${
                isMicListening
                  ? "border-emerald-400/35 text-emerald-300/90 bg-emerald-400/[0.10]"
                  : "border-white/[0.14] text-white/45 bg-white/[0.04]"
              }`}>
                <motion.div
                  className="w-2.5 h-2.5 rounded-full"
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
                <span>{isMicListening ? "🎤 聆听中" : "麦克风"}</span>
              </div>
            )}

            <button
              onClick={() => switchMode(mode === "listening" ? "dialogue" : "listening")}
              disabled={!isConnected}
              className={`px-4 py-2 rounded-full border-2 text-sm font-semibold transition-all duration-300
                disabled:opacity-25 disabled:cursor-not-allowed
                ${
                  mode === "listening"
                    ? "border-blue-400/28 text-blue-300/80 hover:bg-blue-400/[0.07]"
                    : "border-amber-400/28 text-amber-300/80 hover:bg-amber-400/[0.07]"
                }`}
            >
              {mode === "listening" ? "🔊 监听" : "💬 对话"}
            </button>

            {mode === "dialogue" && (
              <div className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-amber-400/[0.08] border border-amber-400/[0.15]">
                <span className="text-sm text-amber-200/60 font-semibold tabular-nums">{dialogueCountdown}s</span>
              </div>
            )}
          </div>
        </div>

        {/* Hint text */}
        <p className="mt-2 text-base text-white/40 max-w-lg mx-auto text-center px-6 font-medium">
          {!micEnabled
            ? "点击「启用麦克风」开始语音交互"
            : mode === "listening"
              ? isMicListening
                ? "持续监听中，说「小爱」唤醒"
                : "等待麦克风权限..."
              : isProcessing
                ? "思考回复中..."
                : "对话模式，可直接说话"}
        </p>

        {/* Mic error toast */}
        {micError && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-3 max-w-lg mx-auto px-5 py-2.5 rounded-xl bg-red-500/15 border border-red-400/25 text-red-300/90 text-sm text-center"
          >
            {micError}
          </motion.div>
        )}
      </div>

      {/* ===== Center: robot face (absolute center) ===== */}
      <div className="flex-1 flex flex-col items-center justify-center relative z-10">
        <AiCharacter />
        <div className="mt-3">
          <ModeIndicator />
        </div>
      </div>

      {/* ===== Bottom bar: 4 buttons with labels ===== */}
      <div className="relative z-10 pb-2 pt-0">
        <div className="max-w-lg mx-auto flex items-center justify-between px-6">
          <button
            onClick={() => !isConnected && connect()}
            className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all duration-300 ${
              isConnected
                ? "text-emerald-400/60"
                : "text-white/30 hover:text-white/55 hover:bg-white/[0.06]"
            }`}
          >
            {isConnected ? <Wifi size={24} /> : <WifiOff size={24} />}
            <span className="text-[11px] font-medium tracking-wide">
              {isConnected ? "已连接" : "重连"}
            </span>
          </button>

          <button
            onClick={() => setChatOpen(!chatOpen)}
            className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all duration-300 ${
              chatOpen
                ? "text-blue-300/90 bg-blue-400/[0.12]"
                : "text-white/70 hover:text-white/90 hover:bg-white/[0.08]"
            }`}
          >
            <MessageSquare size={24} />
            <span className="text-[11px] font-medium tracking-wide">对话</span>
          </button>

          <button
            onClick={() => { setSummaryOpen(!summaryOpen); setChatOpen(false); }}
            className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all duration-300 ${
              summaryOpen
                ? "text-blue-300/90 bg-blue-400/[0.12]"
                : "text-white/70 hover:text-white/90 hover:bg-white/[0.08]"
            }`}
          >
            <ScrollText size={24} />
            <span className="text-[11px] font-medium tracking-wide">监听</span>
          </button>

          <button
            onClick={() => setSettingsOpen(true)}
            className="flex flex-col items-center gap-1 px-4 py-2 rounded-xl
              text-white/30 hover:text-white/55 hover:bg-white/[0.06]
              transition-all duration-200"
          >
            <Settings size={24} />
            <span className="text-[11px] font-medium tracking-wide">设置</span>
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

      {/* Listening summary overlay panel */}
      <AnimatePresence>
        {summaryOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40"
              onClick={() => setSummaryOpen(false)}
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
                <h3 className="text-lg font-semibold text-white/75">监听记录</h3>
                <button
                  onClick={() => setSummaryOpen(false)}
                  className="p-2 rounded-lg text-white/40 hover:text-white/65 hover:bg-white/[0.07] transition-colors"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="flex-1 min-h-0">
                <ListeningSummaryPanel />
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