<template>
  <div class="app-container">
    <AppHeader />
    <ProjectContextBar />

    <main class="app-main"
          :class="{
            'sidebar-collapsed': isSidebarCollapsed,
            'chat-md': store.chatWidth === 'md',
            'chat-lg': store.chatWidth === 'lg'
          }">
      <WorkspaceSidebar
        class="app-sidebar left"
        :collapsed="isSidebarCollapsed"
        @select-project="handleSelectProject"
        @onboard-project="handleOnboardProject"
      >
        <template #agent-list>
          <AgentList
            :agents="store.allAgentsWithOrchestrator"
            :selected-agent-id="store.selectedAgentId"
            @select-agent="handleSelectAgent"
            @add-agent="handleAddAgent"
            @collapse-change="handleSidebarCollapse"
          />
        </template>
      </WorkspaceSidebar>

      <div class="app-content center">
        <!-- Tab bar — always present when flow is available -->
        <div class="center-tabs" :class="{ hidden: !showFlowTab }">
          <button
            class="center-tab"
            :class="{ active: centerView === 'events' }"
            @click="centerView = 'events'"
          >Event Stream</button>
          <button
            class="center-tab"
            :class="{ active: centerView === 'flow' }"
            @click="centerView = 'flow'"
          >Implementation Flow</button>
        </div>

        <!-- Both panels always mounted — pure CSS visibility -->
        <div class="center-panel" :class="{ 'panel-visible': centerView === 'events' }">
          <EventStream
            ref="eventStreamRef"
            :events="store.filteredEventStream"
            :current-filter="store.eventStreamFilter"
            :auto-scroll="true"
            @set-filter="handleSetFilter"
          />
        </div>
        <div class="center-panel" :class="{ 'panel-visible': centerView === 'flow' }">
          <ImplementationFlow
            :visible="centerView === 'flow'"
            @select-feature="handleFeatureSelect"
          />
        </div>
        <FlowFeatureModal
          v-if="selectedFlowFeature"
          :feature="selectedFlowFeature"
          :visible="!!selectedFlowFeature"
          @close="selectedFlowFeature = null"
        />
      </div>

      <div class="app-sidebar right">
        <OrchestratorChat
          :messages="store.chatMessages"
          :is-connected="store.isConnected"
          :is-typing="store.isTyping"
          :auto-scroll="store.autoScroll"
          @send="handleSendMessage"
        />
        <QuestionPanel />
      </div>
    </main>

    <!-- Global Command Input -->
    <GlobalCommandInput
      :visible="store.commandInputVisible"
      @send="handleSendMessage"
    />

    <!-- Onboard Project Modal -->
    <OnboardProjectModal
      :visible="showOnboardModal"
      @close="showOnboardModal = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import AppHeader from './components/AppHeader.vue'
import AgentList from './components/AgentList.vue'
import WorkspaceSidebar from './components/WorkspaceSidebar.vue'
import EventStream from './components/EventStream.vue'
import OrchestratorChat from './components/OrchestratorChat.vue'
import QuestionPanel from './components/QuestionPanel.vue'
import ProjectContextBar from './components/ProjectContextBar.vue'
import GlobalCommandInput from './components/GlobalCommandInput.vue'
import ImplementationFlow from './components/ImplementationFlow.vue'
import FlowFeatureModal from './components/FlowFeatureModal.vue'
import OnboardProjectModal from './components/OnboardProjectModal.vue'
import { useOrchestratorStore } from './stores/orchestratorStore'
import { useWorkspaceStore } from './stores/workspaceStore'
import { useImplementFlowStore } from './stores/implementFlowStore'
import { useKeyboardShortcuts } from './composables/useKeyboardShortcuts'

// Use Pinia store
const store = useOrchestratorStore()
const workspaceStore = useWorkspaceStore()

// Initialize keyboard shortcuts
useKeyboardShortcuts()

// Component refs
const eventStreamRef = ref<InstanceType<typeof EventStream> | null>(null)

// Sidebar collapse state
const isSidebarCollapsed = ref(false)

// Center column tab: 'events' or 'flow'
const centerView = ref<'events' | 'flow'>('events')
const selectedFlowFeature = ref<any>(null)
const showOnboardModal = ref(false)
// Show flow tab only when active project is in implement phase
const showFlowTab = computed(() => {
  const phase = workspaceStore.activeProject?.current_phase
  return phase === 'implement'
})

const flowStore = useImplementFlowStore()

// When project changes or phase changes: auto-switch tabs
watch([() => workspaceStore.activeProjectId, () => workspaceStore.activeProject?.current_phase], ([newProjectId, newPhase]) => {
  if (newPhase === 'implement') {
    centerView.value = 'flow'
  } else {
    // Not in implement phase — switch to events, clear flow store
    centerView.value = 'events'
    flowStore.reset()
  }
})


// Initialize store on mount
onMounted(() => {
  store.initialize()
  workspaceStore.initialize()
})

// Clean up on unmount to prevent duplicate connections during HMR
onUnmounted(() => {
  store.disconnectWebSocket()
})

// Handlers
const handleSelectAgent = (id: string) => {
  store.selectAgent(id)

  // Toggle agent filter in EventStream
  const agent = store.agents.find(a => a.id === id)
  if (agent && eventStreamRef.value) {
    eventStreamRef.value.toggleAgentFilter(agent.name)
  }
}

const handleAddAgent = () => {
  console.log('Add agent clicked')
  // TODO: Open modal to create new agent
}

const handleSetFilter = (filter: string) => {
  store.setEventStreamFilter(filter as any)
}

const handleSendMessage = (message: string) => {
  store.sendUserMessage(message)
}

const handleSidebarCollapse = (isCollapsed: boolean) => {
  isSidebarCollapsed.value = isCollapsed
}

const handleSelectProject = (projectId: string) => {
  console.log('Project selected:', projectId)
}

const handleOnboardProject = () => {
  showOnboardModal.value = true
}

const handleFeatureSelect = (featureId: string) => {
  const feat = flowStore.features[featureId]
  if (feat) {
    selectedFlowFeature.value = feat
  }
}
</script>

<style scoped>
.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Main Layout */
.app-main {
  flex: 1;
  display: grid;
  grid-template-columns: 280px 1fr 418px;
  overflow: hidden;
  transition: grid-template-columns 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Chat width variations */
.app-main.chat-md {
  grid-template-columns: 280px 1fr 518px;
}

.app-main.chat-lg {
  grid-template-columns: 280px 1fr 618px;
}

/* Combined with sidebar collapsed */
.app-main.sidebar-collapsed {
  grid-template-columns: 48px 1fr 418px;
}

.app-main.sidebar-collapsed.chat-md {
  grid-template-columns: 48px 1fr 518px;
}

.app-main.sidebar-collapsed.chat-lg {
  grid-template-columns: 48px 1fr 618px;
}

.app-sidebar,
.app-content {
  height: 100%;
  overflow: hidden;
}

.app-content.center {
  display: flex;
  flex-direction: column;
}

/* Center column tabs */
.center-tabs {
  display: flex;
  gap: 0;
  background: #0d1117;
  border-bottom: 1px solid #21262d;
  flex-shrink: 0;
}

.center-tab {
  padding: 6px 16px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #8b949e;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  font-family: 'SF Mono', 'Fira Code', monospace;
  transition: color 0.15s, border-color 0.15s;
}

.center-tab:hover {
  color: #c9d1d9;
}

.center-tab.active {
  color: #86BC24;
  border-bottom-color: #86BC24;
}

.center-tabs.hidden {
  display: none;
}

/* Panel stacking — only the visible one takes space */
.center-panel {
  display: none;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.center-panel.panel-visible {
  display: flex;
  flex-direction: column;
}

.app-sidebar.right {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-sidebar.right > :first-child {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.app-sidebar.right > .question-panel {
  flex-shrink: 0;
}

/* Responsive */
@media (max-width: 1600px) {
  /* Limit large size on smaller screens */
  .app-main.chat-lg {
    grid-template-columns: 280px 1fr 518px; /* Fall back to medium */
  }

  .app-main.sidebar-collapsed.chat-lg {
    grid-template-columns: 48px 1fr 518px;
  }
}

@media (max-width: 1400px) {
  .app-main {
    grid-template-columns: 260px 1fr 385px;
  }

  .app-main.chat-md {
    grid-template-columns: 260px 1fr 450px; /* Reduced increase */
  }

  .app-main.chat-lg {
    grid-template-columns: 260px 1fr 450px; /* Cap at medium */
  }

  .app-main.sidebar-collapsed {
    grid-template-columns: 48px 1fr 385px;
  }

  .app-main.sidebar-collapsed.chat-md {
    grid-template-columns: 48px 1fr 450px;
  }

  .app-main.sidebar-collapsed.chat-lg {
    grid-template-columns: 48px 1fr 450px;
  }
}

@media (max-width: 1200px) {
  /* Force small size on narrow screens */
  .app-main,
  .app-main.chat-md,
  .app-main.chat-lg {
    grid-template-columns: 240px 1fr 352px;
  }

  .app-main.sidebar-collapsed,
  .app-main.sidebar-collapsed.chat-md,
  .app-main.sidebar-collapsed.chat-lg {
    grid-template-columns: 48px 1fr 352px;
  }
}

@media (max-width: 1024px) {
  .app-main,
  .app-main.chat-md,
  .app-main.chat-lg {
    grid-template-columns: 220px 1fr 330px;
  }

  .app-main.sidebar-collapsed,
  .app-main.sidebar-collapsed.chat-md,
  .app-main.sidebar-collapsed.chat-lg {
    grid-template-columns: 48px 1fr 330px;
  }
}

/* Mobile Responsive Design (< 650px) */
@media (max-width: 650px) {
  /* Force 3-column layout with collapsed sidebars */
  .app-main,
  .app-main.chat-md,
  .app-main.chat-lg,
  .app-main.sidebar-collapsed,
  .app-main.sidebar-collapsed.chat-md,
  .app-main.sidebar-collapsed.chat-lg {
    grid-template-columns: 48px 1fr 280px;
  }

  /* Force AgentList to always be collapsed on mobile */
  .app-sidebar.left {
    width: 48px !important;
    min-width: 48px !important;
  }

  /* OrchestratorChat small mode on mobile */
  .app-sidebar.right {
    width: 280px !important;
    min-width: 280px !important;
  }
}

/* Very narrow mobile devices - hide chat for more event space */
@media (max-width: 400px) {
  .app-main,
  .app-main.chat-md,
  .app-main.chat-lg,
  .app-main.sidebar-collapsed,
  .app-main.sidebar-collapsed.chat-md,
  .app-main.sidebar-collapsed.chat-lg {
    grid-template-columns: 48px 1fr 0;
  }

  .app-sidebar.right {
    display: none;
  }
}
</style>
