import { useCallback, useEffect, useRef, useState } from 'react'
import type { ApiClient, DashboardSnapshot, ExecutionProfile, SubmitJobReceipt } from './types'

interface DashboardState {
  snapshot: DashboardSnapshot | null
  loading: boolean
  refreshing: boolean
  submitting: boolean
  error: string | null
  receipt: SubmitJobReceipt | null
  refresh: () => Promise<void>
  submit: (profile: ExecutionProfile) => Promise<void>
  retry: (id: string) => Promise<void>
}

const errorMessage = (error: unknown): string => {
  if (error instanceof Error) return error.message
  return '发生未知错误'
}

export const useDashboard = (client: ApiClient): DashboardState => {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [receipt, setReceipt] = useState<SubmitJobReceipt | null>(null)
  const mounted = useRef(true)
  const requestInFlight = useRef(false)
  const activePolling = Boolean(
    snapshot?.jobs.some((job) => job.state === 'queued' || job.state === 'running'),
  )

  const load = useCallback(
    async (quiet = false) => {
      if (requestInFlight.current) return
      requestInFlight.current = true
      if (!quiet) setRefreshing(true)
      try {
        const next = await client.getSnapshot()
        if (!mounted.current) return
        setSnapshot(next)
        setError(null)
      } catch (nextError) {
        if (mounted.current) setError(errorMessage(nextError))
      } finally {
        requestInFlight.current = false
        if (mounted.current) {
          setLoading(false)
          setRefreshing(false)
        }
      }
    },
    [client],
  )

  useEffect(() => {
    mounted.current = true
    void load(true)
    const interval = window.setInterval(
      () => {
        if (document.visibilityState === 'visible' || activePolling) void load(true)
      },
      activePolling ? 4_000 : 45_000,
    )
    return () => {
      mounted.current = false
      window.clearInterval(interval)
    }
  }, [activePolling, load])

  const submit = useCallback(async (profile: ExecutionProfile) => {
    setSubmitting(true)
    setError(null)
    try {
      const nextReceipt = await client.submitUpdateInfer(profile)
      if (!mounted.current) return
      setReceipt(nextReceipt)
      await load(true)
    } catch (nextError) {
      if (mounted.current) setError(errorMessage(nextError))
    } finally {
      if (mounted.current) setSubmitting(false)
    }
  }, [client, load])

  const retry = useCallback(
    async (id: string) => {
      setSubmitting(true)
      setError(null)
      try {
        const nextReceipt = await client.retryJob(id)
        if (!mounted.current) return
        setReceipt(nextReceipt)
        await load(true)
      } catch (nextError) {
        if (mounted.current) setError(errorMessage(nextError))
      } finally {
        if (mounted.current) setSubmitting(false)
      }
    },
    [client, load],
  )

  return {
    snapshot,
    loading,
    refreshing,
    submitting,
    error,
    receipt,
    refresh: () => load(false),
    submit,
    retry,
  }
}
