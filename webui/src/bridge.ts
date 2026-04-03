/**
 * CutPilot pywebview bridge — typed wrapper around window.pywebview.api.
 *
 * In dev mode (no pywebview), methods return mock data so the UI still works.
 */

interface PyWebViewAPI {
  ping(): Promise<string>
  get_machine_id(): Promise<string>
  get_license_info(): Promise<Record<string, unknown>>
  activate_license(code: string): Promise<{ success: boolean; message: string }>
  load_settings(): Promise<Record<string, unknown>>
  save_settings(settings: Record<string, unknown>): Promise<{ success: boolean; error?: string }>
  get_providers(): Promise<ProviderPreset[]>
  select_files(): Promise<string[]>
  select_directory(): Promise<string>
  open_folder(path: string): Promise<{ success: boolean; error?: string }>
  get_history(): Promise<HistoryEntry[]>
  clear_history(): Promise<{ success: boolean; error?: string }>
  test_connection(provider: string, apiKey: string, baseUrl?: string, model?: string): Promise<{ success: boolean; error?: string; model?: string; latency_ms?: number }>
  process_batch(videoPaths: string[]): Promise<ProcessResult[]>
  cancel_processing(): Promise<{ success: boolean; error?: string }>
  export_versions(videoPath: string, versionIds: number[], options?: Record<string, unknown>): Promise<{ success: boolean; files?: unknown[]; error?: string }>
  export_logs(): Promise<{ success: boolean; message: string; path?: string }>
  get_encoder_info(): Promise<EncoderInfo>
  get_gpu_info(): Promise<GpuInfo>
  get_max_parallel(): Promise<number>
  check_asr_status(engine: string, model_size: string): Promise<{ ready: boolean; message: string }>
  check_all_model_status(): Promise<{ tiny: boolean; small: boolean; medium: boolean }>
  download_asr_model(engine: string, model_size: string): Promise<{ success: boolean; message: string }>
  run_benchmark(): Promise<BenchmarkResult>
  preview_video(filePath: string): Promise<{ success: boolean; error?: string }>
  get_output_files(videoPath: string): Promise<OutputFile[]>
  delete_history_entry(timestamp: string): Promise<{ success: boolean; error?: string }>
  generate_thumbnail(videoPath: string, timeSec: number): Promise<string>
}

export interface ProviderPreset {
  id: string
  name: string
  base_url: string
  model: string
  api_key_hint: string
}

export interface HistoryEntry {
  video_name: string
  video_path: string
  timestamp: string
  success: boolean
  error: string
  versions_count: number
  output_files: string[]
  approach_tags: string[]
  duration_sec: number
}

export interface ScriptVersion {
  version_id: number
  title: string
  structure: string
  sentence_ids: number[]
  reason: string
  estimated_duration: number
  score: number
  publish_text: string
  cover_title: string
  cover_subtitle: string
  tags: string[]
  approach_tag: string
}

export interface ProcessResult {
  success: boolean
  error: string
  versions: ScriptVersion[]
  output_files: { version_id: number; path: string; speed: string; quality: string }[]
}

export interface OutputFile {
  path: string
  name: string
  size_mb: number
}

export interface BenchmarkResult {
  max_parallel: number
  cpu_cores: number
  ram_gb: number
  encoder: string
  is_hardware: boolean
  reason: string
}

export interface EncoderInfo {
  codec: string
  name: string
  is_hardware: boolean
  extra_params: string[]
}

export interface GpuInfo {
  encoder_name: string
  encoder_codec: string
  is_hardware: boolean
  detection_method: string
  gpu_model: string | null
  nvenc_sessions: number | null
}

declare global {
  interface Window {
    pywebview?: { api: PyWebViewAPI }
  }
}

/**
 * Wait for pywebview API to be injected (max 3s), then return it.
 * Returns null if timeout (browser fallback mode).
 */
let _apiReady: Promise<PyWebViewAPI | null> | null = null

export function waitForApi(): Promise<PyWebViewAPI | null> {
  if (_apiReady) return _apiReady
  _apiReady = new Promise((resolve) => {
    if (window.pywebview?.api) {
      resolve(window.pywebview.api)
      return
    }
    const onReady = () => {
      resolve(window.pywebview?.api ?? null)
    }
    window.addEventListener('pywebviewready', onReady, { once: true })
    globalThis.setTimeout(() => {
      resolve(window.pywebview?.api ?? null)
    }, 3000)
  })
  return _apiReady
}

/**
 * HTTP fallback: call Python backend via Bottle JSON API.
 * Used when running in browser mode (no pywebview).
 */
async function httpCall(method: string, ...args: unknown[]): Promise<any> {
  try {
    const resp = await fetch(`/api/${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ args }),
    })
    return await resp.json()
  } catch {
    return null
  }
}

// ── Bridge functions ───────────────────────────────────────
// Each function tries pywebview API first, then HTTP fallback for browser mode.

export async function ping(): Promise<string> {
  const api = await waitForApi()
  return api ? await api.ping() : (await httpCall('ping') ?? 'pong')
}

export async function getMachineId(): Promise<string> {
  const api = await waitForApi()
  return api ? await api.get_machine_id() : (await httpCall('get_machine_id') ?? 'UNKNOWN')
}

export async function getLicenseInfo(): Promise<Record<string, unknown>> {
  const api = await waitForApi()
  return api ? await api.get_license_info() : (await httpCall('get_license_info') ?? { is_valid: false, trial_remaining: 99 })
}

export async function activateLicense(code: string): Promise<{ success: boolean; message: string }> {
  const api = await waitForApi()
  return api ? await api.activate_license(code) : (await httpCall('activate_license', code) ?? { success: false, message: '后端未连接' })
}

export async function loadSettings(): Promise<Record<string, unknown>> {
  const api = await waitForApi()
  return api ? await api.load_settings() : (await httpCall('load_settings') ?? {})
}

export async function saveSettings(settings: Record<string, unknown>): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.save_settings(settings) : (await httpCall('save_settings', settings) ?? { success: true })
}

export async function getProviders(): Promise<ProviderPreset[]> {
  const api = await waitForApi()
  return api ? await api.get_providers() : (await httpCall('get_providers') ?? [])
}

export async function selectFiles(): Promise<string[]> {
  const api = await waitForApi()
  return api ? await api.select_files() : (await httpCall('select_files') ?? [])
}

export async function selectDirectory(): Promise<string> {
  const api = await waitForApi()
  return api ? await api.select_directory() : (await httpCall('select_directory') ?? '')
}

export async function openFolder(path: string): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.open_folder(path) : (await httpCall('open_folder', path) ?? { success: false })
}

export async function getHistory(): Promise<HistoryEntry[]> {
  const api = await waitForApi()
  return api ? await api.get_history() : (await httpCall('get_history') ?? [])
}

export async function clearHistory(): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.clear_history() : (await httpCall('clear_history') ?? { success: true })
}

export async function testConnection(
  provider: string, apiKey: string, baseUrl?: string, model?: string
): Promise<{ success: boolean; error?: string; model?: string; latency_ms?: number }> {
  const api = await waitForApi()
  return api
    ? await api.test_connection(provider, apiKey, baseUrl ?? '', model ?? '')
    : (await httpCall('test_connection', provider, apiKey, baseUrl ?? '', model ?? '') ?? { success: false })
}

export async function processBatch(videoPaths: string[]): Promise<ProcessResult[]> {
  const api = await waitForApi()
  return api
    ? await api.process_batch(videoPaths)
    : (await httpCall('process_batch', videoPaths) ?? videoPaths.map(() => ({ success: false, error: '后端未连接', versions: [], output_files: [] })))
}

export async function cancelProcessing(): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.cancel_processing() : (await httpCall('cancel_processing') ?? { success: false })
}

export async function getEncoderInfo(): Promise<EncoderInfo> {
  const api = await waitForApi()
  return api ? await api.get_encoder_info() : (await httpCall('get_encoder_info') ?? { codec: 'libx264', name: 'Software x264', is_hardware: false, extra_params: [] })
}

export async function exportLogs(): Promise<{ success: boolean; message: string; path?: string }> {
  const api = await waitForApi()
  return api ? await api.export_logs() : (await httpCall('export_logs') ?? { success: false, message: '后端未连接' })
}

export async function getGpuInfo(): Promise<GpuInfo> {
  const api = await waitForApi()
  return api ? await api.get_gpu_info() : (await httpCall('get_gpu_info') ?? { encoder_name: 'Software x264', encoder_codec: 'libx264', is_hardware: false, detection_method: 'unknown', gpu_model: null, nvenc_sessions: null })
}

export async function getMaxParallel(): Promise<number> {
  const api = await waitForApi()
  return api ? await api.get_max_parallel() : (await httpCall('get_max_parallel') ?? 2)
}

export async function exportVersions(
  videoPath: string, versionIds: number[], options?: Record<string, unknown>
): Promise<{ success: boolean; files?: unknown[]; error?: string }> {
  const api = await waitForApi()
  return api
    ? await api.export_versions(videoPath, versionIds, options)
    : (await httpCall('export_versions', videoPath, versionIds, options) ?? { success: false })
}

export async function checkAsrStatus(engine?: string, modelSize?: string): Promise<{ ready: boolean; message: string }> {
  const api = await waitForApi()
  return api ? await api.check_asr_status(engine ?? '', modelSize ?? '') : (await httpCall('check_asr_status', engine ?? '', modelSize ?? '') ?? { ready: false, message: '后端未连接' })
}

export async function checkAllModelStatus(): Promise<{ tiny: boolean; small: boolean; medium: boolean }> {
  const api = await waitForApi()
  return api ? await api.check_all_model_status() : (await httpCall('check_all_model_status') ?? { tiny: false, small: false, medium: false })
}

export async function downloadAsrModel(engine?: string, modelSize?: string): Promise<{ success: boolean; message: string }> {
  const api = await waitForApi()
  return api ? await api.download_asr_model(engine ?? '', modelSize ?? '') : (await httpCall('download_asr_model', engine ?? '', modelSize ?? '') ?? { success: false, message: '后端未连接' })
}

export async function runBenchmark(): Promise<BenchmarkResult> {
  const api = await waitForApi()
  return api ? await api.run_benchmark() : (await httpCall('run_benchmark') ?? { max_parallel: 1, cpu_cores: 1, ram_gb: 0, encoder: 'unknown', is_hardware: false, reason: '后端未连接' })
}

export async function previewVideo(filePath: string): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.preview_video(filePath) : (await httpCall('preview_video', filePath) ?? { success: false })
}

export async function deleteHistoryEntry(timestamp: string): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.delete_history_entry(timestamp) : (await httpCall('delete_history_entry', timestamp) ?? { success: true })
}

export async function generateThumbnail(videoPath: string, timeSec: number = 1.0): Promise<string> {
  const api = await waitForApi()
  return api ? await api.generate_thumbnail(videoPath, timeSec) : (await httpCall('generate_thumbnail', videoPath, timeSec) ?? '')
}

// ── Progress event listener ────────────────────────────────

export interface ProgressEvent {
  label: string
  percent: number
  index?: number  // video index in batch
  total?: number  // total videos in batch
  stage?: string  // pipeline stage label (e.g. "正在识别语音...")
}

export function onPipelineProgress(callback: (e: ProgressEvent) => void): () => void {
  const handler = (evt: Event) => {
    const detail = (evt as CustomEvent).detail as ProgressEvent
    callback(detail)
  }
  window.addEventListener('pipeline-progress', handler)
  return () => window.removeEventListener('pipeline-progress', handler)
}

// ── Batch summary event listener ──────────────────────────

export interface BatchSummary {
  total: number
  success_count: number
  fail_count: number
  errors: { video: string; error: string }[]
}

export function onBatchSummary(callback: (e: BatchSummary) => void): () => void {
  const handler = (evt: Event) => {
    const detail = (evt as CustomEvent).detail as BatchSummary
    callback(detail)
  }
  window.addEventListener('batch-summary', handler)
  return () => window.removeEventListener('batch-summary', handler)
}

// ── Download progress event listener ──────────────────────

export interface DownloadProgressEvent {
  percent: number
}

export function onDownloadProgress(callback: (e: DownloadProgressEvent) => void): () => void {
  const handler = (evt: Event) => {
    const detail = (evt as CustomEvent).detail as DownloadProgressEvent
    callback(detail)
  }
  window.addEventListener('download-progress', handler)
  return () => window.removeEventListener('download-progress', handler)
}
