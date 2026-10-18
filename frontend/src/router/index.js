import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import NotFoundView from '../views/NotFoundView.vue'

const routes = [
  {
    path: '/workbench/:projectId?',
    name: 'Workbench',
    component: () => import('../views/WorkbenchView.vue'),
    props: true
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsView.vue')
  },
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/process/:projectId',
    name: 'Process',
    component: () => import('../views/MainView.vue'),
    props: true
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: () => import('../views/SimulationView.vue'),
    props: true
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: () => import('../views/SimulationRunView.vue'),
    props: true
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    component: () => import('../views/ReportView.vue'),
    props: true
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    component: () => import('../views/InteractionView.vue'),
    props: true
  },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFoundView }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
