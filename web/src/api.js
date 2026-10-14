const KEY = 'toir-prof-session';
let session = null;
try { session = JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch { sessionStorage.removeItem(KEY); }
let refreshPromise;
export const getSession = () => session;
export function setSession(value) {
  session = value;
  if (value) sessionStorage.setItem(KEY, JSON.stringify(value)); else sessionStorage.removeItem(KEY);
  window.dispatchEvent(new Event('toir-session'));
}
export class ApiError extends Error {
  constructor(message, status, code, details) { super(message); this.status = status; this.code = code; this.details = details; }
}
async function refresh() {
  if (!session?.refresh_token) return false;
  if (!refreshPromise) refreshPromise = (async () => {
    try {
      const res = await fetch('/api/auth/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: session.refresh_token }) });
      const body = await res.json();
      if (!res.ok || !body.success) return false;
      setSession({ ...session, ...body.data });
      return true;
    } catch { return false; }
    finally { refreshPromise = undefined; }
  })();
  return refreshPromise;
}
export async function request(path, options = {}, retry = true) {
  const endpoint = path.replace(/^\/api\//, '').split('?')[0];
  const headers = { ...options.headers };
  if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`;
  if (options.body != null && !(options.body instanceof FormData) && !options.raw) headers['Content-Type'] = 'application/json';
  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method?.toUpperCase()) && !headers['Idempotency-Key']) headers['Idempotency-Key'] = crypto.randomUUID();
  let response;
  try { response = await fetch(path.startsWith('/api/') ? path : `/api/${path}`, { ...options, headers, body: options.raw || options.body == null || options.body instanceof FormData ? options.body : JSON.stringify(options.body) }); }
  catch (cause) {
    if (cause.name === 'AbortError') throw cause;
    logFailure(endpoint, options.method, 0, 'NETWORK');
    throw new ApiError('Нет связи с сервером. Проверьте подключение и повторите действие.', 0, 'NETWORK');
  }
  if (response.status === 401 && retry && !['auth/login', 'auth/refresh'].includes(endpoint)) {
    if (await refresh()) {
      // Refresh rotates both tokens. Logout must revoke the new session, not the old one.
      const body = endpoint === 'auth/logout' ? { ...options.body, refresh_token: session.refresh_token } : options.body;
      return request(path, { ...options, headers, body }, false);
    }
    setSession(null);
  }
  if (response.status === 204) return null;
  let body;
  if (response.headers.get('content-type')?.includes('application/json')) {
    try { body = await response.json(); }
    catch { logFailure(endpoint, options.method, response.status, 'INVALID_RESPONSE'); throw new ApiError('Сервер вернул некорректный ответ. Повторите запрос позднее.', response.status, 'INVALID_RESPONSE'); }
  }
  if (!response.ok || body?.success === false) {
    const detail = body?.message || (Array.isArray(body?.detail) ? body.detail.map(x => x.msg).join('; ') : body?.detail);
    logFailure(endpoint, options.method, response.status, body?.error_code);
    const fallback = { 400: 'Проверьте заполнение полей.', 403: 'У вашей роли нет прав для этого действия.', 404: 'Запись не найдена. Обновите список.', 409: 'Запись изменена другим пользователем. Обновите карточку.', 429: 'Слишком много запросов. Подождите и повторите.', 500: 'Ошибка сервера. Данные формы сохранены, повторите позднее.' };
    throw new ApiError(detail || fallback[response.status] || `Не удалось выполнить запрос (${response.status}).`, response.status, body?.error_code, body?.data);
  }
  return body ? body.data ?? body : response;
}
function logFailure(endpoint, method = 'GET', status, code) {
  // Never log headers, URL queries, bodies, credentials or server-provided personal data.
  const route = endpoint.replace(/(download\/)[^/]+/, '$1:token');
  console.error('[ТОиР API]', { method, endpoint: route, status, code: code || 'HTTP_ERROR', stack: new Error('API request failed').stack });
}
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  return value;
}
async function payloadFingerprint(body) {
  if (body instanceof Blob) {
    const digest = await crypto.subtle.digest('SHA-256', await body.arrayBuffer());
    return `blob:${Array.from(new Uint8Array(digest), x => x.toString(16).padStart(2, '0')).join('')}`;
  }
  return JSON.stringify(canonical(body ?? null));
}
// One instance per UI action/form: failed manual retries keep their key until reset,
// a different path/payload, or a confirmed successful response.
export function createMutationAttempt() {
  let pending = null;
  return {
    reset() { pending = null; },
    async run(path, options) {
      const fingerprint = `${options.method?.toUpperCase() || 'GET'}:${path}:${await payloadFingerprint(options.body)}`;
      if (!pending || pending.fingerprint !== fingerprint) pending = { fingerprint, key: crypto.randomUUID() };
      const key = pending.key;
      const result = await request(path, { ...options, headers: { ...options.headers, 'Idempotency-Key': key } });
      if (pending?.key === key) pending = null;
      return result;
    },
  };
}
export const query = values => new URLSearchParams(Object.entries(values).filter(([, v]) => v !== '' && v != null)).toString();
export async function download(path, filename) {
  const result = await request(path);
  if (result instanceof Response) {
    const blob = await result.blob();
    const disposition = result.headers.get('content-disposition') || '';
    const match = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = match ? decodeURIComponent(match[1]) : filename;
    document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } else if (result?.url || result?.download_url) {
    await download(result.url || result.download_url, filename);
  } else throw new ApiError('Сервер не вернул файл для скачивания.', 0, 'EXPORT');
}
