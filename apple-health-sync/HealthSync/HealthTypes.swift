import Foundation
import HealthKit

/// Every Apple Health type the app syncs, loaded from HealthTypes.json (generated from the
/// iOS SDK by scripts/generate-type-catalog.swift). The dashboard reads the same file, so
/// units and "sum vs average" rules can never drift between the two.
enum HealthTypes {
    struct Entry: Decodable {
        let id: String
        let kind: String          // "quantity" | "category" | "workout"
        let group: String
        let name: String
        let unit: String?
        let aggregation: String   // "sum" | "average" | "duration"
    }

    static let catalog: [Entry] = {
        guard let url = Bundle.main.url(forResource: "HealthTypes", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let entries = try? JSONDecoder().decode([Entry].self, from: data)
        else { fatalError("HealthTypes.json missing from the app bundle") }
        return entries
    }()

    /// Canonical unit per quantity type, so the database never mixes lb/kg or °F/°C.
    static let units: [HKQuantityType: HKUnit] = {
        var map: [HKQuantityType: HKUnit] = [:]
        for e in catalog where e.kind == "quantity" {
            guard let unit = e.unit,
                  let type = HKQuantityType.quantityType(forIdentifier: .init(rawValue: e.id)) else { continue }
            map[type] = HKUnit(from: unit)
        }
        return map
    }()

    /// All types this iOS version supports. Identifiers newer than the phone's iOS are skipped.
    static let all: [HKSampleType] = catalog.compactMap { e in
        switch e.kind {
        case "quantity": HKQuantityType.quantityType(forIdentifier: .init(rawValue: e.id))
        case "category": HKCategoryType.categoryType(forIdentifier: .init(rawValue: e.id))
        case "workout": HKObjectType.workoutType()
        default: nil
        }
    }
}
