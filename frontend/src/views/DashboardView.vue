<template>
  <div class="p-4 space-y-6">
    <h1 class="text-3xl font-bold text-blue-600">Metrastics Dashboard</h1>

    <section class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="md:col-span-2 bg-white shadow rounded p-4">
        <div class="flex justify-between items-center mb-2">
          <h2 class="font-semibold text-lg">Listener & Local Node Status</h2>
          <button @click="fetchConnectionStatus" class="text-sm text-blue-600 hover:underline">Refresh</button>
        </div>
        <div v-if="connectionStatus">
          <p><strong>Listener Status:</strong> {{ connectionStatus.status }}</p>
          <div v-if="connectionStatus.local_node_info">
            <p><strong>Local Node:</strong> {{ connectionStatus.local_node_info.name }}
              (<code class="bg-gray-100 px-1 rounded">{{ connectionStatus.local_node_info.node_id }}</code>)
            </p>
            <p><strong>Channels Mapped:</strong> {{ connectionStatus.local_node_info.channel_map }}</p>
          </div>
          <p v-if="connectionStatus.error" class="text-red-600">{{ connectionStatus.error }}</p>
        </div>
        <div v-else>Loading status...</div>
      </div>

      <div class="bg-white shadow rounded p-4">
        <div class="flex justify-between items-center mb-2">
          <h2 class="font-semibold text-lg">Avg Signals (12h)</h2>
          <button @click="fetchAverageSignalStats" class="text-sm text-blue-600 hover:underline">Refresh</button>
        </div>
        <div v-if="averageSignal">
          <p><strong>Avg. SNR:</strong> {{ averageSignal.avg_snr ?? 'N/A' }}</p>
          <p><strong>Avg. RSSI:</strong> {{ averageSignal.avg_rssi ?? 'N/A' }}</p>
          <small class="text-gray-500">Based on {{ averageSignal.count ?? 'N/A' }} packets.</small>
        </div>
        <div v-else>Loading stats...</div>
      </div>
    </section>

    <section class="bg-white shadow rounded p-4">
      <div class="flex justify-between items-center mb-2">
        <h2 class="font-semibold text-lg">Counters</h2>
        <button @click="fetchCounters" class="text-sm text-blue-600 hover:underline">Refresh</button>
      </div>
      <div v-if="counters" class="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
        <div>
          <p class="text-xl font-bold">{{ counters.total_nodes ?? 0 }}</p>
          <p class="text-xs uppercase">Nodes</p>
        </div>
        <div>
          <p class="text-xl font-bold">{{ counters.total_packets ?? 0 }}</p>
          <p class="text-xs uppercase">Packets</p>
        </div>
        <div>
          <p class="text-xl font-bold">{{ counters.message_packets ?? 0 }}</p>
          <p class="text-xs uppercase">Messages</p>
        </div>
        <div>
          <p class="text-xl font-bold">{{ counters.position_packets ?? 0 }}</p>
          <p class="text-xs uppercase">Positions</p>
        </div>
      </div>
      <div v-else>Loading counters...</div>
    </section>

    <section class="bg-white shadow rounded p-4">
      <div class="flex justify-between items-center mb-2">
        <h2 class="font-semibold text-lg">Nodes</h2>
        <button @click="fetchNodes" class="text-sm text-blue-600 hover:underline">Refresh</button>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-100">
            <tr>
              <th class="px-2 py-1 text-left">Name</th>
              <th class="px-2 py-1 text-left">ID</th>
              <th class="px-2 py-1 text-left">HW</th>
              <th class="px-2 py-1 text-left">Last Heard</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="node in nodes" :key="node.node_id" class="odd:bg-white even:bg-gray-50">
              <td class="px-2 py-1">{{ node.long_name || node.short_name || 'N/A' }}</td>
              <td class="px-2 py-1"><code class="bg-gray-100 px-1 rounded">{{ node.node_id }}</code></td>
              <td class="px-2 py-1">{{ node.hw_model || 'N/A' }}</td>
              <td class="px-2 py-1">{{ formatTimeAgo(node.last_heard) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- TODO: Map and live packet feed components -->
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';

const connectionStatus = ref(null);
const counters = ref(null);
const nodes = ref([]);
const averageSignal = ref(null);

async function fetchJson(url) {
  const res = await fetch(url);
  if (res.ok) {
    return await res.json();
  }
  return null;
}

async function fetchConnectionStatus() {
  connectionStatus.value = await fetchJson('/api/connection_status/');
}

async function fetchCounters() {
  counters.value = await fetchJson('/api/counters/');
}

async function fetchNodes() {
  nodes.value = await fetchJson('/api/nodes/');
}

async function fetchAverageSignalStats() {
  averageSignal.value = await fetchJson('/api/average_signal_stats/');
}

function formatTimeAgo(value) {
  if (!value) return 'N/A';
  const date = new Date(value);
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

onMounted(() => {
  fetchConnectionStatus();
  fetchCounters();
  fetchNodes();
  fetchAverageSignalStats();
});
</script>

<style scoped>
</style>

