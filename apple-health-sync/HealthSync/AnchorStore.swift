import Foundation
import HealthKit

/// Persists one HKQueryAnchor per data type ("where did I leave off?").
/// Files use Data Protection so they're encrypted with a key derived from the device passcode.
actor AnchorStore {
    private let directory: URL

    init() {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        directory = base.appendingPathComponent("anchors", isDirectory: true)
        Self.createDirectory(at: directory)
    }

    func anchor(for type: HKSampleType) -> HKQueryAnchor? {
        guard let data = try? Data(contentsOf: url(for: type)) else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data)
    }

    func save(_ anchor: HKQueryAnchor, for type: HKSampleType) throws {
        let data = try NSKeyedArchiver.archivedData(withRootObject: anchor, requiringSecureCoding: true)
        // "Until first user authentication" lets background delivery work after the first unlock post-reboot.
        try data.write(to: url(for: type), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }

    /// Called on sign-out so a different account starts from scratch.
    func reset() {
        try? FileManager.default.removeItem(at: directory)
        Self.createDirectory(at: directory)
    }

    private func url(for type: HKSampleType) -> URL {
        directory.appendingPathComponent(type.identifier)
    }

    private static func createDirectory(at url: URL) {
        try? FileManager.default.createDirectory(
            at: url, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]
        )
    }
}
