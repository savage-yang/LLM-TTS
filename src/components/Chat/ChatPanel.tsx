import { useState, useRef, useEffect } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { useChatStore } from "@/store/chatStore"
import { MessageBubble } from "./MessageBubble"
import { TypingIndicator } from "./TypingIndicator"
import { Sparkles } from "lucide-react"

function ListeningEmpty() {
  const { wakeWord } = useChatStore()
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center pt-6 pb-4 gap-2"
    >
      <div className="w-10 h-10 rounded-full bg-blue-400/5 flex items-center justify-center mb-1">
        <Sparkles size={18} className="text-blue-400/30" />
      </div>
      <p className="text-white/15 text-sm">监听模式已开启</p>
      <p className="text-white/8 text-[11px]">
        说「{wakeWord}」即可唤醒我
      </p>
    </motion.div>
  )
}

function SummaryCard({ content, timestamp }: { content: string; timestamp: string }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = content.length > 120
  const display = expanded || !isLong ? content : content.slice(0, 120) + "..."

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className="bg-blue-400/[0.03] border border-blue-400/[0.06] rounded-xl px-3.5 py-3 mb-2"
    >
      <div className="flex items-center gap-1.5 mb-1.5">
        <div className="w-1 h-1 rounded-full bg-blue-400/50" />
        <span className="text-[10px] text-white/20">监听总结</span>
        <span className="text-[10px] text-white/10 ml-auto">{timestamp}</span>
      </div>
      <p className="text-[12px] text-white/45 leading-relaxed whitespace-pre-wrap">{display}</p>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[10px] text-blue-400/40 hover:text-blue-400/60 mt-1 transition-colors"
        >
          {expanded ? "收起" : "展开全文"}
        </button>
      )}
    </motion.div>
  )
}

function ChatEmpty() {
  return (
    <div className="flex flex-col items-center justify-center pt-8 pb-4">
      <p className="text-white/15 text-sm">开始对话</p>
    </div>
  )
}

function SummarizingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-2 px-3.5 py-2.5 bg-white/[0.02] border border-white/[0.04] rounded-xl mb-2"
    >
      <div className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="w-1 h-1 rounded-full bg-blue-400/40"
            animate={{ opacity: [0.2, 0.6, 0.2] }}
            transition={{ duration: 1, repeat: Infinity, delay: i * 0.18 }}
          />
        ))}
      </div>
      <span className="text-[11px] text-white/20">正在生成监听总结...</span>
    </motion.div>
  )
}

export function ChatPanel() {
  const { messages, mode, summaries, isProcessing, isSummarizing, lastRecordedText, wordCount } = useChatStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isProcessing])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3">
      <div className="max-w-lg mx-auto">
        {mode === "listening" ? (
          <>
            {isSummarizing && <SummarizingIndicator />}
            {summaries.length > 0 ? (
              summaries.map((s) => (
                <SummaryCard key={s.id} content={s.content} timestamp={s.timestamp} />
              ))
            ) : !isSummarizing ? (
              <ListeningEmpty />
            ) : null}
            {lastRecordedText && wordCount > 0 && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="mt-3"
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <div className="w-1 h-1 rounded-full bg-emerald-400/50 animate-pulse" />
                  <span className="text-[10px] text-white/15">
                    已监听 {wordCount} 字
                  </span>
                </div>
                <p className="text-[11px] text-white/20 truncate">
                  最近: {lastRecordedText}
                </p>
              </motion.div>
            )}
          </>
        ) : (
          <>
            {messages.length === 0 && !isProcessing && <ChatEmpty />}
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <AnimatePresence>
              {isProcessing && <TypingIndicator />}
            </AnimatePresence>
          </>
        )}
        <div ref={bottomRef} className="h-1" />
      </div>
    </div>
  )
}