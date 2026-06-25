import SwiftUI
import WebKit
import UIKit

struct ContentView: View {
    @State private var currentURL = AppConfig.startURL

    var body: some View {
        NavigationView {
            WebView(url: currentURL)
                .ignoresSafeArea(edges: .bottom)
                .navigationTitle(AppConfig.appName)
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItemGroup(placement: .navigationBarTrailing) {
                        Button("Início") { currentURL = AppConfig.startURL }
                        Button("Live") {
                            currentURL = URL(string: AppConfig.fallbackURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/live") ?? AppConfig.startURL
                        }
                    }
                }
        }
        .navigationViewStyle(.stack)
        .onOpenURL { url in
            currentURL = routeDeepLink(url)
        }
    }

    private func routeDeepLink(_ url: URL) -> URL {
        guard url.scheme?.lowercased() == "brechorisee" else { return url }
        let host = (url.host ?? "").lowercased()
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let id = components?.queryItems?.first(where: { $0.name == "id" })?.value ?? ""
        let base = AppConfig.fallbackURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))

        if ["produto", "peca", "product"].contains(host), !id.isEmpty {
            return URL(string: base + "/products/" + id) ?? AppConfig.startURL
        }
        if ["live", "aovivo", "ao-vivo", "studio"].contains(host) {
            return URL(string: base + "/live") ?? AppConfig.startURL
        }
        if ["caixa", "cashier"].contains(host) {
            return URL(string: base + "/cashier") ?? AppConfig.startURL
        }
        return AppConfig.startURL
    }
}

struct WebView: UIViewRepresentable {
    let url: URL

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []
        config.websiteDataStore = .default()

        let preferences = WKWebpagePreferences()
        preferences.allowsContentJavaScript = true
        config.defaultWebpagePreferences = preferences
        config.preferences.javaScriptCanOpenWindowsAutomatically = true

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.keyboardDismissMode = .interactive
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        if webView.url?.absoluteString != url.absoluteString {
            webView.load(URLRequest(url: url))
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.allow)
                return
            }

            if let scheme = url.scheme?.lowercased(), !["http", "https", "about"].contains(scheme) {
                UIApplication.shared.open(url)
                decisionHandler(.cancel)
                return
            }


            decisionHandler(.allow)
        }


        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if navigationAction.targetFrame == nil, let url = navigationAction.request.url {
                webView.load(URLRequest(url: url))
            }
            return nil
        }

        @available(iOS 15.0, *)
        func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
            decisionHandler(.grant)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            showOfflinePage(webView)
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            showOfflinePage(webView)
        }

        private func showOfflinePage(_ webView: WKWebView) {
            let html = """
            <!doctype html>
            <html lang="pt-BR">
            <head>
              <meta name="viewport" content="width=device-width, initial-scale=1">
              <style>
                body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#fbf6ef;color:#2c1d1b;margin:0;display:grid;place-items:center;min-height:100vh;text-align:center;padding:24px}
                .card{background:#fff;border-radius:28px;padding:32px;box-shadow:0 20px 60px rgba(80,40,30,.12)}
                a{display:inline-block;margin-top:16px;padding:12px 18px;border-radius:999px;background:#a84d3a;color:#fff;text-decoration:none;font-weight:700}
              </style>
            </head>
            <body>
              <div class="card">
                <h1>BRECHORISEE</h1>
                <p>Sem conexão no momento.</p>
                <p>Verifique a internet e tente novamente.</p>
                <a href="\(AppConfig.startURL.absoluteString)">Tentar abrir novamente</a>
              </div>
            </body>
            </html>
            """
            webView.loadHTMLString(html, baseURL: nil)
        }
    }
}
