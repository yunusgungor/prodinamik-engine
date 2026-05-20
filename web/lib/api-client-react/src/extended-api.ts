/**
 * Extended API hooks — auth, raft, chaos, plugins, config, ratelimit.
 *
 * These endpoints exist on the Prodinamik Engine backend but are not
 * in the generated OpenAPI spec (api.ts). Manually maintained hooks
 * following the same pattern as the generated ones.
 */
import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
  type UseQueryResult,
  type QueryKey,
  type MutationFunction,
  type UseMutationOptions,
  type UseMutationResult,
  type QueryFunction,
} from "@tanstack/react-query";
import { customFetch, type ErrorType, type BodyType } from "./custom-fetch";

// ──────────────────────────────────────────────
// Schema Types
// ──────────────────────────────────────────────

export interface APIKeyInfo {
  id: string;
  name: string;
  role: string;
  created_at: string;
  expires_at?: string | null;
  last_used?: string | null;
  enabled: boolean;
}

export interface APIKeyCreate {
  name: string;
  role?: string;
  expires_in_days?: number;
}

export interface APIKeyCreated {
  id: string;
  name: string;
  role: string;
  key: string;
  created_at: string;
  expires_at?: string | null;
}

export interface RaftNode {
  id: string;
  address: string;
  state: string;
  last_seen?: string | null;
  log_index?: number;
  term?: number;
}

export interface RaftStatus {
  state: string;
  nodes: number;
  term: number;
  leader?: string;
}

export interface ChaosScenario {
  id: string;
  name: string;
  description: string;
  severity?: string;
  duration?: number;
  dangerous?: boolean;
  fault_type?: string;
}

export interface ChaosResult {
  scenario: string;
  outcome: string;
  recovery_time_sec?: number | null;
  metrics_before?: Record<string, unknown> | null;
  metrics_after?: Record<string, unknown> | null;
}

export interface RateLimitInfo {
  total_keys: number;
  total_allowed: number;
  total_denied: number;
  rate: number;
  burst: number;
}

export interface ExtendedActionResult {
  success: boolean;
  message: string;
}

// ──────────────────────────────────────────────
// Auth API Keys
// ──────────────────────────────────────────────

const getListAuthKeysUrl = () => `/api/v1/auth/keys`;

export const listAuthKeys = async (options?: RequestInit): Promise<APIKeyInfo[]> => {
  return customFetch<APIKeyInfo[]>(getListAuthKeysUrl(), {
    ...options,
    method: "GET",
  });
};

export const getListAuthKeysQueryOptions = <TData = Awaited<ReturnType<typeof listAuthKeys>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof listAuthKeys>>, TError, TData>; request?: RequestInit }
) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};
  const queryKey = ["listAuthKeys"] as QueryKey;
  const queryFn: QueryFunction<Awaited<ReturnType<typeof listAuthKeys>>> = () => listAuthKeys(requestOptions);
  return { queryKey, queryFn, refetchInterval: 30_000, ...queryOptions };
};

export function useListAuthKeys<TData = Awaited<ReturnType<typeof listAuthKeys>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof listAuthKeys>>, TError, TData>; request?: RequestInit }
): UseQueryResult<TData, TError> & { queryKey: QueryKey } {
  const queryOptions = getListAuthKeysQueryOptions(options);
  const query = useQuery(queryOptions) as UseQueryResult<TData, TError> & { queryKey: QueryKey };
  return { ...query, queryKey: queryOptions.queryKey };
}

// ── Create API Key ──

const getCreateAuthKeyUrl = () => `/api/v1/auth/keys`;

export const createAuthKey = async (data: APIKeyCreate, options?: RequestInit): Promise<APIKeyCreated> => {
  return customFetch<APIKeyCreated>(getCreateAuthKeyUrl(), {
    ...options,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
};

export const getCreateAuthKeyMutationOptions = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof createAuthKey>>, TError, { data: BodyType<APIKeyCreate> }, TContext>; request?: RequestInit }
): UseMutationOptions<Awaited<ReturnType<typeof createAuthKey>>, TError, { data: BodyType<APIKeyCreate> }, TContext> => {
  const mutationKey = ["createAuthKey"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation && "mutationKey" in options.mutation && options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };
  const mutationFn: MutationFunction<Awaited<ReturnType<typeof createAuthKey>>, { data: BodyType<APIKeyCreate> }> = (props) => {
    const { data } = props ?? {};
    return createAuthKey(data, requestOptions);
  };
  return { mutationFn, ...mutationOptions };
};

export type CreateAuthKeyMutationResult = NonNullable<Awaited<ReturnType<typeof createAuthKey>>>;
export type CreateAuthKeyMutationBody = BodyType<APIKeyCreate>;
export type CreateAuthKeyMutationError = ErrorType<void>;

export const useCreateAuthKey = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof createAuthKey>>, TError, { data: BodyType<APIKeyCreate> }, TContext>; request?: RequestInit }
): UseMutationResult<Awaited<ReturnType<typeof createAuthKey>>, TError, { data: BodyType<APIKeyCreate> }, TContext> => {
  const mutationOptions = getCreateAuthKeyMutationOptions(options);
  return useMutation(mutationOptions);
};

// ── Revoke API Key ──

const getRevokeAuthKeyUrl = (keyId: string) => `/api/v1/auth/keys/${keyId}`;

export const revokeAuthKey = async (keyId: string, options?: RequestInit): Promise<{ success: boolean; message: string }> => {
  return customFetch<{ success: boolean; message: string }>(getRevokeAuthKeyUrl(keyId), {
    ...options,
    method: "DELETE",
  });
};

export const getRevokeAuthKeyMutationOptions = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof revokeAuthKey>>, TError, { keyId: string }, TContext>; request?: RequestInit }
): UseMutationOptions<Awaited<ReturnType<typeof revokeAuthKey>>, TError, { keyId: string }, TContext> => {
  const mutationKey = ["revokeAuthKey"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation && "mutationKey" in options.mutation && options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };
  const mutationFn: MutationFunction<Awaited<ReturnType<typeof revokeAuthKey>>, { keyId: string }> = (props) => {
    const { keyId } = props ?? {};
    return revokeAuthKey(keyId, requestOptions);
  };
  return { mutationFn, ...mutationOptions };
};

export type RevokeAuthKeyMutationResult = NonNullable<Awaited<ReturnType<typeof revokeAuthKey>>>;
export type RevokeAuthKeyMutationError = ErrorType<void>;

export const useRevokeAuthKey = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof revokeAuthKey>>, TError, { keyId: string }, TContext>; request?: RequestInit }
): UseMutationResult<Awaited<ReturnType<typeof revokeAuthKey>>, TError, { keyId: string }, TContext> => {
  const mutationOptions = getRevokeAuthKeyMutationOptions(options);
  return useMutation(mutationOptions);
};

// ──────────────────────────────────────────────
// Raft
// ──────────────────────────────────────────────

const getListRaftNodesUrl = () => `/api/v1/raft/nodes`;

export const listRaftNodes = async (options?: RequestInit): Promise<RaftNode[]> => {
  return customFetch<RaftNode[]>(getListRaftNodesUrl(), { ...options, method: "GET" });
};

export const getListRaftNodesQueryOptions = <TData = Awaited<ReturnType<typeof listRaftNodes>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof listRaftNodes>>, TError, TData>; request?: RequestInit }
) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};
  const queryKey = ["listRaftNodes"] as QueryKey;
  const queryFn: QueryFunction<Awaited<ReturnType<typeof listRaftNodes>>> = () => listRaftNodes(requestOptions);
  return { queryKey, queryFn, refetchInterval: 10_000, ...queryOptions };
};

export function useListRaftNodes<TData = Awaited<ReturnType<typeof listRaftNodes>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof listRaftNodes>>, TError, TData>; request?: RequestInit }
): UseQueryResult<TData, TError> & { queryKey: QueryKey } {
  const qo = getListRaftNodesQueryOptions(options);
  const query = useQuery(qo) as UseQueryResult<TData, TError> & { queryKey: QueryKey };
  return { ...query, queryKey: qo.queryKey };
}

// ── Raft Status ──

const getRaftStatusUrl = () => `/api/v1/raft/status`;

export const getRaftStatus = async (options?: RequestInit): Promise<RaftStatus> => {
  return customFetch<RaftStatus>(getRaftStatusUrl(), { ...options, method: "GET" });
};

export const getRaftStatusQueryOptions = <TData = Awaited<ReturnType<typeof getRaftStatus>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof getRaftStatus>>, TError, TData>; request?: RequestInit }
) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};
  const queryKey = ["getRaftStatus"] as QueryKey;
  const queryFn: QueryFunction<Awaited<ReturnType<typeof getRaftStatus>>> = () => getRaftStatus(requestOptions);
  return { queryKey, queryFn, refetchInterval: 10_000, ...queryOptions };
};

export function useGetRaftStatus<TData = Awaited<ReturnType<typeof getRaftStatus>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof getRaftStatus>>, TError, TData>; request?: RequestInit }
): UseQueryResult<TData, TError> & { queryKey: QueryKey } {
  const qo = getRaftStatusQueryOptions(options);
  const query = useQuery(qo) as UseQueryResult<TData, TError> & { queryKey: QueryKey };
  return { ...query, queryKey: qo.queryKey };
}

// ──────────────────────────────────────────────
// Chaos
// ──────────────────────────────────────────────

const getListChaosScenariosUrl = () => `/api/v1/chaos/scenarios`;

export const listChaosScenarios = async (options?: RequestInit): Promise<ChaosScenario[]> => {
  return customFetch<ChaosScenario[]>(getListChaosScenariosUrl(), { ...options, method: "GET" });
};

export const getListChaosScenariosQueryOptions = <TData = Awaited<ReturnType<typeof listChaosScenarios>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof listChaosScenarios>>, TError, TData>; request?: RequestInit }
) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};
  const queryKey = ["listChaosScenarios"] as QueryKey;
  const queryFn: QueryFunction<Awaited<ReturnType<typeof listChaosScenarios>>> = () => listChaosScenarios(requestOptions);
  return { queryKey, queryFn, ...queryOptions };
};

export function useListChaosScenarios<TData = Awaited<ReturnType<typeof listChaosScenarios>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof listChaosScenarios>>, TError, TData>; request?: RequestInit }
): UseQueryResult<TData, TError> & { queryKey: QueryKey } {
  const qo = getListChaosScenariosQueryOptions(options);
  const query = useQuery(qo) as UseQueryResult<TData, TError> & { queryKey: QueryKey };
  return { ...query, queryKey: qo.queryKey };
}

// ── Run Chaos Scenario ──

const getRunChaosScenarioUrl = () => `/api/v1/chaos/run`;

export const runChaosScenario = async (data: { scenario_id: string; duration?: number }, options?: RequestInit): Promise<ChaosResult> => {
  return customFetch<ChaosResult>(getRunChaosScenarioUrl(), {
    ...options,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
};

export const getRunChaosScenarioMutationOptions = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof runChaosScenario>>, TError, { data: BodyType<{ scenario_id: string; duration?: number }> }, TContext>; request?: RequestInit }
): UseMutationOptions<Awaited<ReturnType<typeof runChaosScenario>>, TError, { data: BodyType<{ scenario_id: string; duration?: number }> }, TContext> => {
  const mutationKey = ["runChaosScenario"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation && "mutationKey" in options.mutation && options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };
  const mutationFn: MutationFunction<Awaited<ReturnType<typeof runChaosScenario>>, { data: BodyType<{ scenario_id: string; duration?: number }> }> = (props) => {
    const { data } = props ?? {};
    return runChaosScenario(data, requestOptions);
  };
  return { mutationFn, ...mutationOptions };
};

export type RunChaosScenarioMutationResult = NonNullable<Awaited<ReturnType<typeof runChaosScenario>>>;
export type RunChaosScenarioMutationBody = BodyType<{ scenario_id: string; duration?: number }>;
export type RunChaosScenarioMutationError = ErrorType<void>;

export const useRunChaosScenario = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof runChaosScenario>>, TError, { data: BodyType<{ scenario_id: string; duration?: number }> }, TContext>; request?: RequestInit }
): UseMutationResult<Awaited<ReturnType<typeof runChaosScenario>>, TError, { data: BodyType<{ scenario_id: string; duration?: number }> }, TContext> => {
  const mutationOptions = getRunChaosScenarioMutationOptions(options);
  return useMutation(mutationOptions);
};

// ──────────────────────────────────────────────
// Config
// ──────────────────────────────────────────────

const getConfigUrl = () => `/api/v1/config`;

export const getConfig = async (options?: RequestInit): Promise<Record<string, unknown>> => {
  return customFetch<Record<string, unknown>>(getConfigUrl(), { ...options, method: "GET" });
};

export const getGetConfigQueryOptions = <TData = Awaited<ReturnType<typeof getConfig>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof getConfig>>, TError, TData>; request?: RequestInit }
) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};
  const queryKey = ["getConfig"] as QueryKey;
  const queryFn: QueryFunction<Awaited<ReturnType<typeof getConfig>>> = () => getConfig(requestOptions);
  return { queryKey, queryFn, ...queryOptions };
};

export function useGetConfig<TData = Awaited<ReturnType<typeof getConfig>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof getConfig>>, TError, TData>; request?: RequestInit }
): UseQueryResult<TData, TError> & { queryKey: QueryKey } {
  const qo = getGetConfigQueryOptions(options);
  const query = useQuery(qo) as UseQueryResult<TData, TError> & { queryKey: QueryKey };
  return { ...query, queryKey: qo.queryKey };
}

// ── Update Config ──

const getUpdateConfigUrl = () => `/api/v1/config`;

export const updateConfig = async (data: Record<string, unknown>, options?: RequestInit): Promise<{ success: boolean; message: string }> => {
  return customFetch<{ success: boolean; message: string }>(getUpdateConfigUrl(), {
    ...options,
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
};

export const getUpdateConfigMutationOptions = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof updateConfig>>, TError, { data: BodyType<Record<string, unknown>> }, TContext>; request?: RequestInit }
): UseMutationOptions<Awaited<ReturnType<typeof updateConfig>>, TError, { data: BodyType<Record<string, unknown>> }, TContext> => {
  const mutationKey = ["updateConfig"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation && "mutationKey" in options.mutation && options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };
  const mutationFn: MutationFunction<Awaited<ReturnType<typeof updateConfig>>, { data: BodyType<Record<string, unknown>> }> = (props) => {
    const { data } = props ?? {};
    return updateConfig(data, requestOptions);
  };
  return { mutationFn, ...mutationOptions };
};

export type UpdateConfigMutationResult = NonNullable<Awaited<ReturnType<typeof updateConfig>>>;
export type UpdateConfigMutationBody = BodyType<Record<string, unknown>>;
export type UpdateConfigMutationError = ErrorType<void>;

export const useUpdateConfig = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof updateConfig>>, TError, { data: BodyType<Record<string, unknown>> }, TContext>; request?: RequestInit }
): UseMutationResult<Awaited<ReturnType<typeof updateConfig>>, TError, { data: BodyType<Record<string, unknown>> }, TContext> => {
  const mutationOptions = getUpdateConfigMutationOptions(options);
  return useMutation(mutationOptions);
};

// ──────────────────────────────────────────────
// Rate Limit
// ──────────────────────────────────────────────

const getRateLimitStatsUrl = () => `/api/v1/ratelimit/stats`;

export const getRateLimitStats = async (options?: RequestInit): Promise<RateLimitInfo> => {
  return customFetch<RateLimitInfo>(getRateLimitStatsUrl(), { ...options, method: "GET" });
};

export const getRateLimitStatsQueryOptions = <TData = Awaited<ReturnType<typeof getRateLimitStats>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof getRateLimitStats>>, TError, TData>; request?: RequestInit }
) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};
  const queryKey = ["getRateLimitStats"] as QueryKey;
  const queryFn: QueryFunction<Awaited<ReturnType<typeof getRateLimitStats>>> = () => getRateLimitStats(requestOptions);
  return { queryKey, queryFn, ...queryOptions };
};

export function useGetRateLimitStats<TData = Awaited<ReturnType<typeof getRateLimitStats>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof getRateLimitStats>>, TError, TData>; request?: RequestInit }
): UseQueryResult<TData, TError> & { queryKey: QueryKey } {
  const qo = getRateLimitStatsQueryOptions(options);
  const query = useQuery(qo) as UseQueryResult<TData, TError> & { queryKey: QueryKey };
  return { ...query, queryKey: qo.queryKey };
}

// ──────────────────────────────────────────────
// Plugin Types
// ──────────────────────────────────────────────

export interface PluginInfo {
  id: string;
  name: string;
  version: string;
  type: string;
  status: string;
  description?: string | null;
  author?: string | null;
  dependencies?: string[];
}

export interface MarketplacePluginInfo {
  id: string;
  name: string;
  version: string;
  type: string;
  rating: number;
  downloads: number;
  description?: string | null;
}

// ──────────────────────────────────────────────
// Plugins
// ──────────────────────────────────────────────

const getListPluginsUrl = () => `/api/v1/plugins`;

export const listPlugins = async (options?: RequestInit): Promise<PluginInfo[]> => {
  return customFetch<PluginInfo[]>(getListPluginsUrl(), { ...options, method: "GET" });
};

export const getListPluginsQueryOptions = <TData = Awaited<ReturnType<typeof listPlugins>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof listPlugins>>, TError, TData>; request?: RequestInit }
) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};
  const queryKey = ["listPlugins"] as QueryKey;
  const queryFn: QueryFunction<Awaited<ReturnType<typeof listPlugins>>> = () => listPlugins(requestOptions);
  return { queryKey, queryFn, ...queryOptions };
};

export function useListPlugins<TData = Awaited<ReturnType<typeof listPlugins>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof listPlugins>>, TError, TData>; request?: RequestInit }
): UseQueryResult<TData, TError> & { queryKey: QueryKey } {
  const qo = getListPluginsQueryOptions(options);
  const query = useQuery(qo) as UseQueryResult<TData, TError> & { queryKey: QueryKey };
  return { ...query, queryKey: qo.queryKey };
}

// ── List Marketplace ──

const getListMarketplacePluginsUrl = () => `/api/v1/plugins/marketplace`;

export const listMarketplacePlugins = async (options?: RequestInit): Promise<MarketplacePluginInfo[]> => {
  return customFetch<MarketplacePluginInfo[]>(getListMarketplacePluginsUrl(), { ...options, method: "GET" });
};

export const getListMarketplacePluginsQueryOptions = <TData = Awaited<ReturnType<typeof listMarketplacePlugins>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof listMarketplacePlugins>>, TError, TData>; request?: RequestInit }
) => {
  const { query: queryOptions, request: requestOptions } = options ?? {};
  const queryKey = ["listMarketplacePlugins"] as QueryKey;
  const queryFn: QueryFunction<Awaited<ReturnType<typeof listMarketplacePlugins>>> = () => listMarketplacePlugins(requestOptions);
  return { queryKey, queryFn, ...queryOptions };
};

export function useListMarketplacePlugins<TData = Awaited<ReturnType<typeof listMarketplacePlugins>>, TError = ErrorType<void>>(
  options?: { query?: UseQueryOptions<Awaited<ReturnType<typeof listMarketplacePlugins>>, TError, TData>; request?: RequestInit }
): UseQueryResult<TData, TError> & { queryKey: QueryKey } {
  const qo = getListMarketplacePluginsQueryOptions(options);
  const query = useQuery(qo) as UseQueryResult<TData, TError> & { queryKey: QueryKey };
  return { ...query, queryKey: qo.queryKey };
}

// ── Enable Plugin ──

const getEnablePluginUrl = (pluginId: string) => `/api/v1/plugins/${pluginId}/enable`;

export const enablePlugin = async (pluginId: string, options?: RequestInit): Promise<{ success: boolean; message: string }> => {
  return customFetch<{ success: boolean; message: string }>(getEnablePluginUrl(pluginId), { ...options, method: "POST" });
};

export const getEnablePluginMutationOptions = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof enablePlugin>>, TError, { pluginId: string }, TContext>; request?: RequestInit }
): UseMutationOptions<Awaited<ReturnType<typeof enablePlugin>>, TError, { pluginId: string }, TContext> => {
  const mutationKey = ["enablePlugin"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation && "mutationKey" in options.mutation && options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };
  const mutationFn: MutationFunction<Awaited<ReturnType<typeof enablePlugin>>, { pluginId: string }> = (props) => {
    const { pluginId } = props ?? {};
    return enablePlugin(pluginId, requestOptions);
  };
  return { mutationFn, ...mutationOptions };
};

export const useEnablePlugin = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof enablePlugin>>, TError, { pluginId: string }, TContext>; request?: RequestInit }
): UseMutationResult<Awaited<ReturnType<typeof enablePlugin>>, TError, { pluginId: string }, TContext> => {
  const mutationOptions = getEnablePluginMutationOptions(options);
  return useMutation(mutationOptions);
};

// ── Disable Plugin ──

const getDisablePluginUrl = (pluginId: string) => `/api/v1/plugins/${pluginId}/disable`;

export const disablePlugin = async (pluginId: string, options?: RequestInit): Promise<{ success: boolean; message: string }> => {
  return customFetch<{ success: boolean; message: string }>(getDisablePluginUrl(pluginId), { ...options, method: "POST" });
};

export const getDisablePluginMutationOptions = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof disablePlugin>>, TError, { pluginId: string }, TContext>; request?: RequestInit }
): UseMutationOptions<Awaited<ReturnType<typeof disablePlugin>>, TError, { pluginId: string }, TContext> => {
  const mutationKey = ["disablePlugin"];
  const { mutation: mutationOptions, request: requestOptions } = options
    ? options.mutation && "mutationKey" in options.mutation && options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey }, request: undefined };
  const mutationFn: MutationFunction<Awaited<ReturnType<typeof disablePlugin>>, { pluginId: string }> = (props) => {
    const { pluginId } = props ?? {};
    return disablePlugin(pluginId, requestOptions);
  };
  return { mutationFn, ...mutationOptions };
};

export const useDisablePlugin = <TError = ErrorType<void>, TContext = unknown>(
  options?: { mutation?: UseMutationOptions<Awaited<ReturnType<typeof disablePlugin>>, TError, { pluginId: string }, TContext>; request?: RequestInit }
): UseMutationResult<Awaited<ReturnType<typeof disablePlugin>>, TError, { pluginId: string }, TContext> => {
  const mutationOptions = getDisablePluginMutationOptions(options);
  return useMutation(mutationOptions);
};

