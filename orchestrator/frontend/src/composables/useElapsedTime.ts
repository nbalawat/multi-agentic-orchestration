import { ref, onScopeDispose } from 'vue'

export function useElapsedTime() {
  const now = ref(Date.now())
  const interval = setInterval(() => { now.value = Date.now() }, 1000)
  onScopeDispose(() => clearInterval(interval))

  function formatElapsed(since: string | null): string {
    if (!since) return ''
    const elapsed = Math.floor((now.value - new Date(since).getTime()) / 1000)
    if (elapsed < 0) return ''
    if (elapsed < 60) return `${elapsed}s`
    if (elapsed < 3600) return `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`
    return `${Math.floor(elapsed / 3600)}h ${Math.floor((elapsed % 3600) / 60)}m`
  }

  return { now, formatElapsed }
}
