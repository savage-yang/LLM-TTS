import { useState, useRef, useEffect, useCallback } from "react"
import { motion } from "framer-motion"
import { useChatStore } from "@/store/chatStore"
import { Sparkles, Clock } from "lucide-react"

interface ApiSummary {
  content: string
  timestamp: string
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

function CountdownTimer({ seconds }: { seconds: number }) {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  const display = mins > 0 ? `${mins}分${secs}秒` : `${secs}秒`

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex items-center gap-3 px-5 py-3 rounded-xl bg-blue-400/[0.07] border border-blue-400/[0.15]"
    >
      <Clock size={20} className="text-blue-300/50" />
      <span className="text-base text-white/30 font-medium">下次总结: </span>
      <span className="text-xl text-blue-200/70 font-bold tabular-nums tracking-wide">{display}</span>
    </motion.div>
  )
}

export function ListeningSummaryPanel() {
  const { mode, isSummarizing, lastRecordedText, wordCount } = useChatStore()
  const bottomRef = useRef<HTMLDivElement>(null)
  const [apiSummaries, setApiSummaries] = useState<ApiSummary[]>([])
  const [summaryInterval, setSummaryInterval] = useState(60)
  const [lastSummaryTime, setLastSummaryTime] = useState(Date.now())
  const [countdown, setCountdown] = useState(60)

  const fetchSummaries = useCallback(async () => {
    try {
      const proto = window.location.protocol === "https:" ? "https" : "http"
      const host = window.location.hostname
      const url = `${proto}://${host}:8765/api/listening-summaries`
      const res = await fetch(url)
      const data = await res.json()
      if (data.summaries) {
        setApiSummaries(data.summaries)
      }
      if (data.summary_interval) {
        setSummaryInterval(data.summary_interval)
      }
    } catch {
    }
  }, [])

  useEffect(() => {
    fetchSummaries()
    const timer = setInterval(fetchSummaries, 5000)
    return () => clearInterval(timer)
  }, [fetchSummaries])

  useEffect(() => {
    if (mode !== "listening") {
      setCountdown(summaryInterval)
      return
    }
    const updateCountdown = () => {
      const elapsed = Math.floor((Date.now() - lastSummaryTime) / 1000)
      const remaining = Math.max(0, summaryInterval - elapsed)
      setCountdown(remaining)
    }
    updateCountdown()
    const timer = setInterval(updateCountdown, 1000)
    return () => clearInterval(timer)
  }, [mode, summaryInterval, lastSummaryTime])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [apiSummaries])

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5">
      <div className="max-w-lg mx-auto">
        {/* Countdown & header */}
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-2 h-2 rounded-full bg-blue-400/50" />
          <h3 className="text-base text-white/30 font-semibold tracking-wide">监听记录</h3>
          <div className="ml-auto">
            <CountdownTimer seconds={countdown} />
          </div>
        </div>

        {/* Summarizing indicator */}
        {isSummarizing && (
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
        )}

        {/* Summary cards */}
        {apiSummaries.length > 0 ? (
          apiSummaries.map((s, i) => (
            <SummaryCard key={i} content={s.content} timestamp={s.timestamp} />
          ))
        ) : !isSummarizing ? (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center justify-center pt-6 pb-8 gap-4"
          >
            <div className="w-14 h-14 rounded-full bg-blue-400/[0.08] flex items-center justify-center">
              <Sparkles size={24} className="text-blue-300/35" />
            </div>
            <p className="text-lg text-white/30 font-medium">监听模式已开启</p>
            <p className="text-base text-white/15">
              说「{useChatStore.getState().wakeWord}」即可唤醒
            </p>
          </motion.div>
        ) : null}

        {/* Listening status */}
        {lastRecordedText && wordCount > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-2"
          >
            <div className="flex items-center gap-2.5 mb-1">
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

        <div ref={bottomRef} className="h-1" />
      </div>
    </div>
  )
}