import { useState, useEffect } from "react"
import { AiCharacter } from "@/components/AiCharacter/AiCharacter"
import { ChatPanel } from "@/components/Chat/ChatPanel"
import { InputBar } from "@/components/Input/InputBar"
import { ModeIndicator } from "@/components/ModeIndicator/ModeIndicator"
import { SettingsPanel } from "@/components/Settings/SettingsPanel"
import { useWebSocket } from "@/hooks/useWebSocket"
import { useChatStore } from "@/store/chatStore"

function App() {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const { connect, disconnect, sendMessage, switchMode, isConnected } = useWebSocket()
  const mode = useChatStore((s) => s.mode)
  const isProcessing = useChatStore((s) => s.isProcessing)
  const isSummarizing = useChatStore((s) => s.isSummarizing)

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [])

  return (
    <div className="h-screen w-screen flex flex-col bg-[#080c16] font-['Nunito',sans-serif] overflow-hidden">
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/3 w-[500px] h-[500px] bg-blue-400/[0.03] rounded-full blur-[140px]" />
      </div>

      {/* Character */}
      <div className="relative z-10 flex-shrink-0 pt-6 pb-1">
        <AiCharacter />
      </div>

      {/* Mode Indicator */}
      <div className="relative z-10 flex justify-center pb-1">
        <div className="flex items-center gap-2">
          <ModeIndicator />
          <div className="flex items-center gap-1.5">
            <div
              className={`w-1.5 h-1.5 rounded-full transition-colors duration-300 ${
                isConnected ? "bg-emerald-400" : "bg-white/20"
              }`}
            />
            <span className="text-[10px] text-white/25 tracking-wider uppercase">
              {isConnected ? "Online" : "Offline"}
            </span>
          </div>
        </div>
      </div>

      {/* Chat / Listening Log */}
      <div className="relative z-10 flex-1 min-h-0">
        <ChatPanel />
      </div>

      {/* Input */}
      <div className="relative z-10">
        <InputBar
          onSend={sendMessage}
          onSwitchMode={switchMode}
          onOpenSettings={() => setSettingsOpen(true)}
          onConnect={connect}
          isConnected={isConnected}
          canConnect={!isConnected}
          currentMode={mode}
          isProcessing={isProcessing}
          isSummarizing={isSummarizing}
        />
      </div>

      {/* Settings */}
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  )
}

export default App