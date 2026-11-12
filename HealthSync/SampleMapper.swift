import HealthKit

/// One sample as uploaded to CloudKit. Only these fields ever leave the device.
struct HealthRecord: Sendable {
    let hkUUID: UUID
    let type: String
    let startDate: Date
    let endDate: Date
    let value: Double
    let unit: String
    let metadata: [String: String]
}

enum SampleMapper {
    static func record(from sample: HKSample) -> HealthRecord? {
        let value: Double
        let unit: String
        var meta = sanitizedMetadata(sample.metadata)

        switch sample {
        case let q as HKQuantitySample:
            guard let u = HealthTypes.units[q.quantityType] else { return nil }
            value = q.quantity.doubleValue(for: u)
            unit = u.unitString
        case let c as HKCategorySample:            // sleep: HKCategoryValueSleepAnalysis raw value
            value = Double(c.value)
            unit = "category"
        case let w as HKWorkout:                    // workouts: duration; type in metadata
            value = w.duration
            unit = "s"
            meta["activity_type"] = String(w.workoutActivityType.rawValue)
        default:
            return nil
        }

        return HealthRecord(
            hkUUID: sample.uuid,
            type: sample.sampleType.identifier,
            startDate: sample.startDate,
            endDate: sample.endDate,
            value: value,
            unit: unit,
            metadata: meta
        )
    }

    /// Decide which HealthKit metadata is allowed to leave the phone.
    ///
    /// `metadata` is `[String: Any]` — values may be String, NSNumber, Date or HKQuantity.
    /// Useful keys you might allow:  HKMetadataKeyWasUserEntered, HKMetadataKeyHeartRateMotionContext,
    /// HKMetadataKeyTimeZone, HKMetadataKeyIndoorWorkout, HKMetadataKeyAverageMETs.
    /// Keys you probably don't want: anything from third-party apps (arbitrary, unknown content),
    /// HKMetadataKeyDeviceSerialNumber, HKMetadataKeyExternalUUID, sync identifiers.
    ///
    /// Returning [:] (the current behaviour) uploads no metadata at all — the safest default.
    static func sanitizedMetadata(_ metadata: [String: Any]?) -> [String: String] {
        // TODO(you): implement your allowlist here (≈5–10 lines).
        return [:]
    }
}
