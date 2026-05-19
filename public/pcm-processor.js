// pcm-processor.js — AudioWorkletProcessor
// 采集麦克风音频，降采样到 16kHz，输出 Int16 PCM 二进制帧
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buffer = new Float32Array(0)
    this.ratio = Math.round(sampleRate / 16000) // e.g. 48000/16000 = 3
    console.log(`[PCMProcessor] sampleRate=${sampleRate}, ratio=${this.ratio}`)
  }

  process(inputs) {
    const input = inputs[0]
    if (!input || !input[0]) return true

    const inputData = input[0]

    // 累积输入样本
    const newBuf = new Float32Array(this.buffer.length + inputData.length)
    newBuf.set(this.buffer)
    newBuf.set(inputData, this.buffer.length)
    this.buffer = newBuf

    // 每积累够 ratio 个样本就输出 1 个
    const outputLen = Math.floor(this.buffer.length / this.ratio)
    if (outputLen < 1) return true

    const output = new Float32Array(outputLen)
    for (let i = 0; i < outputLen; i++) {
      output[i] = this.buffer[i * this.ratio]
    }
    this.buffer = this.buffer.slice(outputLen * this.ratio)

    // Float32 → Int16
    const int16 = new Int16Array(output.length)
    for (let i = 0; i < output.length; i++) {
      const s = Math.max(-1, Math.min(1, output[i]))
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }

    this.port.postMessage(int16.buffer, [int16.buffer])
    return true
  }
}

registerProcessor("pcm-processor", PCMProcessor)
