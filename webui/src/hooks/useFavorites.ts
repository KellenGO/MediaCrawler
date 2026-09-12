import { useCallback, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import axios from "axios";
import type { FavoritesJobResponse, PlatformSlug } from "@/types/search";

export function useFavorites() {
  const [jobId, setJobId] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: async (platforms: PlatformSlug[]) => {
      const { data } = await axios.post<FavoritesJobResponse>("/api/search/favorites/jobs", {
        platforms, limit_per_platform: 20,
      });
      return data;
    },
    onSuccess: (data) => setJobId(data.job_id),
  });
  const poll = useQuery({
    queryKey: ["favorites-job", jobId],
    queryFn: async () => (await axios.get<FavoritesJobResponse>(
      `/api/search/favorites/jobs/${jobId}`)).data,
    enabled: !!jobId,
    refetchInterval: (query) => query.state.data?.overall === "running" ? 800 : false,
    retry: 1,
  });
  const refresh = useCallback(async (platforms: PlatformSlug[]) => {
    setJobId(null);
    create.reset();
    return create.mutateAsync(platforms);
  }, [create]);
  return {
    sync: refresh,
    data: poll.data ?? create.data ?? null,
    busy: create.isPending || poll.data?.overall === "running",
    error: create.error || poll.error,
  };
}
