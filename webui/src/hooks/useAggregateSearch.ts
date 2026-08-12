import { useCallback, useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import type {
  SearchJobRequest,
  SearchJobResponse,
  PlatformSlug,
} from "@/types/search";

const API_BASE = "/api/search";
const STORAGE_KEY = "aggregate_search_job_id";

async function createJob(req: SearchJobRequest): Promise<SearchJobResponse> {
  const { data } = await axios.post<SearchJobResponse>(`${API_BASE}/jobs`, req);
  return data;
}

async function getJob(
  jobId: string,
  signal?: AbortSignal
): Promise<SearchJobResponse> {
  const { data } = await axios.get<SearchJobResponse>(
    `${API_BASE}/jobs/${jobId}`,
    { signal }
  );
  return data;
}

async function getCurrentJob(
  signal?: AbortSignal
): Promise<SearchJobResponse | null> {
  try {
    const { data } = await axios.get<SearchJobResponse>(
      `${API_BASE}/jobs/current`,
      { signal }
    );
    return data;
  } catch {
    return null;
  }
}

async function cancelJob(jobId: string): Promise<void> {
  await axios.post(`${API_BASE}/jobs/${jobId}/cancel`);
}

// ── Pure, testable decision helpers ─────────────────────────────────────
//
// The mount-time recovery race: a /jobs/current response that arrives AFTER
// the user started a new search (or reset) must not overwrite the newer
// state. Both helpers are pure so they can be unit-tested without a
// frontend test framework.

/** A late recovery response applies only if no startSearch/reset happened
 *  after the request was issued (i.e. the generation is unchanged). */
export function shouldApplyRecoveredJob(
  recoveredJobId: string | null | undefined,
  generationAtRequest: number,
  currentGeneration: number
): boolean {
  if (generationAtRequest !== currentGeneration) return false;
  return typeof recoveredJobId === "string" && recoveredJobId.length > 0;
}

/** A 404 from GET /jobs/{id} clears the tracked job only when the failed
 *  id is the one currently tracked — a stale 404 must not reset a newer job. */
export function shouldClearJobOn404(
  failedJobId: string,
  currentJobId: string | null
): boolean {
  return currentJobId === failedJobId;
}

export function useAggregateSearch() {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(() => {
    return sessionStorage.getItem(STORAGE_KEY) || null;
  });
  const [searchedPlatforms, setSearchedPlatforms] = useState<PlatformSlug[] | null>(null);

  // Generation counter: bumped by startSearch/reset so a late /jobs/current
  // response can never overwrite newer state.
  const generationRef = useRef(0);
  const jobIdRef = useRef(jobId);
  useEffect(() => {
    jobIdRef.current = jobId;
  }, [jobId]);

  // Recover current job from backend on mount (with race protection)
  useEffect(() => {
    const ac = new AbortController();
    const genAtRequest = generationRef.current;
    getCurrentJob(ac.signal).then((resp) => {
      if (ac.signal.aborted) return;
      if (!shouldApplyRecoveredJob(resp?.job_id, genAtRequest, generationRef.current)) {
        return;
      }
      if (resp && resp.job_id) {
        setJobId(resp.job_id);
        sessionStorage.setItem(STORAGE_KEY, resp.job_id);
        const platforms = Object.keys(resp.platforms) as PlatformSlug[];
        setSearchedPlatforms(platforms.length > 0 ? platforms : null);
      }
    }).catch(() => {});
    return () => { ac.abort(); };
  }, []);

  const createMutation = useMutation({
    mutationFn: createJob,
    onSuccess: (data) => {
      setJobId(data.job_id);
      sessionStorage.setItem(STORAGE_KEY, data.job_id);
      const platforms = Object.keys(data.platforms) as PlatformSlug[];
      setSearchedPlatforms(platforms);
    },
    onError: () => {
      setJobId(null);
      sessionStorage.removeItem(STORAGE_KEY);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async () => {
      if (!jobIdRef.current) return;
      await cancelJob(jobIdRef.current);
    },
  });

  const pollQuery = useQuery<SearchJobResponse>({
    queryKey: ["search-job", jobId],
    queryFn: async ({ queryKey, signal }) => {
      const requestedId = queryKey[1] as string;
      try {
        return await getJob(requestedId, signal);
      } catch (err) {
        const status = (err as { response?: { status?: number } })?.response?.status;
        // 404 only clears the job that was requested — never a newer one.
        if (status === 404 && shouldClearJobOn404(requestedId, jobIdRef.current)) {
          setJobId(null);
          sessionStorage.removeItem(STORAGE_KEY);
        }
        throw err;
      }
    },
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 800;
      const terminal = ["completed", "partial", "failed", "cancelled"];
      if (terminal.includes(data.overall)) return false;
      return 800;
    },
    staleTime: 500,
    retry: (count, err) => {
      const status = (err as { response?: { status?: number } })?.response?.status;
      // 404 handled in queryFn (clears only the matching job)
      if (status === 404) return false;
      return count < 1;
    },
  });

  const startSearch = useCallback(
    (keyword: string, platforms: PlatformSlug[], limitPerPlatform?: number) => {
      generationRef.current += 1; // invalidate in-flight recovery responses
      setJobId(null);
      sessionStorage.removeItem(STORAGE_KEY);
      createMutation.reset();
      cancelMutation.reset();
      queryClient.removeQueries({ queryKey: ["search-job"] });

      const req: SearchJobRequest = {
        keyword,
        platforms,
        limit_per_platform: limitPerPlatform ?? 10,
      };
      createMutation.mutate(req);
    },
    [createMutation, cancelMutation, queryClient]
  );

  const cancel = useCallback(() => {
    cancelMutation.mutate();
  }, [cancelMutation]);

  const reset = useCallback(() => {
    generationRef.current += 1; // invalidate in-flight recovery responses
    setJobId(null);
    sessionStorage.removeItem(STORAGE_KEY);
    setSearchedPlatforms(null);
    createMutation.reset();
    cancelMutation.reset();
    queryClient.removeQueries({ queryKey: ["search-job"] });
  }, [createMutation, cancelMutation, queryClient]);

  const overall = !jobId
    ? "idle"
    : cancelMutation.isPending
      ? "cancelling"
      : (pollQuery.data?.overall ?? "running");

  return {
    startSearch,
    cancel,
    reset,
    isCreating: createMutation.isPending,
    isCancelling: cancelMutation.isPending,
    createError: createMutation.error,
    jobResponse: pollQuery.data,
    isPolling: pollQuery.isFetching,
    overall,
    pollError: pollQuery.error,
    searchedPlatforms,
    jobId,
  };
}

// ── Login hook ─────────────────────────────────────────────────────────

interface LoginStatus {
  job_id: string;
  platform: string;
  status: string;
  message: string;
  created_at: string;
  completed_at: string | null;
}

export function useLogin() {
  const [loginJobId, setLoginJobId] = useState<string | null>(null);

  const startLogin = useMutation({
    mutationFn: async (platform: PlatformSlug) => {
      const { data } = await axios.post(`${API_BASE}/login`, { platform });
      return data as LoginStatus;
    },
    onSuccess: (data) => {
      setLoginJobId(data.job_id);
    },
    onError: () => {
      setLoginJobId(null);
    },
  });

  const loginPoll = useQuery<LoginStatus>({
    queryKey: ["login-job", loginJobId],
    queryFn: async () => {
      const { data } = await axios.get(`${API_BASE}/login/${loginJobId}`);
      return data as LoginStatus;
    },
    enabled: !!loginJobId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 1000;
      const terminal = ["succeeded", "failed", "timed_out"];
      if (terminal.includes(data.status)) return false;
      return 1000;
    },
    staleTime: 500,
    retry: 1,
  });

  const resetLogin = useCallback(() => {
    setLoginJobId(null);
    startLogin.reset();
  }, [startLogin]);

  return {
    startLogin: (platform: PlatformSlug) => startLogin.mutate(platform),
    resetLogin,
    isLoggingIn: startLogin.isPending,
    loginError: startLogin.error,
    loginStatus: loginPoll.data,
    loginJobId,
  };
}
