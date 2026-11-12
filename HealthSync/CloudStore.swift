import CloudKit
import HealthKit

/// Mirrors HealthKit samples into the user's *private* CloudKit database.
///
/// Security model:
///   * Private database: only the signed-in iCloud account can read or write it — Apple
///     enforces this; there are no access rules for us to get wrong.
///   * Every field is stored in `encryptedValues`: encrypted on-device with keys in the
///     user's iCloud Keychain, so Apple's servers hold ciphertext only.
///   * Visible to Apple: record type name, record IDs (random HealthKit UUIDs), sizes, timestamps.
///
/// Requires a PAID Apple Developer account. To enable: return `CloudStore()` from
/// `Backends.current` and add the iCloud entitlements to project.yml (see README).
actor CloudStore: HealthBackend {
    /// Must match `com.apple.developer.icloud-container-identifiers` in project.yml.
    static let containerID = "iCloud.com.vishalkotak.HealthSync"
    static let recordType = "HealthSample"

    private let container = CKContainer(identifier: CloudStore.containerID)
    private var database: CKDatabase { container.privateCloudDatabase }
    // A custom zone (vs. the default zone) enables zone-level change tracking for a future restore/reader feature.
    private let zoneID = CKRecordZone.ID(zoneName: "Health", ownerName: CKCurrentUserDefaultName)
    private var zoneReady = false

    /// App-scoped, opaque identifier for the current iCloud account, or nil if iCloud is unavailable.
    func currentAccountID() async throws -> String? {
        guard try await container.accountStatus() == .available else { return nil }
        return try await container.userRecordID().recordName
    }

    /// Saves and deletes in one request. Batches must stay under CloudKit's 400-item limit.
    func write(saving records: [HealthRecord], deleting uuids: [UUID]) async throws {
        guard !records.isEmpty || !uuids.isEmpty else { return }
        try await ensureZone()

        let toSave = records.map(ckRecord)
        let toDelete = uuids.map { CKRecord.ID(recordName: $0.uuidString, zoneID: zoneID) }

        do {
            // .allKeys = overwrite blindly: HealthKit samples are immutable, so a retry
            // just rewrites identical data (idempotent).
            let (saved, deleted) = try await database.modifyRecords(
                saving: toSave, deleting: toDelete, savePolicy: .allKeys, atomically: false
            )
            for (_, result) in saved { _ = try result.get() }
            for (_, result) in deleted {
                // Deleting something that was never uploaded is fine.
                if case .failure(let error) = result, (error as? CKError)?.code != .unknownItem { throw error }
            }
        } catch let error as CKError where error.code == .zoneNotFound || error.code == .userDeletedZone {
            zoneReady = false
            try await ensureZone()
            throw BackendWasReset()
        }
    }

    private func ensureZone() async throws {
        guard !zoneReady else { return }
        _ = try await database.modifyRecordZones(saving: [CKRecordZone(zoneID: zoneID)], deleting: [])  // idempotent
        zoneReady = true
    }

    private func ckRecord(_ r: HealthRecord) -> CKRecord {
        let record = CKRecord(
            recordType: Self.recordType,
            recordID: CKRecord.ID(recordName: r.hkUUID.uuidString, zoneID: zoneID)
        )
        let encrypted = record.encryptedValues
        encrypted["type"] = r.type
        encrypted["startDate"] = r.startDate
        encrypted["endDate"] = r.endDate
        encrypted["value"] = r.value
        encrypted["unit"] = r.unit
        if !r.metadata.isEmpty, let json = try? JSONEncoder().encode(r.metadata) {
            encrypted["metadata"] = json
        }
        return record
    }
}
