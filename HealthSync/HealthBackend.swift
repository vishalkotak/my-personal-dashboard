import Foundation

/// Where synced samples are stored. The sync engine only talks to this protocol.
protocol HealthBackend: Sendable {
    /// Stable ID of the signed-in account, or nil if nobody is signed in / storage is unavailable.
    func currentAccountID() async throws -> String?
    /// Upload new samples and delete removed ones. Must be idempotent (safe to retry).
    func write(saving records: [HealthRecord], deleting uuids: [UUID]) async throws
}

/// Thrown when the remote store lost all data (e.g. the user wiped it); the engine re-uploads full history.
struct BackendWasReset: Error {}

enum Backends {
    /// Supabase works with a free Apple developer account.
    /// CloudStore (end-to-end encrypted iCloud) needs a paid account — see README to switch.
    static let current: any HealthBackend = SupabaseStore()
}
