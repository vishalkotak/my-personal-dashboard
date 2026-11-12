import Foundation
import Supabase
import UIKit

/// Stores samples in Supabase Postgres (`health_samples`, see supabase/schema.sql).
///
/// Security model:
///   * TLS 1.3 minimum, ephemeral URLSession (nothing cached to disk).
///   * The app holds only the public key; Row-Level Security restricts every row to its owner.
///   * user_id is filled server-side (`default auth.uid()`), so the app can't write as anyone else.
///   * No UPDATE permission: rows are immutable once written.
actor SupabaseStore: HealthBackend {
    static let client: SupabaseClient = {
        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.tlsMinimumSupportedProtocolVersion = .TLSv13

        return SupabaseClient(
            supabaseURL: Config.supabaseURL,
            supabaseKey: Config.supabasePublishableKey,
            options: SupabaseClientOptions(global: .init(session: URLSession(configuration: config)))
        )
        // The login session is persisted in the iOS Keychain by supabase-swift.
    }()

    private let table = "health_samples"

    /// Returns the signed-in user, creating an anonymous account on first launch.
    ///
    /// A new account is created ONLY when Supabase positively reports "no saved session" AND
    /// the device is unlocked (Keychain readable). Any other failure — offline, token refresh
    /// failed, phone locked — throws instead, so we never split your data across two accounts.
    func currentAccountID() async throws -> String? {
        do {
            return try await Self.client.auth.session.user.id.uuidString
        } catch AuthError.sessionMissing {
            let unlocked = await MainActor.run { UIApplication.shared.isProtectedDataAvailable }
            guard unlocked else { return nil }
            let session = try await Self.client.auth.signInAnonymously()
            return session.user.id.uuidString
        }
    }

    func write(saving records: [HealthRecord], deleting uuids: [UUID]) async throws {
        if !records.isEmpty {
            // ON CONFLICT DO NOTHING → retries are idempotent and no UPDATE permission is needed.
            try await Self.client
                .from(table)
                .upsert(records.map(Row.init), onConflict: "user_id,hk_uuid", ignoreDuplicates: true)
                .execute()
        }
        if !uuids.isEmpty {
            try await Self.client
                .from(table)
                .delete()
                .in("hk_uuid", values: uuids.map(\.uuidString))
                .execute()
        }
    }

    /// JSON shape of one row. Dates are sent as ISO-8601 strings with fractional seconds.
    private struct Row: Encodable {
        let hkUUID: String
        let type: String
        let startDate: String
        let endDate: String
        let value: Double
        let unit: String
        let metadata: [String: String]

        enum CodingKeys: String, CodingKey {
            case hkUUID = "hk_uuid", type, startDate = "start_date", endDate = "end_date"
            case value, unit, metadata
        }

        init(_ r: HealthRecord) {
            let iso = ISO8601DateFormatter()
            iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            hkUUID = r.hkUUID.uuidString
            type = r.type
            startDate = iso.string(from: r.startDate)
            endDate = iso.string(from: r.endDate)
            value = r.value
            unit = r.unit
            metadata = r.metadata
        }
    }
}
