import Darwin
import Foundation
import Observation

/// Starts the dashboard's Python API as a child process on a free local port, and stops it on quit.
/// The API also serves the built web page, so this one process is all the app needs.
@MainActor
@Observable
final class Backend {
    enum State: Equatable {
        case starting
        case running(URL)
        case failed(String)
    }

    private(set) var state: State = .starting
    @ObservationIgnored private var process: Process?

    private let dashboardDir: URL = {
        let path = Bundle.main.object(forInfoDictionaryKey: "DashboardDirectory") as? String ?? ""
        return URL(fileURLWithPath: path).standardizedFileURL
    }()
    private var logFile: URL { dashboardDir.appending(path: "logs/app.log") }

    func start() async {
        state = .starting
        let python = dashboardDir.appending(path: "backend/.venv/bin/python")
        let page = dashboardDir.appending(path: "frontend/dist/index.html")
        let fm = FileManager.default
        guard fm.isExecutableFile(atPath: python.path), fm.fileExists(atPath: page.path) else {
            state = .failed("The dashboard isn't set up yet.\nRun dashboard/desktop/build.sh once, then open the app again.")
            return
        }
        guard let port = Self.freePort() else {
            state = .failed("Couldn't find a free local port.")
            return
        }

        try? fm.createDirectory(at: logFile.deletingLastPathComponent(), withIntermediateDirectories: true)
        fm.createFile(atPath: logFile.path, contents: nil)
        let log = try? FileHandle(forWritingTo: logFile)

        let p = Process()
        p.executableURL = python
        p.arguments = ["-m", "app"]
        p.currentDirectoryURL = dashboardDir.appending(path: "backend")
        var env = ProcessInfo.processInfo.environment
        env["API_PORT"] = String(port)                       // real env wins over dashboard/.env
        env["HEALTHSYNC_PARENT_PID"] = String(getpid())     // backend exits if this app dies
        env["PYTHONUNBUFFERED"] = "1"
        p.environment = env
        p.standardOutput = log
        p.standardError = log
        p.terminationHandler = { proc in
            Task { @MainActor [weak self] in self?.backendExited(code: proc.terminationStatus) }
        }

        do {
            try p.run()
        } catch {
            state = .failed("Couldn't start the backend: \(error.localizedDescription)")
            return
        }
        process = p

        let base = URL(string: "http://127.0.0.1:\(port)/")!
        if await Self.waitUntilHealthy(base, while: { p.isRunning }) {
            state = .running(base)
        } else if p.isRunning {
            stop()
            state = .failed("The backend didn't answer within 30 seconds.\n\n\(lastLogLines())")
        }
        // If it exited, backendExited(code:) has already set the failure message.
    }

    func stop() {
        guard let p = process else { return }
        process = nil
        p.terminationHandler = nil
        if p.isRunning { p.terminate() }   // SIGTERM: uvicorn shuts down cleanly
    }

    private func backendExited(code: Int32) {
        guard process != nil else { return }   // we stopped it on purpose
        process = nil
        state = .failed("The backend stopped (exit code \(code)).\n\n\(lastLogLines())")
    }

    private func lastLogLines(_ n: Int = 12) -> String {
        guard let text = try? String(contentsOf: logFile, encoding: .utf8) else { return "" }
        return text.split(separator: "\n").suffix(n).joined(separator: "\n")
    }

    /// Asks the OS for an unused port by binding to port 0 on 127.0.0.1.
    private static func freePort() -> Int? {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }
        defer { close(fd) }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        addr.sin_port = 0
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        let ok = withUnsafeMutablePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(fd, $0, len) == 0 && getsockname(fd, $0, &len) == 0
            }
        }
        return ok ? Int(UInt16(bigEndian: addr.sin_port)) : nil
    }

    private static func waitUntilHealthy(_ base: URL, while alive: () -> Bool) async -> Bool {
        let url = base.appending(path: "api/health")
        for _ in 0..<120 {
            guard alive() else { return false }
            if let (_, resp) = try? await URLSession.shared.data(from: url),
               (resp as? HTTPURLResponse)?.statusCode == 200 { return true }
            try? await Task.sleep(for: .milliseconds(250))
        }
        return false
    }
}
