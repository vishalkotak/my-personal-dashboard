import CloudKit
import HealthKit
import Observation
import os

/// Reads new/deleted HealthKit samples per type and mirrors them to the configured backend.
@MainActor
@Observable
final class HealthSyncEngine {
    static let shared = HealthSyncEngine()

    private(set) var lastSyncedAt: Date?
    private(set) var lastError: String?
    /// nil = not checked yet.
    private(set) var accountAvailable: Bool?
    /// The backend's user ID — shown in the app so you can find your rows in the Supabase dashboard.
    private(set) var accountID: String?
    private var inFlight: Set<String> = []
    var isSyncing: Bool { !inFlight.isEmpty }

    @ObservationIgnored private let store = HKHealthStore()
    @ObservationIgnored private let anchors = AnchorStore()
    @ObservationIgnored private let backend = Backends.current
    @ObservationIgnored private var observing = false
    @ObservationIgnored private var rerun: Set<String> = []
    /// Bumped on every anchor reset so an in-flight sync can't save a stale anchor afterwards.
    @ObservationIgnored private var epoch = 0

    // Never log health values. Only type identifiers and error descriptions are marked public.
    private nonisolated static let log = Logger(subsystem: "HealthSync", category: "sync")
    private static let batchSize = 200
    private static let maxConcurrentTypes = 4

    private init() {
        // Only relevant for the CloudKit backend; harmless otherwise.
        NotificationCenter.default.addObserver(forName: .CKAccountChanged, object: nil, queue: .main) { _ in
            Task { @MainActor in
                await HealthSyncEngine.shared.refreshAccount()
                await HealthSyncEngine.shared.syncAll()
            }
        }
    }

    /// True when iOS still has unanswered permission prompts — e.g. after an update adds new types.
    private(set) var needsAuthorization = false
    private var readTypes: Set<HKObjectType> { Set(HealthTypes.all.map { $0 as HKObjectType }) }

    func requestAuthorization() async throws {
        try await store.requestAuthorization(toShare: [], read: readTypes)
        needsAuthorization = false
    }

    func refreshAuthorizationStatus() async {
        let status = try? await store.statusForAuthorizationRequest(toShare: [], read: readTypes)
        needsAuthorization = (status == .shouldRequest)
    }

    /// Checks whether an account is available and detects a switch to a different account.
    func refreshAccount() async {
        do {
            let current = try await backend.currentAccountID()
            accountAvailable = (current != nil)
            accountID = current
            guard let current else { return }

            let previous = UserDefaults.standard.string(forKey: DefaultsKey.accountID)
            if let previous, previous != current {
                await resetAnchors()     // different account → upload full history to it
            }
            UserDefaults.standard.set(current, forKey: DefaultsKey.accountID)
        } catch {
            lastError = Self.message(for: error)
        }
    }

    /// Must run at every launch (including silent background launches) for background delivery to work.
    func startObserving() {
        guard HKHealthStore.isHealthDataAvailable(), !observing else { return }
        observing = true

        for type in HealthTypes.all {
            let query = HKObserverQuery(sampleType: type, predicate: nil) { _, completion, error in
                if let error {
                    Self.log.error("Observer error: \(error.localizedDescription, privacy: .public)")
                    completion()
                    return
                }
                Task { @MainActor in
                    await HealthSyncEngine.shared.sync(type)
                    completion()   // tells HealthKit we're done; skipping this throttles future wakes
                }
            }
            store.execute(query)
            store.enableBackgroundDelivery(for: type, frequency: .immediate) { _, error in
                if let error {
                    Self.log.error("Background delivery failed for \(type.identifier, privacy: .public): \(error.localizedDescription, privacy: .public)")
                }
            }
        }
    }

    /// Syncs every type, a few at a time. With ~190 types, starting them all at once would
    /// open ~190 HealthKit queries and network requests simultaneously.
    func syncAll() async {
        await withTaskGroup(of: Void.self) { group in
            var pending = HealthTypes.all.makeIterator()
            for _ in 0..<Self.maxConcurrentTypes {
                guard let type = pending.next() else { break }
                group.addTask { await self.sync(type) }
            }
            while await group.next() != nil {
                if let type = pending.next() { group.addTask { await self.sync(type) } }
            }
        }
    }

    /// Serialised per type: if a sync is already running, queue exactly one re-run so
    /// samples that arrive mid-sync aren't missed.
    func sync(_ type: HKSampleType) async {
        let id = type.identifier
        guard !inFlight.contains(id) else { rerun.insert(id); return }
        inFlight.insert(id)
        defer { inFlight.remove(id) }

        repeat {
            rerun.remove(id)
            await drain(type)
        } while rerun.contains(id)
    }

    private func resetAnchors() async {
        epoch += 1
        await anchors.reset()
        lastSyncedAt = nil
    }

    private func drain(_ type: HKSampleType) async {
        if accountAvailable == nil { await refreshAccount() }   // e.g. silent background launch
        guard accountAvailable == true else { return }

        let startEpoch = epoch
        var anchor = await anchors.anchor(for: type)

        do {
            while true {
                let descriptor = HKAnchoredObjectQueryDescriptor(
                    predicates: [.sample(type: type)], anchor: anchor, limit: Self.batchSize
                )
                let result = try await descriptor.result(for: store)

                try await backend.write(
                    saving: result.addedSamples.compactMap(SampleMapper.record(from:)),
                    deleting: result.deletedObjects.map(\.uuid)
                )

                // Advance only after the server accepted the batch. Saving per batch also means a
                // years-long first sync makes durable progress even if iOS suspends us midway.
                guard startEpoch == epoch else { return }
                try await anchors.save(result.newAnchor, for: type)
                anchor = result.newAnchor

                if result.addedSamples.count + result.deletedObjects.count < Self.batchSize { break }
            }
            lastSyncedAt = .now
            lastError = nil
        } catch is BackendWasReset {
            Self.log.info("Remote store was reset; re-uploading full history")
            await resetAnchors()
            Task { await syncAll() }
        } catch let error as HKError where error.code == .errorDatabaseInaccessible {
            // The Health database is encrypted while the phone is locked; the next delivery will retry.
            Self.log.info("Health data locked; will retry")
        } catch {
            lastError = Self.message(for: error)
            Self.log.error("Sync failed for \(type.identifier, privacy: .public): \(error.localizedDescription, privacy: .public)")
        }
    }

    private static func message(for error: Error) -> String {
        if let ck = error as? CKError {
            switch ck.code {
            case .quotaExceeded: return "Your iCloud storage is full."
            case .networkUnavailable, .networkFailure: return "Offline — will retry automatically."
            case .notAuthenticated: return "Sign in to iCloud in Settings to sync."
            case .requestRateLimited, .serviceUnavailable, .zoneBusy: return "iCloud is busy — will retry automatically."
            default: break
            }
        }
        if (error as? URLError)?.code == .notConnectedToInternet { return "Offline — will retry automatically." }
        return error.localizedDescription
    }
}
