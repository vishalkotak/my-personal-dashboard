import HealthKit

/// The exact set of data the app is allowed to read. Requesting only what you need is both
/// an App Review requirement and the cheapest security control there is.
enum HealthTypes {
    /// Canonical unit per quantity type, so the database never mixes lb/kg or °F/°C.
    static let units: [HKQuantityType: HKUnit] = [
        // Activity
        HKQuantityType(.stepCount): .count(),
        HKQuantityType(.distanceWalkingRunning): .meter(),
        HKQuantityType(.activeEnergyBurned): .kilocalorie(),
        // Heart
        HKQuantityType(.heartRate): .count().unitDivided(by: .minute()),
        HKQuantityType(.restingHeartRate): .count().unitDivided(by: .minute()),
        HKQuantityType(.heartRateVariabilitySDNN): .secondUnit(with: .milli),
        // Body & vitals
        HKQuantityType(.bodyMass): .gramUnit(with: .kilo),
        HKQuantityType(.bloodPressureSystolic): .millimeterOfMercury(),
        HKQuantityType(.bloodPressureDiastolic): .millimeterOfMercury(),
        HKQuantityType(.oxygenSaturation): .percent(),
        HKQuantityType(.bodyTemperature): .degreeCelsius(),
    ]

    static let all: [HKSampleType] =
        Array(units.keys) + [
            HKCategoryType(.sleepAnalysis),   // Sleep
            HKObjectType.workoutType(),       // Activity: workouts
        ]
}
