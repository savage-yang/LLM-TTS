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
      className="flex flex-col items-center justify-center pt-10 pb-8 gap-4"
    >
      <div className="w-16 h-16 rounded-full bg-blue-400/[0.09] flex items-center justify-center mb-1">
        <Sparkles size={28} className="text-blue-300/40" />
      </div>
      <p className="text-lg text-white/30 font-medium">监听模式已开启</p>
      <p className="text-base text-white/15">
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
      className="bg-blue-400/[0.06] border border-blue-400/[0.10] rounded-xl px-5 py-4 mb-4"
    >
      <div className="flex items-center gap-2.5 mb-2.5">
        <div className="w-2 h-2 rounded-full bg-blue-400/60" />
        <span className="text-sm text-white/30 font-medium">监听总结</span>
        <span className="text-sm text-white/14 ml-auto">{timestamp}</span>
      </div>
      <p className="text-[17px] text-white/55 leading-relaxed whitespace-pre-wrap font-normal">{display}</p>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-sm text-blue-300/55 hover:text-blue-300/75 mt-2 transition-colors font-medium"
        >
          {expanded ? "收起" : "展开全文"}
        </button>
      )}
    </motion.div>
  )
}

function ChatEmpty() {
  return (
    <div className="flex flex-col items-center justify-center pt-12 pb-8">
      <p className="text-lg text-white/30 font-medium">开始对话</p>
    </div>
  )
}

function SummarizingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-3 px-5 py-3.5 bg-white/[0.04] border border-white/[0.08] rounded-xl mb-4"
    >
      <div className="flex gap-1.5">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="w-2 h-2 rounded-full bg-blue-400/50"
            animate={{ opacity: [0.2, 0.6, 0.2] }}
            transition={{ duration: 1, repeat: Infinity, delay: i * 0.18 }}
          />
        ))}
      </div>
      <span className="text-base text-white/30 font-medium">正在生成监听总结...</span>
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
    <div className="flex-1 overflow-y-auto px-6 py-5">
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
                className="mt-5"
              >
                <div className="flex items-center gap-2.5 mb-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-400/60 animate-pulse" />
                  <span className="text-sm text-white/28 font-medium">
                    已监听 {wordCount} 字
                  </span>
                </div>
                <p className="text-base text-white/25 truncate">
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