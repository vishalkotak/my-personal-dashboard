import AppKit
import SwiftUI

@main
struct DashboardApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        Window("Health Dashboard", id: "main") {
            ContentView()
                .environment(delegate.backend)
                .frame(minWidth: 900, minHeight: 600)
        }
        .defaultSize(width: 1320, height: 860)
        .commands {
            CommandGroup(after: .toolbar) {
                Button("Reload") { NotificationCenter.default.post(name: .reloadDashboard, object: nil) }
                    .keyboardShortcut("r")
            }
        }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let backend = Backend()

    func applicationDidFinishLaunching(_ notification: Notification) {
        Task { await backend.start() }
    }

    // Closing the window quits the app, which stops the backend.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        backend.stop()
    }
}

extension Notification.Name {
    static let reloadDashboard = Notification.Name("reloadDashboard")
}

struct ContentView: View {
    @Environment(Backend.self) private var backend

    var body: some View {
        switch backend.state {
        case .starting:
            ProgressView("Starting…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .running(let url):
            DashboardWebView(url: url)
        case .failed(let message):
            VStack(spacing: 16) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 36))
                    .foregroundStyle(.orange)
                Text(message)
                    .font(.callout.monospaced())
                    .textSelection(.enabled)
                    .frame(maxWidth: 640, alignment: .leading)
                Button("Try again") { Task { await backend.start() } }
                    .keyboardShortcut(.defaultAction)
            }
            .padding(32)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}
