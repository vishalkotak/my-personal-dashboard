// Generates HealthSync/HealthTypes.json — the single list of Apple Health types the app syncs
// and the dashboard understands. Re-run after a new iOS SDK adds identifiers:
//
//   swift scripts/generate-type-catalog.swift > HealthSync/HealthTypes.json
//
// For every quantity/category identifier in the SDK header it records: group (the header's
// section heading), a readable name, the canonical unit we store values in, and how values
// combine over a day ("sum" for cumulative types like steps, "average" for everything else).
import Foundation
import HealthKit

// MARK: - Policy

/// Types whose units are fixed because rows already exist in the database with these units.
let lockedUnits: [String: String] = [
    "HKQuantityTypeIdentifierStepCount": "count",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "m",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "kcal",
    "HKQuantityTypeIdentifierHeartRate": "count/min",
    "HKQuantityTypeIdentifierRestingHeartRate": "count/min",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "ms",
    "HKQuantityTypeIdentifierBodyMass": "kg",
    "HKQuantityTypeIdentifierBloodPressureSystolic": "mmHg",
    "HKQuantityTypeIdentifierBloodPressureDiastolic": "mmHg",
    "HKQuantityTypeIdentifierOxygenSaturation": "%",
    "HKQuantityTypeIdentifierBodyTemperature": "degC",
]

/// Readable units for specific types (HealthKit would accept many units; these are the natural ones).
let preferredUnits: [String: String] = [
    "HKQuantityTypeIdentifierDietaryWater": "mL",
    "HKQuantityTypeIdentifierRunningGroundContactTime": "ms",
    "HKQuantityTypeIdentifierRunningVerticalOscillation": "cm",
    "HKQuantityTypeIdentifierWaistCircumference": "cm",
    "HKQuantityTypeIdentifierHeight": "cm",
    "HKQuantityTypeIdentifierBloodGlucose": "mg/dL",
    "HKQuantityTypeIdentifierPeakExpiratoryFlowRate": "L/min",
    "HKQuantityTypeIdentifierTimeInDaylight": "min",
    "HKQuantityTypeIdentifierAppleExerciseTime": "min",
    "HKQuantityTypeIdentifierAppleMoveTime": "min",
    "HKQuantityTypeIdentifierAppleStandTime": "min",
]

/// Dimensionless types that are percentages rather than counts (HealthKit treats both as scalars).
let percentHints = ["Percentage", "Saturation", "AlcoholContent", "WalkingSteadiness",
                    "AtrialFibrillationBurden", "PeripheralPerfusionIndex"]

/// Tried in order for everything else; the first unit HealthKit says is compatible wins.
let candidateUnits = ["count/min", "kcal", "m", "s", "kg", "mmHg", "degC", "L", "ml/(kg*min)",
                      "dBASPL", "m/s", "W", "mg/dL", "IU", "S", "L/min", "kcal/(kg*hr)",
                      "appleEffortScore"]

/// Never synced: write-only/aggregate-only or replaced by newer identifiers.
let excluded: Set<String> = ["HKQuantityTypeIdentifierNikeFuel"]

// MARK: - Parse the SDK header

func sdkHeader() -> String {
    let pipe = Pipe(), p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/xcrun")
    p.arguments = ["--sdk", "iphoneos", "--show-sdk-path"]
    p.standardOutput = pipe
    try! p.run(); p.waitUntilExit()
    let sdk = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
        .trimmingCharacters(in: .whitespacesAndNewlines)
    return try! String(contentsOfFile: sdk + "/System/Library/Frameworks/HealthKit.framework/Headers/HKTypeIdentifiers.h", encoding: .utf8)
}

struct Entry: Encodable {
    let id: String, kind: String, group: String, name: String
    let unit: String?, aggregation: String
}

func readableName(_ id: String) -> String {
    let base = id.replacingOccurrences(of: "HKQuantityTypeIdentifier", with: "")
                 .replacingOccurrences(of: "HKCategoryTypeIdentifier", with: "")
    var words = "", prev: Character = " "
    for ch in base {
        if ch.isUppercase && (prev.isLowercase || prev.isNumber) { words.append(" ") }
        words.append(ch); prev = ch
    }
    return words.replacingOccurrences(of: "Apple ", with: "")
                .replacingOccurrences(of: "V O2", with: "VO2")
                .replacingOccurrences(of: "S D N N", with: "SDNN")
}

func unit(for type: HKQuantityType) -> String? {
    let id = type.identifier
    for choice in [lockedUnits[id], preferredUnits[id]].compactMap({ $0 }) {
        precondition(type.is(compatibleWith: HKUnit(from: choice)), "\(choice) incompatible with \(id)")
        return choice
    }
    if id.hasPrefix("HKQuantityTypeIdentifierDietary"), type.is(compatibleWith: .gram()) { return "g" }
    if type.is(compatibleWith: .count()) {
        return percentHints.contains(where: id.contains) ? "%" : "count"
    }
    return candidateUnits.first { type.is(compatibleWith: HKUnit(from: $0)) }
}

var entries: [Entry] = [], skipped: [String] = []
var group = "Other"
for raw in sdkHeader().split(separator: "\n") {
    let line = String(raw)
    if line.hasPrefix("// ") && !line.contains("HealthKit") && !line.contains("Copyright") && !line.hasSuffix(".h") {
        group = String(line.dropFirst(3)).trimmingCharacters(in: .whitespaces)
        continue
    }
    guard line.hasPrefix("HK_EXTERN HKQuantityTypeIdentifier const ") || line.hasPrefix("HK_EXTERN HKCategoryTypeIdentifier const ") else { continue }
    let id = String(line.split(separator: " ")[3]).trimmingCharacters(in: CharacterSet(charactersIn: ";"))
    if line.contains("DEPRECATED") || excluded.contains(id) { skipped.append(id); continue }

    if id.hasPrefix("HKQuantityTypeIdentifier") {
        guard let type = HKQuantityType.quantityType(forIdentifier: HKQuantityTypeIdentifier(rawValue: id)),
              let u = unit(for: type) else { skipped.append(id); continue }
        entries.append(Entry(id: id, kind: "quantity", group: group, name: readableName(id), unit: u,
                             aggregation: type.aggregationStyle == .cumulative ? "sum" : "average"))
    } else {
        // No runtime check: categories need no unit, and the iPhone skips types its iOS doesn't know.
        entries.append(Entry(id: id, kind: "category", group: group, name: readableName(id), unit: nil,
                             aggregation: "duration"))
    }
}
entries.append(Entry(id: "HKWorkoutTypeIdentifier", kind: "workout", group: "Fitness", name: "Workouts",
                     unit: "s", aggregation: "sum"))

let enc = JSONEncoder()
enc.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
print(String(decoding: try! enc.encode(entries), as: UTF8.self))
FileHandle.standardError.write("\(entries.count) types; skipped \(skipped.count): \(skipped.joined(separator: ", "))\n".data(using: .utf8)!)
