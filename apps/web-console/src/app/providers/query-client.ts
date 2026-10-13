import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30 * 1000,
    },
  },
});

export const vueQueryPlugin = [VueQueryPlugin, { queryClient }] as const;
