<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import Icon from './Icon.vue';
import Dashboard from './Dashboard.vue';
import ResourceView from './ResourceView.vue';
import Reports from './Reports.vue';
import Topbar from './Topbar.vue';
import { connectEvents } from './events.js';
import { request, getSession, setSession } from './api.js';

const session = ref(getSession());
const page = ref(location.hash.slice(1).split('?')[0] || 'dashboard');
const route = ref(Object.fromEntries(new URLSearchParams(location.hash.split('?')[1] || '')));
const connection = ref('connecting'); let stopEvents;
const collapsed = ref(localStorage.getItem('toir-collapsed') === 'true');
const resources = ref([]); const lookups = ref({});
const booting = ref(false); const bootError = ref(''); const busy = ref(false);
const email = ref('admin@toir.local'); const password = ref(''); const showPassword = ref(false); const error = ref('');
const sidebarOpen = ref(false); const toast = ref(''); let toastTimer;
const theme = ref(localStorage.getItem('toir-theme') || 'light');
const directoryKey = ref(route.value.directory || 'materials');
const revision = ref(0);
const primary = [
  { key: 'dashboard', label: 'Обзор предприятия', icon: 'dashboard' },
  { key: 'analytics', label: 'Аналитика', icon: 'analytics' },
  { key: 'work-orders', label: 'Заявки на работы', icon: 'orders' },
  { key: 'equipment', label: 'Оборудование', icon: 'equipment' },
  { key: 'schedule', label: 'График обслуживания', icon: 'calendar' },
  { key: 'directories', label: 'Справочники', icon: 'directory' },
  { key: 'reports', label: 'Отчёты и экспорт', icon: 'report' },
];
const directoryResources = computed(() => resources.value.filter(x => !['equipment', 'work-orders', 'schedule', 'users'].includes(x.key)));
const activeResource = computed(() => resources.value.find(x => x.key === (page.value === 'directories' ? directoryKey.value : page.value)));
const title = computed(() => primary.find(x => x.key === page.value)?.label || (page.value === 'users' ? 'Пользователи' : 'Обзор предприятия'));
const roleNames = { admin: 'Администратор', engineer: 'Инженер ТОиР', master: 'Мастер цеха', member: 'Член бригады', manager: 'Руководитель' };
const role = computed(() => roleNames[session.value?.user?.Role] || session.value?.user?.Role || 'Пользователь');
const initials = computed(() => (session.value?.user?.Name || session.value?.user?.Email || 'ТП').split(/[ @]+/).slice(0, 2).map(x => x[0]).join('').toUpperCase());
function notify(message) { toast.value = message; clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.value = '', 4500); }
function navigate(target) {
  const item = typeof target === 'string' ? { page: target } : target;
  const resource = item.page || item.resource || 'dashboard';
  const parameters = { ...item.filters, ...(item.id ? { id: item.id } : {}) };
  if (!['dashboard', 'analytics', 'work-orders', 'equipment', 'schedule', 'reports', 'users', 'directories'].includes(resource)) {
    directoryKey.value = resource; parameters.directory = resource; page.value = 'directories';
  } else page.value = resource;
  route.value = parameters;
  location.hash = `${page.value}${Object.keys(parameters).length ? '?' + new URLSearchParams(parameters) : ''}`;
  sidebarOpen.value = false;
}
function hashChange() { page.value = location.hash.slice(1).split('?')[0] || 'dashboard'; route.value = Object.fromEntries(new URLSearchParams(location.hash.split('?')[1] || '')); if (route.value.directory) directoryKey.value = route.value.directory; }
function toggleMenu() { if (window.innerWidth <= 760) sidebarOpen.value = !sidebarOpen.value; else { collapsed.value = !collapsed.value; localStorage.setItem('toir-collapsed', String(collapsed.value)); } }
function startEvents() {
  stopEvents?.();
  stopEvents = connectEvents({ onStatus: value => { connection.value = value; }, onRevision: detail => { revision.value++; window.dispatchEvent(new CustomEvent('toir-revision', { detail })); } });
}
async function bootstrap() {
  if (!session.value) return;
  booting.value = true; bootError.value = '';
  try {
    const [meta, refs] = await Promise.all([request('meta'), request('lookups')]);
    resources.value = meta.resources || []; lookups.value = refs;
    if (!directoryResources.value.some(x => x.key === directoryKey.value)) directoryKey.value = directoryResources.value[0]?.key;
    startEvents();
  } catch (e) { bootError.value = e.message; }
  finally { booting.value = false; }
}
async function login() {
  busy.value = true; error.value = '';
  try { const data = await request('auth/login', { method: 'POST', body: { email: email.value.trim(), password: password.value } }); setSession(data); password.value = ''; await bootstrap(); }
  catch (e) { error.value = e.message; }
  finally { busy.value = false; }
}
async function logout() {
  busy.value = true;
  try { if (session.value?.refresh_token) await request('auth/logout', { method: 'POST', body: { refresh_token: session.value.refresh_token } }); }
  catch (e) { notify(e.message); }
  finally { stopEvents?.(); setSession(null); resources.value = []; busy.value = false; }
}
async function changed(message = 'Изменения сохранены') { notify(message); revision.value++; try { lookups.value = await request('lookups'); } catch {} }
function syncSession() { session.value = getSession(); if (!session.value) stopEvents?.(); }
function toggleTheme() { theme.value = theme.value === 'light' ? 'dark' : 'light'; localStorage.setItem('toir-theme', theme.value); }
onMounted(() => { window.addEventListener('toir-session', syncSession); window.addEventListener('hashchange', hashChange); bootstrap(); });
onUnmounted(() => { stopEvents?.(); window.removeEventListener('toir-session', syncSession); window.removeEventListener('hashchange', hashChange); clearTimeout(toastTimer); });
</script>

<template>
  <div class="app" :data-theme="theme">
    <div v-if="!session" class="login-page">
      <section class="login-story">
        <div class="brand brand-light"><span class="brand-mark"><Icon name="bolt" :size="23" /></span><div>ТОиР<span>ПРОФ</span></div></div>
        <div class="login-copy"><p class="eyebrow">ПРОМЫШЛЕННОСТЬ ПОД КОНТРОЛЕМ</p><h1>Надёжная работа<br>начинается здесь.</h1><p>Оборудование, ремонтные бригады и обслуживание — в одной системе.</p><div class="login-tags"><span>Учёт оборудования</span><span>Планирование ТО</span><span>Аналитика</span></div></div>
        <div class="industrial-art" aria-hidden="true"><div v-for="i in 6" :key="i" :style="{ '--i': i }"></div><svg viewBox="0 0 500 140"><path d="M0 95H70V65H105V100H180V35H220V80H285V15H340V60H400V25H500" /></svg></div>
        <div class="login-footer"><span class="tiny-dot"></span> АО «Приволжский машиностроительный завод»</div>
      </section>
      <section class="login-side"><form class="login-card" @submit.prevent="login"><span class="overline">РАБОЧЕЕ ПРОСТРАНСТВО</span><h2>Вход в систему</h2><p class="muted">Используйте вашу учётную запись ТОиР-Проф.</p><label>Электронная почта<input v-model="email" type="email" autocomplete="username" required placeholder="name@company.ru"></label><label>Пароль<span class="password-wrap"><input v-model="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" required minlength="8" placeholder="Введите пароль"><button type="button" @click="showPassword = !showPassword">{{ showPassword ? 'Скрыть' : 'Показать' }}</button></span></label><div v-if="error" class="alert error" role="alert"><Icon name="alert" />{{ error }}</div><button class="button primary login-submit" :disabled="busy">{{ busy ? 'Выполняется вход…' : 'Войти в систему' }}<Icon name="arrow" /></button><div class="login-note"><Icon name="lock" :size="16" />Доступ определяется ролью пользователя</div></form><span class="version-note">ТОиР-Проф / Учебная версия 1.0</span></section>
    </div>
    <div v-else class="workspace" :class="{ 'sidebar-collapsed': collapsed }">
      <div v-if="sidebarOpen" class="mobile-shade" @click="sidebarOpen = false"></div>
      <aside class="sidebar" :class="{ open: sidebarOpen }">
        <button class="brand brand-light" @click="navigate('dashboard')"><span class="brand-mark"><Icon name="bolt" :size="22" /></span><div>ТОиР<span>ПРОФ</span></div></button>
        <div class="enterprise"><div class="enterprise-icon">ПМЗ</div><div><strong>Приволжский завод</strong><span>Управление ТОиР</span></div></div>
        <span class="nav-label">РАБОЧЕЕ ПРОСТРАНСТВО</span>
        <nav aria-label="Основная навигация"><button v-for="item in primary" :key="item.key" :title="item.label" :aria-label="item.label" :class="{ active: page === item.key }" @click="navigate(item.key)"><Icon :name="item.icon" /><span>{{ item.label }}</span><span v-if="page === item.key" class="nav-active-dot"></span></button><button v-if="resources.some(x => x.key === 'users')" title="Пользователи" aria-label="Пользователи" :class="{ active: page === 'users' }" @click="navigate('users')"><Icon name="users" /><span>Пользователи</span></button></nav>
        <div class="sidebar-bottom"><div class="system-label"><span class="tiny-dot"></span> Единая система обслуживания</div><div class="profile"><span class="avatar">{{ initials }}</span><div><strong>{{ session.user?.Name || session.user?.Email }}</strong><small>{{ role }}</small></div><button class="icon-button" @click="logout" title="Выйти" aria-label="Выйти из системы" :disabled="busy"><Icon name="logout" :size="18" /></button></div></div>
      </aside>
      <div class="main-shell">
        <Topbar :title="title" :user="session.user" :initials="initials" :role="role" :connection="connection" @menu="toggleMenu" @navigate="navigate" @theme="toggleTheme" @logout="logout" />
        <main class="main-content">
          <div v-if="booting" class="loading-panel"><span class="spinner"></span>Подготавливаем рабочее пространство…</div>
          <div v-else-if="bootError" class="empty-panel"><Icon name="alert" :size="32" /><h2>Не удалось загрузить систему</h2><p>{{ bootError }}</p><button class="button primary" @click="bootstrap">Повторить</button></div>
          <template v-else>
            <Dashboard v-if="page === 'dashboard' || page === 'analytics'" :key="page" :analytics="page === 'analytics'" :lookups="lookups" :user="session.user" @navigate="navigate" @notify="notify" />
            <Reports v-else-if="page === 'reports'" :lookups="lookups" @notify="notify" />
            <template v-else><div v-if="page === 'directories'" class="directory-tabs" role="tablist" aria-label="Справочники"><button v-for="item in directoryResources" :key="item.key" role="tab" :aria-selected="directoryKey === item.key" :class="{ active: directoryKey === item.key }" @click="directoryKey = item.key">{{ item.label }}</button></div><ResourceView v-if="activeResource" :key="activeResource.key + JSON.stringify(route)" :initial-filters="route" :initial-id="route.id" @navigate="navigate" :resource="activeResource" :lookups="lookups" :user="session.user" @changed="changed" @notify="notify" /><div v-else class="empty-panel"><Icon name="lock" :size="32" /><h2>Раздел недоступен</h2><p>Для вашей роли этот раздел не предусмотрен.</p><button class="button" @click="navigate('dashboard')">Вернуться к обзору</button></div></template>
          </template>
        </main>
        <footer class="app-footer"><span>ТОиР-Проф · Система управления обслуживанием</span><span>АО «ПМЗ»</span></footer>
      </div>
    </div>
    <Transition name="toast"><div v-if="toast" class="toast" role="status"><Icon name="check" :size="18" />{{ toast }}<button class="icon-button" aria-label="Закрыть уведомление" @click="toast = ''"><Icon name="close" :size="16" /></button></div></Transition>
  </div>
</template>
