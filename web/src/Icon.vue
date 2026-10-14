<script setup>
defineProps({ name: String, size: { default: 20 } });
const paths = {
  dashboard: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  analytics: 'M4 20V10m8 10V4m8 16v-7M2 22h20',
  equipment: 'M4 4h16v12H4zM2 20h20M8 16v4m8-4v4M8 8h2m4 0h2M8 12h8',
  orders: 'M9 4H5v17h14V4h-4M9 2h6v4H9zM8 11h8M8 15h8M8 18h4',
  calendar: 'M5 3v4m14-4v4M3 10h18M3 5h18v16H3zM7 14h2m3 0h2m3 0h1M7 18h2m3 0h2',
  directory: 'M3 6h7l2 2h9v12H3zM3 6V4h7l2 2h7v2',
  report: 'M5 2h9l5 5v15H5zM14 2v6h5M9 12h6M9 16h6',
  users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8m8 4a4 4 0 0 1 5 4v2M16 3a4 4 0 0 1 0 8',
  search: 'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14m5-2 6 6',
  plus: 'M12 5v14M5 12h14', close: 'm6 6 12 12M18 6 6 18',
  refresh: 'M20 7a9 9 0 1 0 1 8M20 2v6h-6',
  arrow: 'M5 12h14m-6-6 6 6-6 6', chevron: 'm9 5 7 7-7 7',
  logout: 'M9 3H3v18h6m0-9h12m-5-5 5 5-5 5',
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  upload: 'M12 16V4m-5 5 5-5 5 5M4 17v4h16v-4',
  check: 'm5 12 4 4L20 5', alert: 'M12 3 2 21h20L12 3zm0 6v5m0 3v1',
  bolt: 'm13 2-9 12h7l-1 8L21 9h-8z',
  menu: 'M3 6h18M3 12h18M3 18h18', edit: 'm15 4 5 5M4 20l5-1L21 7l-5-5L4 14z',
  delete: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18m0 4v5l3 2',
  lock: 'M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0v4m-4 4v3',
  settings: 'M3 6h18M3 12h18M3 18h18M7 3v6m10 0v6M9 15v6',
};
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.directory" /></svg></template>
