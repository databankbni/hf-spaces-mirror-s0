import { describe, it, expect, vi, beforeEach } from "vitest"

// `lib/duckdb` imports "server-only" (throws outside RSC) and @duckdb/node-api.
// Stub both so we can unit-test the connection-singleton lifecycle in isolation.
vi.mock("server-only", () => ({}))

const create = vi.fn()
vi.mock("@duckdb/node-api", () => ({
  DuckDBConnection: { create: () => create() },
}))

describe("getConnection() failure-reset (P1 / I6)", () => {
  beforeEach(() => {
    vi.resetModules()
    create.mockReset()
    // file:// path so the CREATE TABLE loop builds a SQL string without any
    // real network/disk read (connection.run is mocked).
    process.env.SNAPSHOT_URL = "file:///tmp/snapshot"
  })

  it("clears the singleton on a transient init failure so the NEXT request retries (no permanent 500)", async () => {
    const conn = { run: vi.fn().mockResolvedValue(undefined) }
    create
      .mockRejectedValueOnce(new Error("transient httpfs blip")) // boot blip
      .mockResolvedValueOnce(conn) // retry succeeds
    const { getConnection } = await import("../lib/duckdb")

    await expect(getConnection()).rejects.toThrow("transient httpfs blip")
    await Promise.resolve() // let the pending.catch microtask null the singleton
    const got = await getConnection()

    expect(got).toBe(conn)
    expect(create).toHaveBeenCalledTimes(2) // retried — not wedged on a rejected promise
  })

  it("dedups concurrent first-callers into ONE init attempt and they share the rejection", async () => {
    create.mockRejectedValueOnce(new Error("boom"))
    const { getConnection } = await import("../lib/duckdb")
    const [a, b] = await Promise.allSettled([getConnection(), getConnection()])
    expect(a.status).toBe("rejected")
    expect(b.status).toBe("rejected")
    expect(create).toHaveBeenCalledTimes(1) // both awaited the same pending promise
  })

  it("reuses the connection once initialised (no re-init on the happy path)", async () => {
    const conn = { run: vi.fn().mockResolvedValue(undefined) }
    create.mockResolvedValue(conn)
    const { getConnection } = await import("../lib/duckdb")
    const a = await getConnection()
    const b = await getConnection()
    expect(a).toBe(b)
    expect(create).toHaveBeenCalledTimes(1)
  })
})
