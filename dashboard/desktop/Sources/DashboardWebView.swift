import AppKit
import SwiftUI
import WebKit

/// Shows the dashboard page. Only pages from the local backend load inside the window;
/// any other link opens in the default browser.
struct DashboardWebView: NSViewRepresentable {
    let url: URL

    func makeCoordinator() -> Coordinator { Coordinator(base: url) }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()   // nothing cached to disk between launches
        let view = WKWebView(frame: .zero, configuration: config)
        view.navigationDelegate = context.coordinator
        view.uiDelegate = context.coordinator
        view.allowsBackForwardNavigationGestures = false
        view.setValue(false, forKey: "drawsBackground")   // no white flash before the page paints
        context.coordinator.webView = view
        view.load(URLRequest(url: url))
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        let base: URL
        weak var webView: WKWebView?
        private var observer: NSObjectProtocol?

        init(base: URL) {
            self.base = base
            super.init()
            observer = NotificationCenter.default.addObserver(forName: .reloadDashboard, object: nil, queue: .main) {
                [weak self] _ in self?.webView?.reload()
            }
        }

        deinit { if let observer { NotificationCenter.default.removeObserver(observer) } }

        private func isLocal(_ url: URL?) -> Bool {
            url?.host == base.host && url?.port == base.port
        }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if isLocal(action.request.url) || action.request.url?.scheme == "about" {
                decisionHandler(.allow)
            } else {
                if let url = action.request.url { NSWorkspace.shared.open(url) }
                decisionHandler(.cancel)
            }
        }

        // target="_blank" links: open in the browser instead of a new web view.
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = action.request.url { NSWorkspace.shared.open(url) }
            return nil
        }
    }
}
