import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiContractError, createApiClient } from './api'

const response = (payload: unknown, status = 200): Response =>
  ({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 404 ? 'Not Found' : 'OK',
    json: async () => payload,
  }) as Response

describe('API runtime contract', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('rejects missing core fields instead of fabricating a production success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/system/status')) {
          return response({ inference_as_of: null, active_job_id: null })
        }
        if (path.endsWith('/jobs')) return response({ items: [] })
        return response({}, 404)
      }),
    )

    await expect(createApiClient().getSnapshot()).rejects.toBeInstanceOf(ApiContractError)
  })

  it('decodes backend DATA_INCOMPLETE jobs into the validation stage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/system/status')) {
          return response({
            service_state: 'degraded',
            server_time: '2026-08-13T02:00:00+08:00',
            latest_closed_session: '2026-08-12',
            data_as_of: null,
            inference_as_of: null,
            active_job_id: null,
            warnings: ['data incomplete'],
          })
        }
        if (path.endsWith('/jobs')) {
          return response({
            items: [
              {
                id: 'job-1',
                status: 'DATA_INCOMPLETE',
                stage: 'DATA_INCOMPLETE',
                created_at: '2026-08-13T02:00:00+08:00',
                requested_session: '2026-08-12',
                error_code: 'DATA_INCOMPLETE',
              },
            ],
          })
        }
        return response({}, 404)
      }),
    )

    const snapshot = await createApiClient().getSnapshot()
    expect(snapshot.jobs[0]).toMatchObject({
      state: 'data_incomplete',
      stage: 'validating_data',
      error_code: 'DATA_INCOMPLETE',
    })
  })
})
