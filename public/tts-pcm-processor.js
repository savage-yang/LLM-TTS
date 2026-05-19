// tts-pcm-processor.js — AudioWorkletProcessor for TTS playback
// 接收 PCM16 音频数据并播放，支持采样率转换和缓冲
class TTSPCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buffer = new Float32Array(0)
    this.inputSampleRate = 24000  // TTS 输出采样率
    this.outputSampleRate = sampleRate  // AudioContext 采样率（通常 48000）
    this.ratio = this.outputSampleRate / this.inputSampleRate  // 上采样比例
    // 缓冲配置：等待 0.5 秒音频数据后再开始播放
    this.bufferDuration = 0.5  // 缓冲时长（秒）
    this.bufferThreshold = Math.ceil(this.outputSampleRate * this.bufferDuration)  // 缓冲样本数
    this.isBuffering = true  // 是否处于缓冲阶段

    this.port.onmessage = (e) => {
      if (e.data === 'reset') {
        // 重置缓冲区
        this.buffer = new Float32Array(0)
        this.isBuffering = true
        return
      }

      const pcm16 = new Int16Array(e.data)
      // Int16 → Float32
      const float32 = new Float32Array(pcm16.length)
      for (let i = 0; i < pcm16.length; i++) {
        float32[i] = pcm16[i] / 32768.0
      }

      // 上采样：24kHz → 48kHz
      let processedData
      if (Math.abs(this.ratio - 1) > 0.01) {
        const upsampled = new Float32Array(Math.ceil(float32.length * this.ratio))
        for (let i = 0; i < upsampled.length; i++) {
          const srcIndex = i / this.ratio
          const srcIndex0 = Math.floor(srcIndex)
          const srcIndex1 = Math.min(srcIndex0 + 1, float32.length - 1)
          const fraction = srcIndex - srcIndex0
          upsampled[i] = float32[srcIndex0] * (1 - fraction) + float32[srcIndex1] * fraction
        }
        processedData = upsampled
      } else {
        processedData = float32
      }

      // 追加到缓冲区
      const newBuf = new Float32Array(this.buffer.length + processedData.length)
      newBuf.set(this.buffer)
      newBuf.set(processedData, this.buffer.length)
      this.buffer = newBuf

      // 检查是否达到缓冲阈值
      if (this.isBuffering && this.buffer.length >= this.bufferThreshold) {
        this.isBuffering = false
      }
    }
  }

  process(inputs, outputs) {
    const output = outputs[0]
    if (!output || !output[0]) return true

    const channelData = output[0]
    const samplesNeeded = channelData.length

    // 如果还在缓冲阶段，输出静音
    if (this.isBuffering) {
      // 输出静音
      return true
    }

    if (this.buffer.length >= samplesNeeded) {
      // 从缓冲区取出所需样本
      channelData.set(this.buffer.subarray(0, samplesNeeded))
      this.buffer = this.buffer.slice(samplesNeeded)
    } else {
      // 缓冲区数据不足，播放已有数据并填充静音
      channelData.set(this.buffer)
      // 剩余部分填充静音（默认为0）
      this.buffer = new Float32Array(0)
    }

    return true
  }
}

registerProcessor("tts-pcm-processor", TTSPCMProcessor)