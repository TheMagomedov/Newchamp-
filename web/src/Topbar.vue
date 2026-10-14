<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import Icon from './Icon.vue';
import { request, query } from './api.js';
const props = defineProps({ title: String, user: Object, initials: String, role: String, connection: String });
const emit = defineEmits(['navigate', 'menu', 'theme', 'logout']);
const search = ref(''); const results = ref([]); const searching = ref(false); const searchOpen = ref(false); const searchError = ref('');
const notifications = ref([]); const notificationsOpen = ref(false); const profileOpen = ref(false); const notificationError = ref('');
const storageKey = `toir-read-${props.user?.Id}`;
const read = ref([]);
try { read.value = JSON.parse(localStorage.getItem(storageKey) || '[]'); } catch { read.value = []; }
const unread = computed(() => notifications.value.filter(item => !read.value.includes(item.id)).length);
const state = computed(() => ({ connected: 'Онлайн · SSE', connecting: 'Подключение…', reconnecting: 'Переподключение…', offline: 'Нет связи · повтор' })[props.connection] || 'Подключение…');
let debounce; let poll; let searchId = 0;
async function find() {
  const id = ++searchId; searchOpen.value = true; searchError.value = '';
  if (search.value.trim().length < 2) { results.value = []; return; }
  searching.value = true;
  try { const result = await request(`search?${query({ q: search.value.trim() })}`); if (id === searchId) results.value = result.items || []; }
  catch (e) { if (id === searchId) searchError.value = e.message; }
  finally { if (id === searchId) searching.value = false; }
}
function queueSearch() { clearTimeout(debounce); debounce = setTimeout(find, 300); }
async function loadNotifications() {
  try { const result = await request('notifications'); notifications.value = result.items || []; notificationError.value = ''; }
  catch (e) { notificationError.value = e.message; }
}
function markRead(id) { read.value = [...new Set([...read.value, id])].slice(-500); localStorage.setItem(storageKey, JSON.stringify(read.value)); }
function openNotification(item) { markRead(item.id); notificationsOpen.value = false; emit('navigate', { page: item.resource, id: item.entity_id }); }
function openSearch(item) { searchOpen.value = false; search.value = ''; emit('navigate', { page: item.resource, id: item.id }); }
function close(event) { if (event.key === 'Escape') { searchOpen.value = false; notificationsOpen.value = false; profileOpen.value = false; } }
onMounted(() => { loadNotifications(); poll = setInterval(loadNotifications, 60000); window.addEventListener('toir-revision', loadNotifications); window.addEventListener('keydown', close); });
onUnmounted(() => { clearInterval(poll); clearTimeout(debounce); searchId++; window.removeEventListener('toir-revision', loadNotifications); window.removeEventListener('keydown', close); });
</script>
<template>
  <header class="topbar topbar-expanded">
    <div class="breadcrumb"><button class="icon-button menu-toggle" aria-label="Свернуть или открыть меню" @click="emit('menu')"><Icon name="menu" /></button><button class="top-logo" @click="emit('navigate', 'dashboard')" aria-label="ТОиР — главная"><Icon name="bolt" :size="18"/>ТОиР</button><span class="breadcrumb-title">{{ title }}</span></div>
    <form class="global-search" role="search" @submit.prevent="find"><Icon name="search" :size="17"/><input v-model="search" type="search" placeholder="Заявка, оборудование, мастер…" aria-label="Глобальный поиск по номеру заявки, инвентарному номеру или ФИО" @input="queueSearch" @focus="searchOpen = true"><button v-if="search" type="button" class="icon-button" @click="searchOpen = false; search = ''" aria-label="Очистить поиск"><Icon name="close" :size="15"/></button>
      <div v-if="searchOpen && search.length >= 2" class="top-dropdown search-results"><p v-if="searching" class="list-empty">Поиск…</p><p v-else-if="searchError" class="alert error" role="alert">{{ searchError }}</p><template v-else><button v-for="item in results" :key="`${item.resource}-${item.id}`" type="button" @click="openSearch(item)"><strong>{{ item.label }}</strong><small>{{ item.subtitle }}</small></button><p v-if="!results.length" class="list-empty">Ничего не найдено</p></template></div>
    </form>
    <div class="topbar-tools"><span class="connection-state" :class="{ offline: connection !== 'connected' }" role="status"><span class="tiny-dot"></span>{{ state }}</span><button class="icon-button theme-toggle" @click="emit('theme')" title="Переключить тему" aria-label="Переключить тему"><Icon name="settings" :size="18"/></button>
      <div class="top-menu"><button class="icon-button notification-button" :aria-label="`Уведомления: ${unread} непрочитанных`" :aria-expanded="notificationsOpen" @click="notificationsOpen = !notificationsOpen; profileOpen = false"><Icon name="alert" :size="19"/><span class="notification-count">{{ unread }}</span></button><div v-if="notificationsOpen" class="top-dropdown notifications-dropdown"><div class="dropdown-heading"><strong>Уведомления</strong><button class="text-button" @click="notifications.forEach(item => markRead(item.id))">Прочитать все</button></div><p v-if="notificationError" class="alert error">{{ notificationError }}</p><button v-for="item in notifications" :key="item.id" :class="{ unread: !read.includes(item.id) }" @click="openNotification(item)"><strong>{{ item.title }}</strong><small>{{ item.message }}</small></button><p v-if="!notifications.length && !notificationError" class="list-empty">Новых событий нет</p></div></div>
      <div class="top-menu"><button class="top-avatar" :aria-expanded="profileOpen" aria-label="Открыть профиль пользователя" @click="profileOpen = !profileOpen; notificationsOpen = false">{{ initials }}</button><div v-if="profileOpen" class="top-dropdown profile-dropdown"><strong>{{ user?.Name || user?.Email }}</strong><small>{{ role }}</small><small>{{ user?.Email }}</small><button @click="emit('logout')"><Icon name="logout" :size="16"/>Выйти из системы</button></div></div>
    </div>
  </header>
</template>
