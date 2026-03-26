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
  test_connection(provider: string, apiKey: string, baseUrl?: string, model?: string): Promise<{ success: boolean; error?: string; model?: string }>
  process_video(videoPath: string, settingsOverride?: Record<string, unknown>): Promise<ProcessResult>
  process_batch(videoPaths: string[]): Promise<ProcessResult[]>
  is_processing(): Promise<boolean>
  cancel_processing(): Promise<{ success: boolean; error?: string }>
  export_versions(videoPath: string, versionIds: number[], options?: Record<string, unknown>): Promise<{ success: boolean; files?: unknown[]; error?: string }>
  get_encoder_info(): Promise<EncoderInfo>
  get_max_parallel(): Promise<number>
  check_asr_status(engine?: string): Promise<{ ready: boolean; message: string }>
  download_asr_model(engine?: string): Promise<{ success: boolean; message: string }>
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
  hook_text: string
  why_it_may_work: string
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

declare global {
  interface Window {
    pywebview?: { api: PyWebViewAPI }
  }
}

/** True when running inside pywebview (not browser dev mode). */
export const isNative = (): boolean => !!window.pywebview?.api

/**
 * Wait for pywebview API to be injected (max 5s), then return it.
 * Returns null if timeout (dev mode).
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
    // Timeout: if pywebview never injects, we're in dev mode
    globalThis.setTimeout(() => {
      resolve(window.pywebview?.api ?? null)
    }, 5000)
  })
  return _apiReady
}

/**
 * Get the pywebview API, or null in dev mode.
 */
function getApi(): PyWebViewAPI | null {
  return window.pywebview?.api ?? null
}

// ── Bridge functions ───────────────────────────────────────

export async function ping(): Promise<string> {
  const api = await waitForApi()
  return api ? await api.ping() : 'pong (dev)'
}

export async function getMachineId(): Promise<string> {
  const api = await waitForApi()
  return api ? await api.get_machine_id() : 'DEV-0000-0000-0000'
}

export async function getLicenseInfo(): Promise<Record<string, unknown>> {
  const api = await waitForApi()
  return api ? await api.get_license_info() : { is_valid: false, status_message: '开发模式', expiry: null, trial_remaining: 0 }
}

export async function activateLicense(code: string): Promise<{ success: boolean; message: string }> {
  const api = await waitForApi()
  return api ? await api.activate_license(code) : { success: false, message: '后端未连接' }
}

export async function loadSettings(): Promise<Record<string, unknown>> {
  const api = await waitForApi()
  return api ? await api.load_settings() : {}
}

export async function saveSettings(settings: Record<string, unknown>): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.save_settings(settings) : { success: true }
}

export async function getProviders(): Promise<ProviderPreset[]> {
  const api = await waitForApi()
  return api ? await api.get_providers() : [
    { id: 'deepseek', name: 'DeepSeek', base_url: '', model: 'deepseek-chat', api_key_hint: 'sk-...' },
    { id: 'qwen', name: '通义千问', base_url: '', model: 'qwen-plus', api_key_hint: 'sk-...' },
  ]
}

export async function selectFiles(): Promise<string[]> {
  const api = await waitForApi()
  return api ? await api.select_files() : []
}

export async function selectDirectory(): Promise<string> {
  const api = await waitForApi()
  return api ? await api.select_directory() : ''
}

export async function openFolder(path: string): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.open_folder(path) : { success: false, error: 'Dev mode' }
}

export async function getHistory(): Promise<HistoryEntry[]> {
  const api = await waitForApi()
  return api ? await api.get_history() : []
}

export async function clearHistory(): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.clear_history() : { success: true }
}

export async function testConnection(
  provider: string, apiKey: string, baseUrl?: string, model?: string
): Promise<{ success: boolean; error?: string; model?: string }> {
  const api = await waitForApi()
  return api
    ? await api.test_connection(provider, apiKey, baseUrl ?? '', model ?? '')
    : { success: true, model: 'dev-mock' }
}

export async function processVideo(
  videoPath: string, settingsOverride?: Record<string, unknown>
): Promise<ProcessResult> {
  const api = await waitForApi()
  return api
    ? await api.process_video(videoPath, settingsOverride)
    : { success: false, error: 'Dev mode — no backend', versions: [], output_files: [] }
}

export async function processBatch(videoPaths: string[]): Promise<ProcessResult[]> {
  const api = await waitForApi()
  return api
    ? await api.process_batch(videoPaths)
    : videoPaths.map(() => ({ success: false, error: 'Dev mode', versions: [], output_files: [] }))
}

export async function cancelProcessing(): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.cancel_processing() : { success: false, error: 'Dev mode' }
}

export async function getEncoderInfo(): Promise<EncoderInfo> {
  const api = await waitForApi()
  return api ? await api.get_encoder_info() : { codec: 'libx264', name: 'Software x264 (dev)', is_hardware: false, extra_params: [] }
}

export async function getMaxParallel(): Promise<number> {
  const api = await waitForApi()
  return api ? await api.get_max_parallel() : 2
}

export async function exportVersions(
  videoPath: string, versionIds: number[], options?: Record<string, unknown>
): Promise<{ success: boolean; files?: unknown[]; error?: string }> {
  const api = await waitForApi()
  return api
    ? await api.export_versions(videoPath, versionIds, options)
    : { success: false, error: 'Dev mode' }
}

export async function checkAsrStatus(engine?: string): Promise<{ ready: boolean; message: string }> {
  const api = await waitForApi()
  return api ? await api.check_asr_status(engine ?? '') : { ready: false, message: '后端未连接' }
}

export async function downloadAsrModel(engine?: string): Promise<{ success: boolean; message: string }> {
  const api = await waitForApi()
  return api ? await api.download_asr_model(engine ?? '') : { success: false, message: '后端未连接' }
}

export async function runBenchmark(): Promise<BenchmarkResult> {
  const api = await waitForApi()
  return api ? await api.run_benchmark() : { max_parallel: 1, cpu_cores: 1, ram_gb: 0, encoder: 'unknown', is_hardware: false, reason: '后端未连接' }
}

export async function previewVideo(filePath: string): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.preview_video(filePath) : { success: false, error: 'Dev mode' }
}

export async function deleteHistoryEntry(timestamp: string): Promise<{ success: boolean; error?: string }> {
  const api = await waitForApi()
  return api ? await api.delete_history_entry(timestamp) : { success: true }
}

export async function generateThumbnail(videoPath: string, timeSec: number = 1.0): Promise<string> {
  const api = await waitForApi()
  return api ? await api.generate_thumbnail(videoPath, timeSec) : ''
}

// ── Progress event listener ────────────────────────────────

export interface ProgressEvent {
  label: string
  percent: number
  index?: number  // video index in batch
  total?: number  // total videos in batch
}

export function onPipelineProgress(callback: (e: ProgressEvent) => void): () => void {
  const handler = (evt: Event) => {
    const detail = (evt as CustomEvent).detail as ProgressEvent
    callback(detail)
  }
  window.addEventListener('pipeline-progress', handler)
  return () => window.removeEventListener('pipeline-progress', handler)
}
