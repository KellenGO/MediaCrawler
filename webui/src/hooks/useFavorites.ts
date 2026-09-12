import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import axios from "axios";
import type { FavoritesJobResponse, PlatformSlug } from "@/types/search";

function isNotFound(error: unknown): boolean {
  return (error as { response?: { status?: number } })?.response?.status === 404;
}

export function useFavorites() {
  const [jobId, setJobId] = useState<string | null>(null);
  const adopted = useRef(false);

  // Re-entering the page restores the last snapshot from the backend. This is a
  // local, in-memory read: it never contacts a platform. Only an explicit sync
  // does. The query is deliberately left at the default staleTime so every
  // mount refetches — otherwise a "no result yet" answer cached on the first
  // visit would keep hiding a snapshot produced later in the session.
  const latest = useQuery({
    queryKey: ["favorites-latest"],
    queryFn: async () => {
      try {
        const { data } = await axios.get<FavoritesJobResponse>(
          "/api/search/favorites/jobs/latest");
        return data;
      } catch (error) {
        if (isNotFound(error)) return null;
        throw error;
      }
    },
    retry: false,
  });

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

  // Leaving the page while a sync is still running and coming back should keep
  // following that job rather than freezing on the restored "running" status.
  // The job already exists in the backend, so this starts no new platform work.
  useEffect(() => {
    if (adopted.current) return;
    const restored = latest.data;
    if (!restored) return;
    adopted.current = true;
    if (restored.overall === "running") setJobId(restored.job_id);
  }, [latest.data]);

  const refresh = useCallback(async (platforms: PlatformSlug[]) => {
    setJobId(null);
    create.reset();
    return create.mutateAsync(platforms);
  }, [create]);

  const data = poll.data ?? create.data ?? latest.data ?? null;

  return {
    sync: refresh,
    data,
    busy: create.isPending || data?.overall === "running",
    error: create.error || (jobId ? poll.error : null),
  };
}
