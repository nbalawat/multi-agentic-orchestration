<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="modal-title">Onboard Project</h3>
          <button class="modal-close" @click="$emit('close')">&times;</button>
        </div>

        <form class="modal-body" @submit.prevent="handleSubmit">
          <!-- Project Name -->
          <div class="form-group">
            <label class="form-label">Project Name</label>
            <input
              v-model="form.name"
              type="text"
              class="form-input"
              placeholder="my-project"
              required
            />
          </div>

          <!-- Source: GitHub URL or Local Path -->
          <div class="form-group">
            <label class="form-label">Source</label>
            <div class="source-tabs">
              <button
                type="button"
                class="source-tab"
                :class="{ active: sourceType === 'github' }"
                @click="sourceType = 'github'"
              >GitHub URL</button>
              <button
                type="button"
                class="source-tab"
                :class="{ active: sourceType === 'local' }"
                @click="sourceType = 'local'"
              >Local Path</button>
            </div>
            <input
              v-if="sourceType === 'github'"
              v-model="form.repoUrl"
              type="text"
              class="form-input"
              placeholder="https://github.com/org/repo"
            />
            <input
              v-if="sourceType === 'local'"
              v-model="form.repoPath"
              type="text"
              class="form-input"
              placeholder="/Users/you/projects/my-project"
              required
            />
            <p v-if="sourceType === 'github'" class="form-hint">
              The repo will be cloned to a local path. Also provide the local path below.
            </p>
          </div>

          <!-- Local Path (shown when GitHub is selected too) -->
          <div v-if="sourceType === 'github'" class="form-group">
            <label class="form-label">Local Clone Path</label>
            <input
              v-model="form.repoPath"
              type="text"
              class="form-input"
              placeholder="/Users/you/projects/my-project"
              required
            />
          </div>

          <!-- Archetype -->
          <div class="form-group">
            <label class="form-label">Project Archetype</label>
            <div class="archetype-grid">
              <button
                v-for="arch in archetypes"
                :key="arch.id"
                type="button"
                class="archetype-option"
                :class="{ selected: form.archetype === arch.id }"
                @click="form.archetype = arch.id"
              >
                <span class="arch-icon">{{ arch.icon }}</span>
                <span class="arch-name">{{ arch.label }}</span>
                <span class="arch-desc">{{ arch.desc }}</span>
              </button>
            </div>
          </div>

          <!-- Error -->
          <div v-if="error" class="form-error">{{ error }}</div>

          <!-- Actions -->
          <div class="form-actions">
            <button type="button" class="btn-cancel" @click="$emit('close')">Cancel</button>
            <button type="submit" class="btn-submit" :disabled="isSubmitting">
              {{ isSubmitting ? 'Onboarding...' : 'Onboard Project' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useWorkspaceStore } from '../stores/workspaceStore'

defineProps<{ visible: boolean }>()
const emit = defineEmits<{ close: [] }>()

const workspaceStore = useWorkspaceStore()

const sourceType = ref<'github' | 'local'>('local')
const isSubmitting = ref(false)
const error = ref('')

const form = reactive({
  name: '',
  repoPath: '',
  repoUrl: '',
  archetype: 'greenfield',
})

const archetypes = [
  { id: 'greenfield', label: 'Greenfield', icon: '🌱', desc: 'New project from scratch' },
  { id: 'brownfield', label: 'Brownfield', icon: '🏗️', desc: 'Extend existing codebase' },
  { id: 'data-modernization', label: 'Data Modernization', icon: '📊', desc: 'Database & ETL migration' },
  { id: 'reverse-engineering', label: 'Reverse Engineering', icon: '🔍', desc: 'Understand undocumented code' },
]

async function handleSubmit() {
  error.value = ''

  if (!form.name.trim()) {
    error.value = 'Project name is required'
    return
  }
  if (!form.repoPath.trim()) {
    error.value = 'Local path is required'
    return
  }
  if (!workspaceStore.activeWorkspaceId) {
    error.value = 'No workspace selected'
    return
  }

  isSubmitting.value = true
  try {
    await workspaceStore.onboardProject(workspaceStore.activeWorkspaceId, {
      name: form.name.trim(),
      repo_path: form.repoPath.trim(),
      archetype: form.archetype,
      repo_url: form.repoUrl.trim() || undefined,
    })

    // Reset form and close
    form.name = ''
    form.repoPath = ''
    form.repoUrl = ''
    form.archetype = 'greenfield'
    emit('close')
  } catch (e: any) {
    error.value = e?.message || e?.response?.data?.detail || 'Failed to onboard project'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 10px;
  width: 520px;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #21262d;
}

.modal-title {
  font-size: 16px;
  font-weight: 600;
  color: #e6edf3;
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  color: #8b949e;
  font-size: 24px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.modal-close:hover { color: #e6edf3; }

.modal-body {
  padding: 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #8b949e;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  background: #0d1117;
  color: #e6edf3;
  border: 1px solid #30363d;
  border-radius: 6px;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  outline: none;
  box-sizing: border-box;
}
.form-input:focus {
  border-color: #58a6ff;
  box-shadow: 0 0 0 2px rgba(88, 166, 255, 0.15);
}
.form-input::placeholder { color: #484f58; }

.form-hint {
  font-size: 11px;
  color: #484f58;
  margin-top: 4px;
}

.source-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 8px;
  border: 1px solid #30363d;
  border-radius: 6px;
  overflow: hidden;
}

.source-tab {
  flex: 1;
  padding: 6px 12px;
  background: #0d1117;
  color: #8b949e;
  border: none;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s, color 0.15s;
}
.source-tab:not(:last-child) { border-right: 1px solid #30363d; }
.source-tab:hover { color: #c9d1d9; }
.source-tab.active {
  background: #1c2333;
  color: #58a6ff;
}

.archetype-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.archetype-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.archetype-option:hover {
  border-color: #58a6ff;
  background: #1c2333;
}
.archetype-option.selected {
  border-color: #86BC24;
  background: rgba(134, 188, 36, 0.1);
}

.arch-icon { font-size: 20px; }
.arch-name {
  font-size: 12px;
  font-weight: 600;
  color: #e6edf3;
}
.arch-desc {
  font-size: 10px;
  color: #8b949e;
  text-align: center;
}

.form-error {
  padding: 8px 12px;
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid rgba(248, 81, 73, 0.3);
  border-radius: 6px;
  color: #f85149;
  font-size: 12px;
  margin-bottom: 16px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid #21262d;
}

.btn-cancel {
  padding: 8px 16px;
  background: transparent;
  color: #8b949e;
  border: 1px solid #30363d;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
}
.btn-cancel:hover { border-color: #8b949e; color: #c9d1d9; }

.btn-submit {
  padding: 8px 20px;
  background: #86BC24;
  color: #0d1117;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
}
.btn-submit:hover { background: #9ad42e; }
.btn-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
