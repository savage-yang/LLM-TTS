import { useState, useRef, useCallback } from "react"

interface UseMicRecorderProps {
  wsRef: React.RefObject<WebSocket | null>
  isConnected: boolean
}

export function useSpeechRecognition({ wsRef, isConnected }: UseMicRecorderProps) {
  const [isRecording, setIsRecording] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const manuallyActivatedRef = useRef(false)

  const isSupported = typeof window !== "undefined" && 
    !!navigator.mediaDevices && !!navigator.mediaDevices.getUserMedia

  const startRecording = useCallback(async () => {
    if (!isSupported || !isConnected) return

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

      let mimeType = ""
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        mimeType = "audio/webm;codecs=opus"
      } else if (MediaRecorder.isTypeSupported("audio/webm")) {
        mimeType = "audio/webm"
      } else {
        mimeType = ""
      }

      const recorder = new MediaRecorder(stream, {
        mimeType: mimeType || undefined,
      })

      recorder.onstart = () => {
        setIsRecording(true)
      }

      recorder.onstop = () => {
        setIsRecording(false)
        if (manuallyActivatedRef.current && streamRef.current && streamRef.current.active) {
          setTimeout(() => {
            try {
              if (recorder.state === "inactive") {
                recorder.start(200)
              }
            } catch {}
          }, 300)
        }
      }

      recorder.onerror = (event) => {
        console.error("MediaRecorder error:", event.error)
        setIsRecording(false)
      }

      recorder.ondataavailable = (event) => {
        if (!event.data || event.data.size === 0) return
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

        event.data.arrayBuffer().then((arrayBuffer) => {
          try {
            wsRef.current.send(arrayBuffer)
          } catch (e) {
            console.warn("Send audio chunk failed:", e)
          }
        })
      }

      mediaRecorderRef.current = recorder
      recorder.start(200)

    } catch (e) {
      console.error("Failed to start recording:", e)
      setIsRecording(false)
    }
  }, [isSupported, isConnected])

  const stopRecording = useCallback(() => {
    manuallyActivatedRef.current = false
    if (mediaRecorderRef.current) {
      try {
        if (mediaRecorderRef.current.state === "recording") {
          mediaRecorderRef.current.stop()
        }
      } catch {}
      mediaRecorderRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    setIsRecording(false)
  }, [])

  return {
    isSupported,
    isRecording,
    startRecording,
    stopRecording,
  }
}