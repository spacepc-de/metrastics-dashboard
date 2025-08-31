import { ref } from 'vue';

const data = ref(null);

export function useLiveData() {
  const connect = (url) => {
    const ws = new WebSocket(url);
    ws.onmessage = (event) => {
      data.value = JSON.parse(event.data);
    };
  };

  return { data, connect };
}
