import SwiftUI

struct ContentView: View {
    @Environment(HealthSyncEngine.self) private var engine
    @AppStorage(DefaultsKey.healthConnected) private var connected = false
    @State private var connectError: String?

    var body: some View {
        NavigationStack {
            List {
                Section("Status") {
                    LabeledContent("Account", value: accountLabel)
                    LabeledContent("Apple Health", value: connected ? "Connected" : "Not connected")
                    LabeledContent("Last sync") {
                        if let date = engine.lastSyncedAt {
                            Text(date, format: .relative(presentation: .named))
                        } else {
                            Text("Never")
                        }
                    }
                    if engine.isSyncing {
                        HStack { ProgressView(); Text("Syncing…") }
                    }
                    if let error = engine.lastError ?? connectError {
                        Text(error).font(.footnote).foregroundStyle(.red)
                    }
                }

                Section {
                    if !connected {
                        Button("Connect Apple Health") { Task { await connect() } }
                    } else {
                        if engine.needsAuthorization {
                            Button("Allow new health data") { Task { await connect() } }
                        }
                        Button("Sync now") { Task { await engine.syncAll() } }
                            .disabled(engine.isSyncing || engine.accountAvailable != true)
                    }
                } footer: {
                    Text("Syncs \(HealthTypes.all.count) kinds of Apple Health data. You choose which ones in the permission sheet.")
                }

                if let id = engine.accountID {
                    Section {
                        Text(id)
                            .font(.footnote.monospaced())
                            .textSelection(.enabled)       // long-press to copy
                    } header: {
                        Text("Account ID")
                    } footer: {
                        Text("Your rows in Supabase have this user_id. Only this app's saved session can access them.")
                    }
                }
            }
            .navigationTitle("Health Sync")
            .task {
                await engine.refreshAccount()
                await engine.refreshAuthorizationStatus()
                #if DEBUG
                // Test hook: `-HSRequestAuthOnLaunch` makes HealthKit validate every requested type at launch.
                if ProcessInfo.processInfo.arguments.contains("-HSRequestAuthOnLaunch") { await connect() }
                #endif
                if connected { await engine.syncAll() }   // catch up whenever the app opens
            }
        }
    }

    private var accountLabel: String {
        switch engine.accountAvailable {
        case .none: "Connecting…"
        case .some(true): "Signed in"
        case .some(false): "Unavailable"
        }
    }

    private func connect() async {
        do {
            try await engine.requestAuthorization()
            connected = true
            connectError = nil
            engine.startObserving()
            await engine.syncAll()
        } catch {
            connectError = error.localizedDescription
        }
    }
}
