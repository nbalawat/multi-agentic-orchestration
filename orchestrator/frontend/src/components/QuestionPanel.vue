<template>
  <div v-if="store.hasPendingQuestion" class="question-panel">
    <div class="question-header">
      <span class="question-icon">&#x2753;</span>
      <span class="question-title">
        {{ store.pendingQuestionAgentName || 'Orchestrator' }} needs your input
      </span>
    </div>

    <div
      v-for="(question, qIdx) in store.pendingQuestions"
      :key="qIdx"
      class="question-block"
    >
      <p class="question-text">{{ question.question }}</p>

      <div class="options-grid">
        <button
          v-for="(option, oIdx) in question.options"
          :key="oIdx"
          class="option-btn"
          :class="{ selected: selectedAnswers[question.question] === option.label }"
          @click="selectOption(question.question, option.label)"
        >
          <span class="option-label">{{ option.label }}</span>
          <span class="option-desc">{{ option.description }}</span>
        </button>
      </div>

      <!-- Free text input -->
      <div class="free-text">
        <input
          type="text"
          :placeholder="'Or type your own answer...'"
          v-model="freeTextAnswers[question.question]"
          @keydown.enter="selectFreeText(question.question)"
          class="free-text-input"
        />
      </div>
    </div>

    <div class="question-actions">
      <button class="submit-btn" :disabled="!allAnswered" @click="submitAnswers">
        Submit Answers
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from "vue";
import { useOrchestratorStore } from "../stores/orchestratorStore";

const store = useOrchestratorStore();
const selectedAnswers = reactive<Record<string, string>>({});
const freeTextAnswers = reactive<Record<string, string>>({});

const allAnswered = computed(() => {
  return store.pendingQuestions.every(
    (q: any) => selectedAnswers[q.question] || freeTextAnswers[q.question]
  );
});

function selectOption(question: string, label: string) {
  selectedAnswers[question] = label;
  freeTextAnswers[question] = ""; // Clear free text when option selected
}

function selectFreeText(question: string) {
  if (freeTextAnswers[question]) {
    selectedAnswers[question] = freeTextAnswers[question];
  }
}

async function submitAnswers() {
  const answers: Record<string, string> = {};
  for (const q of store.pendingQuestions) {
    answers[q.question] =
      freeTextAnswers[q.question] || selectedAnswers[q.question] || "";
  }
  await store.submitQuestionAnswer(answers);
  // Clear local state
  Object.keys(selectedAnswers).forEach((k) => delete selectedAnswers[k]);
  Object.keys(freeTextAnswers).forEach((k) => delete freeTextAnswers[k]);
}
</script>

<style scoped>
.question-panel {
  background: var(--bg-tertiary, #1a1d23);
  border: 2px solid #f59e0b;
  border-radius: 8px;
  padding: 16px;
  margin: 8px;
  max-height: 50vh;
  overflow-y: auto;
  flex-shrink: 0;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.question-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
  color: #f59e0b;
}

.question-icon {
  font-size: 20px;
}

.question-title {
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.question-block {
  margin-bottom: 16px;
}

.question-text {
  color: #e2e8f0;
  font-size: 14px;
  margin-bottom: 8px;
  font-weight: 500;
}

.options-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.option-btn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 10px 14px;
  background: var(--bg-secondary, #111318);
  border: 1px solid var(--border-color, #2d3748);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  width: 100%;
  text-align: left;
}

.option-btn:hover {
  border-color: #f59e0b;
  background: rgba(245, 158, 11, 0.05);
}

.option-btn.selected {
  border-color: #f59e0b;
  background: rgba(245, 158, 11, 0.15);
}

.option-label {
  color: #e2e8f0;
  font-weight: 600;
  font-size: 13px;
}

.option-desc {
  color: #94a3b8;
  font-size: 12px;
  margin-top: 2px;
}

.free-text {
  margin-top: 8px;
}

.free-text-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary, #111318);
  border: 1px solid var(--border-color, #2d3748);
  border-radius: 6px;
  color: #e2e8f0;
  font-size: 13px;
  outline: none;
}

.free-text-input:focus {
  border-color: #f59e0b;
}

.question-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
  position: sticky;
  bottom: 0;
  background: var(--bg-tertiary, #1a1d23);
  padding-top: 8px;
}

.submit-btn {
  padding: 8px 20px;
  background: #f59e0b;
  color: #000;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.submit-btn:hover:not(:disabled) {
  background: #d97706;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
