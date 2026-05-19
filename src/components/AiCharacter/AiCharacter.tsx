import { motion, AnimatePresence } from "framer-motion"
import { useChatStore } from "@/store/chatStore"
import type { EmotionType } from "@/types"
import { SpeechBubble } from "@/components/SpeechBubble/SpeechBubble"

function PixelEye({ side, emotion }: { side: "left" | "right"; emotion: EmotionType }) {
  const isLeft = side === "left"
  const x = isLeft ? 40 : 88
  const isThinking = emotion === "thinking"
  const isHappy = emotion === "happy"

  const w = isHappy ? 16 : 12
  const h = isHappy ? 10 : 14
  const y = isHappy ? 55 : 54

  const pupilW = 5
  const pupilH = isThinking ? 4 : 6
  const pupilX = x + Math.floor((w - pupilW) / 2)
  let pupilY: number

  if (isThinking) {
    pupilY = y + 1
  } else {
    pupilY = y + Math.floor((h - pupilH) / 2)
  }

  return (
    <motion.g
      initial={false}
      animate={{ y: isThinking ? -3 : 0 }}
      transition={{ duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <rect x={x} y={y} width={w} height={h} rx={1} fill="#ffffff" />
      <rect x={pupilX} y={pupilY} width={pupilW} height={pupilH} rx={0.5} fill="#1a2234" />
    </motion.g>
  )
}

function PixelMouth({ emotion, isOpen }: { emotion: EmotionType; isOpen: boolean }) {
  if (emotion === "thinking") {
    return (
      <motion.rect
        x={63}
        y={81}
        width={14}
        height={14}
        rx={1}
        fill="#ffffff"
        animate={{
          width: [14, 18, 14],
          height: [14, 18, 14],
          x: [63, 61, 63],
          y: [81, 79, 81],
        }}
        transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
      />
    )
  }

  if (emotion === "happy") {
    return (
      <motion.g
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
      >
        <rect x={44} y={85} width={12} height={7} rx={1} fill="#ffffff" />
        <rect x={56} y={78} width={28} height={7} rx={1} fill="#ffffff" />
        <rect x={84} y={85} width={12} height={7} rx={1} fill="#ffffff" />
      </motion.g>
    )
  }

  if (isOpen) {
    return (
      <motion.rect
        x={54}
        y={77}
        width={32}
        height={18}
        rx={1}
        fill="#ffffff"
        animate={{ height: [18, 22, 16, 20, 18] }}
        transition={{ duration: 0.28, repeat: Infinity, ease: "easeInOut" }}
      />
    )
  }

  return (
    <rect x={50} y={86} width={40} height={7} rx={1} fill="#ffffff" opacity={0.75} />
  )
}

export function AiCharacter() {
  const { characterState, mode } = useChatStore()
  const { emotion, isMouthOpen } = characterState

  const effectiveEmotion = mode === "listening" ? "listening" : emotion

  return (
    <div className="relative flex items-center justify-center select-none">
      <SpeechBubble />

      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.2, ease: [0.25, 0.46, 0.45, 0.94] }}
      >
        <motion.div
          className="relative"
          animate={{ y: [0, -8, 0] }}
          transition={{
            duration: 5,
            repeat: Infinity,
            ease: "easeInOut",
            times: [0, 0.5, 1],
          }}
        >
          <svg
            width="220"
            height="220"
            viewBox="0 0 140 140"
            shapeRendering="crispEdges"
            style={{ filter: "drop-shadow(0 6px 28px rgba(0,0,0,0.3))" }}
          >
            <circle
              cx={70}
              cy={70}
              r={56}
              fill="none"
              stroke="#ffffff"
              strokeWidth={3}
              opacity={0.85}
            />

            <g>
              <PixelEye side="left" emotion={effectiveEmotion} />
              <PixelEye side="right" emotion={effectiveEmotion} />
            </g>

            <g>
              <PixelMouth emotion={effectiveEmotion} isOpen={isMouthOpen} />
            </g>
          </svg>

          <AnimatePresence>
            {effectiveEmotion === "thinking" && (
              <motion.div
                className="absolute inset-x-0 flex justify-center gap-2"
                style={{ top: -30 }}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.3 }}
              >
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    className="w-[8px] h-[8px] bg-white/70"
                    animate={{ opacity: [0.3, 0.9, 0.3] }}
                    transition={{
                      duration: 1.2,
                      repeat: Infinity,
                      delay: i * 0.22,
                      ease: "easeInOut",
                    }}
                  />
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </motion.div>
    </div>
  )
}