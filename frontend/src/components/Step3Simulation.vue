<template>
  <div class="simulation-panel">
    <!-- Top Control Bar -->
    <div class="control-bar">
      <div class="status-group">
        <!-- Twitter 平台进度 -->
        <div class="platform-status twitter" :class="{ active: runStatus.twitter_running, completed: runStatus.twitter_completed }">
          <div class="platform-header">
            <svg class="platform-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
            </svg>
            <span class="platform-name">{{ $t('studio.plaza') }}</span>
            <span v-if="runStatus.twitter_completed" class="status-badge">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </span>
          </div>
          <div class="platform-stats">
            <span class="stat">
              <span class="stat-label">{{ $t('studio.round') }}</span>
              <span class="stat-value mono">{{ runStatus.twitter_current_round || 0 }}<span class="stat-total">/{{ runStatus.total_rounds || maxRounds || '-' }}</span></span>
            </span>
            <span class="stat">
              <span class="stat-label">{{ $t('studio.time') }}</span>
              <span class="stat-value mono">{{ twitterElapsedTime }}</span>
            </span>
            <span class="stat">
              <span class="stat-label">{{ $t('studio.actions') }}</span>
              <span class="stat-value mono">{{ runStatus.twitter_actions_count || 0 }}</span>
            </span>
          </div>
          <!-- 可用动作提示 -->
          <div class="actions-tooltip">
            <div class="tooltip-title">Available Actions</div>
            <div class="tooltip-actions">
              <span class="tooltip-action">POST</span>
              <span class="tooltip-action">LIKE</span>
              <span class="tooltip-action">REPOST</span>
              <span class="tooltip-action">QUOTE</span>
              <span class="tooltip-action">FOLLOW</span>
              <span class="tooltip-action">IDLE</span>
            </div>
          </div>
        </div>
        
        <!-- Reddit 平台进度 -->
        <div class="platform-status reddit" :class="{ active: runStatus.reddit_running, completed: runStatus.reddit_completed }">
          <div class="platform-header">
            <svg class="platform-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
            </svg>
            <span class="platform-name">{{ $t('studio.community') }}</span>
            <span v-if="runStatus.reddit_completed" class="status-badge">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </span>
          </div>
          <div class="platform-stats">
            <span class="stat">
              <span class="stat-label">{{ $t('studio.round') }}</span>
              <span class="stat-value mono">{{ runStatus.reddit_current_round || 0 }}<span class="stat-total">/{{ runStatus.total_rounds || maxRounds || '-' }}</span></span>
            </span>
            <span class="stat">
              <span class="stat-label">{{ $t('studio.time') }}</span>
              <span class="stat-value mono">{{ redditElapsedTime }}</span>
            </span>
            <span class="stat">
              <span class="stat-label">{{ $t('studio.actions') }}</span>
              <span class="stat-value mono">{{ runStatus.reddit_actions_count || 0 }}</span>
            </span>
          </div>
          <!-- 可用动作提示 -->
          <div class="actions-tooltip">
            <div class="tooltip-title">Available Actions</div>
            <div class="tooltip-actions">
              <span class="tooltip-action">POST</span>
              <span class="tooltip-action">COMMENT</span>
              <span class="tooltip-action">LIKE</span>
              <span class="tooltip-action">DISLIKE</span>
              <span class="tooltip-action">SEARCH</span>
              <span class="tooltip-action">TREND</span>
              <span class="tooltip-action">FOLLOW</span>
              <span class="tooltip-action">MUTE</span>
              <span class="tooltip-action">REFRESH</span>
              <span class="tooltip-action">IDLE</span>
            </div>
          </div>
        </div>
      </div>

      <div class="action-controls">
        <button v-if="canStart" data-testid="start-simulation" class="action-btn" @click="doStartSimulation" :disabled="isStarting">
          {{ isStarting ? $t('common.processing') : $t('workbench.start') }}
        </button>
        <button v-if="phase === 1" class="action-btn" @click="handleStopSimulation" :disabled="isStopping || ['stopping', 'finalizing'].includes(runStatus.runner_status)">
          {{ runStatus.runner_status === 'stopping' ? $t('workbench.stopping') : isStopping ? $t('common.processing') : $t('studio.stopSimulation') }}
        </button>
        <button 
          class="action-btn primary"
          :disabled="!canGenerateReport || isGeneratingReport"
          @click="handleNextStep"
        >
          <span v-if="isGeneratingReport" class="loading-spinner-small"></span>
          {{ isGeneratingReport ? $t('step3.generatingReportBtn') : $t('step3.startGenerateReportBtn') }}
          <span v-if="!isGeneratingReport" class="arrow-icon">→</span>
        </button>
      </div>
    </div>

    <p class="generation-notice">{{ $t('workbench.costNotice') }}</p>
    <div v-if="stateNotice" class="workflow-error" role="alert">{{ stateNotice }} <button class="action-btn" @click="initializeSimulation">{{ $t('workbench.refresh') }}</button></div>
    <p v-if="startError || actionError" class="workflow-error" role="alert">{{ startError || actionError }}</p>
    <div v-if="readError" class="workflow-error" role="alert">{{ readError }} <button class="action-btn" @click="initializeSimulation">{{ $t('workbench.refresh') }}</button></div>

    <!-- Main Content: Dual Timeline -->
    <div class="main-content-area" ref="scrollContainer">
      <!-- Timeline Header -->
      <div class="timeline-header" v-if="allActions.length > 0">
        <div class="timeline-stats">
          <span class="total-count">TOTAL EVENTS: <span class="mono">{{ allActions.length }}</span></span>
          <span class="platform-breakdown">
            <span class="breakdown-item twitter">
              <svg class="mini-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
              <span class="mono">{{ twitterActionsCount }}</span>
            </span>
            <span class="breakdown-divider">/</span>
            <span class="breakdown-item reddit">
              <svg class="mini-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
              <span class="mono">{{ redditActionsCount }}</span>
            </span>
          </span>
        </div>
      </div>
      
      <!-- Timeline Feed -->
      <div class="timeline-feed">
        <div class="timeline-axis"></div>
        
        <TransitionGroup name="timeline-item">
          <div 
            v-for="action in chronologicalActions" 
            :key="action._uniqueId || action.id || `${action.timestamp}-${action.agent_id}`" 
            class="timeline-item"
            :class="action.platform"
          >
            <div class="timeline-marker">
              <div class="marker-dot"></div>
            </div>
            
            <div class="timeline-card">
              <div class="card-header">
                <div class="agent-info">
                  <div class="avatar-placeholder">{{ (action.agent_name || 'A')[0] }}</div>
                  <span class="agent-name">{{ action.agent_name }}</span>
                </div>
                
                <div class="header-meta">
                  <div class="platform-indicator">
                    <svg v-if="action.platform === 'twitter'" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
                    <svg v-else viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                  </div>
                  <div class="action-badge" :class="getActionTypeClass(action.action_type)">
                    {{ getActionTypeLabel(action.action_type) }}
                  </div>
                </div>
              </div>
              
              <div class="card-body">
                <!-- CREATE_POST: 发布帖子 -->
                <div v-if="action.action_type === 'CREATE_POST' && action.action_args?.content" class="content-text main-text">
                  {{ action.action_args.content }}
                </div>

                <!-- QUOTE_POST: 引用帖子 -->
                <template v-if="action.action_type === 'QUOTE_POST'">
                  <div v-if="action.action_args?.quote_content" class="content-text">
                    {{ action.action_args.quote_content }}
                  </div>
                  <div v-if="action.action_args?.original_content" class="quoted-block">
                    <div class="quote-header">
                      <svg class="icon-small" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                      <span class="quote-label">@{{ action.action_args.original_author_name || 'User' }}</span>
                    </div>
                    <div class="quote-text">
                      {{ truncateContent(action.action_args.original_content, 150) }}
                    </div>
                  </div>
                </template>

                <!-- REPOST: 转发帖子 -->
                <template v-if="action.action_type === 'REPOST'">
                  <div class="repost-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>
                    <span class="repost-label">Reposted from @{{ action.action_args?.original_author_name || 'User' }}</span>
                  </div>
                  <div v-if="action.action_args?.original_content" class="repost-content">
                    {{ truncateContent(action.action_args.original_content, 200) }}
                  </div>
                </template>

                <!-- LIKE_POST: 点赞帖子 -->
                <template v-if="action.action_type === 'LIKE_POST'">
                  <div class="like-info">
                    <svg class="icon-small filled" viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                    <span class="like-label">Liked @{{ action.action_args?.post_author_name || 'User' }}'s post</span>
                  </div>
                  <div v-if="action.action_args?.post_content" class="liked-content">
                    "{{ truncateContent(action.action_args.post_content, 120) }}"
                  </div>
                </template>

                <!-- CREATE_COMMENT: 发表评论 -->
                <template v-if="action.action_type === 'CREATE_COMMENT'">
                  <div v-if="action.action_args?.content" class="content-text">
                    {{ action.action_args.content }}
                  </div>
                  <div v-if="action.action_args?.post_id" class="comment-context">
                    <svg class="icon-small" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                    <span>Reply to post #{{ action.action_args.post_id }}</span>
                  </div>
                </template>

                <!-- SEARCH_POSTS: 搜索帖子 -->
                <template v-if="action.action_type === 'SEARCH_POSTS'">
                  <div class="search-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                    <span class="search-label">Search Query:</span>
                    <span class="search-query">"{{ action.action_args?.query || '' }}"</span>
                  </div>
                </template>

                <!-- FOLLOW: 关注用户 -->
                <template v-if="action.action_type === 'FOLLOW'">
                  <div class="follow-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line></svg>
                    <span class="follow-label">Followed @{{ action.action_args?.target_user || action.action_args?.user_id || 'User' }}</span>
                  </div>
                </template>

                <!-- UPVOTE / DOWNVOTE -->
                <template v-if="action.action_type === 'UPVOTE_POST' || action.action_type === 'DOWNVOTE_POST'">
                  <div class="vote-info">
                    <svg v-if="action.action_type === 'UPVOTE_POST'" class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>
                    <svg v-else class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
                    <span class="vote-label">{{ action.action_type === 'UPVOTE_POST' ? 'Upvoted' : 'Downvoted' }} Post</span>
                  </div>
                  <div v-if="action.action_args?.post_content" class="voted-content">
                    "{{ truncateContent(action.action_args.post_content, 120) }}"
                  </div>
                </template>

                <!-- DO_NOTHING: 无操作（静默） -->
                <template v-if="action.action_type === 'DO_NOTHING'">
                  <div class="idle-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                    <span class="idle-label">Action Skipped</span>
                  </div>
                </template>

                <!-- 通用回退：未知类型或有 content 但未被上述处理 -->
                <div v-if="!['CREATE_POST', 'QUOTE_POST', 'REPOST', 'LIKE_POST', 'CREATE_COMMENT', 'SEARCH_POSTS', 'FOLLOW', 'UPVOTE_POST', 'DOWNVOTE_POST', 'DO_NOTHING'].includes(action.action_type) && action.action_args?.content" class="content-text">
                  {{ action.action_args.content }}
                </div>
              </div>

              <div class="card-footer">
                <span class="time-tag">R{{ action.round_num }} • {{ formatActionTime(action.timestamp) }}</span>
                <!-- Platform tag removed as it is in header now -->
              </div>
            </div>
          </div>
        </TransitionGroup>

        <div v-if="allActions.length === 0" class="waiting-state">
          <div v-if="(!statusLoaded || phase === 1) && !startError && !readError" class="pulse-ring" aria-hidden="true"></div>
          <span>{{ $t(startError ? 'common.failed' : phase >= 2 ? 'common.noData' : statusLoaded && phase === 0 ? 'common.pending' : 'common.loading') }}</span>
        </div>
      </div>
    </div>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SIMULATION MONITOR</span>
        <span class="log-id">{{ simulationId || 'NO_SIMULATION' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  startSimulation,
  stopSimulation,
  getRunStatus,
  getRunStatusDetail
} from '../api/simulation'
import { generateReport } from '../api/report'

const { t } = useI18n()

const props = defineProps({
  simulationId: String,
  maxRounds: Number, // 从Step2传入的最大轮数
  minutesPerRound: {
    type: Number,
    default: 30 // 默认每轮30分钟
  },
  projectData: Object,
  graphData: Object,
  systemLogs: Array
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

const router = useRouter()

// State
const isGeneratingReport = ref(false)
const phase = ref(0) // 0: 未开始, 1: 运行中, 2: 已完成
const isStarting = ref(false)
const isStopping = ref(false)
const startError = ref(null)
const actionError = ref('')
const readError = ref('')
const statusLoaded = ref(false)
const finalizingSnapshot = ref(false)
const runStatus = ref({})
const allActions = ref([]) // 所有动作（增量累积）
const actionIds = ref(new Set()) // 用于去重的动作ID集合
const scrollContainer = ref(null)
const activeStatuses = new Set(['starting', 'running', 'stopping', 'finalizing'])
const incompleteStatuses = new Set(['failed', 'stopped', 'interrupted', 'needs_review'])
const canStart = computed(() => statusLoaded.value && runStatus.value.runner_status === 'idle' && !readError.value)
const canGenerateReport = computed(() => runStatus.value.runner_status === 'completed' && runStatus.value.graph_ready === true && !readError.value && !finalizingSnapshot.value)
const stateNotice = computed(() => {
  const status = runStatus.value.runner_status
  if (incompleteStatuses.has(status)) return t(`workbench.${status}`) + '. ' + t('workbench.incomplete') + (runStatus.value.error ? `: ${runStatus.value.error}` : '')
  if (status === 'completed' && runStatus.value.graph_ready !== true) return t('workbench.graphNotReady')
  if (statusLoaded.value && !['idle', 'completed', ...activeStatuses].includes(status)) return t('workbench.unknownState')
  return ''
})

// Computed
// 按时间顺序显示动作（最新的在最后面，即底部）
const chronologicalActions = computed(() => {
  return allActions.value
})

// 各平台动作计数
const twitterActionsCount = computed(() => {
  return allActions.value.filter(a => a.platform === 'twitter').length
})

const redditActionsCount = computed(() => {
  return allActions.value.filter(a => a.platform === 'reddit').length
})

// 格式化模拟流逝时间（根据轮次和每轮分钟数计算）
const formatElapsedTime = (currentRound) => {
  if (!currentRound || currentRound <= 0) return '0h 0m'
  const totalMinutes = currentRound * props.minutesPerRound
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours}h ${minutes}m`
}

// Twitter平台的模拟流逝时间
const twitterElapsedTime = computed(() => {
  return formatElapsedTime(runStatus.value.twitter_current_round || 0)
})

// Reddit平台的模拟流逝时间
const redditElapsedTime = computed(() => {
  return formatElapsedTime(runStatus.value.reddit_current_round || 0)
})

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

// 重置所有状态（用于重新启动模拟）
let mounted = true
let generation = 0
let stateVersion = 0
let statusTimer = null
let detailTimer = null
let statusRequest = null
let detailRequest = null
const current = (token, id) => mounted && token === generation && id === props.simulationId
const stopPolling = () => {
  clearInterval(statusTimer)
  clearInterval(detailTimer)
  statusTimer = detailTimer = null
}
const startPolling = () => {
  if (!mounted || !activeStatuses.has(runStatus.value.runner_status)) return
  if (!statusTimer) statusTimer = setInterval(fetchRunStatus, 2000)
  if (!detailTimer) detailTimer = setInterval(fetchRunStatusDetail, 3000)
}
const resetAllState = () => {
  generation++
  stateVersion++
  stopPolling()
  statusRequest = detailRequest = null
  phase.value = 0
  runStatus.value = {}
  allActions.value = []
  actionIds.value = new Set()
  statusLoaded.value = false
  readError.value = ''
  startError.value = null
  actionError.value = ''
  isStarting.value = isStopping.value = isGeneratingReport.value = false
  finalizingSnapshot.value = false
}
const fetchRunStatusDetail = async (finalSnapshot = false) => {
  const token = generation
  const id = props.simulationId
  if (!current(token, id) || !id) return false
  if (detailRequest) {
    if (!finalSnapshot) return detailRequest
    await detailRequest
    if (!current(token, id)) return false
  }
  const request = (async () => {
    try {
      const res = await getRunStatusDetail(id)
      if (!current(token, id)) return false
      if (!res.success || !res.data) throw new Error(res.error || t('common.unknownError'))
      for (const action of res.data.all_actions || []) {
        const actionId = action.id || `${action.timestamp}-${action.platform}-${action.agent_id}-${action.action_type}`
        if (!actionIds.value.has(actionId)) {
          actionIds.value.add(actionId)
          allActions.value.push({ ...action, _uniqueId: actionId })
        }
      }
      return true
    } catch (err) {
      if (current(token, id)) readError.value = t('workbench.readFailed', { error: err.message })
      return false
    }
  })()
  detailRequest = request
  try { return await request } finally { if (detailRequest === request) detailRequest = null }
}
const applyRunStatus = async (data, token, id) => {
  if (!current(token, id)) return
  const previous = runStatus.value
  runStatus.value = data
  statusLoaded.value = true
  const status = data.runner_status
  for (const [platform, label] of [['twitter', 'Plaza'], ['reddit', 'Community']]) {
    if (data[`${platform}_current_round`] > (previous[`${platform}_current_round`] || 0)) addLog(`[${label}] R${data[`${platform}_current_round`]}/${data.total_rounds || '-'} | A:${data[`${platform}_actions_count`] || 0}`)
  }
  if (previous.runner_status !== status && status === 'completed') addLog(t('log.simCompleted'))
  if (previous.runner_status !== status && incompleteStatuses.has(status)) addLog(t(`workbench.${status}`))
  if (activeStatuses.has(status)) {
    phase.value = 1
    emit('update-status', status)
    startPolling()
  } else {
    phase.value = status === 'completed' ? 2 : status === 'idle' ? 0 : 3
    emit('update-status', status || 'needs_review')
    stopPolling()
    if (status !== 'idle') {
      finalizingSnapshot.value = true
      await fetchRunStatusDetail(true)
      if (current(token, id)) finalizingSnapshot.value = false
    }
  }
}
const fetchRunStatus = async () => {
  const token = generation
  const id = props.simulationId
  const version = stateVersion
  if (!current(token, id) || !id) return false
  if (statusRequest) return statusRequest
  const request = (async () => {
    try {
      const res = await getRunStatus(id)
      if (!current(token, id) || version !== stateVersion) return false
      if (!res.success || !res.data) throw new Error(res.error || t('common.unknownError'))
      readError.value = ''
      await applyRunStatus(res.data, token, id)
      return true
    } catch (err) {
      if (current(token, id)) {
        readError.value = t('workbench.readFailed', { error: err.message })
        emit('update-status', 'error')
      }
      return false
    }
  })()
  statusRequest = request
  try { return await request } finally { if (statusRequest === request) statusRequest = null }
}
const doStartSimulation = async () => {
  if (!canStart.value || isStarting.value) return
  const token = generation
  const id = props.simulationId
  isStarting.value = true
  startError.value = null
  addLog(t('log.startingDualSim'))
  try {
    // Recheck before the explicit action; another tab may already have started it.
    if (!await fetchRunStatus() || !current(token, id) || !canStart.value) return
    stateVersion++
    const params = { simulation_id: id, platform: 'parallel', force: false, enable_graph_memory_update: true }
    if (props.maxRounds) params.max_rounds = props.maxRounds
    const res = await startSimulation(params)
    if (!current(token, id)) return
    if (!res.success || !res.data) throw new Error(res.error || t('common.unknownError'))
    addLog(t('log.engineStarted'))
    await applyRunStatus(res.data, token, id)
    if (current(token, id)) await fetchRunStatus()
  } catch (err) {
    if (current(token, id)) { startError.value = err.message; emit('update-status', 'error') }
  } finally {
    if (current(token, id)) isStarting.value = false
  }
}
const handleStopSimulation = async () => {
  if (!mounted || isStopping.value || !['starting', 'running'].includes(runStatus.value.runner_status)) return
  const token = generation
  const id = props.simulationId
  actionError.value = ''
  isStopping.value = true
  stateVersion++
  addLog(t('log.stoppingSim'))
  try {
    const res = await stopSimulation({ simulation_id: id })
    if (!current(token, id)) return
    if (!res.success) throw new Error(res.error || t('common.unknownError'))
    await applyRunStatus({ ...runStatus.value, ...res.data, runner_status: res.data?.runner_status || 'stopping', graph_ready: false }, token, id)
  } catch (err) {
    if (current(token, id)) actionError.value = t('log.stopException', { error: err.message })
  } finally {
    if (current(token, id)) isStopping.value = false
  }
}

// Helpers
const getActionTypeLabel = (type) => {
  const labels = {
    'CREATE_POST': 'POST',
    'REPOST': 'REPOST',
    'LIKE_POST': 'LIKE',
    'CREATE_COMMENT': 'COMMENT',
    'LIKE_COMMENT': 'LIKE',
    'DO_NOTHING': 'IDLE',
    'FOLLOW': 'FOLLOW',
    'SEARCH_POSTS': 'SEARCH',
    'QUOTE_POST': 'QUOTE',
    'UPVOTE_POST': 'UPVOTE',
    'DOWNVOTE_POST': 'DOWNVOTE'
  }
  return labels[type] || type || 'UNKNOWN'
}

const getActionTypeClass = (type) => {
  const classes = {
    'CREATE_POST': 'badge-post',
    'REPOST': 'badge-action',
    'LIKE_POST': 'badge-action',
    'CREATE_COMMENT': 'badge-comment',
    'LIKE_COMMENT': 'badge-action',
    'QUOTE_POST': 'badge-post',
    'FOLLOW': 'badge-meta',
    'SEARCH_POSTS': 'badge-meta',
    'UPVOTE_POST': 'badge-action',
    'DOWNVOTE_POST': 'badge-action',
    'DO_NOTHING': 'badge-idle'
  }
  return classes[type] || 'badge-default'
}

const truncateContent = (content, maxLength = 100) => {
  if (!content) return ''
  if (content.length > maxLength) return content.substring(0, maxLength) + '...'
  return content
}

const formatActionTime = (timestamp) => {
  if (!timestamp) return ''
  try {
    return new Date(timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

const handleNextStep = async () => {
  if (!canGenerateReport.value || isGeneratingReport.value) return
  const token = generation
  const id = props.simulationId
  actionError.value = ''
  isGeneratingReport.value = true
  addLog(t('log.startingReportGen'))
  try {
    const res = await generateReport({ simulation_id: id, force_regenerate: false })
    if (!current(token, id)) return
    if (!res.success || !res.data?.report_id) throw new Error(res.error || t('common.unknownError'))
    await router.push({ name: 'Report', params: { reportId: res.data.report_id } })
  } catch (err) {
    if (current(token, id)) actionError.value = t('log.reportGenException', { error: err.message })
  } finally {
    if (current(token, id)) isGeneratingReport.value = false
  }
}

// Scroll log to bottom
const logContent = ref(null)
watch(() => props.systemLogs?.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})

const initializeSimulation = async () => {
  if (!mounted || !props.simulationId) return
  const token = generation
  const id = props.simulationId
  if (await fetchRunStatus() && current(token, id) && activeStatuses.has(runStatus.value.runner_status)) await fetchRunStatusDetail()
}
watch(() => props.simulationId, () => {
  resetAllState()
  initializeSimulation()
})
onMounted(initializeSimulation)
onUnmounted(() => {
  mounted = false
  generation++
  stopPolling()
})
</script>

<style scoped>
.generation-notice { margin: 12px 20px; color: var(--studio-muted); font-size: 14px; line-height: 1.7; }

.workflow-error {
  flex-shrink: 0;
  margin: 12px 24px 0;
  padding: 12px 16px;
  border: 1px solid var(--studio-line, #e3e5e4);
  border-left: 3px solid var(--theme-error-ink, #a63b32);
  border-radius: 8px;
  background: var(--theme-error-surface, #fdf0ee);
  color: var(--theme-error-ink, #a63b32);
  font-size: 14px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.simulation-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--theme-surface, #FFFFFF);
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  overflow: hidden;
}

/* --- Control Bar --- */
.control-bar {
  background: var(--theme-surface, #FFF);
  padding: 12px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--theme-line, #EAEAEA);
  z-index: 10;
  height: 64px;
}

.status-group {
  display: flex;
  gap: 12px;
}

/* Platform Status Cards */
.platform-status {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 4px;
  background: var(--theme-surface-soft, #FAFAFA);
  border: 1px solid var(--theme-line, #EAEAEA);
  opacity: 0.7;
  transition: all 0.3s;
  min-width: 140px;
  position: relative;
  cursor: pointer;
}

.platform-status.active {
  opacity: 1;
  border-color: var(--theme-ink, #333);
  background: var(--theme-surface, #FFF);
}

.platform-status.completed {
  opacity: 1;
  border-color: var(--theme-success-line, #1A936F);
  background: var(--theme-success-surface, #F2FAF6);
}

/* Actions Tooltip */
.actions-tooltip {
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-top: 8px;
  padding: 10px 14px;
  background: var(--theme-surface-filled, #000);
  color: var(--theme-on-filled, #FFF);
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  opacity: 0;
  visibility: hidden;
  transition: all 0.2s ease;
  z-index: 100;
  min-width: 180px;
  pointer-events: none;
}

.actions-tooltip::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-bottom: 6px solid var(--theme-ink, #000);
}

.platform-status:hover .actions-tooltip {
  opacity: 1;
  visibility: visible;
}

.tooltip-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--theme-muted, #999);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}

.tooltip-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tooltip-action {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
  color: var(--theme-on-filled, #FFF);
  letter-spacing: 0.03em;
}

.platform-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}

.platform-name {
  font-size: 11px;
  font-weight: 700;
  color: var(--theme-ink, #000);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.platform-status.twitter .platform-icon { color: var(--theme-ink, #000); }
.platform-status.reddit .platform-icon { color: var(--theme-ink, #000); }

.platform-stats {
  display: flex;
  gap: 10px;
}

.stat {
  display: flex;
  align-items: baseline;
  gap: 3px;
}

.stat-label {
  font-size: 8px;
  color: var(--theme-muted, #999);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 11px;
  font-weight: 600;
  color: var(--theme-ink, #333);
}

.stat-total, .stat-unit {
  font-size: 9px;
  color: var(--theme-muted, #999);
  font-weight: 400;
}

.status-badge {
  margin-left: auto;
  color: var(--theme-success-ink, #1A936F);
  display: flex;
  align-items: center;
}

/* Action Button */
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  font-size: 13px;
  font-weight: 600;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.action-btn.primary {
  background: var(--theme-surface-filled, #000);
  color: var(--theme-on-filled, #FFF);
}

.action-btn.primary:hover:not(:disabled) {
  background: var(--theme-surface-filled, #333);
}

.action-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* --- Main Content Area --- */
.main-content-area {
  flex: 1;
  overflow-y: auto;
  position: relative;
  background: var(--theme-surface, #FFF);
}

/* Timeline Header */
.timeline-header {
  position: sticky;
  top: 0;
  background: var(--theme-overlay, rgba(255, 255, 255, 0.9));
  backdrop-filter: blur(8px);
  padding: 12px 24px;
  border-bottom: 1px solid var(--theme-line, #EAEAEA);
  z-index: 5;
  display: flex;
  justify-content: center;
}

.timeline-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 11px;
  color: var(--theme-muted, #666);
  background: var(--theme-surface-soft, #F5F5F5);
  padding: 4px 12px;
  border-radius: 20px;
}

.total-count {
  font-weight: 600;
  color: var(--theme-ink, #333);
}

.platform-breakdown {
  display: flex;
  align-items: center;
  gap: 8px;
}

.breakdown-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.breakdown-divider { color: var(--theme-faint, #DDD); }
.breakdown-item.twitter { color: var(--theme-ink, #000); }
.breakdown-item.reddit { color: var(--theme-ink, #000); }

/* --- Timeline Feed --- */
.timeline-feed {
  padding: 24px 0;
  position: relative;
  min-height: 100%;
  max-width: 900px;
  margin: 0 auto;
}

.timeline-axis {
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--theme-surface-soft, #EAEAEA); /* Cleaner line */
  transform: translateX(-50%);
}

.timeline-item {
  display: flex;
  justify-content: center;
  margin-bottom: 32px;
  position: relative;
  width: 100%;
}

.timeline-marker {
  position: absolute;
  left: 50%;
  top: 24px;
  width: 10px;
  height: 10px;
  background: var(--theme-surface, #FFF);
  border: 1px solid var(--theme-line, #CCC);
  border-radius: 50%;
  transform: translateX(-50%);
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
}

.marker-dot {
  width: 4px;
  height: 4px;
  background: var(--theme-surface-raised, #CCC);
  border-radius: 50%;
}

.timeline-item.twitter .marker-dot { background: var(--theme-surface-filled, #000); }
.timeline-item.reddit .marker-dot { background: var(--theme-surface-filled, #000); }
.timeline-item.twitter .timeline-marker { border-color: var(--theme-ink, #000); }
.timeline-item.reddit .timeline-marker { border-color: var(--theme-ink, #000); }

/* Card Layout */
.timeline-card {
  width: calc(100% - 48px);
  background: var(--theme-surface, #FFF);
  border-radius: 2px;
  padding: 16px 20px;
  border: 1px solid var(--theme-line, #EAEAEA);
  box-shadow: 0 2px 10px rgba(0,0,0,0.02);
  position: relative;
  transition: all 0.2s;
}

.timeline-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  border-color: var(--theme-line, #DDD);
}

/* Left side (Twitter) */
.timeline-item.twitter {
  justify-content: flex-start;
  padding-right: 50%;
}
.timeline-item.twitter .timeline-card {
  margin-left: auto;
  margin-right: 32px; /* Gap from axis */
}

/* Right side (Reddit) */
.timeline-item.reddit {
  justify-content: flex-end;
  padding-left: 50%;
}
.timeline-item.reddit .timeline-card {
  margin-right: auto;
  margin-left: 32px; /* Gap from axis */
}

/* Card Content Styles */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--theme-line, #F5F5F5);
}

.agent-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar-placeholder {
  width: 24px;
  height: 24px;
  background: var(--theme-surface-filled, #000);
  color: var(--theme-on-filled, #FFF);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.agent-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--theme-ink, #000);
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.platform-indicator {
  color: var(--theme-muted, #999);
  display: flex;
  align-items: center;
}

.action-badge {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 2px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border: 1px solid transparent;
}

/* Monochromatic Badges */
.badge-post { background: var(--theme-surface-soft, #F0F0F0); color: var(--theme-ink, #333); border-color: var(--theme-line, #E0E0E0); }
.badge-comment { background: var(--theme-surface-soft, #F0F0F0); color: var(--theme-muted, #666); border-color: var(--theme-line, #E0E0E0); }
.badge-action { background: var(--theme-surface, #FFF); color: var(--theme-muted, #666); border: 1px solid var(--theme-line, #E0E0E0); }
.badge-meta { background: var(--theme-surface-soft, #FAFAFA); color: var(--theme-muted, #999); border: 1px dashed var(--theme-line, #DDD); }
.badge-idle { opacity: 0.5; }

.content-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--theme-ink, #333);
  margin-bottom: 10px;
}

.content-text.main-text {
  font-size: 14px;
  color: var(--theme-ink, #000);
}

/* Info Blocks (Quote, Repost, etc) */
.quoted-block, .repost-content {
  background: var(--theme-surface-soft, #F9F9F9);
  border: 1px solid var(--theme-line, #EEE);
  padding: 10px 12px;
  border-radius: 2px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--theme-ink, #555);
}

.quote-header, .repost-info, .like-info, .search-info, .follow-info, .vote-info, .idle-info, .comment-context {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 11px;
  color: var(--theme-muted, #666);
}

.icon-small {
  color: var(--theme-muted, #999);
}
.icon-small.filled {
  color: var(--theme-muted, #999); /* Keep icons neutral unless highlighted */
}

.search-query {
  font-family: 'JetBrains Mono', monospace;
  background: var(--theme-surface-soft, #F0F0F0);
  padding: 0 4px;
  border-radius: 2px;
}

.card-footer {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  font-size: 10px;
  color: var(--theme-faint, #BBB);
  font-family: 'JetBrains Mono', monospace;
}

/* Waiting State */
.waiting-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  color: var(--theme-faint, #CCC);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.pulse-ring {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid var(--theme-line, #EAEAEA);
  animation: ripple 2s infinite;
}

@keyframes ripple {
  0% { transform: scale(0.8); opacity: 1; border-color: var(--theme-line, #CCC); }
  100% { transform: scale(2.5); opacity: 0; border-color: var(--theme-line, #EAEAEA); }
}

/* Animation */
.timeline-item-enter-active,
.timeline-item-leave-active {
  transition: all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1);
}

.timeline-item-enter-from {
  opacity: 0;
  transform: translateY(20px);
}

.timeline-item-leave-to {
  opacity: 0;
}

/* Logs */
.system-logs {
  background: var(--theme-surface-filled, #000);
  color: var(--theme-faint, #DDD);
  padding: 16px;
  font-family: 'JetBrains Mono', monospace;
  border-top: 1px solid var(--theme-ink, #222);
  flex-shrink: 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid var(--theme-ink, #333);
  padding-bottom: 8px;
  margin-bottom: 8px;
  font-size: 10px;
  color: var(--theme-muted, #666);
}

.log-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 100px;
  overflow-y: auto;
  padding-right: 4px;
}

.log-content::-webkit-scrollbar { width: 4px; }
.log-content::-webkit-scrollbar-thumb { background: var(--theme-surface-filled, #333); border-radius: 2px; }

.log-line {
  font-size: 11px;
  display: flex;
  gap: 12px;
  line-height: 1.5;
}

.log-time { color: var(--theme-ink, #555); min-width: 75px; }
.log-msg { color: var(--theme-faint, #BBB); word-break: break-all; }
.mono { font-family: 'JetBrains Mono', monospace; }

/* Loading spinner for button */
.loading-spinner-small {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: var(--theme-line, #FFF);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-right: 6px;
}
</style>
