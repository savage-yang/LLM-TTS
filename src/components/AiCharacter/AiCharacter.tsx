import { useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useChatStore } from "@/store/chatStore"
import type { EmotionType } from "@/types"

const glowColor: Record<EmotionType, string> = {
  idle: "rgba(140, 180, 220, 0.12)",
  listening: "rgba(100, 200, 255, 0.18)",
  thinking: "rgba(255, 200, 80, 0.15)",
  speaking: "rgba(120, 220, 255, 0.2)",
  happy: "rgba(255, 160, 100, 0.16)",
}

const faceTilt: Record<EmotionType, number> = {
  idle: 0,
  listening: 6,
  thinking: -4,
  speaking: 2,
  happy: 5,
}

function Eye({ side, emotion }: { side: "left" | "right"; emotion: EmotionType }) {
  const x = side === "left" ? -14 : 14
  const isThinking = emotion === "thinking"
  const isHappy = emotion === "happy"
  const isListening = emotion === "listening"

  return (
    <motion.g
      initial={false}
      animate={{
        y: isThinking ? -3 : 0,
        scaleY: isHappy || isListening ? (isHappy ? 0.7 : 1) : 1,
      }}
      transition={{ duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <circle cx={x} cy={0} r={8} fill="white" opacity={0.92} />
      <motion.circle
        cx={x}
        cy={isThinking ? -1 : 0}
        r={4}
        fill="#1a233a"
        transition={{ duration: 0.35 }}
      />
    </motion.g>
  )
}

function Mouth({ emotion, isOpen }: { emotion: EmotionType; isOpen: boolean }) {
  if (emotion === "thinking") {
    return (
      <motion.circle
        cx={0}
        cy={0}
        r={2.5}
        fill="white"
        opacity={0.75}
        animate={{ scale: [1, 1.15, 1] }}
        transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
      />
    )
  }

  if (emotion === "happy") {
    return (
      <motion.path
        d="M-6 -1 Q0 5 6 -1"
        stroke="white"
        strokeWidth={2.2}
        strokeLinecap="round"
        fill="none"
        opacity={0.9}
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.4 }}
      />
    )
  }

  if (isOpen) {
    return (
      <motion.ellipse
        cx={0}
        cy={1}
        rx={5}
        ry={4.5}
        fill="#1a233a"
        initial={false}
        animate={{ ry: [4.5, 6, 3.5, 5.5, 4.5] }}
        transition={{ duration: 0.28, repeat: Infinity, ease: "easeInOut" }}
      />
    )
  }

  return (
    <motion.path
      d="M-4 1 Q0 4 4 1"
      stroke="white"
      strokeWidth={1.8}
      strokeLinecap="round"
      fill="none"
      opacity={0.7}
    />
  )
}

export function AiCharacter() {
  const { characterState } = useChatStore()
  const { emotion, isMouthOpen } = characterState

  return (
    <div className="relative flex items-center justify-center select-none">
      <motion.div
        className="relative"
        initial={{ opacity: 0, scale: 0.85, y: 30 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 1.2, ease: [0.25, 0.46, 0.45, 0.94] }}
      >
        {/* Outer glow ring */}
        <motion.div
          className="absolute inset-0 rounded-full"
          animate={{
            boxShadow: [
              `0 0 40px ${glowColor[emotion]}, 0 0 80px ${glowColor[emotion]}`,
              `0 0 60px ${glowColor[emotion]}, 0 0 110px ${glowColor[emotion]}`,
              `0 0 40px ${glowColor[emotion]}, 0 0 80px ${glowColor[emotion]}`,
            ],
          }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          style={{ width: 180, height: 180, margin: -20 }}
        />

        {/* Floating animation */}
        <motion.div
          animate={{ y: [0, -6, 0] }}
          transition={{
            duration: 5,
            repeat: Infinity,
            ease: "easeInOut",
            times: [0, 0.5, 1],
          }}
        >
          <svg
            width="140"
            height="140"
            viewBox="0 0 140 140"
            style={{ filter: "drop-shadow(0 4px 24px rgba(0,0,0,0.25))" }}
          >
            <defs>
              <radialGradient id="nomiHead" cx="42%" cy="38%" r="62%">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="70%" stopColor="#e8eef5" />
                <stop offset="100%" stopColor="#d0dae8" />
              </radialGradient>
              <radialGradient
                id="nomiInner"
                cx="50%"
                cy="50%"
                r="50%"
              >
                <stop offset="0%" stopColor="transparent" />
                <stop offset="85%" stopColor="rgba(0,0,0,0.02)" />
                <stop offset="100%" stopColor="rgba(0,0,0,0.06)" />
              </radialGradient>
            </defs>

            {/* Head circle */}
            <g
              transform={`rotate(${faceTilt[emotion]} 70 70)`}
              style={{ transformOrigin: "70px 70px" }}
            >
              <motion.circle
                cx={70}
                cy={70}
                r={66}
                fill="url(#nomiHead)"
                initial={false}
                animate={{
                  scaleX:
                    emotion === "listening" ? 1.02 :
                    emotion === "happy" ? 0.98 :
                    1,
                }}
                transition={{ duration: 0.4, ease: "easeOut" }}
              />
              <circle cx={70} cy={70} r={66} fill="url(#nomiInner)" />

              {/* Eyes */}
              <g transform="translate(70, 60)">
                <Eye side="left" emotion={emotion} />
                <Eye side="right" emotion={emotion} />
              </g>

              {/* Blush (subtle) */}
              <AnimatePresence>
                {(emotion === "happy" || emotion === "speaking") && (
                  <motion.g
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 0.25 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.35 }}
                  >
                    <ellipse cx={44} cy={82} rx={8} ry={4.5} fill="#ffb8b8" />
                    <ellipse cx={96} cy={82} rx={8} ry={4.5} fill="#ffb8b8" />
                  </motion.g>
                )}
              </AnimatePresence>

              {/* Mouth */}
              <g transform="translate(70, 82)">
                <Mouth emotion={emotion} isOpen={isMouthOpen} />
              </g>
            </g>
          </svg>
        </motion.div>

        {/* Thinking dots */}
        <AnimatePresence>
          {emotion === "thinking" && (
            <motion.div
              className="absolute -top-6 left-1/2 -translate-x-1/2 flex gap-1.5"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
            >
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-white/60"
                  animate={{ opacity: [0.3, 0.9, 0.3], scale: [0.8, 1, 0.8] }}
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
    </div>
  )
}