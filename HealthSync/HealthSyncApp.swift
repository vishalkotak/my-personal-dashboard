import SwiftUI
import UIKit

enum DefaultsKey {
    static let healthConnected = "healthConnected"
    static let accountID = "backendAccountID"
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // iOS relaunches the app silently for background delivery; observers must be re-registered here.
        if UserDefaults.standard.bool(forKey: DefaultsKey.healthConnected) {
            HealthSyncEngine.shared.startObserving()
        }
        return true
    }
}

@main
struct HealthSyncApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(HealthSyncEngine.shared)
        }
    }
}
