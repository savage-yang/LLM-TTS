import { useState, useRef, useCallback } from "react"

interface UseMicRecorderProps {
  wsRef: React.RefObject<WebSocket | null>
  isConnected: boolean
}

export type MicStartResult = { ok: true } | { ok: false; reason: string }

export function useSpeechRecognition({ wsRef, isConnected }: UseMicRecorderProps) {
  const [isRecording, setIsRecording] = useState(false)
  const manuallyActivatedRef = useRef(false)
  const audioContextRef = useRef<AudioContext | null>(null)
  const workletNodeRef = useRef<AudioWorkletNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const isSupported =
    typeof window !== "undefined" &&
    !!navigator.mediaDevices &&
    !!navigator.mediaDevices.getUserMedia

  const stopRecording = useCallback(() => {
    manuallyActivatedRef.current = false
    if (workletNodeRef.current) {
      try { workletNodeRef.current.disconnect() } catch {}
      workletNodeRef.current = null
    }
    if (sourceRef.current) {
      try { sourceRef.current.disconnect() } catch {}
      sourceRef.current = null
    }
    if (audioContextRef.current) {
      try { audioContextRef.current.close() } catch {}
      audioContextRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    setIsRecording(false)
  }, [])

  const startRecording = useCallback(async (): Promise<MicStartResult> => {
    if (!isSupported) {
      return { ok: false, reason: "浏览器不支持麦克风（请使用 HTTPS 或 localhost 访问）" }
    }
    if (!isConnected) {
      return { ok: false, reason: "后端服务未连接，请检查 web_server.py 是否已启动" }
    }

    try {
      stopRecording()

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })

      streamRef.current = stream
      manuallyActivatedRef.current = true

      // 使用默认采样率（浏览器通常 48kHz），AudioWorklet 内部不做降采样
      // 后端统一处理采样率
      const audioContext = new AudioContext()
      audioContextRef.current = audioContext

      // 等待 AudioContext ready
      if (audioContext.state === "suspended") {
        await audioContext.resume()
      }

      // 加载 AudioWorklet processor
      await audioContext.audioWorklet.addModule("/pcm-processor.js")

      const workletNode = new AudioWorkletNode(audioContext, "pcm-processor")
      workletNodeRef.current = workletNode

      const source = audioContext.createMediaStreamSource(stream)
      sourceRef.current = source

      console.log(`AudioContext sample rate: ${audioContext.sampleRate}Hz`)

      workletNode.port.onmessage = (event) => {
        if (!manuallyActivatedRef.current) return
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

        const pcmBuffer = event.data as ArrayBuffer
        try {
          wsRef.current.send(pcmBuffer)
        } catch (e) {
          console.warn("Send PCM failed:", e)
        }
      }

      // 只连接 source → workletNode，不连接 destination，不会产生回放
      source.connect(workletNode)

      setIsRecording(true)
      return { ok: true }
    } catch (e) {
      console.error("Failed to start recording:", e)
      setIsRecording(false)
      const msg = e instanceof Error ? e.message : String(e)
      return { ok: false, reason: `麦克风启动失败: ${msg}` }
    }
  }, [isSupported, isConnected, stopRecording])

  return {
    isSupported,
    isRecording,
    startRecording,
    stopRecording,
  }
}
